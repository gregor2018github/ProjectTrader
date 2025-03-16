import pygame
from ..config.colors import LIGHT_BLUE, BLACK

class DepotViewDetail:
    def __init__(self, depot_rect):
        # Place the detail panel just to the right of depot view
        self.rect = pygame.Rect(depot_rect.right + 10, depot_rect.top, 300, depot_rect.height)
        self.visible = False

    def toggle(self):
        self.visible = not self.visible

    def draw(self, screen, font):
        if self.visible:
            pygame.draw.rect(screen, LIGHT_BLUE, self.rect)
            lorem = "Lorem ipsum dolor sit amet, consectetur adipiscing elit."
            text_surf = font.render(lorem, True, BLACK)
            screen.blit(text_surf, (self.rect.x + 10, self.rect.y + 10))
