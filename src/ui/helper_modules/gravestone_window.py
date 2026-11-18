"""A gravestone's inscription, opened with "Read" in its house menu.

The stone is drawn once when the window opens, in the shape of the gravestone
on the map: each sprite has a design (`DESIGNS`, by its file name; a stone not
listed is a rounded slab): a rounded slab or a domed one, a square slab with
chipped corners leaning a little, a headstone with shoulders, a Gothic one with
a pointed arch over the grave's mound, a grave cross with the name across its
arms and the rest down its shaft, a Celtic cross with its ring, a boss and
knotwork, and a chest tomb, its name on the lid's edge and the rest in the
middle of three sunk panels. The text is sized to fit (`_fit`, `_body`). The
stone's colour is the sprite's own (`sprite_stone_colour`), its brightness
evened out so the letters read. It is weathered (speckles, a bevel lit from the
upper left, lichen kept off the letters, moss where it meets the ground, all
placed by a generator seeded with the epitaph's key, so a stone looks the same
each time) and the inscription is carved in, each letter a dark cut with a
light edge under it. The texts are models/epitaphs.py. Any click or Escape puts
it away; walking off closes it like a house menu (map_view, by its `house`).
"""

import math
import os
import random
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Dict, List, Optional, Sequence, Tuple

import pygame

from .loan_dialog import _close_dialog
from ...config.constants import FONTS_PATH, SCREEN_HEIGHT, SCREEN_WIDTH, SIDEBAR_WIDTH
from ...models.epitaphs import Epitaph, epitaph, years_line

if TYPE_CHECKING:
    from ...game_state import GameState
    from ...models.house import House

Colour = Tuple[int, int, int]
Line = Tuple[pygame.font.Font, str]

#: The design of each gravestone sprite on the map
DESIGNS: Dict[str, str] = {
    'Deco_16.png': 'gothic',
    'Deco_17.png': 'slab',
    'Deco_18.png': 'cross',
    'Deco_19.png': 'dome',
    'Deco_20.png': 'tomb',
    'Deco_21.png': 'celtic',
    'Deco_22.png': 'shouldered',
    'Deco_23.png': 'rounded',
}
DEFAULT_DESIGN = 'rounded'

PAD = 10                       # around the stone, so its outline is never cut by the surface's edge
LINE_GAP = 6
BEVEL = 5                      # how wide the lit and shaded edges are
SLAB_LEAN = -2.5               # degrees the square slab leans, as it does on the map
HINT_SIZE = 18

DEFAULT_STONE: Colour = (128, 132, 136)
STONE_BRIGHTNESS = (118, 150)  # a sprite's colour is brought within this, so the carving reads
EARTH = (104, 80, 58)
LICHEN = ((168, 164, 112), (150, 152, 98), (186, 178, 128))
MOSS = ((96, 116, 62), (78, 98, 50), (112, 132, 70))
SHADOW = (0, 0, 0, 90)
HINT = (236, 226, 204)


def open_gravestone(game_state: 'GameState', house: 'House') -> bool:
    """Show what is carved on a gravestone; False if its `Epitaph` names no known inscription."""
    found = epitaph(house.epitaph)
    if found is None:
        game_state.show_warning("The inscription is worn away; nothing can be read.")
        return False
    game_state.info_window = GravestoneWindow(game_state.screen, game_state, house, found)
    game_state.active_house_menu = house
    return True


# ---------------------------------------------------------------------------
# Colours and letters
# ---------------------------------------------------------------------------

def _shade(colour: Sequence[int], factor: float) -> Colour:
    return tuple(max(0, min(255, round(v * factor))) for v in colour[:3])


def _lift(colour: Sequence[int], share: float = 0.22) -> Colour:
    return tuple(round(v + (255 - v) * share) for v in colour[:3])


@dataclass(frozen=True)
class Palette:
    stone: Colour
    dark: Colour
    light: Colour
    outline: Colour
    carved: Colour       # the cut of a letter
    edge: Colour         # the light catching the lower edge of a cut

    @classmethod
    def of(cls, stone: Colour) -> 'Palette':
        return cls(stone, _shade(stone, 0.8), _lift(stone), _shade(stone, 0.42), _shade(stone, 0.38),
                   _lift(stone, 0.4))


def sprite_stone_colour(image: Optional[pygame.Surface]) -> Optional[Colour]:
    """The colour of a gravestone sprite's stone: the median of its middle, moss, lichen and cuts left out,
    brought within STONE_BRIGHTNESS; None without a sprite or with too little stone in it."""
    if image is None:
        return None
    w, h = image.get_size()
    found = []
    for y in range(int(h * 0.15), int(h * 0.7)):
        for x in range(int(w * 0.2), int(w * 0.8)):
            r, g, b, a = image.get_at((x, y))
            if a < 200 or r + g + b < 150:
                continue
            if (g > r + 10 and g > b + 6) or (r > b + 30 and g > b + 25):   # moss, lichen
                continue
            found.append((r, g, b))
    if len(found) < 10:
        return None
    median = tuple(sorted(c[i] for c in found)[len(found) // 2] for i in range(3))
    brightness = 0.3 * median[0] + 0.59 * median[1] + 0.11 * median[2]
    low, high = STONE_BRIGHTNESS
    return _shade(median, min(high, max(low, brightness)) / max(1.0, brightness))


def _font(size: int) -> pygame.font.Font:
    try:
        return pygame.font.Font(os.path.join(FONTS_PATH, "RomanAntique.ttf"), size)
    except Exception:
        return pygame.font.SysFont("times new roman", size)


def _line_height(font: pygame.font.Font) -> int:
    """How tall a line is: RomanAntique reports far too small a line size, so measure a rendered one."""
    return max(font.get_linesize(), font.size("Mg")[1])


def _wrap(text: str, font: pygame.font.Font, width: int) -> List[str]:
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if line and font.size(trial)[0] > width:
            lines.append(line)
            line = word
        else:
            line = trial
    if line:
        lines.append(line)
    return lines


def _wrap_even(text: str, font: pygame.font.Font, width: int) -> List[str]:
    """Wrapped into as few lines as at `width`, but as even as they go, so no word is left alone on the last."""
    lines = _wrap(text, font, width)
    if len(lines) < 2:
        return lines
    best = lines
    for narrower in range(width - 8, width // 3, -8):
        trial = _wrap(text, font, narrower)
        if len(trial) != len(lines):
            break
        best = trial
    return best


def _fit(text: str, width: int, start: int, smallest: int, max_lines: int) -> List[Line]:
    """`text` as large as it goes, from `start` down to `smallest`, within `width` on at most `max_lines`."""
    for size in range(start, smallest - 1, -1):
        font = _font(size)
        lines = _wrap_even(text, font, width)
        if len(lines) <= max_lines and all(font.size(line)[0] <= width for line in lines):
            return [(font, line) for line in lines]
    font = _font(smallest)
    return [(font, line) for line in _wrap_even(text, font, width)]


def _body(inscription: Epitaph, width: int, start: int, wrapped: int) -> List[Line]:
    """The inscription's lines as large as they go, from `start` down to `wrapped`, each kept whole; where
    they do not fit whole even then, wrapped at `wrapped` (a narrow shaft), which keeps them readable."""
    for size in range(start, wrapped - 1, -1):
        font = _font(size)
        if all(font.size(line)[0] <= width for line in inscription.lines):
            return [(font, line) for line in inscription.lines]
    font = _font(wrapped)
    return [(font, part) for line in inscription.lines for part in _wrap_even(line, font, width)]


def _gap(height: int) -> Line:
    """An empty line about `height` tall."""
    return (_font(height), "")


def _height(lines: Sequence[Line]) -> int:
    return sum(_line_height(font) + LINE_GAP for font, _ in lines)


def _heading(inscription: Epitaph, width: int, name_size: int, years_size: int) -> List[Line]:
    """The name, as large as fits on two lines, and the years under it."""
    return _fit(inscription.name.upper(), width, name_size, max(18, name_size - 14), 2) + \
        [(_font(years_size), years_line(inscription))]


# ---------------------------------------------------------------------------
# A stone in the making
# ---------------------------------------------------------------------------

class Stone:
    """A stone's shape, its lighter parts, its carving and its inscription, put together by render().

    A design draws in the stone's own coordinates, (0, 0) its top left; the
    surface has PAD more round it. What is carved is kept (`text_rects`), so
    the lichen keeps off it and the tests can check it lies on the stone.
    """

    def __init__(self, width: int, height: int, key: str, palette: Palette) -> None:
        self.size = (width + 2 * PAD, height + 2 * PAD)
        self.rng = random.Random(key)
        self.palette = palette
        self.shape = pygame.Surface(self.size, pygame.SRCALPHA)
        self.bands: List[Tuple[pygame.Rect, Colour]] = []
        self.marks: List[Callable[[pygame.Surface, Colour, Tuple[int, int]], None]] = []
        self.texts: List[Tuple[pygame.font.Font, str, pygame.Rect]] = []
        self.overlays: List[Callable[[pygame.Surface], None]] = []
        self.moss = True
        self.mask: Optional[pygame.mask.Mask] = None

    @staticmethod
    def _at(x: float, y: float) -> Tuple[int, int]:
        return round(x) + PAD, round(y) + PAD

    def _rect(self, rect) -> pygame.Rect:
        return pygame.Rect(rect).move(PAD, PAD)

    # The shape
    def rect(self, rect, **radii) -> None:
        pygame.draw.rect(self.shape, (255, 255, 255, 255), self._rect(rect), **radii)

    def ellipse(self, rect) -> None:
        pygame.draw.ellipse(self.shape, (255, 255, 255, 255), self._rect(rect))

    def circle(self, centre, radius: int, width: int = 0) -> None:
        pygame.draw.circle(self.shape, (255, 255, 255, 255), self._at(*centre), radius, width)

    def polygon(self, points) -> None:
        pygame.draw.polygon(self.shape, (255, 255, 255, 255), [self._at(*p) for p in points])

    def band(self, rect, colour: Colour) -> None:
        """A part of the stone in a colour of its own (a lid, a plinth), outlined; also part of the shape."""
        self.rect(rect)
        self.bands.append((self._rect(rect), colour))

    # The carving
    def cut_lines(self, points, width: int = 3, closed: bool = False) -> None:
        pts = [self._at(*p) for p in points]
        self.marks.append(lambda s, c, o: pygame.draw.lines(s, c, closed, [(x + o[0], y + o[1]) for x, y in pts],
                                                            width))

    def cut_rect(self, rect, width: int = 0) -> None:
        r = self._rect(rect)
        self.marks.append(lambda s, c, o: pygame.draw.rect(s, c, r.move(o), width))

    def cut_circle(self, centre, radius: int, width: int = 0) -> None:
        x, y = self._at(*centre)
        self.marks.append(lambda s, c, o: pygame.draw.circle(s, c, (x + o[0], y + o[1]), radius, width))

    def cut_cross(self, cx: float, top: float, height: int = 40) -> None:
        """A small Latin cross, `height` tall, centred on cx."""
        bar = round(height * 0.22)
        self.cut_rect((cx - bar // 2, top, bar, height))
        self.cut_rect((cx - height * 0.38, top + height * 0.22, height * 0.76, bar))

    def text(self, font: pygame.font.Font, text: str, cx: float, top: float) -> int:
        """Carve a line centred on cx; returns the y under it."""
        w, h = font.size(text)
        rect = pygame.Rect(0, 0, w, h)
        rect.midtop = self._at(cx, top)
        self.texts.append((font, text, rect))
        return round(top) + h

    def lines(self, lines: Sequence[Line], cx: float, top: float) -> float:
        """Carve lines one under another; returns the y under the last."""
        for font, text in lines:
            if text:
                self.text(font, text, cx, top)
            top += _line_height(font) + LINE_GAP
        return top

    # Putting it together
    def render(self) -> pygame.Surface:
        pal, rng = self.palette, self.rng
        mask = self.mask = pygame.mask.from_surface(self.shape)
        face = pygame.Surface(self.size, pygame.SRCALPHA)
        face.fill(pal.stone)
        for rect, colour in self.bands:
            face.fill(colour, rect)
        bounds = mask.get_bounding_rects()
        area = mask.count()
        # Weathering
        for _ in range(area // 380):
            colour = rng.choice((pal.dark, pal.light))
            pygame.draw.circle(face, colour, (rng.randrange(self.size[0]), rng.randrange(self.size[1])),
                               rng.choice((1, 1, 2, 2, 3)))
        # Lit from the upper left: a light band along the top and left edges, a dark one along the others
        lit, shaded = mask.copy(), mask.copy()
        lit.erase(mask, (BEVEL, BEVEL))
        shaded.erase(mask, (-BEVEL, -BEVEL))
        face.blit(lit.to_surface(setcolor=pal.light + (255,), unsetcolor=(0, 0, 0, 0)), (0, 0))
        face.blit(shaded.to_surface(setcolor=pal.dark + (255,), unsetcolor=(0, 0, 0, 0)), (0, 0))
        for rect, _ in self.bands:
            pygame.draw.rect(face, pal.outline, rect, 3)
        # Lichen, clear of the letters
        clear = [rect.inflate(28, 20) for _, _, rect in self.texts]
        for _ in range(max(4, area // 40000)):
            for _ in range(60):
                x, y = rng.randrange(self.size[0]), rng.randrange(self.size[1])
                if mask.get_at((x, y)) and not any(r.collidepoint(x, y) for r in clear):
                    break
            else:
                continue
            for _ in range(rng.randrange(6, 14)):
                spot = (x + rng.randrange(-16, 17), y + rng.randrange(-10, 11))
                if not any(r.collidepoint(spot) for r in clear):
                    pygame.draw.circle(face, rng.choice(LICHEN), spot, rng.randrange(3, 7))
        # Moss where the stone meets the ground
        if self.moss and bounds:
            ground = max(r.bottom for r in bounds) - 1
            for x in range(0, self.size[0], 5):
                if mask.get_at((x, ground)):
                    top = ground - rng.randrange(6, 30)
                    pygame.draw.rect(face, rng.choice(MOSS), (x, top, 6, ground - top + 1))
        # Nothing off the stone, and its outline all round, inside edges too (the Celtic ring's)
        face.blit(mask.to_surface(setcolor=(255, 255, 255, 255), unsetcolor=(0, 0, 0, 0)), (0, 0),
                  special_flags=pygame.BLEND_RGBA_MIN)
        outside = mask.copy()
        outside.invert()
        rim = pygame.mask.Mask(self.size)
        for offset in ((3, 0), (-3, 0), (0, 3), (0, -3), (2, 2), (-2, -2), (2, -2), (-2, 2)):
            rim.draw(mask.overlap_mask(outside, offset), (0, 0))
        face.blit(rim.to_surface(setcolor=pal.outline + (255,), unsetcolor=(0, 0, 0, 0)), (0, 0))
        # The carving: the light edge first, the cut over it
        for mark in self.marks:
            mark(face, pal.edge, (1, 2))
            mark(face, pal.carved, (0, 0))
        for font, text, rect in self.texts:
            face.blit(font.render(text, True, pal.edge), rect.move(1, 2))
            face.blit(font.render(text, True, pal.carved), rect)
        for overlay in self.overlays:
            overlay(face)
        return face

    @property
    def text_rects(self) -> List[pygame.Rect]:
        return [rect for _, _, rect in self.texts]


# ---------------------------------------------------------------------------
# The designs
# ---------------------------------------------------------------------------

def _rounded(ins: Epitaph, pal: Palette, dome: bool = False) -> Stone:
    """A slab with a rounded top; `dome`, narrower under a half-round one (the small old stone)."""
    w = 460 if dome else 560
    arch = w // 2 if dome else int(w * 0.22)
    margin = 56 if dome else 64
    cross_top = int(arch * 0.3) if dome else 46
    lines = _heading(ins, w - 2 * margin, 38, 24) + [_gap(14)] + _body(ins, w - 2 * margin, 25, 20)
    text_top = max(cross_top + 58, int(arch * 0.62) if dome else 0)
    h = max(text_top + _height(lines) + 70, arch + 220)
    s = Stone(w, h, ins.key, pal)
    s.ellipse((0, 0, w, 2 * arch))
    s.rect((0, arch, w, h - arch))
    s.cut_cross(w / 2, cross_top, 40)
    s.lines(lines, w / 2, text_top)
    return s


def _slab(ins: Epitaph, pal: Palette) -> Stone:
    """A plain square slab with chipped corners, the inscription in an incised frame (it leans: SLAB_LEAN)."""
    w, frame = 520, 28
    width = w - 2 * (frame + 26)
    lines = _heading(ins, width, 36, 23) + [_gap(14)] + _body(ins, width, 24, 19)
    h = 66 + _height(lines) + 92
    s = Stone(w, h, ins.key, pal)
    s.polygon([(16, 2), (w * 0.4, 0), (w * 0.62, 5), (w - 34, 2), (w, 34), (w - 2, h), (0, h), (2, 24)])
    s.cut_rect((frame, 34, w - 2 * frame, h - 34 - 58), 2)
    s.lines(lines, w / 2, 58)
    return s


def _shouldered(ins: Epitaph, pal: Palette) -> Stone:
    """A raised round middle between two rounded shoulders, a carved ring in it."""
    w = 560
    radius = int(w * 0.24)
    shoulder = int(radius * 0.8)
    lines = _heading(ins, w - 2 * 64, 38, 24) + [_gap(14)] + _body(ins, w - 2 * 64, 25, 20)
    text_top = shoulder + 52
    h = text_top + _height(lines) + 70
    s = Stone(w, h, ins.key, pal)
    s.ellipse((w / 2 - radius, 0, 2 * radius, 2 * radius))
    s.rect((0, shoulder, w, h - shoulder), border_top_left_radius=46, border_top_right_radius=46)
    s.cut_circle((w / 2, radius * 0.6), int(radius * 0.32), 3)
    s.cut_cross(w / 2, radius * 0.6 - 15, 30)
    s.lines(lines, w / 2, text_top)
    return s


def _arch_points(x0: float, width: float, spring: float, centre_share: float = 0.72, steps: int = 18):
    """A pointed arch from (x0, spring) over to (x0 + width, spring): two arcs meeting at its apex."""
    r = centre_share * width
    rise = math.sqrt(max(0.0, width * r - width * width / 4))
    cx = x0 + r
    end = math.atan2(-rise, x0 + width / 2 - cx)            # the apex, seen from the left arc's centre
    if end < math.pi:
        end += 2 * math.pi                                   # up over the top, not round the bottom
    left = [(cx + r * math.cos(math.pi + (end - math.pi) * t / steps),
             spring + r * math.sin(math.pi + (end - math.pi) * t / steps)) for t in range(steps + 1)]
    right = [(2 * x0 + width - x, y) for x, y in reversed(left)]
    return left + right[1:], rise


def _gothic(ins: Epitaph, pal: Palette) -> Stone:
    """A headstone with a pointed Gothic arch, a carved arch panel with a cross, over the grave's mound."""
    total, stone_w, x0 = 560, 500, 30
    _, rise = _arch_points(x0, stone_w, 0)
    spring = int(rise)
    width = stone_w - 2 * 58
    lines = _heading(ins, width, 36, 23) + [_gap(12)] + _body(ins, width, 24, 19)
    text_top = spring + 64
    foot = text_top + _height(lines) + 84          # the stone's foot, hidden in the mound
    s = Stone(total, foot + 50, ins.key, pal)
    outer, _ = _arch_points(x0, stone_w, spring)
    s.polygon(outer + [(x0 + stone_w, foot), (x0, foot)])
    inner, inner_rise = _arch_points(x0 + 42, stone_w - 84, spring + 16)
    s.cut_lines(inner + [(x0 + stone_w - 42, spring + 40), (x0 + 42, spring + 40)], 3, closed=True)
    apex = spring + 16 - inner_rise
    s.cut_cross(total / 2, apex + (spring + 40 - apex) * 0.3, 52)
    s.lines(lines, total / 2, text_top)
    s.moss = False

    mound = pygame.Rect(0, 0, total, 100)
    mound.midtop = (total / 2 + PAD, foot - 50 + PAD)

    def draw_mound(face: pygame.Surface, rng=random.Random(ins.key + 'mound')) -> None:
        pygame.draw.ellipse(face, EARTH, mound)
        for _ in range(140):
            x, y = rng.randrange(mound.left + 10, mound.right - 10), rng.randrange(mound.top + 6, mound.bottom - 6)
            if ((x - mound.centerx) / (mound.w / 2)) ** 2 + ((y - mound.centery) / (mound.h / 2)) ** 2 < 0.8:
                pygame.draw.circle(face, _shade(EARTH, rng.choice((0.8, 1.15))), (x, y), rng.choice((1, 2, 3)))
        pygame.draw.ellipse(face, _shade(EARTH, 0.5), mound, 3)
        for x in range(mound.left + 14, mound.right - 14, 7):            # grass along its crown
            dx = (x - mound.centerx) / (mound.w / 2)
            y = mound.centery - mound.h / 2 * math.sqrt(max(0.0, 1 - dx * dx))
            pygame.draw.line(face, rng.choice(MOSS), (x, y + 4), (x + rng.randrange(-3, 4), y - rng.randrange(4, 14)), 3)

    s.overlays.append(draw_mound)
    return s


def _cross(ins: Epitaph, pal: Palette, celtic: bool = False) -> Stone:
    """A grave cross: the name and years across the arms, the inscription down the shaft, on a base.
    `celtic`: a ring round the crossing, a boss above it, knotwork down the shaft and a stepped plinth."""
    shaft, span = (380, 720) if celtic else (340, 660)
    heading = _heading(ins, span - 2 * 44, 36, 22)
    arms = _height(heading) + 40
    margin = 40 if celtic else 26
    body = _body(ins, shaft - 2 * margin, 23, 18)
    ring_r = int(math.hypot(shaft / 2, arms / 2)) + 62 if celtic else 0
    ring_w = 38
    stub = max(110, ring_r - arms // 2 + 54) if celtic else 104
    body_top = stub + arms + 30
    base = 84 if celtic else 56
    h = body_top + _height(body) + 34 + base
    cx = span / 2
    s = Stone(span, h, ins.key, pal)
    s.rect((cx - shaft / 2, 0, shaft, h - base))
    s.rect((0, stub, span, arms))
    if celtic:
        s.circle((cx, stub + arms / 2), ring_r, ring_w)
        s.band((cx - shaft / 2 - 50, h - base, shaft + 100, 44), pal.light)
        s.band((cx - shaft / 2 - 82, h - 40, shaft + 164, 40), pal.light)
        boss = (cx, max(38, (stub + arms / 2 - ring_r) / 2 + 20))
        s.cut_circle(boss, 24, 3)
        s.cut_circle(boss, 9)
        for side in (-1, 1):                                  # knotwork down both edges of the shaft
            x = cx + side * (shaft / 2 - 18)
            points = [(x + (6 if i % 2 else -6), y) for i, y in enumerate(range(stub + arms + 18, h - base - 16, 14))]
            if len(points) > 1:
                s.cut_lines(points, 3)
    else:
        s.band((cx - shaft / 2 - 60, h - base, shaft + 120, base), pal.light)
        s.text(_font(30), "IHS", cx, stub / 2 - 18)
    s.lines(heading, cx, stub + 20)
    s.lines(body, cx, body_top)
    return s


def _tomb(ins: Epitaph, pal: Palette) -> Stone:
    """A chest tomb: the name on the lid's edge, the years and inscription in the middle of three sunk
    panels on its side, a cross carved in each of the others, on a low footing."""
    w, inset, side_panel, gap = 840, 30, 130, 18
    name = _fit(ins.name.upper(), w - 2 * 60, 38, 24, 2)
    lid = _height(name) + 26
    middle_w = w - 2 * inset - 2 * 22 - 2 * side_panel - 2 * gap
    inner = [(_font(23), years_line(ins)), _gap(10)] + _body(ins, middle_w - 2 * 22, 22, 18)
    panel_h = _height(inner) + 36
    footing = 34
    h = lid + 26 + panel_h + 26 + footing
    s = Stone(w, h, ins.key, pal)
    s.rect((inset, lid, w - 2 * inset, h - lid - footing))
    s.band((0, 0, w, lid), pal.light)
    s.band((14, h - footing, w - 28, footing), pal.light)
    left = inset + 22
    panels = [(left, side_panel), (left + side_panel + gap, middle_w), (left + side_panel + gap + middle_w + gap, side_panel)]
    for i, (x, pw) in enumerate(panels):
        s.cut_rect((x, lid + 26, pw, panel_h), 3)
        if i != 1:
            s.cut_cross(x + pw / 2, lid + 26 + panel_h / 2 - 28, 56)
    s.lines(name, w / 2, 14)
    s.lines(inner, w / 2, lid + 26 + 18)
    return s


BUILDERS: Dict[str, Callable[[Epitaph, Palette], Stone]] = {
    'rounded': _rounded,
    'dome': lambda ins, pal: _rounded(ins, pal, dome=True),
    'slab': _slab,
    'shouldered': _shouldered,
    'gothic': _gothic,
    'cross': _cross,
    'celtic': lambda ins, pal: _cross(ins, pal, celtic=True),
    'tomb': _tomb,
}


def design_of(house: Optional['House']) -> str:
    return DESIGNS.get(getattr(house, 'file_name', '') or '', DEFAULT_DESIGN)


# ---------------------------------------------------------------------------
# The window
# ---------------------------------------------------------------------------

class GravestoneWindow:
    """The stone with its inscription, in the middle of the screen."""

    def __init__(self, screen: pygame.Surface, game_state: 'GameState', house: Optional['House'],
                 inscription: Epitaph, design: Optional[str] = None) -> None:
        self.screen = screen
        self.game_state = game_state
        self.house = house                 # closes it when the player walks off (map_view)
        self.epitaph = inscription
        self.design = design or design_of(house)
        colour = sprite_stone_colour(getattr(house, 'image', None)) or DEFAULT_STONE
        self.built = BUILDERS.get(self.design, BUILDERS[DEFAULT_DESIGN])(inscription, Palette.of(colour))
        self.stone = self.built.render()
        if self.design == 'slab':
            self.stone = pygame.transform.rotozoom(self.stone, SLAB_LEAN, 1)
        self.hint = self._make_hint("Click to step back from the grave.")
        total_w = SCREEN_WIDTH + SIDEBAR_WIDTH
        height = self.stone.get_height() + 12 + self.hint.get_height()
        self.panel = self.stone.get_rect(centerx=total_w // 2, top=max(10, (SCREEN_HEIGHT - height) // 2))

    @staticmethod
    def _make_hint(text: str) -> pygame.Surface:
        """Light words with a dark rim, readable over whatever of the map is behind them."""
        font = _font(HINT_SIZE)
        light, dark = font.render(text, True, HINT), font.render(text, True, (20, 18, 16))
        hint = pygame.Surface((light.get_width() + 4, light.get_height() + 4), pygame.SRCALPHA)
        for dx, dy in ((0, 2), (4, 2), (2, 0), (2, 4), (4, 4)):
            hint.blit(dark, (dx, dy))
        hint.blit(light, (2, 2))
        return hint

    def carved_text(self) -> List[str]:
        return [text for _, text, _ in self.built.texts]

    # -- the event interface ------------------------------------------------------

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            _close_dialog(self.game_state)

    def handle_click(self, pos: Tuple[int, int]) -> bool:
        _close_dialog(self.game_state)
        return True

    def draw(self, alpha_scale: float = 1.0) -> None:
        if alpha_scale <= 0:
            return
        shadow = pygame.Surface(self.stone.get_size(), pygame.SRCALPHA)
        shadow.fill(SHADOW)
        shadow.blit(self.stone, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)   # the stone's shape, black
        stone, hint = self.stone, self.hint
        if alpha_scale < 1.0:
            alpha = round(255 * alpha_scale)
            stone, hint, shadow = stone.copy(), hint.copy(), shadow.copy()
            for surface in (stone, hint, shadow):
                surface.fill((255, 255, 255, alpha), special_flags=pygame.BLEND_RGBA_MULT)
        self.screen.blit(shadow, self.panel.move(10, 12))
        self.screen.blit(stone, self.panel)
        self.screen.blit(hint, hint.get_rect(centerx=self.panel.centerx, top=self.panel.bottom + 12))
