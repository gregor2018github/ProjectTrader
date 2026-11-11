"""The slip of paper with Uncle Gared's address, over the map while the player looks
for his shop (``Intro.finding_shop``).

It sits folded at the top of the map, a small glowing packet. A click on it
unfolds it into a sheet: the packet comes down out of the item, its two side
flaps open out, and the two lower panels fold down one after the other. The
sheet shows the address in the uncle's hand and a little sketch of the way. The
next click anywhere folds it up again, the same way back, so the town can be
seen; the click does nothing else.

Owned by ``Game`` as ``address_note``. ``begin_frame()`` each frame, then
``draw()`` while it is shown (``map_view``), and ``handle_click()`` only takes a
click if it was drawn that frame.
"""

import math
import os
import random
from typing import Dict, List, Optional, Tuple

import pygame

from ...config.constants import FONTS_PATH, PICTURES_PATH
from ..paper import draw_paper

#: The folded packet at the top of the map: this picture, this high
ITEM_PICTURE = "piece_of_paper_full.png"
ITEM_HEIGHT = 64
ITEM_SIZE = (58, 46)          # the drawn packet's, should the picture be missing
ITEM_TOP = 16                 # its gap below the map's top edge
ITEM_BOB_PX = 2               # it floats up and down by this much
GLOW_PERIOD_S = 1.8           # one pulse of its glow
GLOW_REACH = 26               # how far the glow reaches out from the packet

#: The unfolded sheet: three panels high and three flaps wide
SHEET_SIZE = (540, 450)
UNFOLD_S = 0.75               # opening, in real seconds
FOLD_S = 0.5                  # folding it up again
#: Where each step of the unfolding ends, as a share of the whole: the packet
#: comes out of the item, the side flaps open, the middle panel and the last
#: panel fold down
PHASES = (0.15, 0.45, 0.72, 1.0)

#: The paper: darker and browner than the game's parchment, like the parcel's
PAPER = (204, 174, 128)
PAPER_STAIN = (128, 92, 56)   # its mottled blots
STAINS = 34
ROUGH_PX = 7                  # how deep the torn edge bites in
EDGE_INK = (58, 38, 22)       # the torn edge's outline
PAPER_SEED = 1500             # the same tears and stains every time

INK = (62, 40, 22)
INK_FADED = (120, 88, 56)
BACK_SHADE = 0.9              # the paper's back is a little darker than its front
FLAP_SHADE = 0.72             # how dark a flap still standing up is

FOLDED, UNFOLDING, OPEN, FOLDING = "folded", "unfolding", "open", "folding"


def _ease(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def phase_amounts(t: float) -> Tuple[float, float, float, float]:
    """How far each step of the unfolding has got (0 to 1) at the whole's ``t``."""
    out, start = [], 0.0
    for end in PHASES:
        out.append(_ease((t - start) / (end - start)))
        start = end
    return tuple(out)


class AddressNote:
    """The folded address and its sheet (see the module)."""

    def __init__(self, title: str, address: str) -> None:
        self.title = title
        self.address = address
        self.state: str = FOLDED
        self.t: float = 0.0                   # 0 folded, 1 open
        self.item_rect: Optional[pygame.Rect] = None
        self.sheet_rect: Optional[pygame.Rect] = None
        self._drawn: bool = False
        self._last_ticks: Optional[int] = None
        self._sheet: Optional[pygame.Surface] = None
        self._back: Optional[pygame.Surface] = None
        self._item: Optional[pygame.Surface] = None
        self._item_shadow: Optional[pygame.Surface] = None
        self._glow: Optional[pygame.Surface] = None
        self._fonts: Dict[str, pygame.font.Font] = {}

    # --- State ----------------------------------------------------------------

    @property
    def is_open(self) -> bool:
        """Whether the sheet is out, or on its way in or out."""
        return self.state != FOLDED

    def begin_frame(self) -> None:
        """Forget last frame's drawing; ``draw`` says again if it is still shown."""
        if not self._drawn:
            self._last_ticks = None
        self._drawn = False

    def unfold(self) -> None:
        if self.state in (FOLDED, FOLDING):
            self.state = UNFOLDING

    def fold(self) -> None:
        if self.state in (OPEN, UNFOLDING):
            self.state = FOLDING

    def reset(self) -> None:
        """Folded, as in a new game or a loaded one."""
        self.state, self.t = FOLDED, 0.0

    def update(self, dt: float) -> None:
        if self.state == UNFOLDING:
            self.t = min(1.0, self.t + dt / UNFOLD_S)
            if self.t >= 1.0:
                self.state = OPEN
        elif self.state == FOLDING:
            self.t = max(0.0, self.t - dt / FOLD_S)
            if self.t <= 0.0:
                self.state = FOLDED

    def handle_click(self, pos: Tuple[int, int]) -> bool:
        """A left click: the item unfolds the sheet, and while it is out any click
        folds it again. Whether the click was taken (only if drawn this frame)."""
        if not self._drawn:
            return False
        if self.is_open:
            if self.state != FOLDING:
                self.fold()
            return True
        if self.item_rect is not None and self.item_rect.inflate(12, 12).collidepoint(pos):
            self.unfold()
            return True
        return False

    # --- Layout ---------------------------------------------------------------

    def layout(self, area: pygame.Rect) -> None:
        """Place the item and the sheet at the top of ``area``, the map."""
        self.item_rect = pygame.Rect((0, 0), self._item.get_size() if self._item else ITEM_SIZE)
        self.item_rect.midtop = (area.centerx, area.top + ITEM_TOP)
        width = min(SHEET_SIZE[0], area.width - 24) // 3 * 3
        height = min(SHEET_SIZE[1], area.height - 2 * ITEM_TOP) // 3 * 3
        self.sheet_rect = pygame.Rect(0, 0, width, height)
        self.sheet_rect.midtop = (area.centerx, area.top + ITEM_TOP)

    # --- Drawing --------------------------------------------------------------

    def draw(self, screen: pygame.Surface, area: pygame.Rect) -> None:
        self._drawn = True
        now = pygame.time.get_ticks()
        dt = 0.0 if self._last_ticks is None else min(0.1, (now - self._last_ticks) / 1000.0)
        self._last_ticks = now
        self.update(dt)
        self.layout(area)
        if self._sheet is None or self._sheet.get_size() != self.sheet_rect.size:
            self._build(self.sheet_rect.size)
            self.layout(area)          # the item now the picture's size
        if self.t <= 0.0:
            self._draw_item(screen, now / 1000.0)
        elif self.t >= 1.0:
            screen.blit(self._sheet_shadow, self.sheet_rect.move(6, 8))
            screen.blit(self._sheet, self.sheet_rect)
        else:
            self._draw_unfolding(screen)

    def _draw_item(self, screen: pygame.Surface, seconds: float) -> None:
        pulse = 0.5 + 0.5 * math.sin(seconds * 2 * math.pi / GLOW_PERIOD_S)
        rect = self.item_rect.move(0, round(ITEM_BOB_PX * math.sin(seconds * 2 * math.pi / (GLOW_PERIOD_S * 2))))
        glow = self._glow
        glow.set_alpha(round(90 + 165 * pulse))
        screen.blit(glow, glow.get_rect(center=rect.center))
        screen.blit(self._item_shadow, rect.move(3, 4))
        screen.blit(self._item, rect)

    def _shadow(self, screen: pygame.Surface, pieces: List[Tuple[pygame.Surface, pygame.Rect]],
                drop: int = 6) -> None:
        """The shadow of each piece of paper, in its own torn shape."""
        for part, rect in pieces:
            if rect.width > 0 and rect.height > 0:
                screen.blit(_silhouette(part, (20, 10, 0), 80), rect.move(drop, drop + 2))

    def _draw_unfolding(self, screen: pygame.Surface) -> None:
        come, flaps, middle, last = phase_amounts(self.t)
        sx, sy = self.sheet_rect.topleft
        w, h = self.sheet_rect.size
        f, p = w // 3, h // 3
        packet = pygame.Rect(sx + f, sy, f, p)

        if flaps <= 0.0:
            # The folded packet coming down out of the item, growing to its size,
            # the item's picture turning into it on the way
            rect = _lerp_rect(self.item_rect, packet, come)
            unfolded = pygame.transform.smoothscale(self._packet, rect.size)
            self._shadow(screen, [(unfolded, rect)], 3 + round(3 * come))
            unfolded.set_alpha(round(255 * min(1.0, come * 1.5)))
            screen.blit(unfolded, rect)
            picture = pygame.transform.smoothscale(self._item, rect.size)
            picture.set_alpha(round(255 * (1.0 - come)))
            screen.blit(picture, rect)
            return

        # The panels below the first, folding down from under it one by one
        pieces: List[Tuple[pygame.Surface, pygame.Rect]] = []
        y = sy + p
        for amount, row in ((middle, 1), (last, 2)):
            if amount <= 0.0:
                break
            shown = max(1, round(p * math.sin(amount * math.pi / 2)))
            part = pygame.transform.smoothscale(self._sheet.subsurface((0, row * p, w, p)), (w, shown))
            _darken(part, FLAP_SHADE + (1 - FLAP_SHADE) * amount)
            pieces.append((part, pygame.Rect(sx, y, w, shown)))
            y += shown

        # The first panel, its side flaps opening out from over its middle
        angle = math.pi * (1.0 - flaps)        # pi lying folded over, 0 open
        span = max(0, round(f * abs(math.cos(angle))))
        first = [(self._sheet.subsurface((f, 0, f, p)), packet)]
        shade = FLAP_SHADE + (1 - FLAP_SHADE) * abs(math.cos(angle))
        for side in (0, 2):
            if span <= 0:
                continue
            if angle > math.pi / 2:
                # Still over the middle: its back is up
                part = pygame.transform.smoothscale(self._back.subsurface((side * f, 0, f, p)), (span, p))
                _darken(part, shade)
                x = packet.left if side == 0 else packet.right - span
            else:
                part = pygame.transform.smoothscale(self._sheet.subsurface((side * f, 0, f, p)), (span, p))
                _darken(part, shade)
                x = packet.left - span if side == 0 else packet.right
            first.append((part, pygame.Rect(x, sy, span, p)))

        self._shadow(screen, first + pieces)
        for part, rect in pieces:
            screen.blit(part, rect)
        for part, rect in first:
            screen.blit(part, rect)

    # --- The paper, made once per size ------------------------------------------

    def _font(self, name: str, size: int) -> pygame.font.Font:
        key = f"{name}{size}"
        if key not in self._fonts:
            try:
                self._fonts[key] = pygame.font.Font(os.path.join(FONTS_PATH, name), size)
            except (OSError, FileNotFoundError):
                self._fonts[key] = pygame.font.SysFont("georgia", size)
        return self._fonts[key]

    def _build(self, size: Tuple[int, int]) -> None:
        w, h = size
        f, p = w // 3, h // 3
        rng = random.Random(PAPER_SEED)
        outline = _torn_outline(size, rng)
        sheet = _rough_paper(size, (0, 0), outline, rng)
        # The creases it was folded along
        for x in (f, 2 * f):
            _crease(sheet, (x, 0), (x, p), vertical=True)
        for y in (p, 2 * p):
            _crease(sheet, (0, y), (w, y), vertical=False)
        _cut_to(sheet, outline)
        self._write(sheet, pygame.Rect(0, 0, w, p))
        self._sketch(sheet, pygame.Rect(0, p, w, 2 * p))
        self._sheet = sheet
        self._sheet_shadow = _silhouette(sheet, (20, 10, 0), 80)

        back = _rough_paper(size, (311, 173), outline, rng)
        _darken(back, BACK_SHADE)
        _cut_to(back, outline)
        self._back = back
        self._packet = self._item_packet()

        self._item = _load_picture(ITEM_PICTURE, ITEM_HEIGHT) or pygame.transform.smoothscale(
            self._item_packet(), ITEM_SIZE)
        self._item_shadow = _silhouette(self._item, (20, 10, 0), 80)
        self._glow = _glow_surface(self._item, GLOW_REACH)

    def _item_packet(self) -> pygame.Surface:
        """The packet folded up: the middle of the first panel's back, both flaps over it."""
        w, h = self._back.get_size()
        f, p = w // 3, h // 3
        packet = self._back.subsurface((f, 0, f, p)).copy()
        _crease(packet, (f // 2, 2), (f // 2, p - 2), vertical=True)
        # Its folded sides and bottom are straight; the top is the sheet's torn edge
        pygame.draw.lines(packet, EDGE_INK, False, [(0, 0), (0, p - 1), (f - 1, p - 1), (f - 1, 0)], 2)
        # Tied with twine, like the item's picture
        twine = (92, 64, 38)
        pygame.draw.line(packet, twine, (0, p // 2), (f, p // 2), 3)
        pygame.draw.line(packet, twine, (f // 2, 0), (f // 2, p), 3)
        for dx in (-1, 1):
            pygame.draw.ellipse(packet, twine, pygame.Rect(f // 2 + (dx - 1) * 10, p // 2 - 7, 20, 14), 2)
        return packet

    def _write(self, sheet: pygame.Surface, panel: pygame.Rect) -> None:
        """The address, in the uncle's hand, on the top panel."""
        title_font = self._font("Augusta.ttf", 40)
        font = self._font("RomanAntique.ttf", 22)
        title = title_font.render(self.title, True, INK)
        sheet.blit(title, title.get_rect(midtop=(panel.centerx, panel.top + 10)))
        y = panel.top + 12 + title.get_height()
        line_h = round(font.size("Tg")[1] * 1.15)
        for line in _wrap(font, self.address, panel.width - 60):
            text = font.render(line, True, INK)
            sheet.blit(text, text.get_rect(midtop=(panel.centerx, y)))
            y += line_h

    def _sketch(self, sheet: pygame.Surface, area: pygame.Rect) -> None:
        """A little drawing of the way, on the lower two panels: the docks at the top,
        the market square to the south-west, the row of houses and his marked."""
        label = self._font("RomanAntique.ttf", 18)
        small = self._font("RomanAntique.ttf", 15)
        w, h = area.size

        def at(fx: float, fy: float) -> Tuple[int, int]:
            return area.left + round(fx * w), area.top + round(fy * h)

        # The docks and the water
        for i in range(3):
            y = 0.08 + 0.05 * i
            pts = [at(0.06 + 0.02 * k, y + (0.012 if k % 2 else 0)) for k in range(13)]
            pygame.draw.lines(sheet, INK_FADED, False, pts, 1)
        pygame.draw.rect(sheet, INK, pygame.Rect(*at(0.12, 0.18), round(0.18 * w), round(0.03 * h)), 1)
        for k in range(4):
            x, y = at(0.14 + 0.045 * k, 0.21)
            pygame.draw.line(sheet, INK, (x, y), (x, y + 6), 1)
        text = label.render("Docks", True, INK)
        sheet.blit(text, text.get_rect(midtop=at(0.21, 0.25)))

        # The market square, with its stalls
        square = pygame.Rect(*at(0.12, 0.66), round(0.24 * w), round(0.2 * h))
        pygame.draw.rect(sheet, INK, square, 2)
        for k in range(3):
            stall = pygame.Rect(square.left + 10 + k * (square.width - 20) // 3, square.top + 10,
                                (square.width - 40) // 3, square.height // 3)
            pygame.draw.rect(sheet, INK_FADED, stall, 1)
            pygame.draw.line(sheet, INK_FADED, stall.topleft, stall.bottomright, 1)
        text = label.render("Market", True, INK)
        sheet.blit(text, text.get_rect(midtop=(square.centerx, square.bottom + 4)))

        # The row of houses, north-east of the square, his the middle one
        houses = []
        for k in range(5):
            left, bottom = at(0.5 + 0.085 * k, 0.5)
            body = pygame.Rect(left, bottom - 24, round(0.07 * w), 24)
            pygame.draw.rect(sheet, INK, body, 1)
            pygame.draw.polygon(sheet, INK, [(body.left - 2, body.top), (body.centerx, body.top - 14),
                                             (body.right + 2, body.top)], 1)
            pygame.draw.rect(sheet, INK, pygame.Rect(body.centerx - 3, body.bottom - 9, 6, 9), 1)
            houses.append(body)
        shop = houses[2]

        # The way, dotted, from the docks to his door
        way = [at(0.21, 0.33), at(0.3, 0.42), at(0.38, 0.56), (shop.centerx - 40, shop.bottom + 14),
               (shop.centerx, shop.bottom + 4)]
        _dotted(sheet, way, INK_FADED, 7)

        # His door marked with a cross, and his name under it
        cx, cy = shop.centerx, shop.bottom + 16
        for dx in (-1, 1):
            pygame.draw.line(sheet, (140, 32, 24), (cx - 7, cy - 7 * dx), (cx + 7, cy + 7 * dx), 3)
        text = label.render("Gared", True, (140, 32, 24))
        sheet.blit(text, text.get_rect(midtop=(cx, cy + 10)))

        # North
        nx, ny = at(0.9, 0.12)
        pygame.draw.line(sheet, INK, (nx, ny + 18), (nx, ny - 14), 1)
        pygame.draw.polygon(sheet, INK, [(nx, ny - 18), (nx - 5, ny - 8), (nx + 5, ny - 8)])
        text = small.render("N", True, INK)
        sheet.blit(text, text.get_rect(midtop=(nx, ny + 20)))

        hint = small.render("Click anywhere to fold it away", True, INK_FADED)
        sheet.blit(hint, hint.get_rect(bottomright=(area.right - 14, area.bottom - 10)))


def _torn_outline(size: Tuple[int, int], rng: random.Random) -> List[Tuple[int, int]]:
    """The sheet's torn edge: a polygon wandering up to ``ROUGH_PX`` in from each
    side, with a few deeper nicks and the corners worn off."""
    w, h = size
    points: List[Tuple[int, int]] = []
    depth = rng.uniform(1, ROUGH_PX)

    def bite() -> float:
        nonlocal depth
        depth = min(ROUGH_PX, max(1.0, depth + rng.uniform(-2.5, 2.5)))
        return depth + (rng.uniform(3, 7) if rng.random() < 0.05 else 0.0)

    corner = ROUGH_PX + 3
    for x in range(corner, w - corner, 6):                  # top, left to right
        points.append((x, round(bite())))
    for y in range(corner, h - corner, 6):                  # right, downwards
        points.append((w - 1 - round(bite()), y))
    for x in range(w - corner, corner, -6):                 # bottom, right to left
        points.append((x, h - 1 - round(bite())))
    for y in range(h - corner, corner, -6):                 # left, upwards
        points.append((round(bite()), y))
    return points


def _rough_paper(size: Tuple[int, int], anchor: Tuple[int, int], outline: List[Tuple[int, int]],
                 rng: random.Random) -> pygame.Surface:
    """Brown paper with mottled stains, browned towards its edges."""
    paper = pygame.Surface(size, pygame.SRCALPHA)
    draw_paper(paper, paper.get_rect(), anchor, PAPER, edge_depth=34)
    stains = pygame.Surface((size[0] // 4, size[1] // 4), pygame.SRCALPHA)
    for _ in range(STAINS):
        centre = (rng.randrange(stains.get_width()), rng.randrange(stains.get_height()))
        pygame.draw.circle(stains, (*PAPER_STAIN, rng.randrange(30, 70)), centre, rng.randrange(2, 9))
    paper.blit(pygame.transform.smoothscale(stains, size), (0, 0))
    return paper


def _cut_to(paper: pygame.Surface, outline: List[Tuple[int, int]]) -> None:
    """Clear what lies outside the torn edge and ink the edge."""
    keep = pygame.Surface(paper.get_size(), pygame.SRCALPHA)
    pygame.draw.polygon(keep, (255, 255, 255, 255), outline)
    paper.blit(keep, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    pygame.draw.polygon(paper, EDGE_INK, outline, 2)


def _lerp_rect(a: pygame.Rect, b: pygame.Rect, k: float) -> pygame.Rect:
    return pygame.Rect(round(a.x + (b.x - a.x) * k), round(a.y + (b.y - a.y) * k),
                       max(1, round(a.w + (b.w - a.w) * k)), max(1, round(a.h + (b.h - a.h) * k)))


def _darken(surface: pygame.Surface, factor: float) -> None:
    k = max(0, min(255, round(255 * factor)))
    if k < 255:
        surface.fill((k, k, k), special_flags=pygame.BLEND_RGB_MULT)


def _crease(surface: pygame.Surface, start: Tuple[int, int], end: Tuple[int, int], vertical: bool) -> None:
    """A fold line: a dark groove with a light ridge beside it."""
    shift = (1, 0) if vertical else (0, 1)
    pygame.draw.line(surface, (150, 118, 80), start, end, 1)
    pygame.draw.line(surface, (226, 202, 158), (start[0] + shift[0], start[1] + shift[1]),
                     (end[0] + shift[0], end[1] + shift[1]), 1)


def _dotted(surface: pygame.Surface, points: List[Tuple[int, int]], color, gap: int) -> None:
    carry = 0.0
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        length = math.hypot(x1 - x0, y1 - y0)
        d = carry
        while d < length:
            k = d / length
            pygame.draw.circle(surface, color, (round(x0 + (x1 - x0) * k), round(y0 + (y1 - y0) * k)), 2)
            d += gap
        carry = d - length


def _load_picture(name: str, height: int) -> Optional[pygame.Surface]:
    """The picture cut to its largest painted part (stray specks left out) and
    scaled to ``height``; None if it cannot be loaded."""
    try:
        picture = pygame.image.load(os.path.join(PICTURES_PATH, name))
        picture = picture.convert_alpha() if pygame.display.get_surface() else picture
    except (pygame.error, FileNotFoundError, OSError):
        return None
    parts = pygame.mask.from_surface(picture, 16).connected_components()
    if parts:
        picture = picture.subsurface(max(parts, key=lambda m: m.count()).get_bounding_rects()[0])
    w, h = picture.get_size()
    return pygame.transform.smoothscale(picture, (max(1, round(w * height / h)), height))


def _silhouette(picture: pygame.Surface, color, alpha: int) -> pygame.Surface:
    """The picture's shape in one colour, as see-through as ``alpha``."""
    shape = pygame.mask.from_surface(picture, 16).to_surface(setcolor=(*color, alpha), unsetcolor=(0, 0, 0, 0))
    return shape.convert_alpha() if pygame.display.get_surface() else shape


def _glow_surface(picture: pygame.Surface, reach: int) -> pygame.Surface:
    """A soft golden halo round the picture's shape, fading out over ``reach``."""
    w, h = picture.get_size()
    size = (w + 2 * reach, h + 2 * reach)
    shape = pygame.Surface(size, pygame.SRCALPHA)
    gold = _silhouette(picture, (255, 214, 90), 255)
    # Spread the shape a little, then blur it by scaling down and up again
    for dx, dy in ((0, 0), (-4, 0), (4, 0), (0, -4), (0, 4)):
        shape.blit(gold, (reach + dx, reach + dy))
    small = pygame.transform.smoothscale(shape, (max(1, size[0] // 8), max(1, size[1] // 8)))
    glow = pygame.transform.smoothscale(small, size)
    glow.fill((255, 255, 255, 200), special_flags=pygame.BLEND_RGBA_MULT)
    return glow


def _wrap(font: pygame.font.Font, text: str, width: int) -> List[str]:
    lines: List[str] = []
    for word in text.split():
        if lines and font.size(f"{lines[-1]} {word}")[0] <= width:
            lines[-1] = f"{lines[-1]} {word}"
        else:
            lines.append(word)
    return lines
