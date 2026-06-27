"""Module for displaying population statistics.

This module provides the PopulationStats class which shows an overview
of the town's population, including total population, average happiness,
and detailed stats for each population class.
"""

import pygame
import os
from typing import Optional, Tuple, Dict, TYPE_CHECKING
from ...config.colors import (
    BLACK, WHITE, DARK_BROWN, SANDY_BROWN, BEIGE, DARK_GRAY, LIGHT_GRAY,
    GOLD, DARK_GREEN, DARK_RED, WHEAT
)
from ...config.constants import (
    SCREEN_WIDTH, SCREEN_HEIGHT, SIDEBAR_WIDTH, PICTURES_PATH, FONTS_PATH
)
from ..ui_utils import draw_9slice

if TYPE_CHECKING:
    from ...game_state import GameState
    from ...models.institutions.town import Town


POP_TYPES = ["Poor", "Commons", "Middling Sort", "Nobility"]
COLS = 2


class PopulationStats:
    """A large overlay window displaying population statistics."""

    def __init__(self, screen: pygame.Surface, game_state: 'GameState', house: 'Town') -> None:
        self.screen = screen
        self.game_state = game_state
        self.town = house

        # Fonts --------------------------------------------------------
        try:
            self.title_font = pygame.font.Font(
                os.path.join(FONTS_PATH, "Medici Text.ttf"), 36
            )
            self.heading_font = pygame.font.Font(
                os.path.join(FONTS_PATH, "Augusta.ttf"), 28
            )
            self.body_font = pygame.font.Font(
                os.path.join(FONTS_PATH, "Augusta.ttf"), 22
            )
        except Exception:
            self.title_font = pygame.font.SysFont("arial", 30)
            self.heading_font = pygame.font.SysFont("arial", 24)
            self.body_font = pygame.font.SysFont("arial", 18)

        # Panel dimensions ---------------------------------------------
        total_w = SCREEN_WIDTH + SIDEBAR_WIDTH
        panel_w = int(total_w * 0.42)
        panel_h = int(SCREEN_HEIGHT * 0.62)
        self.panel_rect = pygame.Rect(
            (total_w - panel_w) // 2,
            (SCREEN_HEIGHT - panel_h) // 2,
            panel_w,
            panel_h,
        )

        # Close button --------------------------------------------------
        cb_size = 28
        self.close_rect = pygame.Rect(
            self.panel_rect.right - cb_size - 8,
            self.panel_rect.top + 8,
            cb_size,
            cb_size,
        )

        # Cell layout ---------------------------------------------------
        self.header_h = 120  # space for title and total stats
        cell_area_top = self.panel_rect.top + self.header_h
        cell_area_h = self.panel_rect.height - self.header_h - 20  # bottom pad
        cell_area_w = self.panel_rect.width - 40  # side padding (20 each)

        rows = (len(POP_TYPES) + COLS - 1) // COLS
        self.cell_w = cell_area_w // COLS
        self.cell_h = cell_area_h // rows
        self.cell_origin_x = self.panel_rect.x + 20
        self.cell_origin_y = cell_area_top

        # Pre-load pictograms -------------------------------------------
        self.pictograms: Dict[str, Optional[pygame.Surface]] = {}
        for pop_type in POP_TYPES:
            filename = f"pictogram_{pop_type.lower().replace(' ', '_')}.png"
            path = os.path.join(PICTURES_PATH, filename)
            if os.path.isfile(path):
                try:
                    img = pygame.image.load(path).convert_alpha()
                    # Scale image to fit nicely in the cell
                    target_size = min(self.cell_w - 60, self.cell_h - 120)
                    if target_size > 0:
                        img = pygame.transform.smoothscale(img, (target_size, target_size))
                    self.pictograms[pop_type] = img
                except Exception:
                    self.pictograms[pop_type] = None
            else:
                self.pictograms[pop_type] = None

    def handle_click(self, pos: Tuple[int, int]) -> Optional[bool]:
        """Handle a mouse click.

        Returns ``True`` when the click was consumed (close button or
        click outside the panel).
        """
        # Close button
        if self.close_rect.collidepoint(pos):
            self._close()
            return True

        # Click outside panel closes it
        if not self.panel_rect.collidepoint(pos):
            self._close()
            return True

        return True

    def _close(self) -> None:
        """Trigger the fade-out and clear references."""
        gs = self.game_state
        gs.menu_fade_window = self
        gs.menu_fade_timer = gs.menu_fade_duration
        gs.info_window = None
        gs.active_house_menu = None

    def draw(self, alpha_scale: float = 1.0) -> None:
        """Render the full overlay."""
        if alpha_scale <= 0:
            return

        # Build onto a temp surface so we can apply alpha_scale easily
        surf = pygame.Surface(
            (self.panel_rect.width, self.panel_rect.height), pygame.SRCALPHA
        )

        # Background
        game = getattr(self.game_state, 'game', None)
        if game and hasattr(game, 'pic_info_window'):
            draw_9slice(surf, game.pic_info_window, pygame.Rect(0, 0, self.panel_rect.width, self.panel_rect.height))
        else:
            surf.fill((*SANDY_BROWN, 255))
            pygame.draw.rect(surf, DARK_BROWN, pygame.Rect(0, 0, self.panel_rect.width, self.panel_rect.height), 4)

        # Title
        title = self.title_font.render("Population Statistics", True, DARK_BROWN)
        title_rect = title.get_rect(
            centerx=self.panel_rect.width // 2, top=16
        )
        surf.blit(title, title_rect)

        # Total Stats
        total_pop = self.town.citizens
        max_pop = getattr(self.town, 'max_citizens', 0)
        occupancy = (total_pop / max_pop * 100) if max_pop > 0 else 0
        avg_happiness = getattr(self.town, 'happiness', 80)
        
        stats_text = f"Population: {total_pop}/{max_pop} ({occupancy:.1f}%)    |    Average Happiness: {avg_happiness:.0f}%"
        stats_surf = self.heading_font.render(stats_text, True, DARK_BROWN)
        stats_rect = stats_surf.get_rect(
            centerx=self.panel_rect.width // 2, top=title_rect.bottom + 15
        )
        surf.blit(stats_surf, stats_rect)

        # Decorative line under header
        line_y = stats_rect.bottom + 15
        pygame.draw.line(
            surf,
            DARK_BROWN,
            (30, line_y),
            (self.panel_rect.width - 30, line_y),
            2,
        )

        # Close button
        local_close = self.close_rect.move(
            -self.panel_rect.x, -self.panel_rect.y
        )
        mouse_pos = pygame.mouse.get_pos()
        close_hovered = (
            alpha_scale >= 1.0 and self.close_rect.collidepoint(mouse_pos)
        )
        pygame.draw.rect(surf, (180, 60, 60) if close_hovered else DARK_BROWN, local_close)
        margin = 5
        pygame.draw.line(surf, WHITE, (local_close.left + margin, local_close.top + margin), (local_close.right - margin, local_close.bottom - margin), 2)
        pygame.draw.line(surf, WHITE, (local_close.left + margin, local_close.bottom - margin), (local_close.right - margin, local_close.top + margin), 2)

        # Draw cells
        absolute_mouse_pos = pygame.mouse.get_pos()

        for i, pop_type in enumerate(POP_TYPES):
            col = i % COLS
            row = i // COLS
            
            # Local coordinates for the cell
            cell_x = 20 + col * self.cell_w
            cell_y = self.header_h + row * self.cell_h
            
            cell_rect = pygame.Rect(cell_x, cell_y, self.cell_w, self.cell_h)
            
            # Global coordinates for mouse check
            global_cell_rect = cell_rect.move(self.panel_rect.x, self.panel_rect.y)
            is_hovered = global_cell_rect.collidepoint(absolute_mouse_pos)

            # Cell background and border
            inner_rect = cell_rect.inflate(-20, -20)
            pygame.draw.rect(surf, BEIGE, inner_rect)
            pygame.draw.rect(surf, DARK_BROWN, inner_rect, 2)
            
            # Population Type Name
            name_surf = self.heading_font.render(pop_type, True, DARK_BROWN)
            name_rect = name_surf.get_rect(centerx=inner_rect.centerx, top=inner_rect.top + 10)
            surf.blit(name_surf, name_rect)
            
            # Pictogram
            pic = self.pictograms.get(pop_type)
            if pic:
                pic_rect = pic.get_rect(centerx=inner_rect.centerx, centery=inner_rect.centery + 15)
                
                if is_hovered:
                    # Make pictogram very bright/faint by setting low alpha
                    pic_faint = pic.copy()
                    pic_faint.set_alpha(40) # Nearly merging with background
                    surf.blit(pic_faint, pic_rect)
                    
                    # Draw stats on top
                    count = self.town.population_groups.get(pop_type, 0)
                    happiness = getattr(self.town, 'happiness_groups', {}).get(pop_type, 80)
                    share = (count / total_pop * 100) if total_pop > 0 else 0
                    
                    count_surf = self.body_font.render(f"Citizens: {count}", True, BLACK)
                    count_rect = count_surf.get_rect(centerx=inner_rect.centerx, centery=inner_rect.centery - 10)
                    surf.blit(count_surf, count_rect)
                    
                    hap_surf = self.body_font.render(f"Happiness: {happiness:.0f}%", True, BLACK)
                    hap_rect = hap_surf.get_rect(centerx=inner_rect.centerx, top=count_rect.bottom + 5)
                    surf.blit(hap_surf, hap_rect)

                    share_surf = self.body_font.render(f"{share:.1f}% of population", True, BLACK)
                    share_rect = share_surf.get_rect(centerx=inner_rect.centerx, top=hap_rect.bottom + 5)
                    surf.blit(share_surf, share_rect)
                else:
                    # Regular pictogram
                    surf.blit(pic, pic_rect)

        # Darken background behind panel
        total_w = SCREEN_WIDTH + SIDEBAR_WIDTH
        overlay = pygame.Surface((total_w, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, int(120 * alpha_scale)))
        self.screen.blit(overlay, (0, 0))

        # Apply alpha and blit to screen
        if alpha_scale < 1.0:
            surf.set_alpha(int(255 * alpha_scale))
        self.screen.blit(surf, self.panel_rect)
