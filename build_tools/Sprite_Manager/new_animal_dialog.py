"""The dialog asking for a new animal's name and what it looks like, in the Sprite Manager's dialog protocol."""

from animals import ANIMALS_DIR, NAME_MAX_LENGTH, animal_folder_name, create_animal
from new_crop_dialog import NewCropDialog


class NewAnimalDialog(NewCropDialog):
    TITLE = 'New animal'
    CAPTIONS = ('Name  (the folder and the sprites are named after it)',
                'What it looks like  (for the prompts of its sprites)')
    PLACEHOLDERS = ('e.g. Goat', 'e.g. a nimble brown nanny goat with short horns and a beard')
    ROOT = ANIMALS_DIR
    MAX_LENGTH = NAME_MAX_LENGTH

    @staticmethod
    def folder_name(text):
        return animal_folder_name(text)

    @staticmethod
    def create_item(name, description):
        return create_animal(name, description)
