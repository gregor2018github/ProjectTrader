"""A dish's picture: the example it is drawn after, the prompt, and the picture an answer makes.

A dish is drawn after its type's example (food.example_of): the model gets the example's picture as it
is, and a prompt asking for the very same picture - the same plate (or bowl, or cup), the same table,
angle, framing, light and pixel art - with only the food on it changed to the dish. There is no sketch
and no split image: the answer is the whole new picture.

Accepting an answer (view_food_answers.py) fits it to the example's proportions (cutting off what sticks
out, centred) and size, and saves it as the dish's picture, assets/pictures/dish_<key>.png, keeping one
it replaces in <output>/food/<key>/replaced/ first.

Each dish's answers live in build_tools/output/food/<key>/, with its review.json; the sheet sent,
sheet.png, is a copy of the example's picture, and sheet.txt the prompt.
"""

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pygame

from food import CLASS_TITLES, Dish
from theme import OUTPUT_DIR

FOOD_OUTPUT = OUTPUT_DIR / 'food'
LAYOUT = 'single'            # not a split image: the answer is the whole picture
POSE = 'picture'             # a dish has one picture to make; answers are booked under this pose
SHEET_FILE = 'sheet.png'
EXAMPLE_FILE = 'example.json'
REPLACED_DIR = 'replaced'

# What each type's example shows the food in, for the prompt
VESSELS = {
    'plate': 'plate',
    'bowl': 'bowl',
    'drink': 'cup',
}

PROMPT_TEMPLATE = """\
The attached picture is from my medieval trading game "Merchant's Rise". When the player orders a dish at a tavern, the game shows what is brought to the table as a picture like this one. It shows {example} ({example_description}), served {served}.

Draw the same picture again for another dish of the tavern's bill of fare: {name} - {description}. It is served {served} at a {tavern} tavern.

Change only the food. Everything else stays exactly as it is in the attached picture:
- The same {vessel}: its shape, size, colours, rim and pattern, in the same place in the picture.
- The same table or surface under it, and the same background.
- The same viewing angle, framing and distance: the {vessel} as big in the picture as it is now.
- The same light, coming from the same side, and the same shadows.
- The same style: the same rough, chunky pixel art with big square pixels of the same size, the same thick black outlines, flat colours with only a few shades each and hard edges. No smooth gradients, no soft or blurred edges, no fine detail drawn with smaller pixels.

The new food:
- Is clearly recognisable as {name} at a glance, as a medieval cook around 1500 would have served it.
- Fills the {vessel} about as much as the food in the attached picture does{fill_note}.
- Has nothing of the old dish left: no {example_lower}, unless the new dish has it too.

No text, no labels, no frame. Output one single picture with the same proportions as the attached one.
"""

DRINK_NOTE = (', in a vessel that suits the drink as the example\'s suits its own: a tankard or mug for ale, beer and '
              'milk, a goblet for wine and mead - keep the example\'s vessel if it already suits')


class DishSubject:
    """A dish while its picture is made: what the app keeps as its `npc` (out_dir, prefix, title) for the
    answers, the API and the browser."""

    def __init__(self, dish):
        self.dish = dish
        self.name = dish.name
        self.title = dish.name
        self.prefix = dish.key
        self.out_dir = FOOD_OUTPUT / dish.key

    @property
    def target(self):
        """The dish's picture in the game, which accepting writes."""
        return self.dish.picture


@dataclass
class DishSheet:
    """What is sent for a dish - its example's picture and the prompt - shaped like a sheets.FrameSheet for
    the API, the browser and the answers."""

    subject: DishSubject
    example: Dish
    surface: pygame.Surface
    path: Path
    prompt: str
    sketched: bool = True
    layout: str = LAYOUT
    pose: str = POSE

    @property
    def name(self):
        return f'{self.subject.title} picture'


def prompt_for(dish, example):
    """The prompt asking for `dish` drawn as `example` is."""
    vessel = VESSELS.get(dish.type, 'plate')
    served = {'plate': 'on a plate', 'bowl': 'in a bowl', 'drink': 'as a drink'}.get(dish.type, 'on a plate')
    return PROMPT_TEMPLATE.format(
        example=example.name, example_lower=example.name.lower(), example_description=example.description,
        name=dish.name, description=dish.description, served=served, vessel=vessel,
        tavern=CLASS_TITLES.get(dish.tavern_class, dish.tavern_class).lower(),
        fill_note=DRINK_NOTE if dish.type == 'drink' else '',
    )


def make_sheet(subject, example):
    """The example's picture and the prompt for `subject`, written to its output folder.

    Raises:
        pygame.error, OSError: If the example cannot be read or the sheet not written.
    """
    surface = pygame.image.load(str(example.picture)).convert()
    subject.out_dir.mkdir(parents=True, exist_ok=True)
    path = subject.out_dir / SHEET_FILE
    prompt = prompt_for(subject.dish, example)
    pygame.image.save(surface, str(path))
    path.with_suffix('.txt').write_text(prompt, encoding='utf-8')
    (subject.out_dir / EXAMPLE_FILE).write_text(json.dumps({'example': example.name}) + '\n', encoding='utf-8')
    return DishSheet(subject, example, surface, path, prompt)


def fit_to(image, size):
    """`image` cut to the proportions of `size` (centred) and scaled to it."""
    w, h = image.get_size()
    tw, th = size
    if w * th > tw * h:                      # too wide: cut the sides
        cw, ch = round(h * tw / th), h
    else:                                    # too tall: cut top and bottom
        cw, ch = w, round(w * th / tw)
    crop = pygame.Rect((w - cw) // 2, (h - ch) // 2, cw, ch)
    return pygame.transform.smoothscale(image.subsurface(crop), size)


class DishResult:
    """An answer fitted to the example's proportions and size, as it would be saved."""

    scale = 1.0

    def __init__(self, path, size):
        """
        Raises:
            pygame.error: If the answer cannot be read.
        """
        image = pygame.image.load(str(path)).convert()
        self.scale = size[0] / image.get_width()
        self.output = fit_to(image, size)


class DishDetail:
    """One answer and the picture accepting it would make."""

    def __init__(self, subject, entry, example):
        """
        Args:
            example: The Surface of the example it was drawn after, or None if it is gone.

        Raises:
            pygame.error, OSError: If the answer's image cannot be read.
        """
        self.subject = subject
        self.entry = entry
        self.path = subject.out_dir / entry.image
        image = pygame.image.load(str(self.path))
        entry.width, entry.height = image.get_size()
        self.reference = example
        self.result = None
        self.error = ''
        try:
            if example is None:
                raise ValueError('the example it was drawn after cannot be read')
            self.result = DishResult(self.path, example.get_size())
        except Exception as exc:  # an unreadable image
            self.error = f'Cannot use this image: {exc}'
        self.preview = None

    def toggle_hole(self, pos):
        """Nothing is cut out of a dish's picture: it keeps its table."""


def save_picture(subject, output):
    """Write the dish's picture, keeping one it replaces in replaced/.

    Returns:
        The status message.

    Raises:
        pygame.error, OSError: If it cannot be written.
    """
    path = subject.target
    replaced = path.is_file()
    if replaced:
        stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        backup = subject.out_dir / REPLACED_DIR / f'{stamp}_{path.name}'
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_bytes(path.read_bytes())
    pygame.image.save(output, str(path))
    return f'{"Replaced" if replaced else "Saved"} {path.name}' + (' (the old one is in replaced/)' if replaced else '')
