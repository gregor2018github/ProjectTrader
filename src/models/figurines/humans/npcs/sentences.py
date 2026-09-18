"""Small-talk lines for human NPCs, read from ``assets/texts/NPCs``.

Every NPC draws on the generic file for its social class; traders also draw on
the trader file, which holds most of the lines, so they mostly talk shop. In
the files each sentence is a ``•`` bullet on its own line; empty bullets are
placeholders and are skipped.
"""

import os
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

BULLET = "•"


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
