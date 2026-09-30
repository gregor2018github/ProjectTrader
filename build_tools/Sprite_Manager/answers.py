"""Getting the image model's answers onto disk and into review.json.

Answers come either from the API (create_new_pose.GeminiWorker writes the
file, record_answer() books it) or from the Gemini web view by copy and
paste, a dropped file or an opened one (store_web_answer()).
"""

import io
from datetime import datetime
from pathlib import Path

import pygame

import win_clipboard
from create_new_pose import measure
from gemini_client import next_free_path
from pose_review import Entry

WEB_MODEL = 'web'   # what an answer pasted from the web view is recorded as


class AnswerError(Exception):
    """An answer could not be taken; the message says why, for the status line."""


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
