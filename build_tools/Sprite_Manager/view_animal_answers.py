"""The model's answers for one frame of an animal, and taking one into the game.

The crops' answers screen (view_crop_answers.py) with an animal's frame in
place of a stage sprite: accepting puts the new frame on the animal's canvas
and saves it facing left and, mirrored, facing right (animals.Animal.save_frame).
"""

from animal_sheets import AnimalDetail
from view_crop_answers import CropAnswersView


class AnimalAnswersView(CropAnswersView):
    @property
    def target(self):
        return self.crop.sprite_path(self.sheet.pose)

    def make_detail(self, entry):
        return AnimalDetail(self.crop, entry)

    def current_sprite(self):
        return self.crop.sprite(self.sheet.pose)

    def save_output(self, output):
        path, replaced, grown = self.crop.save_frame(self.sheet.pose, output)
        message = f'{"Replaced" if replaced else "Saved"} {path.name} and its mirror image for the right'
        if grown:
            message += ' - it did not fit the canvas, which grew: the other frames no longer match it'
        return message

    def header(self):
        return (f'Answers for {self.crop.title}: {self.sheet.name}',
                'Ctrl+V or drop a file = answer, Enter = accept into the game, Del = not good enough, '
                'click white gaps in the result to see through them.')
