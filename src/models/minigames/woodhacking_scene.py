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

The player's sprite is cut into head, torso, two arms and two legs (``_HEAD``,
``_FRONT_ARM`` and so on), each turned about its joint every frame: the whole
pose follows the axe's angle (``_pose``), leaning back to lift it, throwing
the weight forward into the blow, the back hand reaching for the handle. Nothing here touches the game: the
minigame tells the scene what happened and plays the sounds the scene's
``update`` asks for, at the moment of impact.
"""

import math
import os
import random
from typing import List, Optional, Tuple

import pygame

from ..figurines.humans.human import HUMAN_SPRITE_ROOT

SPLIT, BITE, WHIFF, SHORT = "split", "bite", "whiff", "short"

SCENE_W, SCENE_H = 560, 484
_FEET_Y = 410                       # where the player, block and pile stand
_HORIZON_Y = 330

# The player: the right-facing standing sprite, scaled to this height and cut
# into parts that move on their own. Rects and joints are in the sprite's own
# pixels (208 x 336); each part turns about its joint.
_PLAYER_FILE = os.path.join(HUMAN_SPRITE_ROOT, "player", "player_right_static.png")
_PLAYER_H = 230
_PLAYER_LEFT = 92
_HEAD = pygame.Rect(0, 0, 208, 172)
_HEAD_CLEAR = pygame.Rect(0, 0, 208, 168)        # the torso keeps the chin's last rows under the head
_NECK = (108, 170)
_BACK_ARM = pygame.Rect(26, 172, 38, 92)
_BACK_SHOULDER = (58, 188)
_BACK_HAND = (48, 246)
_FRONT_ARM = pygame.Rect(147, 176, 61, 112)
_FRONT_SHOULDER = (154, 190)
_FIST = (186, 266)
_BACK_LEG = pygame.Rect(40, 286, 66, 50)
_FRONT_LEG = pygame.Rect(106, 286, 54, 50)
_LEGS_CLEAR = pygame.Rect(40, 290, 108, 46)      # the torso keeps the legs' top rows as an overlap
_BACK_HIP = (80, 290)
_FRONT_HIP = (130, 290)
_HIP = (105, 290)                                # the torso leans about this

# The chopping block and the log standing on it
_BLOCK_CX = 352
_BLOCK_W, _BLOCK_H = 118, 36
_LOG_W, _LOG_H = 62, 60
_LOG_TOP = _FEET_Y - _BLOCK_H - _LOG_H
_END_H = 14                          # height of the cut ends' ellipses

# The axe, in degrees: 0 points forward, 90 straight up (screen counter-clockwise)
_REST_ANGLE = 32.0
_WINDUP_EXTRA = 138.0               # how far back full power lifts it
_WHIFF_ANGLE = -24.0
_SHORT_ANGLE = 50.0
_AXE_TAIL = 14                      # handle sticking out behind the fist
_BITE_DEPTH = 7                     # how far a biting blade sinks into the log

# Timings, seconds
_SWING_S = 0.11
_SHORT_SWING_S = 0.2
_HOLD_S = {SPLIT: 0.14, BITE: 0.34, WHIFF: 0.18, SHORT: 0.12}
_FOLLOW_RATE = 16.0                 # how fast the axe follows the gathered power
_RECOVER_RATE = 9.0                 # and goes back to rest after a swing
_BITES_TO_SPLIT = 2

_GRAVITY = 1500.0
_PILE_ROWS = 6                      # the pile: 6 + 5 + ... + 1 split logs at most
_PILE_LEFT, _PILE_R = 436, 11

# Colours
_SKY_TOP, _SKY_LOW = (214, 205, 176), (236, 226, 194)
_HILLS = (176, 172, 128)
_GRASS, _GRASS_DARK = (128, 140, 82), (104, 118, 66)
_DIRT, _DIRT_DARK = (150, 118, 80), (122, 94, 62)
_BARK, _BARK_DARK, _BARK_LIGHT = (108, 76, 48), (78, 54, 34), (134, 98, 64)
_WOOD, _WOOD_RING, _WOOD_CUT = (222, 186, 128), (184, 140, 86), (238, 210, 160)
_OLD_WOOD, _OLD_RING = (176, 150, 112), (140, 114, 80)
_STEEL, _STEEL_EDGE, _STEEL_DARK = (148, 150, 156), (214, 216, 222), (92, 94, 100)
_HANDLE, _HANDLE_DARK = (160, 112, 62), (96, 64, 34)
_OUTLINE = (44, 32, 22)
_SHADOW = (0, 0, 0, 60)


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
    __slots__ = ("lean", "origin", "hip", "neck", "head_angle", "shoulder", "front_arm", "fist",
                 "back_shoulder", "back_arm", "back_leg", "front_leg")

    def __init__(self, **values) -> None:
        for name, value in values.items():
            setattr(self, name, value)


class ChoppingScene:
    """The player at the chopping block, animated by the minigame's swings."""

    def __init__(self, font: pygame.font.Font, rng: Optional[random.Random] = None) -> None:
        self.font = font
        self.rng = rng or random.Random()
        self.surface = pygame.Surface((SCENE_W, SCENE_H))
        self._overlay = pygame.Surface((SCENE_W, SCENE_H), pygame.SRCALPHA)

        self._build_player()
        self._background = self._build_background()
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

        # Where the axe lands on the log, worked out from the fist at the strike
        self._strike_angle, self._axe_len = self._aim_at_log()

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
        self._back_arm = part(_BACK_ARM, _BACK_SHOULDER)
        self._front_arm = part(_FRONT_ARM, _FRONT_SHOULDER)
        self._back_leg = part(_BACK_LEG, _BACK_HIP)
        self._front_leg = part(_FRONT_LEG, _FRONT_HIP)

        torso = full.copy()
        for rect in (_HEAD_CLEAR, _BACK_ARM, _FRONT_ARM, _LEGS_CLEAR):
            torso.fill((0, 0, 0, 0), sc(rect))
        hip = pygame.Vector2(_HIP[0] * scale, _HIP[1] * scale)
        self._torso = _Part(torso, hip - pygame.Vector2(torso.get_rect().center), hip)

        # The arms' rest directions, shoulder to hand, in screen degrees (0 forward, 90 up)
        def direction(a, b):
            return math.degrees(math.atan2(-(b[1] - a[1]), b[0] - a[0]))

        self._front_rest_dir = direction(_FRONT_SHOULDER, _FIST)
        self._back_rest_dir = direction(_BACK_SHOULDER, _BACK_HAND)
        self._front_arm_len = math.dist(_FRONT_SHOULDER, _FIST) * scale
        self._body_top = _FEET_Y - _PLAYER_H

    def _build_background(self) -> pygame.Surface:
        bg = pygame.Surface((SCENE_W, SCENE_H))
        for y in range(_HORIZON_Y + 10):
            t = y / (_HORIZON_Y + 10)
            bg.fill(tuple(round(_lerp(a, b, t)) for a, b in zip(_SKY_TOP, _SKY_LOW)), (0, y, SCENE_W, 1))

        # Low hills on the horizon
        hills = [(0, _HORIZON_Y)]
        for x in range(0, SCENE_W + 20, 20):
            hills.append((x, _HORIZON_Y - 18 - 14 * math.sin(x / 70.0) - 8 * math.sin(x / 23.0 + 1)))
        hills.append((SCENE_W, _HORIZON_Y + 10))
        hills.append((0, _HORIZON_Y + 10))
        pygame.draw.polygon(bg, _HILLS, hills)

        # Two trees from the map, a little hazy with distance
        trees = os.path.join(os.path.dirname(os.path.dirname(HUMAN_SPRITE_ROOT)), "trees")
        for name, height, x in (("Tree_02.png", 190, -30), ("Tree_05.png", 160, 70), ("Tree_01.png", 230, 430)):
            path = os.path.join(trees, name)
            if not os.path.exists(path):
                continue
            tree = _load_alpha(path)
            w = round(tree.get_width() * height / tree.get_height())
            tree = pygame.transform.smoothscale(tree, (w, height))
            tree.fill((34, 34, 26, 0), special_flags=pygame.BLEND_RGBA_ADD)   # paler with distance
            bg.blit(tree, (x, _HORIZON_Y + 30 - height))

        # The ground, with a trodden patch of dirt round the block
        bg.fill(_GRASS, (0, _HORIZON_Y + 10, SCENE_W, SCENE_H))
        rng = random.Random(7)
        for _ in range(260):
            x = rng.randrange(SCENE_W)
            y = rng.randrange(_HORIZON_Y + 14, SCENE_H)
            pygame.draw.line(bg, _GRASS_DARK, (x, y), (x + rng.choice((-1, 0, 1)), y - 3))
        pygame.draw.ellipse(bg, _DIRT, (120, _FEET_Y - 34, 330, 70))
        pygame.draw.ellipse(bg, _DIRT_DARK, (140, _FEET_Y - 26, 290, 54), 2)
        for _ in range(40):
            x = rng.randrange(150, 420)
            y = rng.randrange(_FEET_Y - 22, _FEET_Y + 26)
            pygame.draw.circle(bg, _DIRT_DARK, (x, y), 1)
        return bg

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

    def _build_log_end(self) -> pygame.Surface:
        """A split log's end in the pile: a half disc of wood in bark."""
        d = _PILE_R * 2
        end = pygame.Surface((d + 2, d + 2), pygame.SRCALPHA)
        c = (_PILE_R + 1, _PILE_R + 1)
        pygame.draw.circle(end, _BARK, c, _PILE_R)
        pygame.draw.circle(end, _WOOD, c, _PILE_R - 3)
        pygame.draw.circle(end, _WOOD_RING, c, _PILE_R - 7, 1)
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
                            (90.0, 40.0), (top, 96.0)])
        dy = self._player_dy()
        origin = pygame.Vector2(_PLAYER_LEFT, self._body_top + dy)
        hip = origin + self._torso.joint

        def lean_about_hip(joint: pygame.Vector2) -> pygame.Vector2:
            return hip + (origin + joint - hip).rotate(-lean)

        shoulder = lean_about_hip(self._front_arm.joint)
        a = math.radians(arm)
        fist = shoulder + pygame.Vector2(math.cos(a), -math.sin(a)) * self._front_arm_len
        if self.state == "charge" and self.charge_t > 0.85:          # straining at the top
            fist += pygame.Vector2(self.rng.uniform(-1, 1), self.rng.uniform(-1, 1)) * (self.charge_t - 0.85) * 8

        # The back hand reaches for the handle just behind the fist
        back_shoulder = lean_about_hip(self._back_arm.joint)
        u = pygame.Vector2(math.cos(math.radians(axe)), -math.sin(math.radians(axe)))
        grip = fist - u * 9
        to_grip = grip - back_shoulder
        back_arm = math.degrees(math.atan2(-to_grip.y, to_grip.x)) if to_grip.length() > 1 else self._back_rest_dir

        # Feet apart; wider as he throws his weight into the blow
        stance = _interp(axe, [(_WHIFF_ANGLE, 1.6), (strike, 1.3), (_REST_ANGLE, 1.0), (top, 0.7)])
        nod = -4.0 * min(1.0, self._squat / 4.0)
        return _Pose(
            lean=lean, origin=origin, hip=hip,
            neck=lean_about_hip(self._head.joint), head_angle=lean * 0.6 + nod,
            shoulder=shoulder, front_arm=arm - self._front_rest_dir, fist=fist,
            back_shoulder=back_shoulder, back_arm=back_arm - self._back_rest_dir,
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
                and self.log_ready and self._popup is None)

    def charge(self, power: float) -> None:
        """Lift the axe for the power gathered so far (0..1)."""
        self.state = "charge"
        self.charge_t = _ease_out(max(0.0, min(1.0, power)))

    def swing(self, outcome: str, points: int = 0, color: Tuple[int, int, int] = (255, 255, 255)) -> List[str]:
        """Bring the axe down. Returns the sounds to play at once (a miss's swish)."""
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
        self._popup = (f"+{points}" if points > 0 else "miss", color, 0.0)
        return ["swoosh"] if outcome in (WHIFF, SHORT) else []

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update(self, dt: float) -> List[str]:
        """Advance the animation; returns the sounds to play now ("chop", "thud")."""
        sounds: List[str] = []
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
        shown = self.pile
        row, placed = 0, 0
        while shown > 0 and row < _PILE_ROWS:
            in_row = _PILE_ROWS - row
            for i in range(min(in_row, shown)):
                x = _PILE_LEFT + i * (_PILE_R * 2 - 1) + row * _PILE_R
                y = _FEET_Y - 26 - _PILE_R * 2 - row * (_PILE_R * 2 - 3)
                surf.blit(self._pile_end, (x, y))
                placed += 1
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

    def draw(self) -> pygame.Surface:
        surf = self.surface
        surf.blit(self._background, (0, 0))
        self._draw_pile(surf)
        self._draw_shadow(surf, _BLOCK_CX, _BLOCK_W + 10)
        self._draw_shadow(surf, _PLAYER_LEFT + self._body_w / 2, self._body_w * 0.75)

        behind_log = self.outcome == WHIFF and self.state in ("swing", "hold")
        if behind_log:
            self._draw_axe(surf)
        surf.blit(self._block, (_BLOCK_CX - _BLOCK_W / 2, _FEET_Y - _BLOCK_H - _END_H / 2))
        self._draw_log(surf)
        for piece in self.pieces:
            img = pygame.transform.rotate(piece.surface, piece.angle)
            alpha = 255 if piece.age < 0.7 else max(0, int(255 * (1.1 - piece.age) / 0.4))
            img.set_alpha(alpha)
            w, h = piece.surface.get_size()
            surf.blit(img, img.get_rect(center=(piece.x + w / 2, piece.y + h / 2)))
        self._draw_player(surf, axe_drawn=behind_log)

        self._draw_particles(surf)
        if self._popup is not None:
            text, color, age = self._popup
            label = self.font.render(text, True, color)
            label.set_alpha(max(0, int(255 * (1 - max(0.0, age - 0.4) / 0.5))))
            surf.blit(label, label.get_rect(center=(_BLOCK_CX + 50, _LOG_TOP - 30 - 50 * _ease_out(min(1.0, age / 0.9)))))
        return surf

    def _draw_player(self, surf: pygame.Surface, axe_drawn: bool) -> None:
        """Legs, back arm, torso, head and front arm, each turned about its joint.

        Lifted back past the vertical, the axe goes behind the torso and head;
        the front fist is always drawn last, so it holds the handle.
        """
        pose = self._pose(self.angle)
        o = pose.origin
        self._back_leg.blit(surf, o + self._back_leg.joint, pose.back_leg)
        self._front_leg.blit(surf, o + self._front_leg.joint, pose.front_leg)
        self._back_arm.blit(surf, pose.back_shoulder, pose.back_arm)
        axe_behind = not axe_drawn and self.angle > 95.0
        if axe_behind:
            self._draw_axe(surf)
        self._torso.blit(surf, pose.hip, pose.lean)
        self._head.blit(surf, pose.neck, pose.head_angle)
        if not axe_drawn and not axe_behind:
            self._draw_axe(surf)
        self._front_arm.blit(surf, pose.shoulder, pose.front_arm)

    def _draw_particles(self, surf: pygame.Surface) -> None:
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
