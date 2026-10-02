"""Animated loading screen shown before the game initializes."""

import os
import random
import time
import pygame
from ..config.constants import FONTS_PATH
from .paper import draw_paper
from .layout_modules.town_plan.style import INK, INK_FADED

_LIGHT_PAPER = (243, 233, 204)

_PLAYER_DIR = os.path.join('assets', 'map_sprites', 'figurines', 'humans', 'player')
_PLAYER_SPRITES = [
    'player_right_static.png',
    'player_right_move1.png',
    'player_right_move2.png',
    'player_right_move1.png',
]

_SHEEP_DIR = os.path.join('assets', 'map_sprites', 'figurines', 'animals', 'sheep')
_SHEEP_SPRITES = [
    'sheep_right_static.png',
    'sheep_right_move1.png',
    'sheep_right_move2.png',
    'sheep_right_move3.png',
    'sheep_right_move4.png',
    'sheep_right_move3.png',
    'sheep_right_move2.png',
    'sheep_right_move1.png',
]

# Any NPC with at least this many frames walking right joins the draw.
_NPC_ROOT = os.path.join('assets', 'map_sprites', 'figurines', 'humans', 'npcs')
_NPC_MIN_WALK_FRAMES = 4

_FRAME_MS = 150
_DOT_CYCLE_TICKS = 3


def _npc_walk_cycles() -> list[tuple[str, list[str]]]:
    """Find every NPC with enough right-walk frames for the animation.

    The prefix is read off the ``<prefix>_right_move1.png`` file in each
    sprite folder, and the frames are counted up from there as the game
    does (``move1``, ``move2``, ... until one is missing).

    Returns:
        list: ``(sprite_dir, frame filenames)`` per qualifying NPC.
    """
    cycles = []
    try:
        folders = sorted(os.listdir(_NPC_ROOT))
    except OSError:
        return cycles
    for folder in folders:
        sprite_dir = os.path.join(_NPC_ROOT, folder)
        if not os.path.isdir(sprite_dir):
            continue
        for name in os.listdir(sprite_dir):
            if not name.endswith('_right_move1.png'):
                continue
            prefix = name[:-len('_right_move1.png')]
            frames = []
            index = 1
            while os.path.exists(os.path.join(sprite_dir, f"{prefix}_right_move{index}.png")):
                frames.append(f"{prefix}_right_move{index}.png")
                index += 1
            if len(frames) >= _NPC_MIN_WALK_FRAMES:
                cycles.append((sprite_dir, frames))
            break
    return cycles


def _draw_rules(surface: pygame.Surface) -> None:
    """A fine double rule round the sheet, knotted at the corners."""
    rect = surface.get_rect()
    outer = rect.inflate(-76, -76)
    inner = rect.inflate(-90, -90)
    pygame.draw.rect(surface, INK, outer, 2)
    pygame.draw.rect(surface, INK_FADED, inner, 1)

    # A small lozenge halfway along each side, sitting on the rules
    for cx, cy in ((outer.centerx, outer.top), (outer.centerx, outer.bottom),
                   (outer.left, outer.centery), (outer.right, outer.centery)):
        diamond = [(cx - 9, cy), (cx, cy - 9), (cx + 9, cy), (cx, cy + 9)]
        pygame.draw.polygon(surface, _LIGHT_PAPER, diamond)
        pygame.draw.polygon(surface, INK, diamond, 1)
        pygame.draw.circle(surface, INK, (cx, cy), 2)

    # A ringed knot at each corner, between the two rules
    for corner in (outer.topleft, outer.topright, outer.bottomleft, outer.bottomright):
        cx = corner[0] + (4 if corner[0] == outer.left else -4)
        cy = corner[1] + (4 if corner[1] == outer.top else -4)
        pygame.draw.circle(surface, _LIGHT_PAPER, (cx, cy), 13)
        pygame.draw.circle(surface, INK, (cx, cy), 13, 2)
        pygame.draw.circle(surface, INK_FADED, (cx, cy), 8, 1)
        pygame.draw.circle(surface, INK, (cx, cy), 3)


def _draw_flourish(surface: pygame.Surface, center: tuple[int, int], half_width: int) -> None:
    """A rule with a lozenge in its middle, fading towards its ends."""
    cx, cy = center
    for side in (-1, 1):
        pygame.draw.line(surface, INK_FADED, (cx + side * 12, cy), (cx + side * half_width, cy))
        pygame.draw.line(surface, INK_FADED, (cx + side * 20, cy + 4), (cx + side * half_width * 0.7, cy + 4))
        pygame.draw.circle(surface, INK, (cx + side * half_width, cy), 2)
    pygame.draw.polygon(surface, INK, [(cx - 8, cy), (cx, cy - 5), (cx + 8, cy), (cx, cy + 5)])


def _background(size: tuple[int, int], flourish_y: int) -> pygame.Surface:
    """Paper, rules and flourish: everything that does not move."""
    surface = pygame.Surface(size).convert()
    rect = surface.get_rect()
    draw_paper(surface, rect, rect.topleft)
    _draw_rules(surface)
    _draw_flourish(surface, (rect.centerx, flourish_y), 130)
    return surface


def run_loading_screen(screen: pygame.Surface, duration: float = 3.0) -> None:
    """Show an animated loading screen for *duration* seconds.

    Args:
        screen: The current pygame display surface.
        duration: Minimum number of seconds to display the animation.
    """
    clock = pygame.time.Clock()

    try:
        font = pygame.font.Font(os.path.join(FONTS_PATH, "RomanAntique.ttf"), 36)
    except Exception:
        font = pygame.font.SysFont("serif", 36)

    candidates = [(_PLAYER_DIR, _PLAYER_SPRITES), (_SHEEP_DIR, _SHEEP_SPRITES)]
    candidates += _npc_walk_cycles()
    sprite_dir, sprite_names = random.choice(candidates)

    target_height = 128
    sprites: list[pygame.Surface] = []
    for name in sprite_names:
        path = os.path.join(sprite_dir, name)
        try:
            img = pygame.image.load(path).convert_alpha()
            w, h = img.get_size()
            new_w = max(1, int(w * target_height / h))
            sprites.append(pygame.transform.scale(img, (new_w, target_height)))
        except Exception:
            pass

    sw, sh = screen.get_size()
    cx, cy = sw // 2, sh // 2
    background = _background((sw, sh), cy + 84)

    frame_idx = 0
    dot_count = 1
    frame_timer = 0
    dot_timer = 0
    tick_count = 0
    start = time.monotonic()

    while time.monotonic() - start < duration:
        dt = clock.tick(30)
        frame_timer += dt
        dot_timer += dt

        if frame_timer >= _FRAME_MS:
            frame_timer -= _FRAME_MS
            tick_count += 1
            frame_idx = tick_count % max(len(sprites), 1)

        if dot_timer >= 400:
            dot_timer -= 400
            dot_count = dot_count % 3 + 1

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return

        screen.blit(background, (0, 0))

        if sprites:
            sprite = sprites[frame_idx]
            screen.blit(sprite, sprite.get_rect(center=(cx, cy - 50)))

        dots = '.' * dot_count
        # Placed by the bare word, so the dots do not shift it
        word = font.render("Loading", True, INK)
        text_surf = font.render(f"Loading{dots}", True, INK)
        screen.blit(text_surf, word.get_rect(center=(cx, cy + 50)))

        pygame.display.flip()
