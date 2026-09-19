"""Medieval first names for townsfolk, used by gemini_sprite_import.py.

Plain lists, so adding a name is adding a line. Keep them letters only: a
name becomes part of the NPC's folder and sprite file names.
"""

import random

MALE_NAMES = [
    'Adam', 'Adelard', 'Alaric', 'Albert', 'Alden', 'Aldric', 'Ambrose', 'Anselm',
    'Arnold', 'Baldwin', 'Bartholomew', 'Benedict', 'Bernard', 'Bertram', 'Conrad', 'Crispin',
    'Cuthbert', 'Dietrich', 'Drogo', 'Eberhard', 'Edgar', 'Edmund', 'Edric', 'Edwin',
    'Egbert', 'Eustace', 'Everard', 'Fulk', 'Gawain', 'Geoffrey', 'Gerald', 'Gerard',
    'Gilbert', 'Godfrey', 'Godric', 'Gottfried', 'Gregory', 'Guy', 'Hamond', 'Hartmann',
    'Heinrich', 'Henry', 'Herbert', 'Hubert', 'Hugh', 'Humphrey', 'Ivo', 'Jakob',
    'Jasper', 'Jocelin', 'Konrad', 'Lambert', 'Lanfranc', 'Leofric', 'Lothar', 'Ludwig',
    'Martin', 'Matthias', 'Miles', 'Nicholas', 'Norbert', 'Odo', 'Osbert', 'Osric',
    'Oswald', 'Otto', 'Percival', 'Peter', 'Piers', 'Ralph', 'Randolf', 'Reginald',
    'Reinhard', 'Richard', 'Robert', 'Roger', 'Roland', 'Rupert', 'Sigmund', 'Simon',
    'Stephen', 'Theobald', 'Thomas', 'Tristan', 'Ulrich', 'Walter', 'Warin', 'Wilhelm',
    'William', 'Wolfram', 'Wulfric',
]

FEMALE_NAMES = [
    'Ada', 'Adela', 'Adelheid', 'Agatha', 'Agnes', 'Alice', 'Alison', 'Amabel',
    'Anna', 'Avice', 'Beatrice', 'Berta', 'Brunhild', 'Cecily', 'Christina', 'Clarice',
    'Constance', 'Denise', 'Dorothea', 'Edith', 'Eleanor', 'Elisabeth', 'Ella',
    'Emma', 'Ermengard', 'Estrild', 'Eva', 'Felicia', 'Frideswide', 'Gertrude', 'Gisela',
    'Godiva', 'Grete', 'Gunhild', 'Guinevere', 'Hawise', 'Hedwig', 'Helena', 'Heloise',
    'Hilda', 'Hildegard', 'Ida', 'Imma', 'Isabel', 'Isolde', 'Ivette', 'Joan',
    'Juliana', 'Katherine', 'Kunigunde', 'Letitia', 'Liesel', 'Lucia', 'Mabel', 'Magdalena',
    'Margery', 'Marion', 'Matilda', 'Maud', 'Mechthild', 'Mildred', 'Muriel', 'Nicola',
    'Odila', 'Ottilie', 'Petronilla', 'Philippa', 'Rohesia', 'Rosamund', 'Sabina', 'Sibyl',
    'Sophia', 'Susanna', 'Sybilla', 'Theda', 'Ursula', 'Walburga', 'Wilhelmina', 'Winifred',
]

NAMES = {'male': MALE_NAMES, 'female': FEMALE_NAMES}


def gender_of(name):
    """'male' or 'female' if the name is in one of the lists, else None."""
    for gender, names in NAMES.items():
        if name.lower() in (n.lower() for n in names):
            return gender
    return None


def random_name(gender, taken=()):
    """A random name of that gender that is not in `taken` (any case), or None."""
    taken = {name.lower() for name in taken}
    free = [name for name in NAMES[gender] if name.lower() not in taken]
    return random.choice(free) if free else None
