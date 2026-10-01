"""The dialog asking what a new person's folder needs: a gender and a name, or a trade."""

import pygame

from figures import GENDERS, TRADER_CATEGORY
from medieval_names import random_name
from theme import BG, CARD_HOVER, DONE_COLOR, ERROR_COLOR, NPC_DIR, TEXT, TEXT_DIM, window_size
from widgets import Button

NAME_MAX_LENGTH = 16
DIE_COLOR = (240, 236, 228)
PIP_COLOR = (60, 50, 40)
DIALOG_SIZE = (520, 290)
GENDER_ROW_HEIGHT = 80      # the row a trader dialog does without
INPUT_BG = (30, 28, 26)


class NewNpcDialog:
    """Asks for what a new NPC folder needs.

    A townsperson is a person: they need a gender and a name of their own, and
    the name can be rolled from the pool in medieval_names.py. A trader is a
    trade: the folder is named after the craft, not after whoever minds the
    stall, so the dialog asks for that one word and leaves the gender to the
    sprite. A trader dialog is therefore shorter by the row it does not need.
    """

    def __init__(self, category, title, taken, fonts):
        """
        Args:
            category: Folder name start, e.g. 'poor' or 'trader'.
            title: Dialog heading.
            taken: {lower-case name: folder name} of every NPC of this kind.
            fonts: (font, small, title_font).
        """
        self.category = category
        self.title = title
        self.taken = taken
        self.font, self.small, self.title_font = fonts
        self.is_trader = category == TRADER_CATEGORY
        self.gender = None
        self.name = ''
        self.error = ''
        height = DIALOG_SIZE[1] - (GENDER_ROW_HEIGHT if self.is_trader else 0)
        self.rect = pygame.Rect((0, 0), (DIALOG_SIZE[0], height))
        self.gender_buttons = [] if self.is_trader else [
            (key, Button(label, 0, 0, 120, 40)) for key, label in GENDERS]
        input_w = self.rect.w - 60 - (0 if self.is_trader else 54)
        self.input_rect = pygame.Rect(0, 0, input_w, 40)
        self.dice_button = None if self.is_trader else Button('', 0, 0, 44, 40)
        self.cancel_button = Button('Cancel', 0, 0, 120)
        self.create_button = Button('Create', 0, 0, 120)
        self.center()
        pygame.key.start_text_input()

    def center(self):
        """Place the dialog in the middle of the window."""
        width, height = window_size()
        self.rect.center = (width // 2, height // 2)
        x, y = self.rect.x + 30, self.rect.y + 80
        for i, (_, button) in enumerate(self.gender_buttons):
            button.rect.topleft = (x + i * 140, y)
        # Without a gender row the name field moves up into its place.
        self.input_rect.topleft = (x, y + (0 if self.is_trader else GENDER_ROW_HEIGHT))
        if self.dice_button:
            self.dice_button.rect.topleft = (self.input_rect.right + 10, self.input_rect.y)
        self.cancel_button.rect.topleft = (self.rect.right - 290, self.rect.bottom - 58)
        self.create_button.rect.topleft = (self.rect.right - 150, self.rect.bottom - 58)

    def folder_name(self):
        return f'{self.category}_{self.name.lower()}'

    def validate(self):
        """Return an error message, or '' if the NPC can be created."""
        if not self.is_trader and not self.gender:
            return 'Choose woman or man.'
        if not self.name:
            return 'Type the trade, e.g. chandler.' if self.is_trader else 'Type a name or roll the dice.'
        if self.name.lower() in self.taken:
            taken_by = self.taken[self.name.lower()]
            if self.is_trader:
                return f'There is already a {self.name.lower()} ({taken_by}).'
            return f'{self.name.capitalize()} is already taken ({taken_by}).'
        if (NPC_DIR / self.folder_name()).exists():
            return f'{self.folder_name()} already exists.'
        return ''

    def type_text(self, text):
        # Letters only: the name becomes part of the folder and file names.
        text = ''.join(c for c in text if c.isascii() and c.isalpha())
        self.name = (self.name + text)[:NAME_MAX_LENGTH]
        self.error = ''

    def roll(self):
        """Propose a random free name for the chosen gender."""
        if not self.gender:
            self.error = 'Choose woman or man first.'
            return
        name = random_name(self.gender, self.taken)
        if name is None:
            self.error = 'Every name in medieval_names.py is taken - type one.'
            return
        self.name = name
        self.error = ''

    def click(self, pos):
        """Return 'create', 'cancel' or None."""
        for key, button in self.gender_buttons:
            if button.hit(pos):
                self.gender = key
                self.error = ''
        if self.dice_button and self.dice_button.hit(pos):
            self.roll()
        if self.cancel_button.hit(pos):
            return 'cancel'
        if self.create_button.hit(pos):
            return 'create'
        return None

    def draw_die(self, screen, mouse):
        self.dice_button.draw(screen, self.font, mouse)
        face = self.dice_button.rect.inflate(-14, -12)
        face.width = face.height
        face.center = self.dice_button.rect.center
        pygame.draw.rect(screen, DIE_COLOR, face, border_radius=5)
        step = face.width // 4
        for dx, dy in ((-1, -1), (1, -1), (0, 0), (-1, 1), (1, 1)):  # the five
            pygame.draw.circle(screen, PIP_COLOR, (face.centerx + dx * step, face.centery + dy * step), 3)

    def draw(self, screen, mouse):
        shade = pygame.Surface(window_size(), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 150))
        screen.blit(shade, (0, 0))
        pygame.draw.rect(screen, BG, self.rect, border_radius=10)
        pygame.draw.rect(screen, CARD_HOVER, self.rect, 2, border_radius=10)
        screen.blit(self.title_font.render(self.title, True, TEXT), (self.rect.x + 30, self.rect.y + 22))

        for key, button in self.gender_buttons:
            button.draw(screen, self.font, mouse)
            if key == self.gender:
                pygame.draw.rect(screen, DONE_COLOR, button.rect, 3, border_radius=6)

        if self.is_trader:
            caption = 'Trade  (one word: the folder and the sprites are named after it)'
        else:
            caption = 'Name  (type one, or roll the dice for a free one)'
        label = self.small.render(caption, True, TEXT_DIM)
        screen.blit(label, (self.input_rect.x, self.input_rect.y - 22))
        pygame.draw.rect(screen, INPUT_BG, self.input_rect, border_radius=4)
        pygame.draw.rect(screen, CARD_HOVER, self.input_rect, 1, border_radius=4)
        cursor = '|' if pygame.time.get_ticks() // 500 % 2 else ''
        text = self.font.render(self.name.capitalize() + cursor, True, TEXT)
        screen.blit(text, text.get_rect(midleft=(self.input_rect.x + 10, self.input_rect.centery)))
        if self.dice_button:
            self.draw_die(screen, mouse)

        if self.error:
            message = self.small.render(self.error, True, ERROR_COLOR)
        elif self.name and (self.gender or self.is_trader):
            message = self.small.render(self.folder_name(), True, TEXT_DIM)
        else:
            message = None
        if message:
            # Errors can be long: they get their own line above the buttons.
            screen.blit(message, (self.rect.x + 30, self.cancel_button.rect.y - 26))
        self.cancel_button.draw(screen, self.font, mouse)
        self.create_button.draw(screen, self.font, mouse)
