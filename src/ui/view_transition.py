"""A sheet of parchment unrolled over a module when the view changes.

When the left or right module shows something else (the market instead of the
map, say), the new view is not just there: a roll of parchment runs down over
the part of the screen that changed, from top to bottom, and the new view is
on the sheet it leaves behind it, the old one still showing below it until the
roll has passed. The roll thins as it goes, the sheet coming off it, and casts
a soft shadow on both. A page turning is heard with it: a short one
(page_turn_1, page_turn_2) when one side changes, the long one (page_turn_3,
the longest of them) when both do.

Owned by Game: begin_frame() before anything is drawn, while the screen still
holds the last frame, which is where the old view is taken from, and draw()
after the modules and before the bars, which cover the roll's ends.
"""

import math
import random
from typing import Dict, List, Optional, Tuple

import pygame

from ..config.constants import MODULE_WIDTH, SCREEN_HEIGHT
from .paper import draw_paper

#: How long the roll takes over one module and over both, in real seconds
ROLL_SECONDS = 0.5
ROLL_SECONDS_WIDE = 0.75
#: The roll's radius in pixels when it starts, and when it has unrolled the whole sheet
ROLL_RADIUS = 21
ROLL_RADIUS_END = 12
#: How far its shadow reaches over the old view below it, and over the new sheet above it, in pixels
SHADOW_BELOW = 30
SHADOW_ABOVE = 22
#: How dark those shadows are where they are darkest (0 to 255)
SHADOW_BELOW_ALPHA = 150
SHADOW_ABOVE_ALPHA = 95
#: The roll's paper: the back of an old sheet, a little browner than the parchment's face
ROLL_PAPER = (226, 204, 156)
#: Volume of the page turning (1.0 is 100%)
PAGE_TURN_VOLUME = 0.6

TOP_BAR = 60
BOTTOM_BAR = 60

Layout = List[Tuple[Tuple[int, int, int, int], str]]


def layout(left: str, right: str) -> Layout:
    """What the content area shows: (rect, what) for each part drawn on its own."""
    height = SCREEN_HEIGHT - TOP_BAR - BOTTOM_BAR
    left_rect = (0, TOP_BAR, MODULE_WIDTH, height)
    right_rect = (MODULE_WIDTH, TOP_BAR, MODULE_WIDTH, height)
    if left == right:
        if left == 'depot':
            return [(left_rect, 'depot_chart'), (right_rect, 'depot')]   # the depot's full view
        return [((0, TOP_BAR, MODULE_WIDTH * 2, height), left)]
    return [(left_rect, left), (right_rect, right)]


def ease(t: float) -> float:
    """Pushed off briskly and coming to rest softly, as a roll does."""
    return 1.0 - (1.0 - t) ** 3


class ViewTransition:
    """The roll running over the view that changed, and the page turning heard with it.

    Args:
        sounds: The game's sounds; those named "page_turn_*" are the pages.
    """

    def __init__(self, sounds: dict) -> None:
        pages = sorted((sound for name, sound in sounds.items() if name.startswith("page_turn_")),
                       key=lambda sound: sound.get_length())
        self.long_page: Optional[pygame.mixer.Sound] = pages[-1] if len(pages) > 1 else None
        self.short_pages = pages[:-1] if len(pages) > 1 else pages
        self.last_layout: Optional[Layout] = None
        self.rect: Optional[pygame.Rect] = None      # the part of the screen being unrolled over, None when done
        self.old_view: Optional[pygame.Surface] = None
        self.elapsed = 0.0
        self.duration = ROLL_SECONDS
        #: (roll, shadow below, shadow above) by the width they are made for
        self.made: Dict[int, Tuple[pygame.Surface, pygame.Surface, pygame.Surface]] = {}
        self.roll: Optional[pygame.Surface] = None
        self.shadow_below: Optional[pygame.Surface] = None
        self.shadow_above: Optional[pygame.Surface] = None

    def prepare(self) -> None:
        """Make the roll and its shadows for one module and for both now, while the game loads."""
        for width in (MODULE_WIDTH, MODULE_WIDTH * 2):
            self.made_for(width)

    def made_for(self, width: int) -> Tuple[pygame.Surface, pygame.Surface, pygame.Surface]:
        if width not in self.made:
            self.made[width] = (make_roll(width, ROLL_RADIUS),
                                make_shadow(width, SHADOW_BELOW, SHADOW_BELOW_ALPHA, darkest_at_top=True),
                                make_shadow(width, SHADOW_ABOVE, SHADOW_ABOVE_ALPHA, darkest_at_top=False))
        return self.made[width]

    @property
    def active(self) -> bool:
        return self.rect is not None

    def begin_frame(self, screen: pygame.Surface, left: str, right: str, dt: float) -> None:
        """Advance by *dt* real seconds, and start a roll if the view is no longer what it was.

        Call before anything is drawn this frame: the screen still holds the last one.
        """
        if self.active:
            self.elapsed += dt
            if self.elapsed >= self.duration:
                self.finish()
        now = layout(left, right)
        last, self.last_layout = self.last_layout, now
        if last is None or now == last:
            return
        changed = [pygame.Rect(rect) for rect, what in now if (rect, what) not in last]
        if not changed:
            return
        self.start(screen, changed[0].unionall(changed[1:]))

    def start(self, screen: pygame.Surface, rect: pygame.Rect) -> None:
        """Unroll a new sheet over *rect*, the old view taken from the screen as it is."""
        wide = rect.width > MODULE_WIDTH
        self.rect = rect
        self.old_view = screen.subsurface(rect).copy()
        self.elapsed = 0.0
        self.duration = ROLL_SECONDS_WIDE if wide else ROLL_SECONDS
        self.roll, self.shadow_below, self.shadow_above = self.made_for(rect.width)
        sound = self.long_page if wide and self.long_page else (
            random.choice(self.short_pages) if self.short_pages else None)
        if sound:
            channel = sound.play()
            if channel:
                channel.set_volume(PAGE_TURN_VOLUME)

    def finish(self) -> None:
        self.rect = None
        self.old_view = None

    def draw(self, screen: pygame.Surface) -> None:
        """Draw the old view still to be rolled over, and the roll; after the modules, before the bars."""
        if not self.active:
            return
        rect = self.rect
        t = ease(min(1.0, self.elapsed / self.duration))
        radius = round(ROLL_RADIUS + (ROLL_RADIUS_END - ROLL_RADIUS) * t)
        # The roll's middle runs from the top edge to a radius past the bottom, so it is gone at the end
        middle = rect.top + round(t * (rect.height + ROLL_RADIUS))
        old_clip = screen.get_clip()
        screen.set_clip(rect)
        below = middle - rect.top
        if below < rect.height:
            screen.blit(self.old_view, (rect.left, middle), pygame.Rect(0, below, rect.width, rect.height - below))
        screen.blit(self.shadow_above, (rect.left, middle - radius - SHADOW_ABOVE + radius // 3))
        screen.blit(self.shadow_below, (rect.left, middle + radius // 3))
        roll = self.roll if radius == ROLL_RADIUS else pygame.transform.smoothscale(
            self.roll, (rect.width, radius * 2))
        screen.blit(roll, (rect.left, middle - radius))
        screen.set_clip(old_clip)


def make_roll(width: int, radius: int) -> pygame.Surface:
    """A roll of parchment lying across, *width* long: the paper's grain, shaded as a cylinder lit from above."""
    height = radius * 2
    roll = pygame.Surface((width, height), pygame.SRCALPHA)
    draw_paper(roll, roll.get_rect(), (0, 0), ROLL_PAPER, edge_depth=0)
    shade = pygame.Surface((1, height))
    shine = pygame.Surface((1, height))
    edge = pygame.Surface((1, height), pygame.SRCALPHA)
    for y in range(height):
        n = (y + 0.5 - radius) / radius            # -1 at the top of the roll, 1 at its underside
        facing = math.sqrt(max(0.0, 1.0 - n * n))  # how squarely this line of it faces the viewer
        light = 0.3 + 0.7 * facing ** 0.8 - 0.2 * n   # lit from above, its underside in shadow
        shade.set_at((0, y), [round(255 * max(0.0, min(1.0, light)))] * 3)
        glint = 22 * math.exp(-((n + 0.45) / 0.14) ** 2)   # a soft sheen along the top
        shine.set_at((0, y), [round(glint)] * 3)
        # The silhouette: the outermost lines of the roll fade into what is behind it
        edge.set_at((0, y), (255, 255, 255, round(255 * min(1.0, facing * 3.0))))
    roll.blit(pygame.transform.scale(shade, (width, height)), (0, 0), special_flags=pygame.BLEND_RGB_MULT)
    roll.blit(pygame.transform.scale(shine, (width, height)), (0, 0), special_flags=pygame.BLEND_RGB_ADD)
    roll.blit(pygame.transform.scale(edge, (width, height)), (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    # The sheet wound on itself: the edges of its outer turns, faint, and darker where it leaves the roll
    seam = pygame.Surface((width, 1), pygame.SRCALPHA)
    for depth, alpha in ((0.62, 40), (0.78, 55), (0.9, 95)):
        seam.fill((90, 62, 34, alpha))
        roll.blit(seam, (0, round(radius + depth * radius) - 1))
    return roll


def make_shadow(width: int, depth: int, alpha: int, darkest_at_top: bool) -> pygame.Surface:
    """A soft shadow *depth* high, fading away from the roll."""
    column = pygame.Surface((1, depth), pygame.SRCALPHA)
    for y in range(depth):
        away = (y + 0.5) / depth if darkest_at_top else 1.0 - (y + 0.5) / depth
        column.set_at((0, y), (40, 26, 12, round(alpha * (1.0 - away) ** 2)))
    return pygame.transform.scale(column, (width, depth))
