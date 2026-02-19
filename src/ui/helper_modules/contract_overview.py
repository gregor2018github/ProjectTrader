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
    BUY_BUTTON, BUY_BUTTON_HOVER, BUY_BUTTON_BORDER, BUTTON_TEXT,
    SELL_BUTTON, SELL_BUTTON_HOVER, SELL_BUTTON_BORDER,
)
from ...config.constants import (
    SCREEN_WIDTH, SCREEN_HEIGHT, SIDEBAR_WIDTH, PICTURES_PATH, FONTS_PATH,
    BASE_CONTRACT_FEE, MONTHLY_CONTRACT_FEES,
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

        # Month Selection State ----------------------------------------
        self.selecting_good: Optional[str] = None  # Good currently being acquired
        self.month_buttons: List[Dict[str, Any]] = []  # [{"months": int, "rect": Rect, "cost": int}]
        self.month_panel_rect: Optional[pygame.Rect] = None
        self.month_cancel_rect: Optional[pygame.Rect] = None

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
        # Handle month selection panel clicks first
        if self.selecting_good:
            return self._handle_month_selection_click(pos)

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
            cell_rect = self._get_cell_rect(i)
            if cell_rect.collidepoint(pos):
                expiry = depot.trading_licenses.get(good)
                has_license = expiry is not None and expiry > current_date
                if has_license:
                    # Click to inspect existing license
                    img = self._get_full_image(good)
                    if img:
                        self.inspecting_good = good
                        self.inspecting_img = img
                else:
                    # Open month selection panel for acquiring a new license
                    self._open_month_selection(good)
                return True

        # Click outside panel -> close
        if not self.panel_rect.collidepoint(pos):
            self._close()
            return True

        # Click inside is consumed but doesn't close
        return True

    def _open_month_selection(self, good: str) -> None:
        """Open the month-duration selection sub-panel for *good*."""
        self.selecting_good = good
        monthly_fee = MONTHLY_CONTRACT_FEES.get(good, BASE_CONTRACT_FEE)

        # Panel dimensions
        panel_w = 340
        row_h = 36
        header_h = 60
        footer_h = 50
        month_options = [1, 2, 3, 6, 12]
        panel_h = header_h + len(month_options) * row_h + footer_h

        total_w = SCREEN_WIDTH + SIDEBAR_WIDTH
        px = (total_w - panel_w) // 2
        py = (SCREEN_HEIGHT - panel_h) // 2
        self.month_panel_rect = pygame.Rect(px, py, panel_w, panel_h)

        # Build buttons
        self.month_buttons = []
        btn_w = panel_w - 40
        btn_h = row_h - 6
        for idx, months in enumerate(month_options):
            cost = BASE_CONTRACT_FEE + monthly_fee * months
            bx = px + 20
            by = py + header_h + idx * row_h + 3
            self.month_buttons.append({
                "months": months,
                "cost": cost,
                "rect": pygame.Rect(bx, by, btn_w, btn_h),
            })

        # Cancel button
        cancel_w = 100
        cancel_h = 32
        self.month_cancel_rect = pygame.Rect(
            px + (panel_w - cancel_w) // 2,
            py + panel_h - footer_h + 8,
            cancel_w,
            cancel_h,
        )

    def _handle_month_selection_click(self, pos: Tuple[int, int]) -> bool:
        """Handle clicks inside the month selection sub-panel."""
        # Cancel button
        if self.month_cancel_rect and self.month_cancel_rect.collidepoint(pos):
            self.selecting_good = None
            self.month_buttons = []
            self.month_panel_rect = None
            self.month_cancel_rect = None
            return True

        # Month option buttons
        for btn in self.month_buttons:
            if btn["rect"].collidepoint(pos):
                self._acquire_license(self.selecting_good, btn["months"], btn["cost"])
                return True

        # Click outside the month panel dismisses it
        if self.month_panel_rect and not self.month_panel_rect.collidepoint(pos):
            self.selecting_good = None
            self.month_buttons = []
            self.month_panel_rect = None
            self.month_cancel_rect = None
            return True

        return True

    def _acquire_license(self, good: str, months: int, cost: int) -> None:
        """Close the overview and open ContractView for signing."""
        from .contract_acquisition import ContractView

        gs = self.game_state

        # Check if the player can afford the license
        if gs.game.depot.money < cost:
            gs.show_warning("Not enough money!")
            return

        # Clear the month selection state
        self.selecting_good = None
        self.month_buttons = []
        self.month_panel_rect = None
        self.month_cancel_rect = None

        # Close the overview
        gs.info_window = None
        gs.active_house_menu = None

        # Pause the game and open the contract acquisition view
        gs.previous_time_level = gs.time_level
        gs.time_level = 1
        gs.contract_acquisition = ContractView(
            gs.screen, gs.game,
            contract_type=good,
            contract_months=months,
            contract_cost=cost,
        )

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
            and not self.selecting_good and not self.inspecting_good
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

            if self.selecting_good:
                self._draw_month_selection()
            elif self.inspecting_img:
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

    def _draw_month_selection(self) -> None:
        """Draw the month-duration selection sub-panel on top of the overview."""
        if not self.month_panel_rect or not self.selecting_good:
            return

        total_w = SCREEN_WIDTH + SIDEBAR_WIDTH

        # Darken background behind the sub-panel
        overlay = pygame.Surface((total_w, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        self.screen.blit(overlay, (0, 0))

        pr = self.month_panel_rect
        mouse_pos = pygame.mouse.get_pos()

        # Panel background
        pygame.draw.rect(self.screen, SANDY_BROWN, pr)
        pygame.draw.rect(self.screen, DARK_BROWN, pr, 3)

        # Header
        header_text = f"Acquire {self.selecting_good} License"
        header_surf = self.heading_font.render(header_text, True, DARK_BROWN)
        header_rect = header_surf.get_rect(centerx=pr.centerx, top=pr.top + 10)
        self.screen.blit(header_surf, header_rect)

        # Decorative line
        line_y = header_rect.bottom + 6
        pygame.draw.line(self.screen, DARK_BROWN, (pr.left + 20, line_y), (pr.right - 20, line_y), 1)

        # Month option buttons
        for btn in self.month_buttons:
            rect = btn["rect"]
            hovered = rect.collidepoint(mouse_pos)
            bg_color = BUY_BUTTON_HOVER if hovered else BUY_BUTTON
            pygame.draw.rect(self.screen, bg_color, rect, border_radius=4)
            pygame.draw.rect(self.screen, BUY_BUTTON_BORDER, rect, 2, border_radius=4)

            # Label: "X month(s) — Y coins"
            m = btn["months"]
            label = f"{m} {'month' if m == 1 else 'months'}  —  {btn['cost']} coins"
            label_surf = self.body_font.render(label, True, BUTTON_TEXT)
            label_rect = label_surf.get_rect(center=rect.center)
            self.screen.blit(label_surf, label_rect)

        # Cancel button
        if self.month_cancel_rect:
            cr = self.month_cancel_rect
            cancel_hovered = cr.collidepoint(mouse_pos)
            cancel_bg = SELL_BUTTON_HOVER if cancel_hovered else SELL_BUTTON
            pygame.draw.rect(self.screen, cancel_bg, cr, border_radius=4)
            pygame.draw.rect(self.screen, SELL_BUTTON_BORDER, cr, 2, border_radius=4)
            cancel_surf = self.body_font.render("Cancel", True, BUTTON_TEXT)
            cancel_rect = cancel_surf.get_rect(center=cr.center)
            self.screen.blit(cancel_surf, cancel_rect)

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
        is_hovered = (
            screen_cell_rect.collidepoint(mouse_pos)
            and not self.inspecting_good
            and not self.selecting_good
        )

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
            
            # Return tooltip data
            if has_license:
                return ("  Inspect Contract", mouse_pos)
            else:
                return ("  Acquire License", mouse_pos)
        
        return None
