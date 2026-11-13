"""The dialog asking for a new fence or wall's name, look and material, in the Sprite Manager's dialog protocol."""

import pygame

from fences import DEFAULT_MATERIAL, FENCES_DIR, MATERIALS, NAME_MAX_LENGTH, create_style, style_folder_name
from new_crop_dialog import NewCropDialog
from theme import DIALOG_PAD, TEXT_DIM
from widgets import draw_chips

DIALOG_SIZE = (620, 420)


class NewFenceDialog(NewCropDialog):
    TITLE = 'New fence or wall'
    CAPTIONS = ('Name  (the folder and the pieces are named after it)',
                'What it looks like  (for the prompt; the material\'s own words if left empty)')
    PLACEHOLDERS = ('e.g. Graveyard railing', 'e.g. black iron bars with spear tips between square posts')
    ROOT = FENCES_DIR
    MAX_LENGTH = NAME_MAX_LENGTH

    def __init__(self, fonts, on_created):
        super().__init__(fonts, on_created)
        self.rect.size = DIALOG_SIZE
        self.material = DEFAULT_MATERIAL
        self.chips = []

    @staticmethod
    def folder_name(text):
        return style_folder_name(text)

    def create_item(self, name, description):
        return create_style(name, description, self.material)

    def draw(self, screen, mouse):
        super().draw(screen, mouse)
        x = self.rect.x + DIALOG_PAD
        y = self.description.rect.bottom + 22
        screen.blit(self.fonts.small.render('Material  (wood and metal have a post every 2 tiles, stone only at '
                                            'its ends)', True, TEXT_DIM), (x, y))
        self.chips, _ = draw_chips(screen, self.fonts.small, [m.key for m in MATERIALS],
                                   lambda key: next(m.title for m in MATERIALS if m.key == key), self.material,
                                   x, y + 24, self.rect.w - 2 * DIALOG_PAD, mouse)

    def click(self, pos):
        for rect, key in self.chips:
            if rect.collidepoint(pos):
                self.material = key
                return None
        return super().click(pos)

    def event(self, event):
        # 1 to 3 pick the material while no field is typed in
        if (event.type == pygame.KEYDOWN and not any(f.focused for f in self.fields())
                and event.unicode in ('1', '2', '3')):
            self.material = MATERIALS[int(event.unicode) - 1].key
            return None
        return super().event(event)
