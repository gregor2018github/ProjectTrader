"""Module for displaying an overview of all trading licenses.

This module provides the ContractOverview class which shows a grid of all
goods with their contract screenshots and validity dates.
"""

import pygame
import os
import datetime
from typing import Optional, List, Tuple, Dict, Any, TYPE_CHECKING
from ...config.colors import (
    BLACK, WHITE, DARK_BROWN, SANDY_BROWN, BEIGE, DARK_GRAY, LIGHT_GRAY,
    GOLD, DARK_GREEN, DARK_RED, WHEAT,
)
from ...config.constants import (
    SCREEN_WIDTH, SCREEN_HEIGHT, SIDEBAR_WIDTH, PICTURES_PATH, FONTS_PATH,
)

if TYPE_CHECKING:
    from ...game_state import GameState
    from ...models.house import House


# All tradeable goods in display order
ALL_GOODS = [
    "Wood", "Stone", "Iron",
    "Wool", "Hide", "Fish",
    "Wheat", "Wine", "Beer",
    "Meat", "Linen", "Pottery",
]

COLS = 3


class ContractOverview:
    """A large overlay window displaying all trading licenses in a grid.

    Each cell shows: good name, miniature contract screenshot (if signed),
    and the 'Valid until' date.  Goods without a contract show an empty
    placeholder.
    """

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(self, screen: pygame.Surface, game_state: 'GameState', house: 'House' = None) -> None:
        self.screen = screen
        self.game_state = game_state
        self.house = house

        # Fonts --------------------------------------------------------
        try:
            self.title_font = pygame.font.Font(
                os.path.join(FONTS_PATH, "Medici Text.ttf"), 36
            )
            self.heading_font = pygame.font.Font(
                os.path.join(FONTS_PATH, "Augusta.ttf"), 24
            )
            self.body_font = pygame.font.Font(
                os.path.join(FONTS_PATH, "Augusta.ttf"), 18
            )
        except Exception:
            self.title_font = pygame.font.SysFont("arial", 30)
            self.heading_font = pygame.font.SysFont("arial", 20)
            self.body_font = pygame.font.SysFont("arial", 15)

        # Panel dimensions ---------------------------------------------
        total_w = SCREEN_WIDTH + SIDEBAR_WIDTH
        panel_w = int(total_w * 0.52)
        panel_h = int(SCREEN_HEIGHT * 0.86)
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
        self.header_h = 60  # space for "Trading Licenses" title
        cell_area_top = self.panel_rect.top + self.header_h
        cell_area_h = self.panel_rect.height - self.header_h - 20  # bottom pad
        cell_area_w = self.panel_rect.width - 40  # side padding (20 each)

        rows = (len(ALL_GOODS) + COLS - 1) // COLS
        self.cell_w = cell_area_w // COLS
        self.cell_h = cell_area_h // rows
        self.cell_origin_x = self.panel_rect.x + 20
        self.cell_origin_y = cell_area_top

        # Pre-load contract screenshots ---------------------------------
        self.contract_images: Dict[str, Optional[pygame.Surface]] = {}
        self.full_images: Dict[str, Optional[pygame.Surface]] = {}
        views_dir = os.path.join(PICTURES_PATH, "contracts", "contract_views")
        for good in ALL_GOODS:
            img = self._load_contract_image(views_dir, good)
            self.contract_images[good] = img
            self.full_images[good] = None # Lazy load on click

        # Full View State ----------------------------------------------
        self.inspecting_good: Optional[str] = None
        self.inspecting_img: Optional[pygame.Surface] = None

        # Scroll state (not needed now but easy to add later) -----------
        self.scroll_y = 0

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_full_image(self, good: str) -> Optional[pygame.Surface]:
        """Get or load the full-sized contract image for a good."""
        if self.full_images.get(good):
            return self.full_images[good]
        
        views_dir = os.path.join(PICTURES_PATH, "contracts", "contract_views")
        img = self._load_contract_image(views_dir, good)
        if img:
            self.full_images[good] = img
        return img

    @staticmethod
    def _load_contract_image(
        directory: str, good: str
    ) -> Optional[pygame.Surface]:
        """Try loading a contract screenshot for *good*.

        Looks for ``start_contract_<good>.jpg`` first, then
        ``contract_<good>.jpg``.
        """
        lower = good.lower()
        # Handle special case: "Hide" -> file uses "hides"
        candidates = [
            f"start_contract_{lower}.jpg",
            f"contract_{lower}.jpg",
            f"start_contract_{lower}s.jpg",
            f"contract_{lower}s.jpg",
        ]
        for name in candidates:
            path = os.path.join(directory, name)
            if os.path.isfile(path):
                try:
                    return pygame.image.load(path).convert()
                except Exception:
                    pass
        return None

    def _get_cell_rect(self, index: int) -> pygame.Rect:
        """Return the screen-space rect for cell *index*."""
        col = index % COLS
        row = index // COLS
        x = self.cell_origin_x + col * self.cell_w
        y = self.cell_origin_y + row * self.cell_h
        return pygame.Rect(x, y, self.cell_w, self.cell_h)

    # ------------------------------------------------------------------
    # Event handling
    # ------------------------------------------------------------------

    def handle_click(self, pos: Tuple[int, int]) -> Optional[bool]:
        """Handle a mouse click.

        Returns ``True`` when the click was consumed (close button or
        click outside the panel).  The caller should set
        ``game_state.info_window = None`` accordingly.
        """
        # Close full view if active
        if self.inspecting_good:
            self.inspecting_good = None
            self.inspecting_img = None
            return True

        # Close button
        if self.close_rect.collidepoint(pos):
            self._close()
            return True

        # Check for cell clicks
        depot = self.game_state.game.depot
        current_date = self.game_state.date
        for i, good in enumerate(ALL_GOODS):
            expiry = depot.trading_licenses.get(good)
            if expiry and expiry > current_date:
                cell_rect = self._get_cell_rect(i)
                if cell_rect.collidepoint(pos):
                    # Click to inspect
                    img = self._get_full_image(good)
                    if img:
                        self.inspecting_good = good
                        self.inspecting_img = img
                    return True

        # Click outside panel -> close
        if not self.panel_rect.collidepoint(pos):
            self._close()
            return True

        # Click inside is consumed but doesn't close
        return True

    def _close(self) -> None:
        """Trigger the fade-out and clear references."""
        gs = self.game_state
        gs.menu_fade_window = self
        gs.menu_fade_timer = gs.menu_fade_duration
        gs.info_window = None
        gs.active_house_menu = None

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def draw(self, alpha_scale: float = 1.0) -> None:
        """Render the full overlay."""
        if alpha_scale <= 0:
            return

        total_w = SCREEN_WIDTH + SIDEBAR_WIDTH

        # Build onto a temp surface so we can apply alpha_scale easily
        surf = pygame.Surface(
            (self.panel_rect.width, self.panel_rect.height), pygame.SRCALPHA
        )

        # Background
        surf.fill((*SANDY_BROWN, 255))
        pygame.draw.rect(
            surf,
            DARK_BROWN,
            pygame.Rect(0, 0, self.panel_rect.width, self.panel_rect.height),
            4,
        )

        # Title
        title = self.title_font.render("Trading Licenses", True, DARK_BROWN)
        title_rect = title.get_rect(
            centerx=self.panel_rect.width // 2, top=16
        )
        surf.blit(title, title_rect)

        # Decorative line under title
        line_y = title_rect.bottom + 6
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
        close_bg = (200, 180, 150) if close_hovered else SANDY_BROWN
        pygame.draw.rect(surf, close_bg, local_close)
        pygame.draw.rect(surf, DARK_BROWN, local_close, 2)
        margin = 7
        pygame.draw.line(
            surf,
            DARK_BROWN,
            (local_close.left + margin, local_close.top + margin),
            (local_close.right - margin, local_close.bottom - margin),
            2,
        )
        pygame.draw.line(
            surf,
            DARK_BROWN,
            (local_close.left + margin, local_close.bottom - margin),
            (local_close.right - margin, local_close.top + margin),
            2,
        )

        # Draw cells
        depot = self.game_state.game.depot
        current_date = self.game_state.date
        tooltips = []

        for i, good in enumerate(ALL_GOODS):
            cell_screen = self._get_cell_rect(i)
            cell_local = cell_screen.move(
                -self.panel_rect.x, -self.panel_rect.y
            )
            tooltip = self._draw_cell(surf, cell_local, good, depot, current_date)
            if tooltip:
                tooltips.append(tooltip)

        # Darken background behind panel
        overlay = pygame.Surface((total_w, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, int(120 * alpha_scale)))
        self.screen.blit(overlay, (0, 0))

        # Blit panel with optional alpha
        if alpha_scale < 1.0:
            surf.set_alpha(int(255 * alpha_scale))
        self.screen.blit(surf, (self.panel_rect.x, self.panel_rect.y))

        # Draw tooltips and inspector if fully active
        if alpha_scale >= 1.0:
            for text, pos in tooltips:
                self._draw_tooltip(text, pos)
            
            if self.inspecting_img:
                self._draw_full_inspector()

    def _draw_tooltip(self, text: str, pos: Tuple[int, int]) -> None:
        """Render a small tooltip near the mouse."""
        tooltip_surf = self.body_font.render(text, True, BLACK)
        tooltip_rect = tooltip_surf.get_rect(topleft=(pos[0] + 15, pos[1] + 10))
        
        # Draw background and border
        pygame.draw.rect(self.screen, WHITE, tooltip_rect.inflate(10, 6))
        pygame.draw.rect(self.screen, DARK_BROWN, tooltip_rect.inflate(10, 6), 1)
        self.screen.blit(tooltip_surf, tooltip_rect)

    def _draw_full_inspector(self) -> None:
        """Draw a modal overlay showing the full contract image."""
        total_w = SCREEN_WIDTH + SIDEBAR_WIDTH
        
        # Darker overlay
        overlay = pygame.Surface((total_w, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 200))
        self.screen.blit(overlay, (0, 0))

        # Scale image to fit screen with padding
        target_h = int(SCREEN_HEIGHT * 0.9)
        orig_w, orig_h = self.inspecting_img.get_size()
        scale = target_h / orig_h
        new_w, new_h = int(orig_w * scale), int(orig_h * scale)
        
        scaled_img = pygame.transform.smoothscale(self.inspecting_img, (new_w, new_h))
        img_rect = scaled_img.get_rect(center=(total_w // 2, SCREEN_HEIGHT // 2))
        
        # Shadow/Border
        pygame.draw.rect(self.screen, BLACK, img_rect.inflate(10, 10))
        self.screen.blit(scaled_img, img_rect)

        # Prompt to close
        close_txt = self.body_font.render("Click anywhere to close", True, WHITE)
        close_rect = close_txt.get_rect(centerx=total_w // 2, bottom=SCREEN_HEIGHT - 20)
        self.screen.blit(close_txt, close_rect)

    # ------------------------------------------------------------------

    def _draw_cell(
        self,
        surf: pygame.Surface,
        rect: pygame.Rect,
        good: str,
        depot: Any,
        current_date: datetime.datetime,
    ) -> Optional[Tuple[str, Tuple[int, int]]]:
        """Draw a single good's cell onto *surf* at *rect*."""
        pad = 8
        inner = rect.inflate(-pad * 2, -pad * 2)

        # License info
        expiry = depot.trading_licenses.get(good)
        has_license = expiry is not None and expiry > current_date
        is_expired = expiry is not None and expiry <= current_date

        # Local mouse pos relative to the cell for hover detection
        mouse_pos = pygame.mouse.get_pos()
        screen_cell_rect = rect.move(self.panel_rect.x, self.panel_rect.y)
        is_hovered = screen_cell_rect.collidepoint(mouse_pos) and not self.inspecting_good

        # Cell background
        # Note: We don't change bg color to PALE_BROWN here because the layout's pictograms 
        # use an overlay instead for the "main" pictogram.
        pygame.draw.rect(surf, BEIGE, inner)
        pygame.draw.rect(surf, DARK_BROWN, inner, 2)

        # --- Good name heading ---
        heading_color = DARK_BROWN if has_license else DARK_GRAY
        heading = self.heading_font.render(good, True, heading_color)
        heading_rect = heading.get_rect(centerx=inner.centerx, top=inner.top + 6)
        surf.blit(heading, heading_rect)

        # --- Contract image or placeholder ---
        img_top = heading_rect.bottom + 6
        img_max_w = inner.width - 20
        img_max_h = inner.height - 80  # leave room for heading + date text
        img_area = pygame.Rect(
            inner.left + 10, img_top, img_max_w, img_max_h
        )

        contract_img = self.contract_images.get(good)
        if has_license and contract_img is not None:
            # Scale the screenshot to fit inside img_area while preserving aspect ratio
            iw, ih = contract_img.get_size()
            scale = min(img_area.width / iw, img_area.height / ih)
            new_w = int(iw * scale)
            new_h = int(ih * scale)
            scaled = pygame.transform.smoothscale(contract_img, (new_w, new_h))
            img_x = img_area.x + (img_area.width - new_w) // 2
            img_y = img_area.y + (img_area.height - new_h) // 2
            
            surf.blit(scaled, (img_x, img_y))
            # Thin border around image
            pygame.draw.rect(
                surf, DARK_BROWN,
                pygame.Rect(img_x - 1, img_y - 1, new_w + 2, new_h + 2), 1
            )
        else:
            # Empty placeholder
            placeholder = pygame.Rect(
                img_area.x,
                img_area.y,
                img_area.width,
                img_area.height,
            )
            pygame.draw.rect(surf, (230, 225, 210), placeholder)
            pygame.draw.rect(surf, LIGHT_GRAY, placeholder, 1)

            # Show a subtle "No License" label
            no_lic = self.body_font.render("No License", True, LIGHT_GRAY)
            no_lic_rect = no_lic.get_rect(center=placeholder.center)
            surf.blit(no_lic, no_lic_rect)

        # --- Valid until / status text ---
        status_y = inner.bottom - 24
        if has_license:
            date_str = expiry.strftime("%d.%m.%Y")
            days_left = (expiry - current_date).days
            if days_left <= 7:
                color = DARK_RED
            elif days_left <= 30:
                color = GOLD
            else:
                color = DARK_GREEN
            status_text = f"Valid until: {date_str}"
        elif is_expired:
            color = DARK_RED
            status_text = "Expired"
        else:
            color = DARK_GRAY
            status_text = ""

        if status_text:
            status_surf = self.body_font.render(status_text, True, color)
            status_rect = status_surf.get_rect(
                centerx=inner.centerx, top=status_y
            )
            surf.blit(status_surf, status_rect)

        # Apply hover overlay effect like in layout.py sidebar
        if is_hovered:
            # Redraw pictogram-style dark overlay
            overlay = pygame.Surface((inner.width, inner.height), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 50))  # Black overlay at 50 alpha
            surf.blit(overlay, inner.topleft)
            
            # Return tooltip data if it's an active license
            if has_license:
                return ("Inspect Contract", mouse_pos)
        
        return None
