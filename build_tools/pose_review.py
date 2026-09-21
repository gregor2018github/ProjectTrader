"""Bookkeeping for the images Gemini returns, and the way into the game.

create_new_pose.py sends a sheet to the image model and writes the answer to
build_tools/output/<npc>/. Every answer is listed in a review.json next to
it, so an answer that is not good enough yet can be left alone and looked at
again in a later run instead of being lost.

    pending   - answered, waiting to be judged
    accepted  - turned into the real sprite in assets/.../npcs/<npc>/
    rejected  - kept on disk, marked as not good enough

Accepting runs the same conversion as create_new_NPC.py (find the cells, cut
the sprite out of its white background, scale it like the player reference),
so a confirmed answer lands in the game as a finished transparent PNG.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

REVIEW_FILE = 'review.json'

PENDING = 'pending'
ACCEPTED = 'accepted'
REJECTED = 'rejected'


@dataclass
class Entry:
    """One image the model returned for one pose."""

    pose: str
    image: str            # file name inside the NPC's output folder
    sheet: str = ''       # the reference sheet it was made from
    model: str = ''
    aspect_ratio: str = ''
    image_size: str = ''
    created: str = ''
    status: str = PENDING
    note: str = ''        # what the model said, or why a request failed

    def details(self) -> str:
        """Model and size that produced it, for the card and the header."""
        parts = [self.model.replace('gemini-', '') or 'unknown model']
        parts += [part for part in (self.aspect_ratio, self.image_size) if part]
        return ', '.join(parts)


class ReviewStore:
    """The review.json of one NPC's output folder."""

    def __init__(self, folder: Path) -> None:
        """
        Args:
            folder: build_tools/output/<npc>; it may not exist yet.
        """
        self.folder = Path(folder)
        self.path = self.folder / REVIEW_FILE
        self.entries = self._read()

    def _read(self) -> list:
        """Entries whose image is still on disk, oldest first."""
        try:
            raw = json.loads(self.path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return []
        entries = []
        for item in raw if isinstance(raw, list) else []:
            known = {key: item[key] for key in Entry.__dataclass_fields__ if key in item}
            try:
                entry = Entry(**known)
            except TypeError:
                continue
            if (self.folder / entry.image).is_file():
                entries.append(entry)
        return entries

    def save(self) -> None:
        """Writes the list back; a failure only costs the bookkeeping."""
        try:
            self.folder.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps([asdict(e) for e in self.entries], indent=2) + '\n', encoding='utf-8')
        except OSError:
            pass

    def add(self, entry: Entry) -> Entry:
        """Records a fresh answer as pending and saves."""
        entry.created = entry.created or datetime.now().isoformat(timespec='seconds')
        self.entries.append(entry)
        self.save()
        return entry

    def set_status(self, entry: Entry, status: str) -> None:
        entry.status = status
        self.save()

    def remove(self, entry: Entry) -> None:
        """Forgets an entry and deletes its image."""
        if entry in self.entries:
            self.entries.remove(entry)
        try:
            (self.folder / entry.image).unlink(missing_ok=True)
        except OSError:
            pass
        self.save()

    def for_pose(self, pose: str) -> list:
        return [e for e in self.entries if e.pose == pose]

    def pending(self, pose: str = '') -> list:
        return [e for e in self.entries
                if e.status == PENDING and (not pose or e.pose == pose)]

    def pose_note(self, pose: str) -> str:
        """Short state of a pose for its card, '' when nothing was generated."""
        waiting = len(self.pending(pose))
        if waiting:
            return f'{waiting} to review'
        for entry in reversed(self.for_pose(pose)):
            if entry.status == REJECTED:
                return 'rejected'
        return ''

    def sorted_entries(self) -> list:
        """Pending first, then by pose and age - the order of the review screen."""
        order = {PENDING: 0, REJECTED: 1, ACCEPTED: 2}
        return sorted(self.entries, key=lambda e: (order.get(e.status, 3), e.pose, e.created))


# ---------------------------------------------------------------------------
# From a returned image to a real sprite (shared with create_new_NPC.py)
# ---------------------------------------------------------------------------

def _import_tool():
    """The import tool's module, imported late to avoid a circular import."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import create_new_NPC  # noqa: PLC0415 - create_new_NPC imports create_new_pose
    return create_new_NPC


def load_player_shapes(player_poses: dict) -> dict:
    """{pose: mask} of the player sprites, used to recognise the reference pose.

    Needs a pygame display, like every sprite load in these tools.
    """
    import pygame  # noqa: PLC0415 - only needed together with the tool's window

    tool = _import_tool()
    shapes = {}
    for pose, path in player_poses.items():
        sprite = pygame.image.load(str(path)).convert_alpha()
        mask = pygame.mask.from_surface(sprite)
        shapes[pose] = tool.shape_mask(mask, sprite.get_bounding_rect())
    return shapes


def build_sprite(image_path: Path, pose: str, player_poses: dict, player_shapes: dict):
    """Cuts the NPC out of a returned image and scales it like the player.

    Args:
        image_path: The image the model returned.
        pose: The pose that was asked for; it wins over the detected one.
        player_poses: {pose: player sprite path}.
        player_shapes: As returned by load_player_shapes().

    Returns:
        A create_new_NPC.Result, holding the finished sprite in .output.

    Raises:
        ValueError, pygame.error: If the cells or the sprite cannot be found.
    """
    result = _import_tool().Result(image_path, player_poses, player_shapes)
    if pose in player_poses and result.pose != pose:
        result.set_pose(pose)
    return result


def save_sprite(result, npc, pose: str) -> Path:
    """Writes the finished sprite into the NPC's folder in assets/.

    Args:
        result: The Result from build_sprite().
        npc: The create_new_pose.Npc it belongs to.
        pose: The pose the sprite shows.

    Returns:
        The path written.
    """
    import pygame  # noqa: PLC0415 - only needed together with the tool's window

    path = npc.sprite_path(pose)
    path.parent.mkdir(parents=True, exist_ok=True)
    pygame.image.save(result.output, str(path))
    return path
