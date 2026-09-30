"""New people: their folder, and the first sprite everything else is made from.

A person is added with create_new_NPC.py's dialog and folder layout, so both
tools make the same folders. Until they have a front standing sprite they are
a NewFigure: the split image the model draws them on is the player's front
sprite beside an empty cell (as sprite_prompts/blanco_human.jpg), and the
prompt comes from description.txt in their output folder, which says who
they are and how they look.
"""

import os
import sys
from dataclasses import dataclass
from pathlib import Path

import pygame

import create_new_NPC
from create_new_NPC import CATEGORIES, GENDERS, OTHER, TRADER_CATEGORY, NewNpcDialog
from create_new_pose import OUTPUT_DIR, PLAYER_DIR
from images import scaled, trim
from medieval_names import NAMES
from sheets import FRAME_COLOR, FRAME_WIDTH, MARGIN_RATIO, MIN_MARGIN

FIRST_FOLDER = 'first_sprite'
DESCRIPTION_FILE = 'description.txt'
FIRST_POSE = 'front_static'
SPLIT_HEIGHT = 600       # the player is blown up by whole pixels to about this height
PLACEHOLDER = '...'      # what the description holds until it is written

FIRST_PROMPT_TEMPLATE = """\
The attached picture is a split view. The left side shows a sprite of the main character from my game "Merchant's Rise", a medieval trading game. The right side is empty. Draw a new character in the empty right side: {who}.

The most important thing is that the new character looks like they come from the exact same game as the character on the left:
- Copy his art style exactly: the same big, blocky pixels (same pixel size, not finer), the same thick dark outline, the same flat colors with only one or two shades per color. No anti-aliasing, gradients, blur or extra detail.
- Copy his body exactly: the same chibi proportions, the same head size and shape, the same height and width, the same front-facing standing pose, arms hanging at the sides, feet in the same place.
- Copy his face exactly. Do not add or change any facial features.
- Plain white background, no shadow or ground.

Only the hair and clothes are different:
{looks}

{colours}Change only the right side and leave the left side exactly as it is. Output the full split image.
"""

DESCRIPTION_TEMPLATE = """\
# The first sprite of {label}. Lines starting with # are left out.
# Who they are, one line, e.g. "a town baker who steps out of his bakehouse".
Who: {who}
# How they look apart from the player, one line each: hair, clothes, shoes,
# what the hands hold ("Hands empty, hanging at the sides" if nothing).
- {placeholder}
- {placeholder}
- Hands empty, hanging at the sides, holding nothing.
# The few colours to keep to, e.g. "charcoal gray, soot black and dull brick red".
Colours: {placeholder}
"""


class NewFigure:
    """A person's folder without a front standing sprite yet."""

    def __init__(self, npc):
        """
        Args:
            npc: A create_new_NPC.Npc.
        """
        self.folder = npc.folder
        self.name = npc.name
        self.prefix = npc.prefix
        self.category = npc.category
        self.gender = npc.gender
        self.label = npc.label
        self.display_name = npc.display_name if npc.is_townsperson else npc.prefix
        self.is_new = True

    def sprite_path(self, pose):
        return self.folder / f'{self.prefix}_{pose}.png'

    @property
    def out_dir(self):
        """The split image, prompt, description and answers of the first sprite."""
        return OUTPUT_DIR / self.name / FIRST_FOLDER

    @property
    def description_path(self):
        return self.out_dir / DESCRIPTION_FILE

    def default_who(self):
        if self.category == TRADER_CATEGORY:
            return f'a {self.prefix} who sells at a medieval town market'
        title = dict((key, title) for key, title, _ in CATEGORIES).get(self.category, '')
        person = dict(GENDERS).get(self.gender, 'person').lower()
        return f'{self.display_name}, a {person} of the {title} who walks through the town'

    def ensure_description(self):
        """Write description.txt from the template if it is not there yet; returns its path."""
        path = self.description_path
        if not path.is_file():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(DESCRIPTION_TEMPLATE.format(
                label=self.label, who=self.default_who(), placeholder=PLACEHOLDER), encoding='utf-8')
        return path


def name_usage():
    """How far the name pool of medieval_names.py is used up by the townsfolk.

    Every name may be used once, by one townsperson (traders are named after
    their trade). A name typed in the dialog need not be from the pool.

    Returns:
        ({gender: (used, in the pool)}, [typed names not from the pool]).
    """
    townsfolk = [n for n in create_new_NPC.find_npcs() if n.is_townsperson]
    used = {n.display_name.lower() for n in townsfolk}
    usage = {gender: (sum(name.lower() in used for name in names), len(names))
             for gender, names in NAMES.items()}
    pool = {name.lower() for names in NAMES.values() for name in names}
    typed = sorted(n.display_name for n in townsfolk if n.display_name.lower() not in pool)
    return usage, typed


def find_new_figures():
    """Every NPC folder without a front standing sprite, as a NewFigure."""
    return [NewFigure(n) for n in create_new_NPC.find_npcs()
            if n.category != OTHER[0] and not NewFigure(n).sprite_path(FIRST_POSE).is_file()]


# ---------------------------------------------------------------------------
# The description and the prompt
# ---------------------------------------------------------------------------

@dataclass
class Description:
    who: str
    looks: list
    colours: str

    def unfinished(self):
        """What still has to be written, or ''."""
        if not self.who or PLACEHOLDER in self.who:
            return 'who they are'
        if not self.looks or any(PLACEHOLDER in line for line in self.looks):
            return 'how they look'
        return ''


def read_description(path):
    """Parse description.txt: 'Who:', '- ' lines and 'Colours:'."""
    who, looks, colours = '', [], ''
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        key, _, value = line.partition(':')
        if key.lower() == 'who':
            who = value.strip().rstrip('.')
        elif key.lower() in ('colours', 'colors'):
            colours = value.strip().rstrip('.')
        elif line.startswith('-'):
            looks.append(line.lstrip('- ').strip())
    return Description(who, looks, colours)


def first_prompt(description):
    colours = description.colours
    return FIRST_PROMPT_TEMPLATE.format(
        who=description.who,
        looks='\n'.join(f'- {line}' for line in description.looks),
        colours=f'Keep the colors simple: {colours}. ' if colours and PLACEHOLDER not in colours else '')


# ---------------------------------------------------------------------------
# The split image
# ---------------------------------------------------------------------------

@dataclass
class FirstSheet:
    """The split image of a new figure and its prompt, shaped like a sheets.FrameSheet."""

    surface: pygame.Surface
    path: Path
    prompt: str
    pose: str = FIRST_POSE
    name: str = 'First sprite'


def build_split_sheet(player):
    """The player's front sprite in the left cell, the right cell empty and white."""
    player = trim(player)
    player = scaled(player, max(1, SPLIT_HEIGHT // player.get_height()))
    margin = max(MIN_MARGIN, int(max(player.get_size()) * MARGIN_RATIO))
    cell_w, cell_h = player.get_width() + 2 * margin, player.get_height() + 2 * margin
    sheet = pygame.Surface((2 * cell_w + 3 * FRAME_WIDTH, cell_h + 2 * FRAME_WIDTH))
    sheet.fill(FRAME_COLOR)
    cells = [pygame.Rect(FRAME_WIDTH + col * (cell_w + FRAME_WIDTH), FRAME_WIDTH, cell_w, cell_h)
             for col in range(2)]
    for cell in cells:
        sheet.fill((255, 255, 255), cell)
    sheet.blit(player, player.get_rect(midbottom=(cells[0].centerx, cells[0].bottom - margin)))
    return sheet


def write_first_sheet(figure):
    """Build the figure's split image and prompt from the files on disk and write them.

    Returns:
        (FirstSheet, Description).

    Raises:
        pygame.error, OSError: If the player's sprite or the description cannot be read.
    """
    description = read_description(figure.ensure_description())
    player = pygame.image.load(str(PLAYER_DIR / f'player_{FIRST_POSE}.png')).convert_alpha()
    surface = build_split_sheet(player)
    stem = f'{figure.prefix}_{FIRST_POSE}'
    path = figure.out_dir / f'{stem}_sheet.png'
    prompt = first_prompt(description)
    pygame.image.save(surface, str(path))
    (figure.out_dir / f'{stem}_prompt.txt').write_text(prompt, encoding='utf-8')
    return FirstSheet(surface, path, prompt), description


def open_in_editor(path):
    """Open a text file in the program Windows has for it."""
    if sys.platform == 'win32':
        os.startfile(path)
    else:
        raise OSError(f'Open {path} yourself')


# ---------------------------------------------------------------------------
# Adding a person
# ---------------------------------------------------------------------------

class AddFigureDialog:
    """create_new_NPC's NewNpcDialog, in the Sprite Manager's dialog protocol."""

    def __init__(self, category, title, fonts, on_created):
        """
        Args:
            category: 'trader', 'poor', 'commons', 'middling' or 'nobility'.
            title: The group's title, e.g. 'Middling Sort'.
            fonts: widgets.Fonts.
            on_created: Called with the new folder once it is made.
        """
        is_trader = category == TRADER_CATEGORY
        taken = create_new_NPC.taken_names(create_new_NPC.find_npcs(), is_trader)
        heading = f'New trader: {title}' if is_trader else f'New NPC: {title}'
        self.dialog = NewNpcDialog(category, heading, taken, tuple(fonts))
        self.on_created = on_created

    def draw(self, screen, mouse):
        self.dialog.center()  # the window may have changed size
        self.dialog.draw(screen, mouse)

    def click(self, pos):
        return self.act(self.dialog.click(pos))

    def event(self, event):
        """Typing and keys; returns 'close' when the dialog is done."""
        if event.type == pygame.TEXTINPUT:
            self.dialog.type_text(event.text)
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                return self.act('cancel')
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                return self.act('create')
            if event.key == pygame.K_BACKSPACE:
                self.dialog.name = self.dialog.name[:-1]
        return None

    def act(self, action):
        if action == 'cancel':
            pygame.key.stop_text_input()
            return 'close'
        if action == 'create':
            error = self.dialog.validate()
            if error:
                self.dialog.error = error
                return None
            folder = create_new_NPC.create_npc_folder(
                self.dialog.category, self.dialog.name, self.dialog.gender)
            pygame.key.stop_text_input()
            self.on_created(folder)
            return 'close'
        return None
