"""The dialog asking for a new crop's name and what it looks like ripe, in the Sprite Manager's dialog protocol."""

import pygame

from crops import CROPS_DIR, NAME_MAX_LENGTH, create_crop, crop_folder_name
from theme import DIALOG_PAD, ERROR_COLOR, TEXT, TEXT_DIM, window_size
from widgets import Button, TextField, draw_dialog_box

DIALOG_SIZE = (620, 330)
FIELD_H = 40
FIELD_GAP = 30


class NewCropDialog:
    def __init__(self, fonts, on_created):
        """
        Args:
            fonts: widgets.Fonts.
            on_created: Called with the new crops.Crop.
        """
        self.fonts = fonts
        self.on_created = on_created
        self.rect = pygame.Rect((0, 0), DIALOG_SIZE)
        self.name = TextField('', placeholder='e.g. Barley', h=FIELD_H)
        self.description = TextField('', placeholder='e.g. nodding golden ears with long whiskers', h=FIELD_H)
        self.cancel_button = Button('Cancel', w=120)
        self.create_button = Button('Create', w=120)
        self.error = ''
        self.name.focus(True)

    def place(self):
        width, height = window_size()
        self.rect.center = (width // 2, height // 2)
        x, w = self.rect.x + DIALOG_PAD, self.rect.w - 2 * DIALOG_PAD
        self.name.rect = pygame.Rect(x, self.rect.y + 92, w, FIELD_H)
        self.description.rect = pygame.Rect(x, self.name.rect.bottom + FIELD_GAP, w, FIELD_H)
        self.cancel_button.rect.bottomright = (self.rect.right - DIALOG_PAD - 132, self.rect.bottom - DIALOG_PAD)
        self.create_button.rect.bottomright = (self.rect.right - DIALOG_PAD, self.rect.bottom - DIALOG_PAD)

    def fields(self):
        return self.name, self.description

    def draw(self, screen, mouse):
        self.place()
        draw_dialog_box(screen, self.rect)
        fonts = self.fonts
        screen.blit(fonts.title.render('New crop', True, TEXT), (self.rect.x + DIALOG_PAD, self.rect.y + 18))
        captions = ('Name  (the folder and the sprites are named after it)',
                    'What it looks like ripe  (for the prompt of its first sprite)')
        for field, caption in zip(self.fields(), captions):
            screen.blit(fonts.small.render(caption, True, TEXT_DIM), (field.rect.x, field.rect.y - 22))
            field.draw(screen, fonts.font, mouse)
        if self.error:
            line, color = self.error, ERROR_COLOR
        elif crop_folder_name(self.name.text):
            line, color = f'fields/{crop_folder_name(self.name.text)}/', TEXT_DIM
        else:
            line = ''
        if line:
            screen.blit(fonts.small.render(line, True, color), (self.rect.x + DIALOG_PAD, self.cancel_button.rect.y - 28))
        self.cancel_button.draw(screen, fonts.font, mouse)
        self.create_button.draw(screen, fonts.font, mouse)

    def click(self, pos):
        if self.cancel_button.hit(pos):
            return self.close()
        if self.create_button.hit(pos):
            return self.create()
        for field in self.fields():
            field.focus(field.rect.collidepoint(pos))
        return None

    def event(self, event):
        """Typing and keys; returns 'close' when the dialog is done."""
        focused = next((f for f in self.fields() if f.focused), None)
        if event.type == pygame.TEXTINPUT and focused:
            focused.type(event.text)
            if focused is self.name:
                self.name.text = self.name.text[:NAME_MAX_LENGTH]
            self.error = ''
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                return self.close()
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                return self.create()
            if event.key == pygame.K_TAB:
                other = self.description if focused is self.name else self.name
                if focused:
                    focused.focus(False)
                other.focus(True)
            elif focused:
                focused.key(event)
        return None

    def close(self):
        for field in self.fields():
            field.focus(False)
        return 'close'

    def create(self):
        name = crop_folder_name(self.name.text)
        if not name:
            self.error = 'Type a name.'
            return None
        if (CROPS_DIR / name).exists():
            self.error = f'fields/{name}/ exists already.'
            return None
        try:
            crop = create_crop(self.name.text, self.description.text)
        except (ValueError, OSError) as exc:
            self.error = str(exc)
            return None
        self.close()
        self.on_created(crop)
        return 'close'
