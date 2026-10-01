"""Requests to the image API, sent in a background thread."""

import queue
import threading
from datetime import datetime

from gemini_client import GeminiClient, GeminiError, next_free_path
from pose_review import Entry


class GeminiWorker:
    """Sends a list of sheets to Gemini in a background thread.

    The pygame loop stays responsive; the answers are collected by polling
    poll(), which drains the messages the thread has produced so far and
    hands the finished ones to the caller's callback.
    """

    def __init__(self, npc, jobs, settings, on_result):
        """Starts the requests.

        Args:
            npc: The figure the sheets belong to.
            jobs: [(pose, sheet_path, prompt)], one entry per request; the same
                pose may appear several times (Settings.tries).
            settings: Model and output size to ask for.
            on_result: Called on the main thread with one pose_review.Entry
                per answer that was written.
        """
        self.npc = npc
        self.settings = settings
        self.total = len(jobs)
        self.done = 0
        self.failures = []
        self.finished = False
        self.error = ''
        self._on_result = on_result
        self._queue = queue.Queue()
        self._thread = threading.Thread(target=self._run, args=(jobs,), daemon=True)
        self._thread.start()

    def _run(self, jobs):
        """Thread body: one request per job, answers written to disk."""
        try:
            client = GeminiClient()
        except Exception as exc:  # missing SDK, missing key, bad setup
            self._queue.put(('fatal', str(exc)))
            return
        for pose, sheet_path, prompt in jobs:
            try:
                image = client.complete_sheet(prompt, sheet_path.read_bytes(), self.settings)
                out_path = next_free_path(
                    sheet_path.parent, f'{self.npc.prefix}_{pose}_gemini', image.suffix)
                out_path.write_bytes(image.data)
                self._queue.put(('ok', Entry(
                    pose=pose,
                    image=out_path.name,
                    sheet=sheet_path.name,
                    model=self.settings.model,
                    aspect_ratio=self.settings.aspect_ratio,
                    image_size=self.settings.image_size,
                    created=datetime.now().isoformat(timespec='seconds'),
                    note=image.model_text[:200],
                    warning=image.warning,
                    prompt_tokens=image.prompt_tokens,
                    output_tokens=image.output_tokens,
                    total_tokens=image.total_tokens,
                )))
            except (GeminiError, OSError) as exc:
                self._queue.put(('error', f'{pose}: {exc}'))
        self._queue.put(('finished', None))

    def poll(self):
        """Drains the thread's messages and updates the counters."""
        while True:
            try:
                kind, payload = self._queue.get_nowait()
            except queue.Empty:
                return
            if kind == 'ok':
                self.done += 1
                self._on_result(payload)
            elif kind == 'error':
                self.done += 1
                self.failures.append(payload)
            elif kind == 'fatal':
                self.error = payload
                self.finished = True
            elif kind == 'finished':
                self.finished = True

    def status(self):
        """One line describing the current state, for the header."""
        if self.error:
            return f'Gemini: {self.error}'
        if not self.finished:
            return f'Gemini: {self.done}/{self.total} answered ...'
        ok = self.done - len(self.failures)
        if self.failures:
            return f'Gemini: {ok}/{self.total} ok, failed: ' + '; '.join(self.failures[:2])
        return f'Gemini: {self.total}/{self.total} answered, ready for review'
