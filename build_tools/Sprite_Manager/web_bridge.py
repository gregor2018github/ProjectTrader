"""Sending a sheet to the Gemini web view in the browser, without copy and paste.

A small HTTP server on this machine only (127.0.0.1:PORT) holds the sheet
waiting to go out. The userscript gemini_bridge.user.js, installed in
Violentmonkey or Tampermonkey in Firefox's FIREFOX_PROFILE profile, asks it
for work from every open Gemini tab once a second. The tab that takes a sheet
opens a new chat, sets the thinking level to High, pastes the image and the
prompt and presses send, telling the server how far it got; the tool shows
that in its status line.

Then the tab waits for Gemini's answer, however long it takes, by looking
for an image with a "Download full size" button once a second. It says so
just before it clicks that button, and from then on downloaded() watches the
Downloads folder: the first new image there whose size has stopped changing
is the answer, handed to the deliver callback given with the sheet.

The userscript is served by the same server: with the tool running, open
INSTALL_URL in that profile and the userscript manager offers to install it,
and later updates it from there.

If no Gemini tab has asked for work lately, submit() opens one in Firefox
(found through FIREFOX_PATH, the registry or Program Files; the default
browser if it is not found), always in FIREFOX_PROFILE, where the userscript
lives - not in whichever profile Firefox would start by default. The profile
is looked up by its name in the new profile manager's database (Profile
Groups) or in profiles.ini. Nothing here is pygame; the server runs in a
daemon thread.
"""

import base64
import itertools
import json
import os
import re
import shutil
import sqlite3
import subprocess
import threading
import time
import uuid
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
DOWNLOAD_WAIT_S = 180    # after the tab clicked download, how long the file may take to land
SCAN_S = 0.5             # how often the Downloads folder is looked at meanwhile
IMAGE_SUFFIXES = {'.png', '.jpg', '.jpeg', '.webp'}
DOWNLOADS_ID = '374DE290-123F-4565-9164-39C4925E467B'   # Windows' known folder "Downloads"
ENV_FIREFOX = 'FIREFOX_PATH'
FIREFOX_PROFILE = 'ProjectTrader'   # the profile Violentmonkey and the userscript are installed in
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


def downloads_folder():
    """Where Firefox puts downloads unless told otherwise: the user's Downloads folder."""
    try:
        import ctypes  # noqa: PLC0415 - Windows only, the folder may have been moved
        folder_id = ctypes.create_string_buffer(uuid.UUID(DOWNLOADS_ID).bytes_le, 16)
        path = ctypes.c_wchar_p()
        if ctypes.windll.shell32.SHGetKnownFolderPath(folder_id, 0, None, ctypes.byref(path)) == 0:
            found = path.value
            ctypes.windll.ole32.CoTaskMemFree(path)
            return Path(found)
    except (ImportError, AttributeError, OSError):
        pass
    return Path.home() / 'Downloads'


def script_version():
    """The @version of the userscript served, or None."""
    try:
        found = re.search(r'@version\s+(\S+)', SCRIPT_FILE.read_text(encoding='utf-8'))
    except OSError:
        return None
    return found.group(1) if found else None


def image_files(folder):
    """{name: size} of the images in a folder."""
    try:
        return {f.name: f.stat().st_size for f in folder.iterdir()
                if f.suffix.lower() in IMAGE_SUFFIXES and f.is_file()}
    except OSError:
        return {}


def find_profile(name=FIREFOX_PROFILE):
    """The folder of the Firefox profile called name, or None."""
    root = Path(os.environ.get('APPDATA', '')) / 'Mozilla' / 'Firefox'
    # Profiles made with the new profile manager are only in its profile groups' database
    for db in sorted((root / 'Profile Groups').glob('*.sqlite')):
        try:
            with sqlite3.connect(f'{db.as_uri()}?mode=ro', uri=True) as con:
                rows = con.execute('SELECT path, name FROM Profiles').fetchall()
        except sqlite3.Error:
            continue
        for path, found in rows:
            if found == name and (root / path).is_dir():
                return root / path
    profile = None
    try:
        for line in (root / 'profiles.ini').read_text(encoding='utf-8').splitlines():
            key, _, value = line.partition('=')
            if line.startswith('['):
                profile = {}
            elif profile is not None:
                profile[key.strip()] = value.strip()
                if profile.get('Name') == name and 'Path' in profile:
                    path = Path(profile['Path'])
                    path = root / path if profile.get('IsRelative', '1') == '1' else path
                    if path.is_dir():
                        return path
    except OSError:
        pass
    return None


def open_in_firefox(url):
    """Open a page in a new tab of Firefox in FIREFOX_PROFILE.

    Returns an error to show, or None: the default browser is used if there is
    no Firefox, and Firefox's own default profile if FIREFOX_PROFILE is not found.
    """
    firefox = find_firefox()
    if not firefox:
        webbrowser.open(url)
        return 'Firefox not found, opened in the default browser'
    profile = find_profile()
    try:
        if profile:
            # A Firefox already running this profile gets the tab, as with clicking a link
            subprocess.Popen([firefox, '--profile', str(profile), '--new-tab', url])
            return None
        subprocess.Popen([firefox, '--new-tab', url])
    except OSError:
        webbrowser.open(url)
        return 'Firefox did not start, opened in the default browser'
    return f'no Firefox profile "{FIREFOX_PROFILE}" found, opened in Firefox with its default profile'


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
            try:
                version = json.loads(body or b'{}').get('version')
            except (ValueError, AttributeError):
                version = None
            job = self.bridge.take(version)
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
        self.last_id = None         # the id of the last sheet submitted, see in_flight()
        self._awaiting = {}         # job id: (label, deliver) of sheets whose image is not in yet
        self._downloads = []        # the images the tabs are downloading, oldest first, see downloaded()
        self._scanned = 0.0

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

    def submit(self, png, prompt, label, deliver=None):
        """Hand a sheet (PNG bytes) and its prompt to the next Gemini tab that asks.

        deliver(path) is called with Gemini's answer once the tab has downloaded
        it, see downloaded(). Returns the message to show. A sheet still waiting
        is replaced.
        """
        self.start()
        with self._lock:
            if self._job:
                self._awaiting.pop(self._job['id'], None)   # replaced before any tab took it
            self._job = {'id': next(self._ids), 'label': label, 'prompt': prompt,
                         'image': base64.b64encode(png).decode('ascii'), 'name': f'{label}.png'}
            self._awaiting[self._job['id']] = (label, deliver)
            self.last_id = self._job['id']
            self._job_since = time.monotonic()
            listening = time.monotonic() - self._last_poll < LISTENING_S
            self.sent_label = label
        if listening:
            return f'{label} handed to the Gemini tab'
        problem = open_in_firefox(GEMINI_URL)
        if problem:
            return f'{label} waiting - {problem}, which may not have the userscript'
        if not self._ever_polled:
            return (f'{label} waiting - opening Gemini in Firefox ({FIREFOX_PROFILE}). Nothing happens? '
                    f'Install the userscript: open {INSTALL_URL} there')
        return f'{label} waiting - opening Gemini in Firefox ({FIREFOX_PROFILE})'

    def fetch(self, label, deliver=None):
        """Have the next Gemini tab that asks download the image of the answer it shows, sending nothing.

        For an answer whose download did not come through; deliver as for submit().
        """
        self.start()
        with self._lock:
            self._job = {'id': next(self._ids), 'label': label, 'fetch': True}
            self._job_since = time.monotonic()
            self._awaiting[self._job['id']] = (label, deliver)
            self.sent_label = label

    def poll(self):
        """(text, error) to show, or None: the browser's reports, or a sheet nobody took."""
        with self._lock:
            if self._job and time.monotonic() - self._job_since > TAKE_TIMEOUT_S:
                self._awaiting.pop(self._job['id'], None)   # nothing will ever deliver it
                self._job = None
                if self._ever_polled:
                    return f'No Gemini tab took {self.sent_label} - is Gemini open in Firefox ({FIREFOX_PROFILE})?', True
                return (f'The userscript never answered - install Violentmonkey in Firefox ({FIREFOX_PROFILE}), '
                        f'then open {INSTALL_URL} there and reload Gemini', True)
            return self._reports.pop(0) if self._reports else None

    def downloaded(self):
        """(label, path, deliver) of an answer the browser has finished downloading, or None.

        A tab downloading an image is given the first new image file in the
        Downloads folder, once its size has stayed the same between two looks
        (Firefox writes it as a .part file and renames it when done).
        """
        now = time.monotonic()
        with self._lock:
            if not self._downloads or now - self._scanned < SCAN_S:
                return None
            self._scanned = now
            watch = self._downloads[0]
            if now - watch['since'] > DOWNLOAD_WAIT_S:
                self._downloads.pop(0)
                self._reports.append((f'No image of {watch["label"]} turned up in {watch["folder"]} - '
                                      f'download it by hand and use Open image', True))
                return None
        files = image_files(watch['folder'])
        for name, size in files.items():
            if name in watch['known'] or not size:
                continue
            if watch['sizes'].get(name) == size:
                with self._lock:
                    self._downloads.remove(watch)
                return watch['label'], watch['folder'] / name, watch['deliver']
            watch['sizes'][name] = size
        return None

    def in_flight(self, job_id):
        """Whether a sheet is still on its way: waiting for a tab, being drawn or downloading.

        False once its answer was handed to deliver, or it failed on the way.
        """
        with self._lock:
            return ((self._job or {}).get('id') == job_id or job_id in self._awaiting
                    or any(w['id'] == job_id for w in self._downloads))

    # --- the browser's side -----------------------------------------------

    def take(self, version=None):
        """The sheet waiting, for a tab running the userscript of that version (None: older than 1.7)."""
        with self._lock:
            self._last_poll = time.monotonic()
            self._ever_polled = True
            job, self._job = self._job, None
            current = script_version()
            if job and version != current:
                # Violentmonkey looks for updates only now and then
                self._reports.append((f'The Gemini tab runs userscript {version or "1.6 or older"}, this tool has '
                                      f'{current}: open {INSTALL_URL} in Firefox and install it', True))
            return job

    def report(self, report):
        text = str(report.get('message', ''))[:300]
        with self._lock:
            if text:
                self._reports.append((f'Gemini tab: {text}', bool(report.get('error'))))
            if report.get('error') and not report.get('waiting'):
                self._awaiting.pop(report.get('id'), None)
            if report.get('download'):
                # Sent before the click, so the folder is looked at before the file is there
                label, deliver = self._awaiting.pop(report.get('id'), ('the answer', None))
                folder = downloads_folder()
                self._downloads.append({'id': report.get('id'), 'label': label, 'deliver': deliver, 'folder': folder,
                                        'known': set(image_files(folder)), 'sizes': {},
                                        'since': time.monotonic()})


BRIDGE = WebBridge()
