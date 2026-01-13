import pygame
from typing import Optional
from ...config.colors import BEIGE, DARK_BROWN, TAN

def draw_depot_chart(screen: pygame.Surface, rect: pygame.Rect) -> None:
    """Draws the depot chart view.
    
    Currently an empty plane as requested.

    Args:
        screen: The pygame surface to draw on.
        rect: The area where the chart should be drawn.
    """
    pygame.draw.rect(screen, BEIGE, rect)
    pygame.draw.rect(screen, TAN, rect, 10)
    pygame.draw.rect(screen, DARK_BROWN, rect, 2)
