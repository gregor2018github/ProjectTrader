"""The tavern dishes' pictures: every dish of assets/texts/taverns/dishes.csv, its type and its picture.

The game shows a dish's picture when the player orders it at a tavern (src/models/tavern_menu.py,
tavern_menu_window.py); it is assets/pictures/dish_<key>.png, the key being the dish's name in snake
case, as the game names it (tavern_menu.dish_key).

Every dish has a type, how it is served, in the csv's "type" column:

    plate   roasts, pies, fish, sausages, breads, tarts and sweets: on a plate
    bowl    pottages, stews and whatever is served in its broth
    drink   ales, beers, wines and the like

A new dish picture is drawn after an example of its type, to keep the same look: the same plate (or
bowl, or cup) on the same table, only the dish on it changed. The example is the dish named in
EXAMPLE_DISHES, else the first dish of the type that has a picture; a type with neither has none yet.

No pygame here.
"""

import csv
import re
from dataclasses import dataclass

from theme import ROOT

DISHES_CSV = ROOT / 'assets' / 'texts' / 'taverns' / 'dishes.csv'
PICTURES_DIR = ROOT / 'assets' / 'pictures'

# (key, title, what it is served in), in the order the types are listed
TYPES = (
    ('plate', 'Plates', 'on a plate'),
    ('bowl', 'Bowls', 'in a bowl'),
    ('drink', 'Drinks', 'as a drink'),
)
TYPE_TITLES = {key: title for key, title, _ in TYPES}

# The dish whose picture the others of its type are drawn after
EXAMPLE_DISHES = {'plate': 'Roast Pigeons', 'drink': 'Buttermilk'}

FOOD_PICTURES = 'food pictures'   # what the app's GIMP watch files a dish's picture under

CLASS_TITLES = {'low': 'Low', 'middle': 'Middle', 'high': 'High'}


def dish_key(name):
    """The dish's name in snake case, as the game names its picture (tavern_menu.dish_key)."""
    return re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')


@dataclass(frozen=True)
class Dish:
    name: str
    tavern_class: str
    course: str
    type: str
    meat: bool
    price: float
    description: str

    @property
    def key(self):
        return dish_key(self.name)

    @property
    def picture(self):
        """Where the game looks for its picture."""
        return PICTURES_DIR / f'dish_{self.key}.png'

    def has_picture(self):
        return self.picture.is_file()


def find_dishes():
    """Every dish of dishes.csv, in its order; a row of an unknown type counts as a plate."""
    dishes = []
    with open(DISHES_CSV, newline='', encoding='utf-8') as file:
        for row in csv.DictReader(file):
            dish_type = (row.get('type') or 'plate').strip().lower()
            dishes.append(Dish(
                name=row['dish'].strip(),
                tavern_class=row['class'].strip().lower(),
                course=row['course'].strip().lower(),
                type=dish_type if dish_type in TYPE_TITLES else 'plate',
                meat=row['meat'].strip().lower() == 'yes',
                price=float(row['price']),
                description=row['description'].strip(),
            ))
    return dishes


def example_of(dish_type, dishes):
    """The dish whose picture the others of `dish_type` are drawn after, or None if there is none yet."""
    named = EXAMPLE_DISHES.get(dish_type)
    for dish in dishes:
        if dish.name == named and dish.has_picture():
            return dish
    return next((d for d in dishes if d.type == dish_type and d.has_picture()), None)


def tally(dishes):
    """{type key: (with a picture, dishes)}."""
    return {key: (sum(d.has_picture() for d in dishes if d.type == key), sum(d.type == key for d in dishes))
            for key, _, _ in TYPES}
