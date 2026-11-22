"""The player's name: rolled for a new game, and made up for a save from before it was chosen.

No pygame. A name is a first name and a family name, or now and then a first
name and where he comes from ("Konrad of Bremen"). The player is a man (his
sprites are), so the first names are men's; Gared and Osric are left out, being
the uncle's and the old woodcutter's.

A save from before the name was chosen has "New Player" in it (or nothing):
``name_of_save`` gives it a name of its own, the same every time it is read
(drawn from the save's seed), so the load list and the game agree on it until
the game is saved with it.
"""

import random
from typing import Any, Dict, Optional

#: The longest name the new game's field takes
MAX_NAME_LENGTH = 24
#: What every game was called before the player chose a name
LEGACY_NAMES = frozenset({"", "new player"})
#: The share of rolled names that say where he comes from instead of a family name
PLACE_SHARE = 0.2

FIRST_NAMES = (
    'Adam', 'Adelard', 'Alaric', 'Albert', 'Alden', 'Aldric', 'Ambrose', 'Anselm',
    'Arnold', 'Baldwin', 'Bartholomew', 'Benedict', 'Bernard', 'Bertram', 'Conrad', 'Crispin',
    'Cuthbert', 'Dietrich', 'Edgar', 'Edmund', 'Edric', 'Edwin', 'Eustace', 'Everard',
    'Fulk', 'Geoffrey', 'Gerald', 'Gerard', 'Gilbert', 'Godfrey', 'Godric', 'Gottfried',
    'Gregory', 'Guy', 'Hamond', 'Hartmann', 'Heinrich', 'Henry', 'Herbert', 'Hubert',
    'Hugh', 'Humphrey', 'Ivo', 'Jakob', 'Jasper', 'Jocelin', 'Konrad', 'Lambert',
    'Leofric', 'Lothar', 'Ludwig', 'Martin', 'Matthias', 'Miles', 'Nicholas', 'Norbert',
    'Odo', 'Osbert', 'Oswald', 'Otto', 'Percival', 'Peter', 'Piers', 'Ralph',
    'Randolf', 'Reginald', 'Reinhard', 'Richard', 'Robert', 'Roger', 'Roland', 'Rupert',
    'Simon', 'Stephen', 'Theobald', 'Thomas', 'Tristan', 'Ulrich', 'Walter', 'Warin',
    'Wilhelm', 'William', 'Wolfram', 'Wulfric',
)

FAMILY_NAMES = (
    'Ashdown', 'Atwood', 'Baker', 'Barber', 'Becker', 'Brewer', 'Brandt', 'Carter',
    'Chandler', 'Cooper', 'Draper', 'Dyer', 'Fairfax', 'Fischer', 'Fletcher', 'Fuller',
    'Gardner', 'Glover', 'Hartwig', 'Hayward', 'Holt', 'Hooper', 'Hoffmann', 'Kellner',
    'Krause', 'Lange', 'Mason', 'Mercer', 'Miller', 'Moller', 'Nagel', 'Parker',
    'Potter', 'Reeve', 'Roper', 'Salter', 'Sawyer', 'Schreiber', 'Shepherd', 'Smith',
    'Spicer', 'Stone', 'Tanner', 'Thatcher', 'Turner', 'Vogt', 'Wagner', 'Walker',
    'Ward', 'Weaver', 'Weber', 'Webster', 'Whitlock', 'Winter', 'Wright', 'Ziegler',
)

PLACES = (
    'Bergen', 'Bremen', 'Bruges', 'Cologne', 'Danzig', 'Dorpat', 'Hamburg', 'Kampen',
    'Lubeck', 'Lynn', 'Novgorod', 'Riga', 'Rostock', 'Stralsund', 'Visby', 'Wismar',
    'York',
)


def random_name(rng: Optional[random.Random] = None, avoid: str = "") -> str:
    """A name for the player, never *avoid* (the one just shown, so a reroll changes it)."""
    rng = rng or random.Random()
    while True:
        first = rng.choice(FIRST_NAMES)
        if rng.random() < PLACE_SHARE:
            name = f"{first} of {rng.choice(PLACES)}"
        else:
            name = f"{first} {rng.choice(FAMILY_NAMES)}"
        if name != avoid and len(name) <= MAX_NAME_LENGTH:
            return name


def clean_name(text: str) -> str:
    """What was typed as a name: spaces trimmed and run together, at most MAX_NAME_LENGTH long."""
    return " ".join(str(text).split())[:MAX_NAME_LENGTH].strip()


def is_legacy(name: Any) -> bool:
    """True for a name the player never chose (a save from before names)."""
    return not isinstance(name, str) or name.strip().lower() in LEGACY_NAMES


def name_of_save(data: Dict[str, Any]) -> str:
    """The player's name in a save, made up (the same every time) if it has none of its own."""
    name = (data.get("player") or {}).get("name")
    if not is_legacy(name):
        return name
    sim = data.get("sim") or {}
    seed = sim.get("seed") if isinstance(sim, dict) else None
    if seed is None:
        seed = str(data.get("saved_at", ""))
    return random_name(random.Random(f"player-name:{seed}"))
