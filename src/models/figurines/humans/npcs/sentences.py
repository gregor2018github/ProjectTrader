"""Small-talk lines for human NPCs, read from ``assets/texts/NPCs``.

Every NPC draws on the generic file for its social class; traders also draw on
the trader file, which holds most of the lines, so they mostly talk shop.
An NPC may instead pass on a rumour about how things work in town, with a chance
of RUMOUR_CHANCE, so these do not crowd out a class's own lines however many
there are. The poor say a line of their own file when given a coin. In the files each sentence
is a ``•`` bullet on its own line; empty bullets are placeholders and are
skipped.

A rumour names who may say it in brackets at its start, as
``• [Poor, Commons, Traders] The sentence.``: social classes, and TRADER_TAG for
anyone who trades for a living, whatever their class. Without brackets anyone may.

A sentence about the speaker's marriage uses the placeholders of SPOUSE_WORDS,
as ``my {spouse}``, which for_speaker() fills in by the speaker's gender.
"""

import os
import re
from functools import lru_cache
from typing import List, Tuple

from .....config.constants import MAIN_PATH

NPC_TEXTS_PATH = os.path.join(MAIN_PATH, "assets", "texts", "NPCs")

CLASS_SENTENCE_FILES = {
    "Poor": "sentences_generic_poor.txt",
    "Commons": "sentences_generic_commons.txt",
    "Middling Sort": "sentences_generic_middling_sort.txt",
    "Nobility": "sentences_generic_nobility.txt",
}
TRADER_SENTENCE_FILE = "sentences_traders.txt"
ALMS_THANKS_FILE = "sentences_thanks_alms.txt"
RUMOUR_FILE = "sentences_generic_rumours.txt"
RUMOUR_CHANCE = 0.3
TRADER_TAG = "Traders"

#: Placeholder in a sentence file: what a man says, what a woman says.
SPOUSE_WORDS = {
    "{spouse}": ("wife", "husband"),
    "{spouse_pronoun}": ("she", "he"),
    "{love_rival}": ("the tanner", "the miller's daughter"),
}

BULLET = "•"
_RUMOUR_TAGS = re.compile(r"\[([^\]]*)\]\s*(.*)")


@lru_cache(maxsize=None)
def load_sentences(filename: str) -> Tuple[str, ...]:
    """Read one sentence file, cached after the first read.

    Args:
        filename: File name inside NPC_TEXTS_PATH.

    Returns:
        The non-empty sentences, or nothing if the file is missing.
    """
    try:
        with open(os.path.join(NPC_TEXTS_PATH, filename), encoding="utf-8") as f:
            raw_lines = f.read().splitlines()
    except OSError:
        return ()
    sentences = (line.strip().lstrip(BULLET).strip() for line in raw_lines)
    return tuple(sentence for sentence in sentences if sentence)


def sentences_for(social_class: str, is_trader: bool) -> List[str]:
    """All lines an NPC of this kind may say.

    Args:
        social_class: One of the four population groups.
        is_trader: Whether the NPC trades for a living.

    Returns:
        The candidate sentences, possibly empty.
    """
    sentences = list(load_sentences(CLASS_SENTENCE_FILES.get(social_class, "")))
    if is_trader:
        sentences += load_sentences(TRADER_SENTENCE_FILE)
    return sentences


def for_speaker(sentence: str, gender: str) -> str:
    """Fill in a sentence's placeholders for who is saying it.

    Args:
        sentence: A sentence as it stands in its file.
        gender: The speaker's, ``"male"`` or ``"female"``.

    Returns:
        The sentence as they say it: a man has a wife, a woman a husband.
    """
    for placeholder, (his, hers) in SPOUSE_WORDS.items():
        sentence = sentence.replace(placeholder, hers if gender == "female" else his)
    return sentence


def rumours() -> List[Tuple[Tuple[str, ...], str]]:
    """Every rumour with who may say it.

    Returns:
        (tags, sentence) pairs; no tags mean anyone may say it.
    """
    result = []
    for line in load_sentences(RUMOUR_FILE):
        match = _RUMOUR_TAGS.fullmatch(line)
        if match:
            tags = tuple(tag.strip() for tag in match.group(1).split(","))
            result.append((tags, match.group(2)))
        else:
            result.append(((), line))
    return result


def rumours_for(social_class: str, is_trader: bool) -> List[str]:
    """The rumours an NPC of this kind may pass on.

    Args:
        social_class: One of the four population groups.
        is_trader: Whether the NPC trades for a living.

    Returns:
        The candidate sentences, possibly empty.
    """
    return [sentence for tags, sentence in rumours()
            if not tags or social_class in tags or (is_trader and TRADER_TAG in tags)]
