"""The goods' menu pictures: which ones each good of assets/data/goods.json needs, which it has.

A good is shown in the game's menus by up to five pictures, all in
assets/pictures:

    Icon 30px     <good>_30.png        the top bar, the market, the depot, every list of goods.
                                       The game does not start without it. The goods added in P1.3
                                       have placeholders: a disc in the good's chart colour with its
                                       initials, told here by that colour filling most of the icon.
    Painting      <good>_full.jpeg     the 1024px painting the cut-out icon is made from
    Cut-out icon  <good>_icon.png      bigger UI: warehouse inventory, the pack, the feast menu (else
                                       the 30px icon blown up); cut out of the painting by
                                       build_tools/Good_Icons/cut_good_icons.py (its GOODS list too)
    Licence       contracts/<good>.png the picture on the licence document, the good toned sepia
                                       (goods_sheets.licence_picture); every good has one, though the
                                       game shows only a licence's head's (Bread is traded under Wheat's)
    Signed        contracts/contract_views/contract_<good>.jpg
                                       a snapshot of the signed licence, which the game writes itself
                                       when a licence is bought: not art to make, shown as information

No pygame at import time; placeholder() loads the icon when asked.
"""

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from theme import ROOT

GOODS_JSON = ROOT / 'assets' / 'data' / 'goods.json'
COLORS_PY = ROOT / 'src' / 'config' / 'colors.py'
PICTURES_DIR = ROOT / 'assets' / 'pictures'
CONTRACTS_DIR = PICTURES_DIR / 'contracts'
CONTRACT_VIEWS_DIR = CONTRACTS_DIR / 'contract_views'

# Goods whose files are named otherwise than after the good (as the game and cut_good_icons.py name them)
PAINTING_FILES = {'Candle': 'candles_full.jpg', 'Hide': 'hides_full.jpeg'}
LICENCE_FILE_NAMES = {'Hide': 'hides'}       # contract_acquisition.py: "Hide" -> "Hides"

# A 30px icon is a placeholder when its chart colour covers at least this share of its opaque pixels
PLACEHOLDER_SHARE = 0.5

OK = 'ok'
PLACEHOLDER = 'placeholder'
MISSING = 'missing'
NOT_NEEDED = 'not needed'


@dataclass(frozen=True)
class Kind:
    key: str
    title: str
    size: str           # how big it is, for the detail panel
    use: str            # where the game shows it
    counted: bool = True  # False: made by the game, shown but not counted as work


KINDS = (
    Kind('small', 'Icon 30px', '30 x 30', 'top bar, market, depot and every list of goods; the game needs it'),
    Kind('painting', 'Painting', '1024 x 1024', 'the source of the cut-out icon'),
    Kind('icon', 'Cut-out', '128 on the long side',
         'warehouse inventory, the pack, the feast menu; else the 30px icon blown up. '
         'Made from the painting by cut_good_icons.py'),
    Kind('licence', 'Licence', "as the painting's figure",
         "the picture on the guild licence's document: the good toned sepia, made from its painting"),
    Kind('signed', 'Signed', 'a screenshot', 'the signed licence in the overview; the game writes it when bought',
         counted=False),
)
KIND_BY_KEY = {kind.key: kind for kind in KINDS}


@dataclass
class Good:
    name: str
    color_name: str
    color: tuple            # the chart colour, (r, g, b), or None if colors.py lacks it
    licence: str            # the good whose licence it is traded under: its own or its chain's head

    @property
    def is_head(self):
        return self.licence == self.name

    def path(self, kind):
        """Where the game looks for the picture of `kind` (the first candidate, if it tries several)."""
        lower = self.name.lower()
        if kind == 'small':
            return PICTURES_DIR / f'{lower}_30.png'
        if kind == 'painting':
            return PICTURES_DIR / PAINTING_FILES.get(self.name, f'{lower}_full.jpeg')
        if kind == 'icon':
            return PICTURES_DIR / f'{lower}_icon.png'
        if kind == 'licence':
            return CONTRACTS_DIR / f'{LICENCE_FILE_NAMES.get(self.name, lower)}.png'
        if kind == 'signed':
            for name in (f'start_contract_{lower}.jpg', f'contract_{lower}.jpg',
                         f'start_contract_{lower}s.jpg', f'contract_{lower}s.jpg'):
                if (CONTRACT_VIEWS_DIR / name).is_file():
                    return CONTRACT_VIEWS_DIR / name
            return CONTRACT_VIEWS_DIR / f'contract_{lower}.jpg'
        raise KeyError(kind)

    def needs(self, kind):
        return self.is_head if kind == 'signed' else True   # a licence is bought for its head only

    def status(self, kind):
        if not self.needs(kind):
            return NOT_NEEDED
        path = self.path(kind)
        if not path.is_file():
            return MISSING
        if kind == 'small' and placeholder(path, self.color):
            return PLACEHOLDER
        return OK


def chart_colors():
    """{name: (r, g, b)} of src/config/colors.py, read as text (the tool does not import the game)."""
    colors = {}
    pattern = re.compile(r'^([A-Z_0-9]+)\s*=\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)')
    for line in COLORS_PY.read_text(encoding='utf-8').splitlines():
        match = pattern.match(line)
        if match:
            colors[match.group(1)] = tuple(int(v) for v in match.groups()[1:])
    return colors


def find_goods():
    """Every good of goods.json, in its order."""
    colors = chart_colors()
    goods = []
    for entry in json.loads(GOODS_JSON.read_text(encoding='utf-8'))['goods']:
        name = entry['name']
        goods.append(Good(name, entry['color'], colors.get(entry['color']), entry.get('license') or name))
    return goods


@lru_cache(maxsize=None)
def _placeholder(path, mtime, color):
    import pygame
    image = pygame.image.load(str(path))
    opaque = same = 0
    w, h = image.get_size()
    for x in range(w):
        for y in range(h):
            pixel = image.get_at((x, y))
            if pixel.a > 200:
                opaque += 1
                same += tuple(pixel)[:3] == color
    return opaque > 0 and same / opaque >= PLACEHOLDER_SHARE


def placeholder(path, color):
    """True if the 30px icon at `path` is a disc in the chart colour `color` (with the good's initials)."""
    if color is None:
        return False
    return _placeholder(Path(path), Path(path).stat().st_mtime, tuple(color))


def tally(goods):
    """{kind key: (done, needed, placeholders)} over `goods`; a placeholder is not done."""
    totals = {}
    for kind in KINDS:
        statuses = [good.status(kind.key) for good in goods]
        totals[kind.key] = (statuses.count(OK), sum(s != NOT_NEEDED for s in statuses),
                            statuses.count(PLACEHOLDER))
    return totals
