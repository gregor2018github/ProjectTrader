"""The main menu's page before a new game: the player's name, typed or rolled.

``NewGamePage`` opens with a random name (``player_names.random_name``) in its
field, already chosen, so typing replaces it and Enter starts at once. The die
beside the field rolls another. Under the field the player's figure stands as
he will look in the game (``preview``). "Start" (or Enter) starts the game with the
name, "Back" (or Escape) goes back to the menu. A field left empty starts with
a rolled name all the same.
"""

import os
from typing import Optional, Tuple

import pygame

from ..config.colors import BLACK, DARK_BROWN, DARK_GRAY, PALE_BROWN, SANDY_BROWN, TAN, WHITE
from ..config.constants import SCREEN_HEIGHT, SCREEN_WIDTH, SIDEBAR_WIDTH
from ..models.player_names import MAX_NAME_LENGTH, clean_name, random_name
from .ui_utils import draw_mouse_tooltip

START = "start"
BACK = "back"
DIE_TOOLTIP = "Roll a random name"

PANEL_W = 560
PANEL_H = 540
FIELD_H = 52
DIE_SIZE = 52
BUTTON_W = 180
BUTTON_H = 52
PREVIEW_H = 190   # the figure's height on the page
PREVIEW_FILE = os.path.join('assets', 'map_sprites', 'figurines', 'humans', 'player',
                            'player_front_static.png')

#: Where the pips sit on each face of the die, in thirds of its inner square
PIPS = {
    1: [(1, 1)], 2: [(0, 0), (2, 2)], 3: [(0, 0), (1, 1), (2, 2)],
    4: [(0, 0), (2, 0), (0, 2), (2, 2)], 5: [(0, 0), (2, 0), (1, 1), (0, 2), (2, 2)],
    6: [(0, 0), (2, 0), (0, 1), (2, 1), (0, 2), (2, 2)],
}


class NewGamePage:
    """The name field, the die, Start and Back; ``name`` is what the game starts with."""

    def __init__(self, title_font: pygame.font.Font, font: pygame.font.Font,
                 small_font: pygame.font.Font) -> None:
        self.title_font = title_font
        self.font = font
        self.small_font = small_font
        self.text: str = random_name()
        #: The rolled name is chosen as a whole: the first key typed replaces it
        self.selected: bool = True
        self.face: int = 5

        cx = (SCREEN_WIDTH + SIDEBAR_WIDTH) // 2
        self.panel = pygame.Rect(cx - PANEL_W // 2, (SCREEN_HEIGHT - PANEL_H) // 2, PANEL_W, PANEL_H)
        field_w = PANEL_W - 60 - DIE_SIZE - 12
        self.field = pygame.Rect(self.panel.left + 30, self.panel.top + 140, field_w, FIELD_H)
        self.die = pygame.Rect(self.field.right + 12, self.field.top, DIE_SIZE, DIE_SIZE)
        self.preview_rect = pygame.Rect(0, 0, PANEL_W - 60, PREVIEW_H)
        self.preview_rect.midtop = (cx, self.field.bottom + 40)
        self.preview: Optional[pygame.Surface] = _load_preview()
        buttons_top = self.preview_rect.bottom + 34
        self.start_button = pygame.Rect(cx - BUTTON_W - 10, buttons_top, BUTTON_W, BUTTON_H)
        self.back_button = pygame.Rect(cx + 10, buttons_top, BUTTON_W, BUTTON_H)

    @property
    def name(self) -> str:
        """The name to start with: the one typed, or a rolled one if the field is empty."""
        return clean_name(self.text) or random_name()

    def roll(self) -> None:
        """Put another random name in the field, chosen as a whole."""
        self.text = random_name(avoid=self.text)
        self.selected = True
        self.face = self.face % 6 + 1

    # ------------------------------------------------------------------
    # Input
    # ------------------------------------------------------------------

    def handle_click(self, pos: Tuple[int, int]) -> Optional[str]:
        """START, BACK or None for a left click at *pos*."""
        if self.die.collidepoint(pos):
            self.roll()
        elif self.field.collidepoint(pos):
            self.selected = False   # a click in the field puts the caret after the name
        elif self.start_button.collidepoint(pos):
            return START
        elif self.back_button.collidepoint(pos):
            return BACK
        return None

    def handle_event(self, event: pygame.event.Event) -> Optional[str]:
        """Typing into the field; START on Enter, BACK on Escape, else None."""
        if event.type == pygame.TEXTINPUT:
            if self.selected:
                self.text, self.selected = "", False
            for char in event.text:
                if char.isprintable() and len(self.text) < MAX_NAME_LENGTH:
                    self.text += char
        elif event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                return START
            if event.key == pygame.K_ESCAPE:
                return BACK
            if event.key == pygame.K_BACKSPACE:
                self.text = "" if self.selected else self.text[:-1]
                self.selected = False
        return None

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def draw(self, screen: pygame.Surface, mouse_pos: Tuple[int, int]) -> None:
        pygame.draw.rect(screen, SANDY_BROWN, self.panel, border_radius=6)
        pygame.draw.rect(screen, DARK_BROWN, self.panel, 3, border_radius=6)

        title = self.title_font.render("New Game", True, DARK_BROWN)
        title_rect = title.get_rect(centerx=self.panel.centerx, top=self.panel.top + 22)
        screen.blit(title, title_rect)
        divider_y = title_rect.bottom + 10
        pygame.draw.line(screen, DARK_BROWN, (self.panel.left + 30, divider_y),
                         (self.panel.right - 30, divider_y), 1)

        prompt = self.small_font.render("What is your name, merchant?", True, DARK_BROWN)
        screen.blit(prompt, prompt.get_rect(left=self.field.left, bottom=self.field.top - 8))

        self._draw_field(screen)
        self._draw_die(screen, self.die.collidepoint(mouse_pos))
        counter = self.small_font.render(f"{len(self.text)}/{MAX_NAME_LENGTH}", True, DARK_GRAY)
        screen.blit(counter, counter.get_rect(right=self.field.right, top=self.field.bottom + 4))

        self._draw_preview(screen)

        for rect, label in ((self.start_button, "Start"), (self.back_button, "Back")):
            hovered = rect.collidepoint(mouse_pos)
            pygame.draw.rect(screen, PALE_BROWN if hovered else TAN, rect, border_radius=4)
            pygame.draw.rect(screen, DARK_BROWN, rect, 2, border_radius=4)
            text = self.font.render(label, True, WHITE if hovered else DARK_BROWN)
            screen.blit(text, text.get_rect(center=rect.center))

        if self.die.collidepoint(mouse_pos):
            draw_mouse_tooltip(screen, self.small_font, DIE_TOOLTIP, mouse_pos)

    def _draw_field(self, screen: pygame.Surface) -> None:
        pygame.draw.rect(screen, WHITE, self.field, border_radius=4)
        pygame.draw.rect(screen, DARK_BROWN, self.field, 2, border_radius=4)
        text = self.font.render(self.text, True, BLACK)
        x = self.field.left + 12
        y = self.field.centery - text.get_height() // 2
        if self.selected and self.text:
            pygame.draw.rect(screen, PALE_BROWN, text.get_rect(topleft=(x, y)).inflate(6, 2))
            text = self.font.render(self.text, True, WHITE)
        screen.blit(text, (x, y))
        if not self.selected and pygame.time.get_ticks() // 500 % 2 == 0:
            caret_x = x + text.get_width() + 2
            pygame.draw.line(screen, BLACK, (caret_x, self.field.top + 10), (caret_x, self.field.bottom - 10), 2)

    def _draw_preview(self, screen: pygame.Surface) -> None:
        """The player's figure standing on a soft shadow under the name."""
        if self.preview is None:
            return
        feet_y = self.preview_rect.bottom - 6
        shadow_w = int(self.preview.get_width() * 0.75)
        shadow = pygame.Surface((shadow_w, 18), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow, (60, 35, 15, 70), shadow.get_rect())
        screen.blit(shadow, shadow.get_rect(center=(self.preview_rect.centerx, feet_y)))
        screen.blit(self.preview, self.preview.get_rect(midbottom=(self.preview_rect.centerx, feet_y + 2)))

    def _draw_die(self, screen: pygame.Surface, hovered: bool) -> None:
        pygame.draw.rect(screen, PALE_BROWN if hovered else TAN, self.die, border_radius=8)
        pygame.draw.rect(screen, DARK_BROWN, self.die, 2, border_radius=8)
        face = self.die.inflate(-18, -18)
        pygame.draw.rect(screen, WHITE, face, border_radius=5)
        pygame.draw.rect(screen, DARK_BROWN, face, 1, border_radius=5)
        inner = face.inflate(-10, -10)
        step = inner.width / 2
        for col, row in PIPS[self.face]:
            centre = (round(inner.left + col * step), round(inner.top + row * step))
            pygame.draw.circle(screen, DARK_BROWN, centre, 3)


def _load_preview() -> Optional[pygame.Surface]:
    """The player's front standing sprite, cut to what is drawn and scaled to PREVIEW_H.

    None if it cannot be loaded, so the page still works without it.
    """
    try:
        image = pygame.image.load(PREVIEW_FILE).convert_alpha()
    except (pygame.error, FileNotFoundError):
        return None
    image = image.subsurface(image.get_bounding_rect()).copy()
    w, h = image.get_size()
    return pygame.transform.smoothscale(image, (max(1, round(w * PREVIEW_H / h)), PREVIEW_H))
