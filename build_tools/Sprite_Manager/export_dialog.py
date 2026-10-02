"""The export dialog: the animation as a GIF or as a video, saved and put on the clipboard."""

import pygame

from theme import DIALOG_PAD, TEXT, TEXT_DIM, window_size
from widgets import Button, draw_dialog_box

DIALOG_SIZE = (520, 230)
CHOICE_W = 220
CHOICE_H = 56

GIF = 'gif'
VIDEO = 'video'


class ExportDialog:
    """Asks GIF or video and hands the choice to on_choice."""

    def __init__(self, fonts, on_choice, gif_error='', video_error=''):
        """
        Args:
            fonts: The app's fonts.
            on_choice: Called with GIF or VIDEO once one is clicked.
            gif_error, video_error: Why that format cannot be made; its button is then off.
        """
        self.fonts = fonts
        self.on_choice = on_choice
        self.gif_button = Button('GIF' if not gif_error else 'GIF (needs Pillow)', w=CHOICE_W, h=CHOICE_H)
        self.video_button = Button('Video (MP4)' if not video_error else 'Video (needs PyAV)',
                                   w=CHOICE_W, h=CHOICE_H)
        self.gif_button.enabled = not gif_error
        self.video_button.enabled = not video_error

    def rect(self):
        width, height = window_size()
        size = (min(DIALOG_SIZE[0], width - 40), DIALOG_SIZE[1])
        return pygame.Rect(((width - size[0]) // 2, (height - size[1]) // 2), size)

    def draw(self, screen, mouse):
        rect = self.rect()
        draw_dialog_box(screen, rect)
        x, y = rect.x + DIALOG_PAD, rect.y + DIALOG_PAD
        screen.blit(self.fonts.title.render('Export the animation', True, TEXT), (x, y))
        y += 40
        for line in ('GIF: see-through, loops - for browsers and Discord.',
                     'Video: on white, a few seconds - for WhatsApp and phones.'):
            screen.blit(self.fonts.small.render(line, True, TEXT_DIM), (x, y))
            y += 20
        self.gif_button.rect.bottomleft = (x, rect.bottom - DIALOG_PAD)
        self.video_button.rect.bottomright = (rect.right - DIALOG_PAD, rect.bottom - DIALOG_PAD)
        self.gif_button.draw(screen, self.fonts.font, mouse)
        self.video_button.draw(screen, self.fonts.font, mouse)

    def scroll_by(self, steps):
        """Nothing to scroll."""

    def click(self, pos):
        """Handles one click; returns 'close' when the dialog is done."""
        for button, choice in ((self.gif_button, GIF), (self.video_button, VIDEO)):
            if button.hit(pos):
                self.on_choice(choice)
                return 'close'
        if not self.rect().collidepoint(pos):
            return 'close'
        return None
