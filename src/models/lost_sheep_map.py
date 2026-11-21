"""The quest for Flip (lost_sheep.py) on the map: Flip, the shepherdess, the fold and its gates.

``LostSheepOnMap`` finds them on the map (Flip is the sheep named ``FLIP``, the
fold and Flip's strip on the island are rectangles on the "Movements" layer,
the fold's gates are ``FOLD_GATES``), tells the shepherdess which days she
keeps the fold, and each game update hands the quest what happened:

* ``update`` -- whether a fold gate stands open, whether the player has gone
  away and the fold is out of sight (Flip may slip out then), whether Flip on
  the leash is back inside the fold; and it puts Flip where the quest has him
  (``sync``: with the flock, on the island or on the leash, as after loading);
* ``step_leash`` -- each frame the map runs, Flip following the player's trail
  (leash.py);
* ``player_opened`` -- the player opened a gate (house_click_menu.use_gate).

No drawing: the rope and the marker over the shepherdess are drawn by the map
view (leash_view.py, quest_marker.py), her talks played by lost_sheep_talks.py.
"""

import datetime
import math
from typing import Optional, Tuple

import pygame

from .gate import Gate
from .leash import Leash
from .lost_sheep import (
    AT_FOLD, AWAY_TILES, FLIP, FOLD_AREA, FOLD_GATES, ISLAND_ZONE, ON_ISLAND, ON_LEASH, LostSheep,
)

Point = Tuple[float, float]

#: Events update() returns
ESCAPED_NOW, HOME_NOW = "escaped", "home"
#: Where the rope is held and tied, as shares of the figures' sizes (from their feet)
HAND_UP = 0.42          # of the player's height
HAND_OUT = 0.32         # of the player's width, towards the sheep
NECK_UP = 0.55          # of the sheep's sprite height
NECK_OUT = 0.3          # of the sheep's sprite width, to the side it faces


class LostSheepOnMap:
    """The quest's figures and places on the map, and what it is told of them."""

    def __init__(self, quest: LostSheep, tmx_map) -> None:
        from .figurines.humans.npcs.trader_shepherdess import TraderShepherdess
        self.quest = quest
        self.tile_size: int = tmx_map.tile_size
        self.flip = tmx_map.sheep_named(FLIP)
        self.shepherdess: Optional[TraderShepherdess] = next(
            (npc for npc in tmx_map.npcs if isinstance(npc, TraderShepherdess)), None)
        self.fold: Optional[pygame.Rect] = tmx_map.movement_rect(FOLD_AREA)
        self.island: Optional[pygame.Rect] = tmx_map.movement_rect(ISLAND_ZONE)
        self.gates = [house for house in tmx_map.houses if isinstance(house, Gate) and house.name in FOLD_GATES]
        self.leash = Leash()
        if self.shepherdess is not None:
            self.shepherdess.keeps_fold = quest.on_meadow

    @property
    def ready(self) -> bool:
        """Whether the map has all it needs (Flip, the fold, his island); without, nothing happens."""
        return self.flip is not None and self.fold is not None and self.island is not None

    # ------------------------------------------------------------------
    # Each update
    # ------------------------------------------------------------------

    def player_opened(self, gate) -> None:
        """The player opened a gate; one of the fold's puts Flip in danger."""
        if gate in self.gates and gate.is_open:
            self.quest.gate_opened_by_player()

    def player_away(self, player_feet: Point) -> bool:
        """Whether the player's feet are AWAY_TILES or more from the fold."""
        fold = self.fold
        dx = max(fold.left - player_feet[0], 0.0, player_feet[0] - fold.right)
        dy = max(fold.top - player_feet[1], 0.0, player_feet[1] - fold.bottom)
        return math.hypot(dx, dy) >= AWAY_TILES * self.tile_size

    def shepherdess_there(self) -> bool:
        """Whether the shepherdess is out at the fold now."""
        her = self.shepherdess
        return her is not None and her.at_fold and not her.is_hidden

    def update(self, now: datetime.datetime, player_feet: Point,
               view: Optional[pygame.Rect]) -> Optional[str]:
        """Tell the quest what happened since the last update, and put Flip where it has him.

        Args:
            now: The game's time.
            player_feet: Where the player stands, world pixels.
            view: The part of the world shown on the map now, None while the map is not shown.

        Returns:
            ESCAPED_NOW if Flip slipped out just now, HOME_NOW if he was led back into the fold, else None.
        """
        if not self.ready:
            return None
        quest = self.quest
        quest.note_gates(any(gate.is_open for gate in self.gates))
        seen = view is not None and view.colliderect(self.fold)
        if quest.check_escape(now, self.player_away(player_feet), seen):
            self.sync(player_feet)
            return ESCAPED_NOW
        if quest.leading and self.flip.leashed and self.fold.collidepoint(self.flip.feet):
            quest.bring_home(self.shepherdess_there())
            self.flip.walk_home()
            return HOME_NOW
        self.sync(player_feet)
        return None

    def sync(self, player_feet: Point) -> None:
        """Put Flip where the quest has him, if he is not there yet (as after loading a save)."""
        if not self.ready:
            return
        flip, quest = self.flip, self.quest
        flip.name_known = quest.flip_named
        where = quest.flip_at
        if where == ON_ISLAND:
            if flip.leashed or flip.zone_foot_y != float(self.island.bottom) or flip.zone_left != float(self.island.x):
                flip.leashed = False
                flip.set_zone(self.island.x, self.island.y, self.island.width, self.island.height)
        elif where == ON_LEASH:
            if not flip.leashed:
                self.put_on_leash(player_feet)
        elif where == AT_FOLD:
            if flip.leashed or (not flip.in_home_zone and flip.walk_target is None):
                flip.go_home()

    def put_on_leash(self, player_feet: Point) -> None:
        """Flip on the leash, just behind the player if he is not near them already."""
        flip = self.flip
        flip.lead()
        if math.dist(flip.feet, player_feet) > 2 * self.tile_size:
            flip.place_feet(player_feet[0] - 0.9 * self.tile_size, player_feet[1])
        self.leash.reset(player_feet, flip.feet)

    def step_leash(self, dt: float, player_feet: Point, player_speed: float) -> None:
        """Flip on the leash follows the player's trail for a frame."""
        flip = self.flip
        if flip is None or not flip.leashed:
            return
        self.leash.record(player_feet)
        feet, walked = self.leash.step(flip.feet, player_feet, player_speed, dt)
        flip.move_led(feet, walked)

    # ------------------------------------------------------------------
    # The rope's ends
    # ------------------------------------------------------------------

    def rope_ends(self, player) -> Optional[Tuple[Point, Point]]:
        """Where the rope is held (the player's hand) and tied (Flip's neck), world pixels; None
        while he is not on the leash."""
        flip = self.flip
        if flip is None or not flip.leashed:
            return None
        px, py = player.feet
        fx, fy = flip.feet
        toward = 1.0 if fx >= px else -1.0
        hand = (px + toward * HAND_OUT * player.width, py - HAND_UP * player.height)
        facing = 1.0 if flip.direction == "right" else -1.0
        neck = (fx + facing * NECK_OUT * flip.sprite_width, fy - NECK_UP * flip.sprite_height)
        return hand, neck
