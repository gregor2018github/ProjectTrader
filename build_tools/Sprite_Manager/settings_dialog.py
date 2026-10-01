"""The settings dialog: which image model to ask, and for what size."""

import pygame

import gemini_client
from gemini_client import GeminiClient, GeminiError
from theme import (
    CHIP_BG, CHIP_HEIGHT, CHIP_HOVER, CHIP_ON, DIALOG_PAD, DONE_COLOR, ERROR_COLOR, TEXT, TEXT_DIM,
    window_size,
)
from widgets import Button, draw_chips, draw_dialog_box

DIALOG_WIDTH = 700
MODEL_ROW = 40
MAX_VISIBLE_MODELS = 8   # taller lists (after "Fetch models") scroll
SECTION_GAP = 18


class SettingsDialog:
    """Model and output size to ask the image API for."""

    def __init__(self, settings, fonts):
        """
        Args:
            settings: The gemini_client.Settings to edit.
            fonts: (font, small, title_font).
        """
        self.settings = settings
        self.font, self.small, self.title_font = fonts
        self.models = gemini_client.known_models()
        if settings.model not in self.models:
            self.models.append(settings.model)
        self.status = ''
        self.status_error = False
        self.model_scroll = 0
        self.model_area = pygame.Rect(0, 0, 0, 0)
        self.model_rows = []
        self.ratio_chips = []
        self.size_chips = []
        self.tries_chips = []
        self.fetch_button = Button('Fetch models from API', w=250)
        self.close_button = Button('Done', w=120)

    def fixed_height(self):
        """Everything in the dialog except the model list."""
        return (2 * DIALOG_PAD + 40 + 22
                + 3 * (SECTION_GAP + 22 + CHIP_HEIGHT) + SECTION_GAP + 60)

    def rect(self):
        width, height = window_size()
        rows = min(len(self.models), MAX_VISIBLE_MODELS)
        size = (min(DIALOG_WIDTH, width - 40),
                min(self.fixed_height() + rows * MODEL_ROW, height - 40))
        return pygame.Rect(((width - size[0]) // 2, (height - size[1]) // 2), size)

    def scroll_models(self, steps):
        """Mouse wheel over the model list."""
        hidden = max(0, len(self.models) * MODEL_ROW - self.model_area.h)
        self.model_scroll = max(0, min(hidden, self.model_scroll - steps * MODEL_ROW))

    def fetch_models(self):
        """Ask the API which image models the key can reach and offer them too."""
        try:
            found = GeminiClient().discover_models()
        except GeminiError as exc:
            self.status, self.status_error = str(exc), True
            return
        added = [model for model in found if model not in self.models]
        self.models.extend(added)
        self.status = f'{len(found)} image model(s) found, {len(added)} new'
        self.status_error = False

    # --- drawing ----------------------------------------------------------

    def draw(self, screen, mouse):
        rect = self.rect()
        draw_dialog_box(screen, rect)

        x = rect.x + DIALOG_PAD
        width = rect.w - 2 * DIALOG_PAD
        y = rect.y + DIALOG_PAD
        screen.blit(self.title_font.render('Image generation', True, TEXT), (x, y))
        y += 40

        label = 'Model' if len(self.models) <= MAX_VISIBLE_MODELS else 'Model  (scroll for more)'
        screen.blit(self.small.render(label, True, TEXT_DIM), (x, y))
        y += 22
        self.model_area = pygame.Rect(x, y, width, max(MODEL_ROW, rect.h - self.fixed_height()))
        self.model_rows = []
        screen.set_clip(self.model_area)
        row_y = y - self.model_scroll
        for model in self.models:
            row = pygame.Rect(x, row_y, width, MODEL_ROW - 4)
            row_y += MODEL_ROW
            if not row.colliderect(self.model_area):
                continue
            if model == self.settings.model:
                color = CHIP_ON
            elif row.collidepoint(mouse):
                color = CHIP_HOVER
            else:
                color = CHIP_BG
            pygame.draw.rect(screen, color, row, border_radius=6)
            name = self.font.render(model, True, TEXT)
            screen.blit(name, name.get_rect(midleft=(row.x + 12, row.centery)))
            note = gemini_client.model_note(model)
            if note:
                text = self.small.render(note, True, TEXT_DIM)
                screen.blit(text, text.get_rect(midright=(row.right - 12, row.centery)))
            self.model_rows.append((row.clip(self.model_area), model))
        screen.set_clip(None)

        y = self.model_area.bottom + SECTION_GAP
        screen.blit(self.small.render('Aspect ratio', True, TEXT_DIM), (x, y))
        y += 22
        self.ratio_chips, y = draw_chips(
            screen, self.small, gemini_client.ASPECT_RATIOS,
            lambda v: v or 'keep sheet', self.settings.aspect_ratio, x, y, width, mouse)

        y += SECTION_GAP
        screen.blit(self.small.render(
            'Image size  -  512 halves the tokens; a model that refuses it '
            'falls back to its own size', True, TEXT_DIM), (x, y))
        y += 22
        self.size_chips, y = draw_chips(
            screen, self.small, gemini_client.IMAGE_SIZES,
            lambda v: gemini_client.SIZE_LABELS.get(v, v),
            self.settings.image_size, x, y, width, mouse)

        y += SECTION_GAP
        screen.blit(self.small.render('Answers per sheet', True, TEXT_DIM), (x, y))
        y += 22
        self.tries_chips, y = draw_chips(
            screen, self.small, range(1, gemini_client.MAX_TRIES + 1),
            lambda v: f'{v}x', self.settings.tries, x, y, width, mouse)

        self.fetch_button.rect.bottomleft = (x, rect.bottom - DIALOG_PAD)
        self.close_button.rect.bottomright = (rect.right - DIALOG_PAD, rect.bottom - DIALOG_PAD)
        self.fetch_button.draw(screen, self.font, mouse)
        self.close_button.draw(screen, self.font, mouse)
        if self.status:
            text = self.small.render(self.status, True, ERROR_COLOR if self.status_error else DONE_COLOR)
            screen.blit(text, text.get_rect(midleft=(self.fetch_button.rect.right + 16,
                                                     self.fetch_button.rect.centery)))

    # --- input ------------------------------------------------------------

    def click(self, pos):
        """Handles one click; returns 'close' when the dialog is done."""
        if self.close_button.hit(pos):
            return 'close'
        if self.fetch_button.hit(pos):
            self.fetch_models()
            return None
        for row, model in self.model_rows:
            if row.collidepoint(pos):
                self.settings = self.settings.with_values(model=model)
                return None
        for chips, key in ((self.ratio_chips, 'aspect_ratio'), (self.size_chips, 'image_size'),
                           (self.tries_chips, 'tries')):
            for rect, value in chips:
                if rect.collidepoint(pos):
                    self.settings = self.settings.with_values(**{key: value})
                    return None
        if not self.rect().collidepoint(pos):
            return 'close'
        return None
