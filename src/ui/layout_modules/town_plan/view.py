"""The town plan module: an old paper plan of the town and its surroundings.

``TownPlan`` is owned by ``Game`` and shown wherever a side of the screen is
set to the ``"building"`` view. It draws into whatever module rect it is
given, zooms with the mouse wheel towards the cursor and is moved by
dragging. Its parts:

- ``terrain``   reads the kinds of ground off the map's tiles,
- ``landmarks`` decides what each building is and where names go,
- ``engraving`` inks the unchanging plan, once per zoom level,
- ``ornaments`` draws frame, title, compass, scale, legend and labels,
- ``paper``     makes the sheet it all lies on,
- ``glyphs``    holds the little drawings shared by plan and legend,
- ``style``     holds the colours and tuning.
"""

from typing import Dict, List, Optional, Tuple

import pygame

from . import glyphs, ornaments
from .engraving import engrave
from .landmarks import MAJOR_KINDS, MINOR_KINDS, Landmarks, PlanBuilding, gather
from .paper import get_paper
from .style import (
    DETAIL_LABEL_LEVEL, FONT_PLAIN, FONT_SCRIPT, GOLD_INK, INK, INK_FADED,
    LEGEND_MIN_SIDE_ROOM, PAPER, WATER_LINE, ZOOM_LEVELS,
)
from .terrain import Ground


class TownPlan:
    """The plan of the town, drawn as on old paper."""

    def __init__(self, game_map) -> None:
        """
        Args:
            game_map: The game's ``GameMap``; the plan follows its player
                and, while the map is shown too, its camera.
        """
        self.game_map = game_map
        tmx = game_map.tmx_map
        self.world_size: Tuple[int, int] = (tmx.width * tmx.tile_size, tmx.height * tmx.tile_size)
        self.level: int = 0
        #: World point shown at the middle of the plan
        self.center: List[float] = [self.world_size[0] / 2, self.world_size[1] / 2]

        #: Where the plan was drawn this frame; None while it is not shown
        self.view_rect: Optional[pygame.Rect] = None
        self._inner: Optional[pygame.Rect] = None
        self._dragging: bool = False

        # Built on first sight, so a game that never opens the plan pays nothing
        self._ground: Optional[Ground] = None
        self._marks: Optional[Landmarks] = None
        self._engraved: Dict[int, pygame.Surface] = {}

    # --- Frame bookkeeping ------------------------------------------------

    def begin_frame(self) -> None:
        """Forget last frame's place; ``draw`` sets it again if still shown."""
        self.view_rect = None
        self._inner = None

    # --- Geometry -----------------------------------------------------------

    @property
    def px_per_tile(self) -> float:
        return ZOOM_LEVELS[self.level]

    @property
    def scale(self) -> float:
        """Screen pixels per world pixel."""
        return self.px_per_tile / self.game_map.tmx_map.tile_size

    def world_to_screen(self, x: float, y: float) -> Tuple[float, float]:
        s = self.scale
        return (self._inner.centerx + (x - self.center[0]) * s,
                self._inner.centery + (y - self.center[1]) * s)

    def screen_to_world(self, x: float, y: float) -> Tuple[float, float]:
        s = self.scale
        return (self.center[0] + (x - self._inner.centerx) / s,
                self.center[1] + (y - self._inner.centery) / s)

    def _rect_to_screen(self, rect: pygame.Rect) -> pygame.Rect:
        left, top = self.world_to_screen(rect.left, rect.top)
        s = self.scale
        return pygame.Rect(round(left), round(top), max(1, round(rect.width * s)), max(1, round(rect.height * s)))

    def _clamp(self) -> None:
        """Keep the land filling the view, or centred when it is smaller."""
        s = self.scale
        for axis, view_len in ((0, self._inner.width), (1, self._inner.height)):
            world_len = self.world_size[axis]
            if world_len * s <= view_len:
                self.center[axis] = world_len / 2
            else:
                half = view_len / 2 / s
                self.center[axis] = max(half, min(world_len - half, self.center[axis]))

    # --- Input ----------------------------------------------------------------

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Zoom and drag the plan. Returns True when the event was used."""
        if self._inner is None:
            self._dragging = False
            return False

        if event.type == pygame.MOUSEWHEEL:
            pos = pygame.mouse.get_pos()
            if self._inner.collidepoint(pos):
                self._zoom(1 if event.y > 0 else -1, pos)
                return True
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self._inner.collidepoint(event.pos):
                self._dragging = True
                return True
        elif event.type == pygame.MOUSEMOTION and self._dragging:
            if not event.buttons[0]:
                # Released while something else had the mouse
                self._dragging = False
                return False
            s = self.scale
            self.center[0] -= event.rel[0] / s
            self.center[1] -= event.rel[1] / s
            self._clamp()
            return True
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self._dragging:
            self._dragging = False
            return True
        return False

    def _zoom(self, step: int, anchor: Tuple[int, int]) -> None:
        """Change level, keeping the spot under the cursor where it is."""
        level = max(0, min(len(ZOOM_LEVELS) - 1, self.level + step))
        if level == self.level:
            return
        world = self.screen_to_world(*anchor)
        self.level = level
        s = self.scale
        self.center[0] = world[0] - (anchor[0] - self._inner.centerx) / s
        self.center[1] = world[1] - (anchor[1] - self._inner.centery) / s
        self._clamp()

    # --- Drawing ----------------------------------------------------------------

    def _ensure_built(self) -> None:
        if self._ground is not None:
            return
        tmx = self.game_map.tmx_map
        self._ground = Ground(tmx.tmx_data)
        water = self._ground.masks((tmx.width, tmx.height))["water"]
        self._marks = gather(tmx, water)

    def _plan_at(self, level: int) -> pygame.Surface:
        if level not in self._engraved:
            self._engraved[level] = engrave(self.game_map.tmx_map, self._ground, self._marks, ZOOM_LEVELS[level])
        return self._engraved[level]

    def draw(self, screen: pygame.Surface, rect: pygame.Rect, game_state) -> None:
        """Draw the plan into ``rect``."""
        self._ensure_built()
        self.view_rect = rect
        self._inner = inner = ornaments.frame_inner(rect)
        self._clamp()

        screen.blit(get_paper(rect.size), rect.topleft)

        old_clip = screen.get_clip()
        screen.set_clip(inner)
        plan = self._plan_at(self.level)
        land = plan.get_rect(topleft=(round(inner.centerx - self.center[0] * self.scale),
                                      round(inner.centery - self.center[1] * self.scale)))
        screen.blit(plan, land)
        ornaments.neat_line(screen, land)

        mouse = pygame.mouse.get_pos()
        hovered = None
        if not self._dragging and inner.collidepoint(mouse) and not game_state.info_window:
            hovered = self._building_at(mouse)

        self._draw_live_buildings(screen, game_state, hovered)
        if game_state.is_map_visible:
            self._draw_camera_view(screen)

        # Sheet furniture first, so the names know where not to go
        taken = self._ornament_rects(inner)
        self._draw_labels(screen, inner, taken)
        player = self.game_map.map_player
        ornaments.player_mark(screen, self.world_to_screen(player.x + player.width / 2, player.y + player.height),
                              pygame.time.get_ticks() / 1000.0)
        screen.set_clip(old_clip)

        ornaments.frame(screen, rect)
        self._draw_ornaments(screen, inner, taken)

        if hovered is not None:
            ornaments.tooltip(screen, mouse, hovered.name, hovered.describe(), inner)

    def _building_at(self, pos: Tuple[int, int]) -> Optional[PlanBuilding]:
        wx, wy = self.screen_to_world(*pos)
        slack = 3 / self.scale  # A few screen pixels of grace around small roofs
        hits = [b for b in self._marks.buildings if b.footprint.inflate(slack * 2, slack * 2).collidepoint(wx, wy)]
        return min(hits, key=lambda b: b.footprint.width * b.footprint.height) if hits else None

    def _draw_live_buildings(self, screen: pygame.Surface, game_state, hovered: Optional[PlanBuilding]) -> None:
        """What changes while playing: closed stalls, property owned, hover."""
        for building in self._marks.buildings:
            r = self._rect_to_screen(building.footprint)
            if building.kind == "market" and building.house.is_closed_at(game_state.date):
                # A packed-up stall is covered over and fades into the paper
                glyphs.wash_rect(screen, PAPER, 150, r)
                pygame.draw.line(screen, INK_FADED, r.topleft, r.bottomright)
                pygame.draw.line(screen, INK_FADED, r.bottomleft, r.topright)
            elif building.kind == "warehouse" and getattr(building.house, "is_owned", False):
                pygame.draw.rect(screen, GOLD_INK, r.inflate(6, 6), 2)
        if hovered is not None:
            r = self._rect_to_screen(hovered.footprint).inflate(6, 6)
            pygame.draw.rect(screen, INK, r, 2)

    def _draw_camera_view(self, screen: pygame.Surface) -> None:
        """A dashed frame round what the map module is showing."""
        camera = self.game_map.camera
        tile = self.game_map.tmx_map.tile_size
        factor = round(tile * camera.zoom) / tile
        seen = pygame.Rect(round(camera.x), round(camera.y),
                           round(camera.screen_width / factor), round(camera.screen_height / factor))
        ornaments.dashed_rect(screen, self._rect_to_screen(seen), INK_FADED)

    def _ornament_rects(self, inner: pygame.Rect) -> List[pygame.Rect]:
        """Lay out title, compass, scale and legend; returns the rects they cover."""
        self._cartouche = ornaments.cartouche_rect((inner.left + 16, inner.top + 16))
        radius = 50
        self._compass_center = (inner.right - radius - 26, inner.top + radius + 34)
        compass_box = pygame.Rect(0, 0, 2 * radius + 8, 2 * radius + 40)
        compass_box.center = (self._compass_center[0], self._compass_center[1] - 14)
        self._scale_bar = ornaments.scale_bar_rect((inner.left + 18, inner.bottom - 14), self.px_per_tile)

        # The legend only where the land leaves room beside it
        self._legend = None
        land_width = self.world_size[0] * self.scale
        if (inner.width - land_width) / 2 >= LEGEND_MIN_SIDE_ROOM:
            w, h = ornaments.legend_size()
            self._legend = pygame.Rect(0, 0, w, h)
            self._legend.bottomright = (inner.right - 20, inner.bottom - 36)

        taken = [self._cartouche.inflate(8, 8), compass_box, self._scale_bar]
        if self._legend is not None:
            taken.append(self._legend.inflate(8, 8))
        return taken

    def _draw_ornaments(self, screen: pygame.Surface, inner: pygame.Rect, taken: List[pygame.Rect]) -> None:
        ornaments.cartouche(screen, self._cartouche)
        ornaments.compass(screen, self._compass_center, 50)
        ornaments.scale_bar(screen, self._scale_bar.bottomleft, self.px_per_tile)
        if self._legend is not None:
            ornaments.legend(screen, self._legend)
        ornaments.hint(screen, inner)

    def _draw_labels(self, screen: pygame.Surface, inner: pygame.Rect, taken: List[pygame.Rect]) -> None:
        """Names, the most important first, each only where it fits."""
        grow = self.level * 2
        for region in self._marks.regions:
            if region.style == "water":
                surface = ornaments.text(region.text, FONT_SCRIPT, 26 + grow, WATER_LINE, spaced=True)
            else:
                surface = ornaments.text(region.text, FONT_SCRIPT, 24 + grow, INK_FADED)
            ornaments.place_label(screen, surface, [("center", self.world_to_screen(*region.position))], taken, inner)

        if self._marks.market_area is not None:
            area = self._rect_to_screen(self._marks.market_area)
            surface = ornaments.text("Market Place", FONT_PLAIN, 18 + grow, INK)
            ornaments.place_label(screen, surface, [("midbottom", (area.centerx, area.top - 1)),
                                                    ("midtop", (area.centerx, area.bottom + 1))], taken, inner)

        kinds = MAJOR_KINDS + (MINOR_KINDS if self.level >= DETAIL_LABEL_LEVEL else ())
        named = [b for b in self._marks.buildings if b.kind in kinds]
        named.sort(key=lambda b: MAJOR_KINDS.index(b.kind) if b.kind in MAJOR_KINDS else len(MAJOR_KINDS))
        for building in named:
            r = self._rect_to_screen(building.footprint)
            surface = ornaments.text(building.name, FONT_PLAIN, 15 + grow, INK)
            ornaments.place_label(screen, surface, [
                ("midtop", (r.centerx, r.bottom + 2)),
                ("midbottom", (r.centerx, r.top - 2)),
                ("midleft", (r.right + 4, r.centery)),
                ("midright", (r.left - 4, r.centery)),
            ], taken, inner)
