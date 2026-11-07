"""The little chopping scene beside the woodhacking gauges.

The player's own side sprite stands at a chopping block with a log on it and
swings an axe: lifted while power is gathered (the higher the power, the
further back), brought down on release, and then, by how the swing was
graded,

  SPLIT  the log flies apart in two halves, chips fly, and a new log drops on
         the block; the split wood is stacked on the pile behind,
  BITE   the axe sticks in the log and cracks it; a second bite splits it,
  WHIFF  the axe swishes down past the log into the dirt, raising dust,
  SHORT  too little power: the swing dies above the log.

The scene is the whole minigame: the gauges are part of it. The power gauge is
a post at the left (``POWER_RECT``), the aim a plumb line swinging from a beam
over the block (``AIM_PIVOT``) above a scale board; the minigame draws both
through ``draw``'s ``underlay`` (behind the player and the block) and
``overlay`` (over everything), and the scene draws the beam and the board.

A swing perfect on both gauges (``swing(..., flourish=2)``) lands with a
little more weight: the blow stops for a heartbeat (``_HITSTOP_S``), the
log splits in a warm glow, a few motes of sawdust drift up as if caught in
the sun, and the axe's steel rings ("ring" among the sounds ``update`` asks
for).

The scene is played out of doors at the hour and in the weather of the game
(``set_time``; ``outdoors.py``, shared with the other minigames played
outside): the sky behind it with the sun or the moon and the stars, the light
of the hour over everything else, the rain or snow, the fog and the lightning.
Once it grows dark the two lanterns, one on an arm at the power post and one
hanging from the beam, are lit and throw warm light round the gauges, the
player and the block.

The player's sprite is cut into head, torso and two legs (``_HEAD`` and so
on), each turned about its joint every frame. Its painted arms (and the scroll
in the front hand) are taken out and the arms drawn anew each frame instead,
upper arm, elbow, forearm and hand, as pixel art on a coarse layer
(``_ARM_PX``) so they match the sprite: the far arm, always behind the body,
holds the axe at the fist; the near arm, always in front of it, grips the
handle further down. The whole pose follows the axe's angle
(``_pose``), leaning back to lift it and throwing the weight into the blow. Nothing here touches the game: the
minigame tells the scene what happened and plays the sounds the scene's
``update`` asks for, at the moment of impact.
"""

import datetime
import math
import os
import random
from typing import List, Optional, Tuple

import pygame

from .outdoors import Conditions, Outdoors, radial
from ..figurines.humans.human import HUMAN_SPRITE_ROOT

SPLIT, BITE, WHIFF, SHORT = "split", "bite", "whiff", "short"

SCENE_W, SCENE_H = 1000, 520
_FEET_Y = 430                       # where the player, block and pile stand
_HORIZON_Y = 344

# The player: the right-facing standing sprite, scaled to this height and cut
# into parts that move on their own. Rects and joints are in the sprite's own
# pixels (208 x 336); each part turns about its joint.
_PLAYER_FILE = os.path.join(HUMAN_SPRITE_ROOT, "player", "player_right_static.png")
_PLAYER_H = 230
_PLAYER_LEFT = 302
_HEAD = pygame.Rect(0, 0, 208, 172)
_HEAD_CLEAR = pygame.Rect(0, 0, 208, 168)        # the torso keeps the chin's last rows under the head
_NECK = (108, 170)
# The painted arms, taken out of the torso: the back sleeve and hand, and the
# front sleeve with the scrolled-up hand
_ARMS_CLEAR = (pygame.Rect(24, 172, 42, 78), pygame.Rect(24, 250, 30, 16), pygame.Rect(147, 176, 61, 112))
# Where the drawn arms join the body: the far arm's inside it, so the torso
# covers the joint; the near arm's at the back of the torso under the head,
# where the near shoulder sits (it is drawn over the body and under the head)
_FRONT_SHOULDER = (138, 196)
_NEAR_SHOULDER = (76, 190)

# The drawn arms, in screen pixels at the scene's scale, and their pixel art
_ARM_PX = 4                          # one art pixel of the arms, like the sprite's
_UPPER_ARM, _FOREARM = 21.0, 20.0
_NEAR_UPPER_ARM, _NEAR_FOREARM = 30.0, 28.0   # the near arm reaches across the body
_ARM_REACH = 0.9                     # the front hand's distance from the shoulder, of the arm's full length
_SLEEVE, _SLEEVE_LIGHT, _SLEEVE_DARK = (92, 116, 152), (132, 152, 178), (46, 62, 86)
_ARM_OUTLINE = (26, 30, 46)
_CUFF = (62, 44, 28)
_SKIN, _SKIN_LIGHT = (232, 180, 140), (246, 214, 182)
_BACK_LEG = pygame.Rect(40, 286, 66, 50)
_FRONT_LEG = pygame.Rect(106, 286, 54, 50)
_LEGS_CLEAR = pygame.Rect(40, 290, 108, 46)      # the torso keeps the legs' top rows as an overlap
_BACK_HIP = (80, 290)
_FRONT_HIP = (130, 290)
_HIP = (105, 290)                                # the torso leans about this

# The chopping block and the log standing on it
_BLOCK_CX = 560
_BLOCK_W, _BLOCK_H = 118, 36
_LOG_W, _LOG_H = 62, 60
_LOG_TOP = _FEET_Y - _BLOCK_H - _LOG_H
_END_H = 14                          # height of the cut ends' ellipses

# The axe, in degrees: 0 points forward, 90 straight up (screen counter-clockwise)
_REST_ANGLE = 32.0
_WINDUP_EXTRA = 138.0               # how far back full power lifts it
_WHIFF_ANGLE = -24.0
_SHORT_ANGLE = 50.0
_AXE_TAIL = 26                      # handle behind the fist, room for the near hand
_NEAR_GRIP = (8.0, 24.0)            # how far behind the fist the near hand may hold it
_BITE_DEPTH = 7                     # how far a biting blade sinks into the log

# Timings, seconds
_SWING_S = 0.11
_SHORT_SWING_S = 0.2
_HOLD_S = {SPLIT: 0.14, BITE: 0.34, WHIFF: 0.18, SHORT: 0.12}
_FOLLOW_RATE = 16.0                 # how fast the axe follows the gathered power
_RECOVER_RATE = 9.0                 # and goes back to rest after a swing
_BITES_TO_SPLIT = 2

_GRAVITY = 1500.0

# A swing perfect on both gauges
_HITSTOP_S = 0.08                   # the blow holds still this long on impact
_GLOW_S = 0.8                       # the warm glow round the split log fades over this
_GLOW_RADIUS = 96
_GLOW_COLOUR = (70, 52, 22)         # added to what is under it, at its brightest
_MOTES = 18
_MOTE_COLOUR = (250, 224, 150)
_PILE_ROWS = 8                      # the pile: 8 + 7 + ... + 1 = 36 split logs, room for every swing
_PILE_LEFT, _PILE_R = 648, 10

# Colours

_LANTERN_GLASS, _LANTERN_GLASS_LIT = (96, 76, 44), (255, 222, 150)
_HILLS = (176, 172, 128)
_GRASS, _GRASS_DARK = (128, 140, 82), (104, 118, 66)
# The forest floor: shaded grass at the tree line, lighter in front, a band of
# moss and needles under the trees, and the blades of the tufts, dark to light
_GRASS_FAR, _GRASS_NEAR = (98, 114, 64), (134, 148, 84)
_MOSS, _NEEDLES = (84, 98, 54), (118, 98, 62)
_BLADES = ((62, 86, 44), (84, 110, 54), (108, 134, 64), (138, 160, 82), (164, 172, 96))
_CHIP, _CHIP_DARK = (214, 182, 128), (170, 136, 88)
_STONE, _STONE_LIGHT = (128, 124, 114), (164, 160, 148)
_FLOWERS = ((236, 232, 214), (232, 206, 96), (200, 170, 214))
_DIRT, _DIRT_DARK = (150, 118, 80), (122, 94, 62)
_BARK, _BARK_DARK, _BARK_LIGHT = (108, 76, 48), (78, 54, 34), (134, 98, 64)
_WOOD, _WOOD_RING, _WOOD_CUT = (222, 186, 128), (184, 140, 86), (238, 210, 160)
_OLD_WOOD, _OLD_RING = (176, 150, 112), (140, 114, 80)
_STEEL, _STEEL_EDGE, _STEEL_DARK = (148, 150, 156), (214, 216, 222), (92, 94, 100)
_HANDLE, _HANDLE_DARK = (160, 112, 62), (96, 64, 34)
_OUTLINE = (44, 32, 22)
_SHADOW = (0, 0, 0, 60)

# The wood round the clearing, trees of the map in three depths: (sprite,
# height, left edge, how much paler with distance, how far below the horizon
# its foot stands). The far row stands in clusters with gaps, so the hills
# show between them; the near one is drawn over everything, cut by the frame.
_FAR_TREES = (
    ("Tree_12.png", 150, -30, 52, 16), ("Tree_19.png", 132, 28, 52, 14), ("Tree_22.png", 146, 70, 50, 16),
    ("Tree_04.png", 126, 230, 54, 14), ("Tree_44.png", 104, 270, 50, 16), ("Tree_08.png", 120, 300, 54, 14),
    ("Tree_17.png", 112, 628, 54, 14), ("Tree_06.png", 128, 662, 52, 15), ("Tree_15.png", 118, 760, 54, 14),
    ("Tree_46.png", 100, 940, 50, 16), ("Tree_12.png", 140, 968, 52, 15),
)
_MID_TREES = (
    ("Tree_39.png", 214, -120, 30, 34), ("Tree_02.png", 190, 110, 30, 30), ("Tree_05.png", 160, 196, 30, 30),
    ("Tree_24.png", 196, 700, 28, 30), ("Tree_03.png", 120, 880, 30, 30), ("Tree_01.png", 236, 852, 30, 30),
)
_NEAR_TREE = ("Tree_40.png", 430, 776, SCENE_H - 14)   # sprite, height, left edge, foot
# A big pine on the left, nearer than the wood but not as near as the oak: in
# the background picture, so behind the power post, and so standing a little
# further back than the post (its foot higher), its trunk beside it
POWER_POST_FOOT = SCENE_H - 70                 # where the power post stands in the grass
_LEFT_TREE = ("Tree_38.png", 330, 70, POWER_POST_FOOT - 14)
_LEFT_SHADE = (230, 230, 220)
_NEAR_SHADE = (214, 214, 204)                           # a touch darker, being nearer and in its own shade

# The gauges, in the scene's pixels: the power post at the left, and the plumb
# line's pivot under the beam, right over the log, with its scale board's radius
POWER_RECT = pygame.Rect(54, 104, 34, 290)
AIM_PIVOT = (_BLOCK_CX, 92)
AIM_RADIUS = 148
_BEAM_Y = 72                        # the beam's top
_BEAM_LEFT, _POST_X = 384, 806      # the beam's left end, the post holding it
_BOARD_WIDTH = 34                   # the scale board under the beam, a half ring
_WOOD_DARK, _WOOD_MID, _WOOD_LIGHT = (86, 58, 36), (122, 86, 54), (150, 112, 72)
_BRASS, _BRASS_LIGHT, _BRASS_DARK = (196, 154, 64), (236, 204, 120), (120, 86, 30)
_IRON = (64, 62, 60)
# The lanterns: on an arm at the left of the power post, and hanging from the beam's left end (their tops)
_POST_LANTERN = (POWER_RECT.left - 34, POWER_RECT.top - 12)
_BEAM_LANTERN = (_BEAM_LEFT + 6, _BEAM_Y + 44)


def _ease_out(t: float) -> float:
    return 1.0 - (1.0 - t) ** 2


def _ease_in(t: float) -> float:
    return t * t


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _interp(x: float, points: List[Tuple[float, float]]) -> float:
    """Piecewise linear through (x, y) points sorted by x, flat beyond them."""
    if x <= points[0][0]:
        return points[0][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x <= x1:
            return _lerp(y0, y1, (x - x0) / (x1 - x0))
    return points[-1][1]


def _load_alpha(path: str) -> pygame.Surface:
    image = pygame.image.load(path)
    return image.convert_alpha() if pygame.display.get_surface() else image


class _Particle:
    __slots__ = ("x", "y", "vx", "vy", "life", "age", "size", "color", "grow", "ground")

    def __init__(self, x, y, vx, vy, life, size, color, grow=0.0, ground=_FEET_Y + 6):
        self.x, self.y, self.vx, self.vy = x, y, vx, vy
        self.life, self.age, self.size, self.color = life, 0.0, size, color
        self.grow = grow
        self.ground = ground


class _Piece:
    """Half of a split log, flying off and fading."""
    __slots__ = ("surface", "x", "y", "vx", "vy", "angle", "spin", "age", "landed")

    def __init__(self, surface, x, y, vx, vy, spin):
        self.surface, self.x, self.y, self.vx, self.vy = surface, x, y, vx, vy
        self.angle, self.spin, self.age, self.landed = 0.0, spin, 0.0, False


class _Part:
    """A piece of the player's sprite that turns about its joint."""

    def __init__(self, image: pygame.Surface, pivot_from_centre: pygame.Vector2, joint: pygame.Vector2) -> None:
        self.image = image
        self.pivot_from_centre = pivot_from_centre   # the joint, from the image's centre
        self.joint = joint                           # the joint, in the scaled sprite

    def blit(self, surf: pygame.Surface, at: pygame.Vector2, angle: float) -> None:
        """Draw it turned by angle degrees (counter-clockwise) with its joint at `at`."""
        if abs(angle) < 0.05:
            image, offset = self.image, self.pivot_from_centre
        else:
            image = pygame.transform.rotate(self.image, angle)
            offset = self.pivot_from_centre.rotate(-angle)
        centre = at - offset
        surf.blit(image, image.get_rect(center=(round(centre.x), round(centre.y))))


class _Pose:
    __slots__ = ("lean", "origin", "hip", "neck", "head_angle", "shoulder", "fist",
                 "near_shoulder", "near_hand", "back_leg", "front_leg")

    def __init__(self, **values) -> None:
        for name, value in values.items():
            setattr(self, name, value)


class ChoppingScene:
    """The player at the chopping block, animated by the minigame's swings."""

    def __init__(self, font: pygame.font.Font, rng: Optional[random.Random] = None,
                 when: Optional[datetime.datetime] = None, weather: Optional[Conditions] = None) -> None:
        self.font = font
        self.rng = rng or random.Random()
        self.surface = pygame.Surface((SCENE_W, SCENE_H))                    # the picture handed out
        self._world = pygame.Surface((SCENE_W, SCENE_H), pygame.SRCALPHA)    # all but the sky, to be lit
        self._overlay = pygame.Surface((SCENE_W, SCENE_H), pygame.SRCALPHA)

        self._build_player()
        self._near_tree = self._build_near_tree()
        self._foot_tufts = self._build_foot_tufts()
        self._block = self._build_block()
        self._log = self._build_log()
        self._halves = self._build_halves()
        self._pile_end = self._build_log_end()

        self.state = "idle"             # idle, charge, swing, hold, recover
        self.angle = _REST_ANGLE
        self.charge_t = 0.0             # 0..1, eased power while lifting
        self.outcome: Optional[str] = None
        self._swing_from = _REST_ANGLE
        self._swing_to = _REST_ANGLE
        self._swing_s = _SWING_S
        self._timer = 0.0
        self._trail: List[float] = []   # recent angles while swinging, for the blur
        self._squat = 0.0               # pixels the player dips on impact
        self._shake = 0.0

        self.log_damage = 0             # bites taken by the log on the block
        self.log_drop = 0.0             # >0 while a new log is falling onto the block
        self._log_vy = 0.0
        self._log_bounced = False
        self.pile = 0                   # split logs stacked behind

        self.pieces: List[_Piece] = []
        self.particles: List[_Particle] = []
        self._popup: Optional[Tuple[str, Tuple[int, int, int], float]] = None  # text, colour, age
        self.flourish = 0               # 2 for a swing perfect on both gauges
        self._hitstop = 0.0
        self._glow_age: Optional[float] = None
        self.motes: List[List[float]] = []   # x, y, vx, vy, age, life, phase
        self._glow = self._build_glow()

        # Where the axe lands on the log, worked out from the fist at the strike
        self._strike_angle, self._axe_len = self._aim_at_log()

        self._lantern_glow = radial(1.0, 46, (255, 200, 130))
        self.set_time(when, weather)

    # ------------------------------------------------------------------
    # Building the pictures, once
    # ------------------------------------------------------------------

    def _build_player(self) -> None:
        """Scale the sprite once, then cut it into its parts (cut in scaled pixels, so the parts meet exactly)."""
        sprite = _load_alpha(_PLAYER_FILE)
        scale = _PLAYER_H / sprite.get_height()
        self._scale = scale
        full = pygame.transform.smoothscale(sprite, (round(sprite.get_width() * scale), _PLAYER_H))
        self._body_w = full.get_width()

        def sc(rect: pygame.Rect) -> pygame.Rect:
            return pygame.Rect(round(rect.x * scale), round(rect.y * scale),
                               round(rect.w * scale), round(rect.h * scale)).clip(full.get_rect())

        def part(rect: pygame.Rect, joint: Tuple[int, int]) -> _Part:
            r = sc(rect)
            image = full.subsurface(r).copy()
            pivot = pygame.Vector2(joint[0] * scale, joint[1] * scale)
            return _Part(image, pivot - pygame.Vector2(r.center), pivot)

        self._head = part(_HEAD, _NECK)
        self._back_leg = part(_BACK_LEG, _BACK_HIP)
        self._front_leg = part(_FRONT_LEG, _FRONT_HIP)

        torso = full.copy()
        for rect in (_HEAD_CLEAR, _LEGS_CLEAR) + _ARMS_CLEAR:
            torso.fill((0, 0, 0, 0), sc(rect))
        hip = pygame.Vector2(_HIP[0] * scale, _HIP[1] * scale)
        self._torso = _Part(torso, hip - pygame.Vector2(torso.get_rect().center), hip)

        self._front_shoulder = pygame.Vector2(_FRONT_SHOULDER) * scale
        self._near_shoulder = pygame.Vector2(_NEAR_SHOULDER) * scale
        self._arm_layer = pygame.Surface((math.ceil(SCENE_W / _ARM_PX), math.ceil(SCENE_H / _ARM_PX)), pygame.SRCALPHA)
        self._body_top = _FEET_Y - _PLAYER_H

    def _build_background(self) -> pygame.Surface:
        bg = pygame.Surface((SCENE_W, SCENE_H), pygame.SRCALPHA)    # see-through where the sky shows

        # Low hills on the horizon
        hills = [(0, _HORIZON_Y)]
        for x in range(0, SCENE_W + 20, 20):
            hills.append((x, _HORIZON_Y - 18 - 14 * math.sin(x / 70.0) - 8 * math.sin(x / 23.0 + 1)))
        hills.append((SCENE_W, _HORIZON_Y + 10))
        hills.append((0, _HORIZON_Y + 10))
        pygame.draw.polygon(bg, _HILLS, hills)

        rng = random.Random(7)
        self._draw_ground(bg, rng)
        if self.outdoors.snow_ground is not None:          # under the trees and the trodden clearing
            bg.blit(self.outdoors.snow_ground, (0, 0))

        # The wood: the far row on the hills, then the nearer one at the clearing's edge,
        # standing in the grass
        for name, height, x, haze, foot in _FAR_TREES + _MID_TREES:
            tree = self._tree(name, height)
            if tree is None:
                continue
            tree.fill((haze, haze, round(haze * 0.8), 0), special_flags=pygame.BLEND_RGBA_ADD)
            bg.blit(tree, (x, _HORIZON_Y + foot - height))
            if foot >= 28:
                self._tufts_along(bg, rng, x + tree.get_width() / 2, tree.get_width() * 0.35,
                                  _HORIZON_Y + foot - 2, scale=0.55, density=0.7)
        self._draw_clearing(bg, rng)
        name, height, x, foot = _LEFT_TREE
        tree = self._tree(name, height)
        if tree is not None:
            tree.fill(_LEFT_SHADE, special_flags=pygame.BLEND_RGB_MULT)
            self._overlay.fill((0, 0, 0, 0))
            pygame.draw.ellipse(self._overlay, _SHADOW, (x + tree.get_width() * 0.2, foot - 8, tree.get_width() * 0.6, 14))
            bg.blit(self._overlay, (0, 0))
            bg.blit(tree, (x, foot - height))
            self._tufts_along(bg, rng, x + tree.get_width() / 2, 40, foot - 2, scale=0.9)
        self._draw_rig(bg)
        self._tufts_along(bg, rng, _POST_X, 22, _HORIZON_Y + 34, scale=0.7)        # the beam's post
        return bg

    # ------------------------------------------------------------------
    # The forest floor
    # ------------------------------------------------------------------

    def _draw_ground(self, bg: pygame.Surface, rng: random.Random) -> None:
        """Grass shaded at the tree line and lighter in front, mottled, with a band
        of moss and needles under the trees and scattered tufts and flowers."""
        top = _HORIZON_Y + 10
        for y in range(top, SCENE_H):
            t = ((y - top) / (SCENE_H - top)) ** 0.8
            bg.fill(tuple(round(_lerp(a, b, t)) for a, b in zip(_GRASS_FAR, _GRASS_NEAR)), (0, y, SCENE_W, 1))
        mottle = pygame.Surface((SCENE_W, SCENE_H), pygame.SRCALPHA)
        for _ in range(140):             # soft patches, lighter and darker, flatter further back
            y = rng.uniform(top, SCENE_H)
            depth = (y - top) / (SCENE_H - top)
            w = rng.uniform(40, 150) * (0.5 + depth)
            colour = (*(_GRASS_DARK if rng.random() < 0.5 else (150, 162, 96)), rng.randrange(18, 40))
            pygame.draw.ellipse(mottle, colour, (rng.uniform(-40, SCENE_W), y, w, w * (0.12 + 0.12 * depth)))
        for _ in range(60):              # moss and fallen needles under the trees, along the tree line
            x = rng.uniform(-30, SCENE_W)
            if 330 < x < 600:            # not in the open middle, where the hills show
                continue
            w = rng.uniform(50, 120)
            colour = (*(_MOSS if rng.random() < 0.6 else _NEEDLES), rng.randrange(60, 110))
            pygame.draw.ellipse(mottle, colour, (x, top - 4 + rng.uniform(0, 22), w, rng.uniform(6, 12)))
        bg.blit(mottle, (0, 0))
        for _ in range(900):             # short blades everywhere, longer in front
            x = rng.uniform(0, SCENE_W)
            y = rng.uniform(top + 4, SCENE_H)
            depth = (y - top) / (SCENE_H - top)
            h = 2 + 5 * depth * rng.random()
            pygame.draw.line(bg, rng.choice(_BLADES[:3]), (x, y), (x + rng.uniform(-1.5, 1.5), y - h), 1)
        for _ in range(70):              # tufts dotted over the grass
            y = rng.uniform(top + 14, SCENE_H)
            depth = (y - top) / (SCENE_H - top)
            self._tuft(bg, rng, rng.uniform(0, SCENE_W), y, 6 + 10 * depth, 4 + 10 * depth)
        for _ in range(26):              # a few small flowers in front
            x, y = rng.uniform(0, SCENE_W), rng.uniform(_FEET_Y + 20, SCENE_H - 4)
            if abs(x - _BLOCK_CX) < 240:
                continue
            colour = rng.choice(_FLOWERS)
            pygame.draw.line(bg, _BLADES[1], (x, y), (x, y - 5), 1)
            pygame.draw.circle(bg, colour, (x, y - 6), 2)

    def _draw_clearing(self, bg: pygame.Surface, rng: random.Random) -> None:
        """The trodden dirt round the block: a soft edge with the grass creeping in,
        chips of wood from earlier work and a few stones."""
        rect = pygame.Rect(_BLOCK_CX - 240, _FEET_Y - 34, 360, 70)
        dirt = pygame.Surface((SCENE_W, SCENE_H), pygame.SRCALPHA)
        for i, inset in enumerate((0, 10, 20)):   # three steps darker to the middle: a soft edge
            pygame.draw.ellipse(dirt, (*_DIRT, 90 + 70 * i), rect.inflate(-inset * 2, -inset * 0.6))
        bg.blit(dirt, (0, 0))
        for _ in range(60):
            x = rng.uniform(rect.left + 30, rect.right - 30)
            y = rng.uniform(rect.top + 10, rect.bottom - 8)
            pygame.draw.circle(bg, _DIRT_DARK, (x, y), 1)
        for _ in range(26):              # chips of wood, most near the block
            x = _BLOCK_CX + rng.gauss(0, 70)
            y = _FEET_Y + rng.uniform(-14, 22)
            if not rect.inflate(-40, -16).collidepoint(x, y):
                continue
            w = rng.choice((3, 4, 5))
            pygame.draw.rect(bg, rng.choice((_CHIP, _CHIP_DARK)), (x, y, w, 2))
        for x, y, r in ((_BLOCK_CX - 190, _FEET_Y + 12, 4), (_BLOCK_CX + 92, _FEET_Y + 20, 3), (_BLOCK_CX - 60, _FEET_Y + 26, 2)):
            pygame.draw.ellipse(bg, _STONE, (x - r, y - r * 0.6, r * 2, r * 1.3))
            pygame.draw.line(bg, _STONE_LIGHT, (x - r * 0.5, y - r * 0.3), (x + r * 0.2, y - r * 0.4), 1)
        # The grass creeping in at the rim, more on the near side
        for i in range(48):
            a = math.tau * i / 48 + rng.uniform(-0.05, 0.05)
            x = rect.centerx + rect.w / 2 * math.cos(a)
            y = rect.centery + rect.h / 2 * math.sin(a)
            near = math.sin(a) > 0
            if rng.random() < (0.85 if near else 0.5):
                self._tuft(bg, rng, x, y + 2, 8 if near else 6, 8 if near else 5)

    def _tuft(self, surf: pygame.Surface, rng: random.Random, x: float, y: float,
              width: float, height: float) -> None:
        """A tuft of grass, blades fanning up from (x, y), dark ones behind and light in front."""
        blades = max(3, int(width / 2.2))
        for i in range(blades):
            shade = _BLADES[min(len(_BLADES) - 1, int(i / blades * len(_BLADES) + rng.uniform(0, 1.2)))]
            bx = x + rng.uniform(-width / 2, width / 2)
            h = height * rng.uniform(0.55, 1.0) * (1 - 0.5 * abs(bx - x) / max(1.0, width / 2))
            lean = (bx - x) / max(1.0, width / 2) * h * 0.45 + rng.uniform(-0.2, 0.2) * h
            pygame.draw.line(surf, shade, (bx, y), (bx + lean, y - h), 2 if h > 7 else 1)

    def _tufts_along(self, surf: pygame.Surface, rng: random.Random, cx: float, half_width: float,
                     y: float, scale: float = 1.0, density: float = 1.0) -> None:
        """Tufts along the foot of something standing in the grass, over its foot."""
        n = max(2, int(half_width * 2 / 9 * density))
        for i in range(n):
            x = cx - half_width + (2 * half_width) * (i + rng.uniform(0.1, 0.9)) / n
            self._tuft(surf, rng, x, y + rng.uniform(0, 4), rng.uniform(9, 15) * scale, rng.uniform(8, 15) * scale)

    def _build_foot_tufts(self) -> dict:
        """The tufts in front of what is drawn over the background: the power post
        (drawn by the minigame), the block and the woodpile, and the oak."""
        rng = random.Random(11)
        layers = {}
        for key in ("post", "block", "near"):
            layers[key] = pygame.Surface((SCENE_W, SCENE_H), pygame.SRCALPHA)
        post = POWER_RECT
        self._tufts_along(layers["post"], rng, post.centerx, post.width / 2 + 22, POWER_POST_FOOT + 2, scale=1.0, density=1.4)
        # The block stands on the trodden dirt: only a few blades, and chips at its foot
        block_foot = _FEET_Y + _END_H / 2 - 1
        for dx in (-62, -50, 50, 60):
            self._tuft(layers["block"], rng, _BLOCK_CX + dx, block_foot + rng.uniform(0, 3), 7, 7)
        for _ in range(8):
            x = _BLOCK_CX + rng.uniform(-60, 60)
            pygame.draw.rect(layers["block"], rng.choice((_CHIP, _CHIP_DARK)),
                             (x, block_foot + rng.uniform(-1, 4), rng.choice((3, 4)), 2))
        # The woodpile sits in the grass
        pile_foot = _FEET_Y - 24
        pile_w = _PILE_ROWS * (_PILE_R * 2 - 1)
        self._tufts_along(layers["block"], rng, _PILE_LEFT + pile_w / 2, pile_w / 2 + 8, pile_foot + 2,
                          scale=1.0, density=1.8)
        # The oak's roots
        if self._near_tree is not None:
            tree, (x, y) = self._near_tree
            self._tufts_along(layers["near"], rng, x + tree.get_width() * 0.52, 70, y + tree.get_height() - 4,
                              scale=1.5, density=1.2)
        return layers

    @staticmethod
    def _tree(name: str, height: int) -> Optional[pygame.Surface]:
        """A tree of the map, scaled to that height; None if the sprite is missing."""
        path = os.path.join(os.path.dirname(os.path.dirname(HUMAN_SPRITE_ROOT)), "trees", name)
        if not os.path.exists(path):
            return None
        tree = _load_alpha(path)
        return pygame.transform.smoothscale(tree, (round(tree.get_width() * height / tree.get_height()), height))

    def _build_near_tree(self) -> Optional[Tuple[pygame.Surface, Tuple[int, int]]]:
        """The tree in the foreground, a little darker, with where it is drawn."""
        name, height, x, foot = _NEAR_TREE
        tree = self._tree(name, height)
        if tree is None:
            return None
        tree.fill(_NEAR_SHADE, special_flags=pygame.BLEND_RGB_MULT)
        return tree, (x, foot - height)

    def _plank(self, surf: pygame.Surface, rect: pygame.Rect, grain_seed: int) -> None:
        """A rough-hewn plank: dark outline, lit top edge, a few grain strokes."""
        pygame.draw.rect(surf, _WOOD_MID, rect)
        rng = random.Random(grain_seed)
        horizontal = rect.w >= rect.h
        for _ in range(max(rect.w, rect.h) // 14):
            if horizontal:
                x = rng.randrange(rect.left + 4, rect.right - 20)
                y = rng.randrange(rect.top + 3, rect.bottom - 2)
                pygame.draw.line(surf, _WOOD_DARK, (x, y), (x + rng.randrange(10, 30), y), 1)
            else:
                x = rng.randrange(rect.left + 3, rect.right - 2)
                y = rng.randrange(rect.top + 4, rect.bottom - 20)
                pygame.draw.line(surf, _WOOD_DARK, (x, y), (x, y + rng.randrange(10, 30)), 1)
        if horizontal:
            pygame.draw.line(surf, _WOOD_LIGHT, (rect.left + 1, rect.top + 1), (rect.right - 2, rect.top + 1), 2)
        else:
            pygame.draw.line(surf, _WOOD_LIGHT, (rect.left + 1, rect.top + 1), (rect.left + 1, rect.bottom - 2), 2)
        pygame.draw.rect(surf, _OUTLINE, rect, 2)

    def _nail(self, surf: pygame.Surface, x: float, y: float) -> None:
        pygame.draw.circle(surf, _IRON, (x, y), 3)
        pygame.draw.circle(surf, (120, 116, 110), (x - 1, y - 1), 1)

    def _draw_rig(self, surf: pygame.Surface) -> None:
        """The post and beam behind the block, with the plumb line's scale board nailed under it."""
        # Its shadow on the ground, the post and a brace
        self._overlay.fill((0, 0, 0, 0))
        pygame.draw.ellipse(self._overlay, _SHADOW, (_POST_X - 20, _HORIZON_Y + 30, 46, 10))
        surf.blit(self._overlay, (0, 0))
        self._plank(surf, pygame.Rect(_POST_X - 10, _BEAM_Y - 6, 20, _HORIZON_Y + 38 - _BEAM_Y), 11)
        brace = [(_POST_X - 8, _BEAM_Y + 74), (_POST_X - 74, _BEAM_Y + 22), (_POST_X - 62, _BEAM_Y + 18),
                 (_POST_X - 8, _BEAM_Y + 60)]
        pygame.draw.polygon(surf, _WOOD_MID, brace)
        pygame.draw.polygon(surf, _OUTLINE, brace, 2)
        # The board: a half ring of planks hanging under the beam
        cx, cy = AIM_PIVOT
        outer, inner = AIM_RADIUS + _BOARD_WIDTH / 2, AIM_RADIUS - _BOARD_WIDTH / 2
        ring = []
        for i in range(61):
            a = math.radians(-90 + 180 * i / 60)
            ring.append((cx + outer * math.sin(a), cy + outer * math.cos(a)))
        for i in range(60, -1, -1):
            a = math.radians(-90 + 180 * i / 60)
            ring.append((cx + inner * math.sin(a), cy + inner * math.cos(a)))
        pygame.draw.polygon(surf, _WOOD_MID, ring)
        for k in range(1, 6):            # the joints between its planks
            a = math.radians(-90 + 180 * k / 6)
            pygame.draw.line(surf, _WOOD_DARK, (cx + inner * math.sin(a), cy + inner * math.cos(a)),
                             (cx + outer * math.sin(a), cy + outer * math.cos(a)), 2)
        pygame.draw.polygon(surf, _OUTLINE, ring, 2)
        # The beam over it all, nailed to the post
        self._plank(surf, pygame.Rect(_BEAM_LEFT, _BEAM_Y, _POST_X + 26 - _BEAM_LEFT, 22), 5)
        for x in (_BEAM_LEFT + 12, cx - outer + 8, cx + outer - 8, _POST_X):
            self._nail(surf, x, _BEAM_Y + 11)
        # The pivot: an iron eye the cord hangs from
        pygame.draw.circle(surf, _IRON, AIM_PIVOT, 7)
        pygame.draw.circle(surf, _OUTLINE, AIM_PIVOT, 7, 2)

    def _cylinder(self, w: int, h: int, top: Tuple, ring: Tuple, rings: int) -> pygame.Surface:
        """An upright log seen from the side and a little above: bark, and its cut top."""
        surf = pygame.Surface((w, h + _END_H), pygame.SRCALPHA)
        body = pygame.Rect(0, _END_H // 2, w, h)
        pygame.draw.rect(surf, _BARK, body)
        pygame.draw.ellipse(surf, _BARK, (0, h - 1, w, _END_H))
        rng = random.Random(w * 31 + h)
        for _ in range(w // 5):
            x = rng.randrange(3, w - 3)
            y0 = rng.randrange(_END_H, _END_H + h // 2)
            pygame.draw.line(surf, _BARK_DARK, (x, y0), (x, y0 + rng.randrange(8, h // 2 + 8)), 2)
        pygame.draw.line(surf, _BARK_LIGHT, (4, _END_H), (4, h), 2)
        pygame.draw.rect(surf, _BARK_DARK, (w - 8, _END_H // 2, 8, h))
        pygame.draw.ellipse(surf, _BARK_DARK, (w - 8, h - 1, 8, _END_H))
        top_rect = pygame.Rect(0, 0, w, _END_H)
        pygame.draw.ellipse(surf, top, top_rect)
        for i in range(1, rings + 1):
            f = i / (rings + 1)
            pygame.draw.ellipse(surf, ring, top_rect.inflate(-w * f, -_END_H * f), 1)
        pygame.draw.ellipse(surf, _BARK_DARK, top_rect, 2)
        pygame.draw.lines(surf, _OUTLINE, False, [(0, _END_H // 2), (0, h + _END_H // 2)], 1)
        pygame.draw.lines(surf, _OUTLINE, False, [(w - 1, _END_H // 2), (w - 1, h + _END_H // 2)], 1)
        return surf

    def _build_block(self) -> pygame.Surface:
        block = self._cylinder(_BLOCK_W, _BLOCK_H, _OLD_WOOD, _OLD_RING, 4)
        rng = random.Random(3)
        for _ in range(6):       # old cuts in its top
            x = rng.randrange(20, _BLOCK_W - 20)
            pygame.draw.line(block, _OLD_RING, (x - 8, rng.randrange(3, _END_H - 3)), (x + 8, rng.randrange(3, _END_H - 3)), 1)
        return block

    def _build_log(self) -> pygame.Surface:
        return self._cylinder(_LOG_W, _LOG_H, _WOOD, _WOOD_RING, 3)

    def _build_halves(self) -> Tuple[pygame.Surface, pygame.Surface]:
        half = _LOG_W // 2
        left = self._log.subsurface((0, 0, half, self._log.get_height())).copy()
        right = self._log.subsurface((half, 0, _LOG_W - half, self._log.get_height())).copy()
        # The fresh split faces
        pygame.draw.rect(left, _WOOD_CUT, (half - 6, _END_H // 2, 6, _LOG_H))
        pygame.draw.rect(right, _WOOD_CUT, (0, _END_H // 2, 6, _LOG_H))
        return left, right

    def _build_glow(self) -> pygame.Surface:
        """A soft round glow, brightest in the middle, to be added over the scene."""
        size = _GLOW_RADIUS * 2
        glow = pygame.Surface((size, size))
        glow.fill((0, 0, 0))
        for r in range(_GLOW_RADIUS, 0, -2):
            k = (1 - r / _GLOW_RADIUS) ** 1.6
            pygame.draw.circle(glow, tuple(round(c * k) for c in _GLOW_COLOUR), (_GLOW_RADIUS, _GLOW_RADIUS), r)
        return glow

    # ------------------------------------------------------------------
    # The time of day
    # ------------------------------------------------------------------

    def set_time(self, when: Optional[datetime.datetime], weather: Optional[Conditions] = None) -> None:
        """Play the scene at that moment and in that weather (None: noon, clear)."""
        self.outdoors = Outdoors((SCENE_W, SCENE_H), _HORIZON_Y, when, weather,
                                 lamps=self._lantern_places(), rng=random.Random(self.rng.random()))
        self._background = self._build_background()       # snow may lie on its ground

    @property
    def lanterns(self) -> float:
        """How brightly the lanterns burn: 0 by day, 1 at night."""
        return self.outdoors.lamps

    @property
    def night(self) -> float:
        return self.outdoors.night

    @property
    def _lightmap(self) -> pygame.Surface:
        return self.outdoors.lightmap

    def _lantern_places(self) -> List[Tuple[Tuple[int, int], int]]:
        """Each lantern's light: its middle and how far it reaches."""
        return [((_POST_LANTERN[0], _POST_LANTERN[1] + 12), 250), ((_BEAM_LANTERN[0], _BEAM_LANTERN[1] + 12), 330)]

    def _draw_lanterns(self, surf: pygame.Surface) -> None:
        """The lanterns themselves, unlit glass by day; the post's on an iron arm, the beam's on a chain."""
        ax, ay = _POST_LANTERN
        post_left = POWER_RECT.left - 16
        pygame.draw.line(surf, _IRON, (post_left, ay - 8), (ax, ay - 8), 3)          # the arm
        pygame.draw.line(surf, _IRON, (ax, ay - 8), (ax, ay - 2), 2)
        bx, by = _BEAM_LANTERN
        pygame.draw.line(surf, _IRON, (bx, _BEAM_Y + 22), (bx, by - 2), 2)            # the chain
        for y in range(_BEAM_Y + 24, by - 2, 5):
            pygame.draw.circle(surf, _IRON, (bx, y), 2, 1)
        for x, y in (_POST_LANTERN, _BEAM_LANTERN):
            pygame.draw.polygon(surf, _IRON, [(x - 8, y + 4), (x, y - 2), (x + 8, y + 4)])   # the cap
            body = pygame.Rect(x - 7, y + 4, 14, 18)
            pygame.draw.rect(surf, _LANTERN_GLASS, body)
            pygame.draw.rect(surf, _IRON, body, 2)
            pygame.draw.line(surf, _IRON, (x, y + 4), (x, y + 21), 1)
            pygame.draw.rect(surf, _IRON, (x - 8, y + 21, 16, 3))

    def _draw_lantern_flames(self, surf: pygame.Surface) -> None:
        """After the lighting: the lit glass, a small flickering flame and its halo."""
        if self.lanterns <= 0:
            return
        flicker = 0.9 + 0.1 * math.sin(pygame.time.get_ticks() / 90.0) * math.sin(pygame.time.get_ticks() / 37.0)
        for x, y in (_POST_LANTERN, _BEAM_LANTERN):
            glass = pygame.Rect(x - 5, y + 6, 10, 14)
            colour = tuple(round(_lerp(a, b, self.lanterns)) for a, b in zip(_LANTERN_GLASS, _LANTERN_GLASS_LIT))
            pygame.draw.rect(surf, colour, glass)
            pygame.draw.line(surf, _IRON, (x, y + 4), (x, y + 21), 1)
            pygame.draw.ellipse(surf, (255, 246, 210), (x - 2, y + 9 - flicker, 4, 7 + flicker))
            halo = self._lantern_glow.copy()
            k = round(255 * self.lanterns * flicker * 0.6)
            halo.fill((k, k, k), special_flags=pygame.BLEND_RGB_MULT)
            surf.blit(halo, halo.get_rect(center=(x, y + 13)), special_flags=pygame.BLEND_RGB_ADD)

    def _build_log_end(self) -> pygame.Surface:
        """A split log's end in the pile: a half disc of wood in bark."""
        d = _PILE_R * 2
        end = pygame.Surface((d + 2, d + 2), pygame.SRCALPHA)
        c = (_PILE_R + 1, _PILE_R + 1)
        pygame.draw.circle(end, _BARK, c, _PILE_R)
        pygame.draw.circle(end, _WOOD, c, _PILE_R - 3)
        pygame.draw.circle(end, _WOOD_RING, c, _PILE_R - 6, 1)
        pygame.draw.circle(end, _OUTLINE, c, _PILE_R, 1)
        return end

    # ------------------------------------------------------------------
    # The pose: everything follows the axe's angle
    # ------------------------------------------------------------------

    def _pose(self, axe: float) -> "_Pose":
        """Where every part is for the axe at that angle (degrees, 0 forward, 90 up)."""
        strike = getattr(self, "_strike_angle", 20.0)
        top = _REST_ANGLE + _WINDUP_EXTRA
        # Leaning back to lift, forward into the blow, further when it finds nothing
        lean = _interp(axe, [(_WHIFF_ANGLE, -15.0), (strike, -9.0), (_REST_ANGLE, -2.0), (top, 8.0)])
        # The front arm, shoulder to fist, in screen degrees
        arm = _interp(axe, [(_WHIFF_ANGLE, -78.0), (strike, -32.0), (_REST_ANGLE, -46.0),
                            (90.0, 50.0), (top, 128.0)])
        dy = self._player_dy()
        origin = pygame.Vector2(_PLAYER_LEFT, self._body_top + dy)
        hip = origin + self._torso.joint

        def lean_about_hip(joint: pygame.Vector2) -> pygame.Vector2:
            return hip + (origin + joint - hip).rotate(-lean)

        shoulder = lean_about_hip(self._front_shoulder)
        a = math.radians(arm)
        fist = shoulder + pygame.Vector2(math.cos(a), -math.sin(a)) * (_UPPER_ARM + _FOREARM) * _ARM_REACH
        if self.state == "charge" and self.charge_t > 0.85:          # straining at the top
            fist += pygame.Vector2(self.rng.uniform(-1, 1), self.rng.uniform(-1, 1)) * (self.charge_t - 0.85) * 8

        # The back hand reaches for the handle just behind the fist
        # The near hand takes the handle behind the fist, as far down it as it can reach
        near_shoulder = lean_about_hip(self._near_shoulder)
        u = pygame.Vector2(math.cos(math.radians(axe)), -math.sin(math.radians(axe)))
        reach = _NEAR_UPPER_ARM + _NEAR_FOREARM
        lo, hi = _NEAR_GRIP
        grips = [fist - u * (lo + (hi - lo) * i / 7) for i in range(8)]
        near_hand = next((g for g in reversed(grips) if g.distance_to(near_shoulder) <= reach),
                         min(grips, key=lambda g: g.distance_to(near_shoulder)))

        # Feet apart; wider as he throws his weight into the blow
        stance = _interp(axe, [(_WHIFF_ANGLE, 1.6), (strike, 1.3), (_REST_ANGLE, 1.0), (top, 0.7)])
        nod = -4.0 * min(1.0, self._squat / 4.0)
        return _Pose(
            lean=lean, origin=origin, hip=hip,
            neck=lean_about_hip(self._head.joint), head_angle=lean * 0.6 + nod,
            shoulder=shoulder, fist=fist, near_shoulder=near_shoulder, near_hand=near_hand,
            back_leg=-7.0 * stance, front_leg=6.0 * stance,
        )

    def _aim_at_log(self) -> Tuple[float, float]:
        """The axe's angle and length that bring its blade down on the log's top."""
        target = pygame.Vector2(_BLOCK_CX - 4, _LOG_TOP + _END_H / 2 - 24)
        angle, length = 20.0, 120.0
        for _ in range(6):   # the fist moves with the pose, which follows the angle
            self._strike_angle = angle
            d = target - self._pose(angle).fist
            angle = math.degrees(math.atan2(-d.y, d.x))
            length = d.length()
        return angle, length

    # ------------------------------------------------------------------
    # What the minigame tells it
    # ------------------------------------------------------------------

    @property
    def log_ready(self) -> bool:
        return self.log_drop <= 0.0

    @property
    def can_charge(self) -> bool:
        """Whether a new swing may be gathered (not while one is still landing)."""
        return self.state in ("idle", "recover", "charge")

    @property
    def settled(self) -> bool:
        """Nothing left moving: the swing is over and every chip has landed."""
        return (self.state == "idle" and not self.pieces and not self.particles
                and self.log_ready and self._popup is None and not self.motes)

    def charge(self, power: float) -> None:
        """Lift the axe for the power gathered so far (0..1)."""
        self.state = "charge"
        self.charge_t = _ease_out(max(0.0, min(1.0, power)))

    def swing(self, outcome: str, points: int = 0, color: Tuple[int, int, int] = (255, 255, 255),
              label: Optional[str] = None, flourish: int = 0) -> List[str]:
        """Bring the axe down; label is the popup over the log (by default the points),
        flourish 2 for a swing perfect on both gauges. Returns the sounds to play at
        once (a miss's swish)."""
        self.flourish = flourish
        if outcome == BITE and self.log_damage + 1 >= _BITES_TO_SPLIT:
            outcome = SPLIT
        if outcome in (SPLIT, BITE) and not self.log_ready:
            outcome = WHIFF            # the next log is not on the block yet
        self.outcome = outcome
        self.state = "swing"
        self._timer = 0.0
        self._trail = []
        self._swing_from = self.angle
        if outcome == WHIFF:
            self._swing_to = _WHIFF_ANGLE
        elif outcome == SHORT:
            self._swing_to = max(_SHORT_ANGLE, min(self.angle, _SHORT_ANGLE + 10))
        else:
            self._swing_to = self._strike_angle - (2.0 if outcome == BITE else 0.0)
        self._swing_s = _SHORT_SWING_S if outcome == SHORT else _SWING_S
        self.charge_t = 0.0
        if label is None:
            label = f"+{points}" if points > 0 else "miss"
        self._popup = (label, color, 0.0)
        return ["swoosh"] if outcome in (WHIFF, SHORT) else []

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update(self, dt: float) -> List[str]:
        """Advance the animation; returns the sounds to play now ("chop", "thud", "ring")."""
        if self._hitstop > 0:            # the perfect blow holds still for a heartbeat, the rain too
            self._hitstop -= dt
            return []
        sounds: List[str] = self.outdoors.update(dt)
        if self.state == "charge":
            target = _REST_ANGLE + _WINDUP_EXTRA * self.charge_t
            self.angle += (target - self.angle) * min(1.0, _FOLLOW_RATE * dt)
        elif self.state == "swing":
            self._timer += dt
            t = min(1.0, self._timer / self._swing_s)
            self._trail.append(self.angle)
            self._trail = self._trail[-4:]
            ease = _ease_out(t) if self.outcome == SHORT else _ease_in(t)
            self.angle = _lerp(self._swing_from, self._swing_to, ease)
            if t >= 1.0:
                self.state = "hold"
                self._timer = 0.0
                self._trail = []
                sounds += self._impact()
        elif self.state == "hold":
            self._timer += dt
            if self.outcome == SHORT:
                self.angle += (_SHORT_ANGLE - 8 - self.angle) * min(1.0, 6 * dt)
            if self._timer >= _HOLD_S[self.outcome]:
                self.state = "recover"
        elif self.state == "recover":
            self.angle += (_REST_ANGLE - self.angle) * min(1.0, _RECOVER_RATE * dt)
            if abs(self.angle - _REST_ANGLE) < 0.5:
                self.angle = _REST_ANGLE
                self.state = "idle"

        self._squat = max(0.0, self._squat - 30 * dt)
        self._shake = max(0.0, self._shake - dt)
        sounds += self._update_log(dt)
        self._update_pieces(dt)
        self._update_particles(dt)
        self._update_motes(dt)
        if self._glow_age is not None:
            self._glow_age += dt
            if self._glow_age >= _GLOW_S:
                self._glow_age = None
        if self._popup is not None:
            text, color, age = self._popup
            age += dt
            self._popup = None if age > 0.9 else (text, color, age)
        return sounds

    def _impact(self) -> List[str]:
        head = self._axe_head()
        if self.outcome == SPLIT:
            self._squat = 4.0
            self._shake = 0.16
            self._split_log()
            if self.flourish >= 2:
                self._hitstop = _HITSTOP_S
                self._shake = 0.22
                self._glow_age = 0.0
                self._release_motes()
                return ["chop", "ring"]
            return ["chop"]
        if self.outcome == BITE:
            self._squat = 3.0
            self.log_damage += 1
            self._chips(head.x, _LOG_TOP + _END_H / 2, 5, spread=0.7)
            return ["chop"]
        if self.outcome == WHIFF:
            self._squat = 5.0
            self._dust(head.x + 6, _FEET_Y + 2)
        return []

    def _split_log(self) -> None:
        x = _BLOCK_CX - _LOG_W / 2
        y = _LOG_TOP - _END_H / 2
        left, right = self._halves
        self.pieces.append(_Piece(left, x, y, -self.rng.uniform(150, 210), -self.rng.uniform(260, 340), self.rng.uniform(140, 220)))
        self.pieces.append(_Piece(right, x + _LOG_W // 2, y, self.rng.uniform(150, 210), -self.rng.uniform(260, 340), -self.rng.uniform(140, 220)))
        self._chips(_BLOCK_CX, _LOG_TOP + _END_H / 2, 14, spread=1.0)
        self.log_damage = 0
        self.pile += 1
        self.log_drop = SCENE_H          # the next log falls in from above
        self._log_vy = 0.0
        self._log_bounced = False

    def _chips(self, x: float, y: float, count: int, spread: float) -> None:
        for _ in range(count):
            angle = math.radians(self.rng.uniform(25, 155))
            speed = self.rng.uniform(140, 380) * spread
            color = self.rng.choice((_WOOD, _WOOD_CUT, _WOOD_RING, _BARK))
            self.particles.append(_Particle(
                x + self.rng.uniform(-8, 8), y, math.cos(angle) * speed, -math.sin(angle) * speed,
                self.rng.uniform(0.6, 1.0), self.rng.choice((2, 3, 3, 4)), color))

    def _release_motes(self) -> None:
        """Fine sawdust from the split, drifting up slowly and swaying, as if caught in the sun."""
        for _ in range(_MOTES):
            self.motes.append([
                _BLOCK_CX + self.rng.uniform(-30, 30), _LOG_TOP + self.rng.uniform(-6, 24),
                self.rng.uniform(-14, 14), -self.rng.uniform(16, 42),
                0.0, self.rng.uniform(1.2, 2.0), self.rng.uniform(0, math.tau)])

    def _update_motes(self, dt: float) -> None:
        for m in self.motes:
            m[4] += dt
            m[0] += (m[2] + 10 * math.sin(m[4] * 3 + m[6])) * dt
            m[1] += m[3] * dt
            m[3] *= 1 - min(1.0, 0.6 * dt)
        self.motes = [m for m in self.motes if m[4] < m[5]]

    def _dust(self, x: float, y: float) -> None:
        for _ in range(9):
            self.particles.append(_Particle(
                x + self.rng.uniform(-10, 10), y + self.rng.uniform(-4, 2),
                self.rng.uniform(-60, 60), -self.rng.uniform(10, 50),
                self.rng.uniform(0.5, 0.8), self.rng.uniform(4, 7), (176, 150, 112), grow=14.0, ground=None))

    def _update_log(self, dt: float) -> List[str]:
        if self.log_drop <= 0.0:
            return []
        # Wait for the halves to clear before the next log comes down
        if self.pieces and self.pieces[0].age < 0.25:
            return []
        self._log_vy += _GRAVITY * 1.6 * dt
        self.log_drop -= self._log_vy * dt
        if self.log_drop <= 0.0:
            if not self._log_bounced and self._log_vy > 300:
                self._log_bounced = True
                self.log_drop = 0.01
                self._log_vy = -self._log_vy * 0.18
                return ["thud"]
            self.log_drop = 0.0
            self._log_vy = 0.0
        return []

    def _update_pieces(self, dt: float) -> None:
        ground = _FEET_Y + 4
        for piece in self.pieces:
            piece.age += dt
            if not piece.landed:
                piece.vy += _GRAVITY * dt
                piece.x += piece.vx * dt
                piece.y += piece.vy * dt
                piece.angle += piece.spin * dt
                if piece.y + piece.surface.get_height() * 0.6 >= ground and piece.vy > 0:
                    piece.landed = True
                    piece.angle = 90.0 if piece.spin > 0 else -90.0
                    piece.y = ground - piece.surface.get_width() - 4
        self.pieces = [p for p in self.pieces if p.age < 1.1]

    def _update_particles(self, dt: float) -> None:
        for p in self.particles:
            p.age += dt
            if p.ground is None:          # dust: drifts and spreads
                p.x += p.vx * dt
                p.y += p.vy * dt
                p.vx *= 1 - min(1.0, 3 * dt)
                p.size += p.grow * dt
                continue
            if p.y < p.ground:
                p.vy += _GRAVITY * dt
                p.x += p.vx * dt
                p.y += p.vy * dt
                if p.y >= p.ground:
                    p.y = p.ground + self.rng.uniform(-6, 6)
        self.particles = [p for p in self.particles if p.age < p.life]

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def _player_dy(self) -> float:
        """The player rises a little on his toes lifting the axe, and dips on impact."""
        lift = -3.0 * self.charge_t if self.state == "charge" else 0.0
        return lift + self._squat

    def _axe_head(self) -> pygame.Vector2:
        a = math.radians(self.angle)
        return self._pose(self.angle).fist + pygame.Vector2(math.cos(a), -math.sin(a)) * self._axe_len

    def _axe_polys(self, angle: float):
        """The handle's and the head's polygons, and the blade's edge, for the axe at that angle."""
        fist = self._pose(angle).fist
        a = math.radians(angle)
        u = pygame.Vector2(math.cos(a), -math.sin(a))      # along the handle
        v = pygame.Vector2(math.sin(a), math.cos(a))       # towards the blade's edge
        if self.state == "hold" and self.outcome == BITE:
            fist = fist + v * _BITE_DEPTH * 0.5
        length = self._axe_len

        def p(du, dv):
            return fist + u * du + v * dv

        handle = [p(-_AXE_TAIL, -3), p(length + 6, -3), p(length + 6, 3), p(-_AXE_TAIL, 3)]
        edge = [p(length + 15 - 30 * i / 8, 25 + 5 * math.sin(math.pi * i / 8)) for i in range(9)]
        head = [p(length - 7, -9), p(length + 7, -9), p(length + 7, 5)] + edge + [p(length - 7, 5)]
        return handle, head, edge

    def _draw_axe(self, surf: pygame.Surface) -> None:
        if self._trail:
            self._overlay.fill((0, 0, 0, 0))
            for i, angle in enumerate(self._trail[-3:]):
                handle, head, _ = self._axe_polys(angle)
                pygame.draw.polygon(self._overlay, (*_HANDLE, 30 + 25 * i), handle)
                pygame.draw.polygon(self._overlay, (*_STEEL_EDGE, 45 + 30 * i), head)
            surf.blit(self._overlay, (0, 0))
        handle, head, edge = self._axe_polys(self.angle)
        pygame.draw.polygon(surf, _HANDLE, handle)
        pygame.draw.polygon(surf, _HANDLE_DARK, handle, 1)
        pygame.draw.polygon(surf, _STEEL, head)
        pygame.draw.lines(surf, _STEEL_EDGE, False, edge, 3)
        pygame.draw.polygon(surf, _STEEL_DARK, head[:3] + [head[-1]])
        pygame.draw.polygon(surf, _OUTLINE, head, 1)

    def _draw_pile(self, surf: pygame.Surface) -> None:
        """The split logs stacked behind the block, bottom row first, with a shadow under them."""
        shown = self.pile
        if shown:
            width = min(shown, _PILE_ROWS) * (_PILE_R * 2 - 1) + 10
            self._overlay.fill((0, 0, 0, 0))
            pygame.draw.ellipse(self._overlay, _SHADOW, (_PILE_LEFT - 5, _FEET_Y - 30, width, 12))
            surf.blit(self._overlay, (0, 0))
        row = 0
        while shown > 0 and row < _PILE_ROWS:
            in_row = _PILE_ROWS - row
            for i in range(min(in_row, shown)):
                x = _PILE_LEFT + i * (_PILE_R * 2 - 1) + row * _PILE_R
                y = _FEET_Y - 26 - _PILE_R * 2 - row * (_PILE_R * 2 - 3)
                surf.blit(self._pile_end, (x, y))
            shown -= in_row
            row += 1

    def _draw_shadow(self, surf: pygame.Surface, cx: float, w: float) -> None:
        self._overlay.fill((0, 0, 0, 0))
        pygame.draw.ellipse(self._overlay, _SHADOW, (cx - w / 2, _FEET_Y - 7, w, 14))
        surf.blit(self._overlay, (0, 0))

    def _draw_log(self, surf: pygame.Surface) -> None:
        if self.log_drop >= SCENE_H:
            return
        x = _BLOCK_CX - _LOG_W / 2
        y = _LOG_TOP - _END_H / 2 - self.log_drop
        surf.blit(self._log, (x, y))
        if self.log_damage:
            top = y + _END_H / 2
            cx = _BLOCK_CX - 4
            pygame.draw.lines(surf, _OUTLINE, False,
                              [(cx - 2, top - 3), (cx + 1, top + 1), (cx - 1, top + 10), (cx + 2, top + 22)], 2)

    def draw(self, underlay=None, overlay=None) -> pygame.Surface:
        """Draw the scene; underlay(surface) is called behind the block and the
        player (the aim's zones and plumb line), overlay(surface) over all of it."""
        surf = self._world
        surf.fill((0, 0, 0, 0))
        surf.blit(self._background, (0, 0))
        if underlay is not None:
            underlay(surf)
        surf.blit(self._foot_tufts["post"], (0, 0))
        self._draw_lanterns(surf)
        self._draw_pile(surf)
        self._draw_shadow(surf, _BLOCK_CX, _BLOCK_W + 10)
        self._draw_shadow(surf, _PLAYER_LEFT + self._body_w / 2, self._body_w * 0.75)

        behind_log = self.outcome == WHIFF and self.state in ("swing", "hold")
        if behind_log:
            self._draw_axe(surf)
        surf.blit(self._block, (_BLOCK_CX - _BLOCK_W / 2, _FEET_Y - _BLOCK_H - _END_H / 2))
        surf.blit(self._foot_tufts["block"], (0, 0))
        self._draw_log(surf)
        for piece in self.pieces:
            img = pygame.transform.rotate(piece.surface, piece.angle)
            alpha = 255 if piece.age < 0.7 else max(0, int(255 * (1.1 - piece.age) / 0.4))
            img.set_alpha(alpha)
            w, h = piece.surface.get_size()
            surf.blit(img, img.get_rect(center=(piece.x + w / 2, piece.y + h / 2)))
        if self._glow_age is not None:
            k = (1 - self._glow_age / _GLOW_S) ** 1.5
            glow = self._glow.copy()
            glow.fill((round(255 * k),) * 3, special_flags=pygame.BLEND_RGB_MULT)
            surf.blit(glow, glow.get_rect(center=(_BLOCK_CX, _LOG_TOP + 20)), special_flags=pygame.BLEND_RGB_ADD)
        self._draw_player(surf, axe_drawn=behind_log)

        self._draw_particles(surf)
        if self._near_tree is not None:
            tree, at = self._near_tree
            surf.blit(tree, at)
            surf.blit(self._foot_tufts["near"], (0, 0))
        self.outdoors.draw_weather(surf)
        self.outdoors.light(surf)
        frame = self.surface
        self.outdoors.compose(frame, surf)
        self._draw_lantern_flames(frame)
        surf = frame
        if self._popup is not None:
            text, color, age = self._popup
            face = self.font.render(text, True, color)
            rim = self.font.render(text, True, _OUTLINE)
            label = pygame.Surface((face.get_width() + 2, face.get_height() + 2), pygame.SRCALPHA)
            for offset in ((0, 1), (2, 1), (1, 0), (1, 2)):   # a thin dark rim, to read on trees and sky
                label.blit(rim, offset)
            label.blit(face, (1, 1))
            label.set_alpha(max(0, int(255 * (1 - max(0.0, age - 0.4) / 0.5))))
            surf.blit(label, label.get_rect(center=(_BLOCK_CX + 120, _LOG_TOP - 50 * _ease_out(min(1.0, age / 0.9)))))
        if overlay is not None:
            overlay(surf)
        return surf

    def _draw_player(self, surf: pygame.Surface, axe_drawn: bool) -> None:
        """Legs, axe and far arm behind the body, then the torso, the near arm and the head.

        The far arm (holding the axe at the fist) and the axe are always behind
        the body; the near arm (gripping the handle) always over the body and
        under the head.
        """
        pose = self._pose(self.angle)
        o = pose.origin
        self._back_leg.blit(surf, o + self._back_leg.joint, pose.back_leg)
        self._front_leg.blit(surf, o + self._front_leg.joint, pose.front_leg)
        if not axe_drawn:
            self._draw_axe(surf)
        self._draw_arm(surf, pose.shoulder, pose.fist, shade=0.86)   # over the axe, so its fist holds it
        self._torso.blit(surf, pose.hip, pose.lean)
        self._draw_arm(surf, pose.near_shoulder, pose.near_hand, _NEAR_UPPER_ARM, _NEAR_FOREARM)
        self._head.blit(surf, pose.neck, pose.head_angle)

    def _draw_arm(self, surf: pygame.Surface, shoulder: pygame.Vector2, hand: pygame.Vector2,
                  upper: float = _UPPER_ARM, forearm: float = _FOREARM,
                  shade: float = 1.0) -> None:
        """An arm from shoulder to hand, bent at the elbow, drawn as pixel art.

        The elbow is found by the two segments' lengths (it bends downwards); a
        hand beyond reach stretches the arm straight, which only the back arm,
        mostly hidden behind the body, ever needs. Drawn on the coarse layer and
        blown up without smoothing, so its pixels are the size of the sprite's.
        """
        px = _ARM_PX
        s, h = shoulder / px, hand / px
        a, b = upper / px, forearm / px
        d = h - s
        dist = d.length()
        if dist < 1e-6:
            elbow = s + pygame.Vector2(0, a)
        elif dist >= a + b:
            elbow = s + d * (a / (a + b))
        else:
            turn = math.degrees(math.acos(max(-1.0, min(1.0, (a * a + dist * dist - b * b) / (2 * a * dist)))))
            one = s + d.normalize().rotate(turn) * a
            two = s + d.normalize().rotate(-turn) * a
            elbow = one if one.y > two.y else two

        def col(c):
            return tuple(round(v * shade) for v in c)

        layer = self._arm_layer
        layer.fill((0, 0, 0, 0))
        cuff = h + (elbow - h) * min(1.0, 1.6 / max(1e-6, (elbow - h).length()))
        # Outline, then sleeve, a light seam along it, the cuff and the hand
        for width, colour in ((6, _ARM_OUTLINE), (4, _SLEEVE)):
            pygame.draw.line(layer, col(colour), s, elbow, width)
            pygame.draw.line(layer, col(colour), elbow, h, width - 1)
            pygame.draw.circle(layer, col(colour), elbow, width / 2)
            pygame.draw.circle(layer, col(colour), s, width / 2)
        pygame.draw.line(layer, col(_SLEEVE_DARK), elbow + pygame.Vector2(0, 1), h + pygame.Vector2(0, 1), 1)
        pygame.draw.line(layer, col(_SLEEVE_LIGHT), s + pygame.Vector2(0, -1), elbow + pygame.Vector2(0, -1), 1)
        pygame.draw.line(layer, col(_CUFF), cuff, h, 3)
        pygame.draw.circle(layer, col(_ARM_OUTLINE), h, 2.6)
        pygame.draw.circle(layer, col(_SKIN), h, 1.7)
        pygame.draw.circle(layer, col(_SKIN_LIGHT), h + pygame.Vector2(-0.5, -0.6), 0.7)
        surf.blit(pygame.transform.scale(layer, (layer.get_width() * px, layer.get_height() * px)), (0, 0))

    def _draw_particles(self, surf: pygame.Surface) -> None:
        if self.motes:
            self._overlay.fill((0, 0, 0, 0))
            for x, y, _, _, age, life, phase in self.motes:
                fade = min(1.0, age / 0.2) * (1 - age / life)
                twinkle = 0.7 + 0.3 * math.sin(age * 9 + phase)
                pygame.draw.circle(self._overlay, (*_MOTE_COLOUR, int(235 * fade * twinkle)), (x, y), 2.2)
            surf.blit(self._overlay, (0, 0))
        dust = [p for p in self.particles if p.ground is None]
        if dust:
            self._overlay.fill((0, 0, 0, 0))
            for p in dust:
                alpha = int(110 * (1 - p.age / p.life))
                pygame.draw.circle(self._overlay, (*p.color, alpha), (p.x, p.y), p.size)
            surf.blit(self._overlay, (0, 0))
        for p in self.particles:
            if p.ground is None:
                continue
            if p.age > p.life - 0.25:
                continue    # chips vanish at the end, too small to fade
            surf.fill(p.color, (round(p.x), round(p.y), p.size, max(2, p.size - 1)))

    @property
    def shake_offset(self) -> Tuple[int, int]:
        if self._shake <= 0:
            return 0, 0
        k = self._shake / 0.16
        return round(self.rng.uniform(-3, 3) * k), round(self.rng.uniform(-2, 2) * k)
