"""Drawing pieces of the Sound Manager, beside the Sprite Manager's widgets: states, badges, play buttons, waveforms."""

import pygame

from audio import WAVE_BINS
from sound_library import MUSIC, RAW
from theme import BAR_BG, BUTTON_BG, BUTTON_HOVER, DONE_COLOR, ERROR_COLOR, TEXT, TEXT_DIM

USED_COLOR = (110, 190, 120)
MUSIC_COLOR = (120, 160, 220)
NEW_COLOR = (90, 140, 200)
RAW_COLOR = (120, 114, 104)
WAVE_COLOR = (200, 170, 110)
CURSOR_COLOR = (240, 236, 228)
QUIET_DB = -40.0         # loudness under which a sound is flagged: far below the others (around -20 to -35)


def state(family):
    """(colour, words) for how far the game uses a family."""
    if family.place == MUSIC:
        return MUSIC_COLOR, 'in the music rotation'
    if family.place == RAW:
        return RAW_COLOR, 'raw recording, not loaded by the game'
    if not family.used:
        return TEXT_DIM, 'not used yet'
    if family.unused_files:
        return DONE_COLOR, f'{len(family.unused_files)} of {len(family.files)} never played'
    return USED_COLOR, 'played by the game'


def quiet(family, decoded):
    """True if one of the family's decoded files is far quieter than the rest of the game."""
    return any(decoded.get(file.path) and decoded[file.path][1].loud_db < QUIET_DB for file in family.files)


def duration_text(seconds):
    if seconds >= 60:
        return f'{int(seconds // 60)}:{int(seconds % 60):02d}'
    return f'{seconds:.1f} s' if seconds < 10 else f'{seconds:.0f} s'


def size_text(size):
    return f'{size / 1024:.0f} KB' if size < 1024 * 1024 else f'{size / 1024 / 1024:.1f} MB'


def lengths_text(family, decoded):
    """The length of a family's files, or their range; '' while not decoded (or never: music, raw)."""
    lengths = [decoded[file.path][1].length for file in family.files if file.path in decoded]
    if not lengths:
        return ''
    low, high = min(lengths), max(lengths)
    if duration_text(low) == duration_text(high):
        return duration_text(low)
    return f'{duration_text(low)} - {duration_text(high)}'


def draw_badge(screen, font, text, x, cy, color):
    """A small outlined label starting at x, centred on cy; returns where the next one may start."""
    label = font.render(text, True, color)
    rect = pygame.Rect(x, 0, label.get_width() + 12, label.get_height() + 2)
    rect.centery = cy
    pygame.draw.rect(screen, color, rect, 1, border_radius=5)
    screen.blit(label, label.get_rect(center=rect.center))
    return rect.right + 6


def draw_play(screen, rect, playing, mouse):
    """A round play button, a stop square while playing."""
    color = BUTTON_HOVER if rect.collidepoint(mouse) else BUTTON_BG
    pygame.draw.circle(screen, color, rect.center, rect.w // 2)
    cx, cy = rect.center
    s = rect.w // 5
    if playing:
        pygame.draw.rect(screen, TEXT, (cx - s, cy - s, 2 * s, 2 * s))
    else:
        pygame.draw.polygon(screen, TEXT, [(cx - s + 2, cy - s - 2), (cx - s + 2, cy + s + 2), (cx + s + 3, cy)])


def draw_progress(screen, rect, share):
    pygame.draw.rect(screen, BAR_BG, rect, border_radius=2)
    if share:
        pygame.draw.rect(screen, USED_COLOR, (rect.x, rect.y, round(rect.w * share), rect.h), border_radius=2)


class Waveforms:
    """Waveform pictures of decoded files, made once per file and size."""

    def __init__(self):
        self._cache = {}

    def draw(self, screen, rect, path, analysis, position=None, warn=False):
        key = (path, rect.size)
        image = self._cache.get(key)
        if image is None:
            image = self._cache[key] = self._make(rect.size, analysis.peaks, warn)
        screen.blit(image, rect)
        if position is not None:
            x = rect.x + round(position * (rect.w - 1))
            pygame.draw.line(screen, CURSOR_COLOR, (x, rect.y), (x, rect.bottom - 1), 2)

    @staticmethod
    def _make(size, peaks, warn):
        w, h = size
        image = pygame.Surface(size)
        image.fill(BAR_BG)
        mid = h / 2
        color = ERROR_COLOR if warn else WAVE_COLOR
        pygame.draw.line(image, RAW_COLOR, (0, round(mid)), (w, round(mid)))
        for x in range(w):
            first = x * WAVE_BINS // w
            part = peaks[first:max(first + 1, (x + 1) * WAVE_BINS // w)]
            low = min(p[0] for p in part)
            high = max(p[1] for p in part)
            top, bottom = round(mid - high * mid), round(mid - low * mid)
            pygame.draw.line(image, color, (x, top), (x, max(top, bottom)))
        return image
