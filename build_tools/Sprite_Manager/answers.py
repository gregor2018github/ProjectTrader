"""Getting the image model's answers onto disk and into review.json.

Answers come either from the API (gemini_worker.GeminiWorker writes the
file, record_answer() books it) or from the Gemini web view by copy and
paste, a dropped file or an opened one (store_web_answer()). A Detail is one
answer cut out and scaled, as it would be saved.
"""

import io
from datetime import datetime
from pathlib import Path

import pygame

import pose_review
import win_clipboard
from gemini_client import next_free_path
from pose_review import Entry
from theme import ROOT

WEB_MODEL = 'web'   # what an answer pasted from the web view is recorded as


class AnswerError(Exception):
    """An answer could not be taken; the message says why, for the status line."""


def measure(path, entry, store=None):
    """Note the answer's real resolution on its entry, once.

    The model does not always deliver the image size that was asked for, and
    older entries were written before this was recorded, so the file itself
    is the only source. Runs on the main thread, where pygame can load.

    Args:
        path: The image file.
        entry: The pose_review.Entry to fill in.
        store: Store to save, when the entry gained a size.
    """
    if entry.width and entry.height:
        return
    try:
        entry.width, entry.height = pygame.image.load(str(path)).get_size()
    except (pygame.error, OSError):
        return
    if store:
        store.save()


def ask_open_file():
    """Native file dialog for an answer image (tkinter ships with Python); None if cancelled."""
    try:
        import tkinter  # noqa: PLC0415 - only when the dialog is asked for
        from tkinter import filedialog  # noqa: PLC0415
    except ImportError:
        return None
    root = tkinter.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    downloads = Path.home() / 'Downloads'
    path = filedialog.askopenfilename(
        title='Gemini result', initialdir=str(downloads if downloads.exists() else ROOT),
        filetypes=[('Images', '*.png *.jpg *.jpeg *.webp *.bmp'), ('All files', '*.*')])
    root.destroy()
    return path or None


class Detail:
    """The image of one answer and the sprite accepting it would make."""

    def __init__(self, npc, entry, player_poses, player_shapes, layout='2x2'):
        """
        Raises:
            pygame.error, OSError: If the answer's image cannot be read.
        """
        self.npc = npc
        self.entry = entry
        self.path = npc.out_dir / entry.image
        self.image = pygame.image.load(str(self.path)).convert()
        entry.width, entry.height = self.image.get_size()
        self.result = None
        self.error = ''
        try:
            self.result = pose_review.build_sprite(
                self.path, entry.pose, player_poses, player_shapes, layout)
        except Exception as exc:  # cell detection and extraction fail in many ways
            self.error = f'Cannot use this image: {exc}'
        self.preview = None  # (rect, factor) of the sprite in the preview panel

    def toggle_hole(self, pos):
        """Click in the preview: switch an enclosed white area transparent."""
        if not (self.result and self.preview):
            return
        rect, factor = self.preview
        if not rect.collidepoint(pos):
            return
        point = self.result.output_to_cell(
            ((pos[0] - rect.x) / factor, (pos[1] - rect.y) / factor))
        target = self.result.target
        if target.surface.get_rect().collidepoint(point) and target.toggle_hole(point):
            self.result.build()


def clipboard_answer():
    """(source, kind) of the image on the clipboard, for store_web_answer().

    Raises:
        AnswerError: If there is no image on the clipboard or it cannot be read.
    """
    try:
        found = win_clipboard.paste_image()
    except win_clipboard.ClipboardError as exc:
        raise AnswerError(str(exc)) from exc
    if not found:
        raise AnswerError('No image on the clipboard - copy the answer in Gemini first')
    kind, data = found
    return (Path(data), '') if kind == 'file' else (data, kind)


def encoded_image(source, kind=''):
    """(bytes, suffix) of an answer, checked to be an image.

    Args:
        source: A file path, or the encoded image bytes.
        kind: 'png' or 'bmp' when source is bytes.
    """
    try:
        if isinstance(source, Path):
            pygame.image.load(str(source))  # refuse what is not an image
            return source.read_bytes(), source.suffix.lower() or '.png'
        image = pygame.image.load(io.BytesIO(source), f'answer.{kind}')
        buffer = io.BytesIO()
        pygame.image.save(image, buffer, 'answer.png')
        return buffer.getvalue(), '.png'
    except (pygame.error, OSError) as exc:
        raise AnswerError(f'Not an image I can read: {exc}') from exc


def store_web_answer(npc, store, sheet, source, kind=''):
    """Write an answer from the web view next to its sheet and book it.

    Args:
        npc: The WalkNpc.
        store: Its pose_review.ReviewStore.
        sheet: The FrameSheet the answer is for.
        source, kind: As for encoded_image().

    Returns:
        The new pose_review.Entry.

    Raises:
        AnswerError: If the source is not an image.
    """
    data, suffix = encoded_image(source, kind)
    npc.out_dir.mkdir(parents=True, exist_ok=True)
    path = next_free_path(npc.out_dir, f'{npc.prefix}_{sheet.pose}_{WEB_MODEL}', suffix)
    path.write_bytes(data)
    entry = Entry(pose=sheet.pose, image=path.name, sheet=sheet.path.name, model=WEB_MODEL,
                  created=datetime.now().isoformat(timespec='seconds'))
    measure(path, entry)
    store.add(entry)
    return entry


def record_answer(npc, store):
    """The callback GeminiWorker hands each answer from the API to."""
    def record(entry):
        measure(npc.out_dir / entry.image, entry)
        store.add(entry)
    return record
