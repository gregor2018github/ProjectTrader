"""The sound files, their families and kinds, and what is written down about them (no pygame).

assets/sound/ is read flat by the game (Game._load_sounds): every file there
is a sound, keyed by its name without the extension, and subfolders are
skipped, so "Raw Materials/" holds recordings that are not in the game.
assets/music/ is the music player's rotation (SoundControl), every track of
it played.

Numbered variants are one family: knock_1 ... knock_5 are "knock", which is
how the code mostly picks them (at random). A family's kind is read off its
name by KINDS, the first matching prefix winning.

sound_catalog.json, beside this file, keeps what the files cannot say:
a note per family (what it is for, or meant for) and where a file came from
(author, title, url, licence), for a credits screen one day.
"""

import json
import re
import subprocess
from pathlib import Path

import usage_scan

ROOT = Path(__file__).resolve().parents[2]
SOUND_DIR = ROOT / 'assets' / 'sound'
MUSIC_DIR = ROOT / 'assets' / 'music'
SOURCE_DIR = ROOT / 'src'
CATALOG_PATH = Path(__file__).resolve().parent / 'sound_catalog.json'
AUDIO_EXTENSIONS = ('.ogg', '.mp3', '.wav', '.flac')

# Where a file lives, which is what the game does with it
SOUND, MUSIC, RAW = 'sound', 'music', 'raw'

# (kind, name prefixes), in the order shown; a family matching none is 'Other'
KINDS = (
    ('Interface', ('ui_',)),
    ('Paper and books', ('parchment', 'scroll', 'page_turn', 'book_', 'scribble', 'stamp', 'rip_paper')),
    ('Coins', ('coin_', 'falling_coins')),
    ('Ambience', ('amb_',)),
    ('Animals', ('sheep', 'chicken')),
    ('Town', ('door', 'knock', 'horse_cart', 'church_bell', 'splash', 'wish_granted')),
    ('Work', ('chop', 'swoosh')),
    ('Player', ('map_foot_steps',)),
    ('Voices', ('merchant', 'story_teller')),
)
OTHER = 'Other'
KIND_ORDER = [kind for kind, _ in KINDS] + [OTHER]

_VARIANT = re.compile(r'^(.+?)_(\d+)$')


class SoundFile:
    """One audio file, and what the code does with it."""

    def __init__(self, path, place, new=False):
        self.path = path
        self.place = place               # SOUND, MUSIC or RAW
        self.key = path.stem             # the name the game knows it by
        self.new = new                   # not in git yet
        self.size = path.stat().st_size
        self.uses = []                   # [usage_scan.Reference], SOUND only
        self.clash = False               # another file has the same key; which one the game gets is luck

    @property
    def loop(self):
        return self.key.endswith('_loop')


class Family:
    """Numbered variants of one sound (knock_1 ... knock_5), or a sound on its own."""

    def __init__(self, name, place):
        self.name = name
        self.place = place
        self.files = []
        self.kind = kind_of(name) if place == SOUND else OTHER

    @property
    def uses(self):
        """Every place in the code using one of its files, each once."""
        seen, uses = set(), []
        for file in self.files:
            for ref in file.uses:
                if (ref.path, ref.line) not in seen:
                    seen.add((ref.path, ref.line))
                    uses.append(ref)
        return uses

    @property
    def used(self):
        """In the game: played by the code, or in the music rotation."""
        return self.place == MUSIC or any(file.uses for file in self.files)

    @property
    def unused_files(self):
        """Variants nothing plays while others of the family are played."""
        return [file for file in self.files if not file.uses] if self.place == SOUND else []

    @property
    def new(self):
        return any(file.new for file in self.files)


def family_name(key):
    match = _VARIANT.match(key)
    return match.group(1) if match else key


def kind_of(name):
    lower = name.lower()
    for kind, prefixes in KINDS:
        if lower.startswith(prefixes):
            return kind
    return OTHER


def untracked(folders):
    """Paths under `folders` git does not know yet (new files), as resolved Paths."""
    try:
        out = subprocess.run(['git', 'status', '--porcelain', '-z', '--untracked-files=all', '--',
                              *[str(f) for f in folders]],
                             cwd=ROOT, capture_output=True, check=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return set()
    paths = set()
    for entry in out.decode('utf-8', 'replace').split('\0'):
        if entry[:2] in ('??', 'A '):
            paths.add((ROOT / entry[3:]).resolve())
    return paths


def _audio_files(folder):
    if not folder.is_dir():
        return []
    return sorted((p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in AUDIO_EXTENSIONS),
                  key=lambda p: p.name.lower())


class Library:
    """Every sound and music file, grouped in families, with their uses in the code."""

    def __init__(self):
        self.families = []
        self.missing = []        # [usage_scan.Reference]: played by name, but no such file
        self.clashes = []        # [[SoundFile]] sharing one key
        self.catalog = Catalog.load()
        self.reload()

    def reload(self):
        new = untracked([SOUND_DIR, MUSIC_DIR])
        files = [SoundFile(p, SOUND, p.resolve() in new) for p in _audio_files(SOUND_DIR)]
        raw = [SoundFile(p, RAW, p.resolve() in new)
               for folder in sorted(d for d in SOUND_DIR.iterdir() if d.is_dir())
               for p in _audio_files(folder)]
        music = [SoundFile(p, MUSIC, p.resolve() in new) for p in _audio_files(MUSIC_DIR)]

        by_key = {}
        for file in files:
            by_key.setdefault(file.key, []).append(file)
        self.clashes = [same for same in by_key.values() if len(same) > 1]
        for same in self.clashes:
            for file in same:
                file.clash = True

        uses, self.missing = usage_scan.uses_of(usage_scan.scan(SOURCE_DIR), list(by_key))
        for file in files:
            file.uses = uses[file.key]

        families = {}
        for file in files + raw + music:
            name = family_name(file.key)
            family = families.get((file.place, name))
            if family is None:
                family = families[(file.place, name)] = Family(name, file.place)
            family.files.append(file)
        self.families = sorted(families.values(), key=lambda f: f.name.lower())

    def sound_files(self):
        """The files the game loads."""
        return [file for family in self.families if family.place == SOUND for file in family.files]


class Catalog:
    """sound_catalog.json: {"notes": {family: text}, "credits": {key: [{author, title, url, license}]}}.

    A file's credits are a list, as a file mixed from several recordings
    (amb_watermill_loop) owes each of them.
    """

    def __init__(self, notes=None, credits=None):
        self.notes = notes or {}
        self.credits = credits or {}

    @classmethod
    def load(cls):
        try:
            data = json.loads(CATALOG_PATH.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return cls()
        return cls(data.get('notes'), data.get('credits'))

    def save(self):
        notes = {name: text for name, text in sorted(self.notes.items()) if text.strip()}
        data = {'notes': notes, 'credits': dict(sorted(self.credits.items()))}
        CATALOG_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')

    def note(self, family):
        return self.notes.get(family.name, '')

    def set_note(self, family, text):
        self.notes[family.name] = text.strip()
        self.save()

    def credits_of(self, file):
        return self.credits.get(file.key, [])
