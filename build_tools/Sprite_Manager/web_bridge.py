"""Sending a sheet to the Gemini web view in the browser, without copy and paste.

A small HTTP server on this machine only (127.0.0.1:PORT) holds the sheet
waiting to go out. The userscript gemini_bridge.user.js, installed in
Violentmonkey or Tampermonkey in Firefox, asks it for work from every open
Gemini tab once a second. The tab that takes a sheet opens a new chat,
chooses the Pro model with extended thinking off, pastes the image and the
prompt and presses send, telling the server how far it got; the tool shows
that in its status line.

The userscript is served by the same server: with the tool running, open
INSTALL_URL in Firefox and the userscript manager offers to install it, and
later updates it from there.

If no Gemini tab has asked for work lately, submit() opens one in Firefox
(found through FIREFOX_PATH, the registry or Program Files; the default
browser if it is not found), where the userscript lives. Nothing here is pygame; the server runs in a daemon thread.
"""

import base64
import itertools
import json
import os
import shutil
import subprocess
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOST = '127.0.0.1'
PORT = 47613
SCRIPT_FILE = Path(__file__).resolve().parent / 'gemini_bridge.user.js'
INSTALL_URL = f'http://{HOST}:{PORT}/{SCRIPT_FILE.name}'
GEMINI_URL = 'https://gemini.google.com/app'
LISTENING_S = 4          # a tab that asked within this long is there to take the sheet
TAKE_TIMEOUT_S = 25      # waited this long for a tab to take it: say so
MAX_BODY = 64 * 1024     # status reports are small
ENV_FIREFOX = 'FIREFOX_PATH'
FIREFOX_KEY = r'SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\firefox.exe'


def find_firefox():
    """firefox.exe, or None."""
    candidates = [os.environ.get(ENV_FIREFOX)]
    try:
        import winreg  # noqa: PLC0415 - Windows only
        for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            try:
                candidates.append(winreg.QueryValue(root, FIREFOX_KEY))
            except OSError:
                pass
    except ImportError:
        pass
    candidates += [shutil.which('firefox')] + [
        str(Path(os.environ.get(var, '')) / 'Mozilla Firefox' / 'firefox.exe')
        for var in ('ProgramFiles', 'ProgramFiles(x86)', 'LOCALAPPDATA')]
    return next((c for c in candidates if c and Path(c).is_file()), None)


def open_in_firefox(url):
    """Open a page in a new tab of Firefox (of the default browser if there is no Firefox)."""
    firefox = find_firefox()
    if firefox:
        try:
            subprocess.Popen([firefox, '--new-tab', url])
            return
        except OSError:
            pass
    webbrowser.open(url)


class BridgeError(RuntimeError):
    pass


class _Handler(BaseHTTPRequestHandler):
    bridge = None   # set on the subclass made per server

    def log_message(self, *args):   # the console stays quiet
        pass

    def _reply(self, code, body=b'', kind='application/json'):
        self.send_response(code)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.split('?')[0] == f'/{SCRIPT_FILE.name}':
            try:
                self._reply(200, SCRIPT_FILE.read_bytes(), 'text/javascript; charset=utf-8')
            except OSError:
                self._reply(404)
        else:
            self._reply(404)

    def do_POST(self):
        length = min(int(self.headers.get('Content-Length') or 0), MAX_BODY)
        body = self.rfile.read(length) if length else b''
        if self.path == '/take':
            job = self.bridge.take()
            self._reply(200, json.dumps(job).encode()) if job else self._reply(204)
        elif self.path == '/status':
            try:
                report = json.loads(body or b'{}')
            except ValueError:
                self._reply(400)
                return
            self.bridge.report(report)
            self._reply(204)
        else:
            self._reply(404)


class WebBridge:
    """The one sheet waiting for the browser, and what the browser said about the last one."""

    def __init__(self):
        self._lock = threading.Lock()
        self._server = None
        self._ids = itertools.count(1)
        self._job = None            # the sheet waiting, as the userscript gets it
        self._job_since = 0.0
        self._last_poll = 0.0       # when a Gemini tab last asked for work
        self._ever_polled = False   # whether the userscript has been heard from at all
        self._reports = []          # (text, error) not shown yet
        self.sent_label = ''        # what the last sheet was, for the messages

    def start(self):
        """Start the server if it is not running yet. Raises BridgeError if the port is taken."""
        if self._server:
            return
        handler = type('Handler', (_Handler,), {'bridge': self})
        try:
            self._server = ThreadingHTTPServer((HOST, PORT), handler)
        except OSError as exc:
            raise BridgeError(f'Cannot listen on port {PORT} (is the tool open twice?): {exc}') from exc
        self._server.daemon_threads = True
        threading.Thread(target=self._server.serve_forever, daemon=True, name='web-bridge').start()

    # --- the tool's side --------------------------------------------------

    def submit(self, png, prompt, label):
        """Hand a sheet (PNG bytes) and its prompt to the next Gemini tab that asks.

        Returns the message to show. A sheet still waiting is replaced.
        """
        self.start()
        with self._lock:
            self._job = {'id': next(self._ids), 'label': label, 'prompt': prompt,
                         'image': base64.b64encode(png).decode('ascii'), 'name': f'{label}.png'}
            self._job_since = time.monotonic()
            listening = time.monotonic() - self._last_poll < LISTENING_S
            self.sent_label = label
        if listening:
            return f'{label} handed to the Gemini tab'
        open_in_firefox(GEMINI_URL)
        if not self._ever_polled:
            return (f'{label} waiting - opening Gemini in Firefox. Nothing happens? '
                    f'Install the userscript: open {INSTALL_URL} there')
        return f'{label} waiting - opening Gemini in Firefox'

    def poll(self):
        """(text, error) to show, or None: the browser's reports, or a sheet nobody took."""
        with self._lock:
            if self._job and time.monotonic() - self._job_since > TAKE_TIMEOUT_S:
                self._job = None
                if self._ever_polled:
                    return f'No Gemini tab took {self.sent_label} - is Gemini open in Firefox?', True
                return (f'The userscript never answered - install Violentmonkey in Firefox, '
                        f'then open {INSTALL_URL} there and reload Gemini', True)
            return self._reports.pop(0) if self._reports else None

    # --- the browser's side -----------------------------------------------

    def take(self):
        with self._lock:
            self._last_poll = time.monotonic()
            self._ever_polled = True
            job, self._job = self._job, None
            return job

    def report(self, report):
        text = str(report.get('message', ''))[:300]
        if text:
            with self._lock:
                self._reports.append((f'Gemini tab: {text}', bool(report.get('error'))))


BRIDGE = WebBridge()
