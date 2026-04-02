"""Animated loading screen shown before the game initializes."""

import os
import random
import time
import pygame
from ..config.constants import FONTS_PATH
from ..config.colors import BEIGE, DARK_BROWN

_PLAYER_DIR = os.path.join('assets', 'map_sprites')
_PLAYER_SPRITES = [
    'player_right_static.png',
    'player_right_move1.png',
    'player_right_move2.png',
    'player_right_move1.png',
]

_SHEEP_DIR = os.path.join('assets', 'map_sprites', 'figurines', 'sheep')
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
_FRAME_MS = 150
_DOT_CYCLE_TICKS = 3


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

    if random.random() < 0.5:
        sprite_dir, sprite_names = _PLAYER_DIR, _PLAYER_SPRITES
    else:
        sprite_dir, sprite_names = _SHEEP_DIR, _SHEEP_SPRITES

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

        screen.fill(BEIGE)

        if sprites:
            sprite = sprites[frame_idx]
            screen.blit(sprite, sprite.get_rect(center=(cx, cy - 50)))

        dots = '.' * dot_count
        text_surf = font.render(f"Loading{dots}", True, DARK_BROWN)
        screen.blit(text_surf, text_surf.get_rect(center=(cx, cy + 50)))

        pygame.display.flip()
