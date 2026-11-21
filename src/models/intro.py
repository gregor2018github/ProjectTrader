"""The start of a new game: arriving at the harbour and finding Uncle Gared's shop.

A new game opens on the docks (``START_X_POSITION``, ``START_Y_POSITION``) with
the story teller's first scene. Its answer, "Follow the Address", hands the
player back the map: they walk into town themselves, guided by the address on
their slip of paper (a map drawn on it, folded at the top of the map and
unfolded with a click, ``ui/helper_modules/address_note.py``) and golden rings on
the doorstep of the shop. Standing within ``ARRIVAL_REACH_TILES`` of that
doorstep plays the rest of the story, the shop, the uncle and the hug, and the
intro is done.

The texts are voiced (``SCENES``' sounds), so a change to one wants a new
recording. Saved under ``"intro"`` (``to_save`` / ``load``); a save from before
the intro is taken as having had it.
"""

from dataclasses import dataclass
from typing import Any, Iterable, Optional, Tuple

from ..config.constants import TILE_SIZE

ARRIVAL = "arrival"        # the harbour scene still to be shown
FIND_SHOP = "find_shop"    # walking into town to the uncle's door
DONE = "done"              # the uncle found: the intro is over
STAGES = (ARRIVAL, FIND_SHOP, DONE)

#: The uncle's shop: the middle house of the row House_29, and the door of it
#: on the "Doors" layer (the doors nearest this point are looked through)
SHOP_HOUSE = "House_29"
SHOP_POINT = (5678.0, 3760.0)
SHOP_DOOR_SEARCH_TILES = 2.0
#: How near the doorstep the player's feet must come for the uncle's scene
ARRIVAL_REACH_TILES = 1.5


@dataclass(frozen=True)
class Scene:
    """One page of the story: who speaks, what, and the one answer that ends it."""
    picture: str           # key in Game.pic_portraits
    speaker: str
    text: str
    answer: str
    sound: str
    next: Optional[str] = None   # the scene after it; None ends the chain


SCENES = {
    "harbour": Scene(
        "portrait_harbor", "Story Teller",
        "With nothing but hopes and an address scribbled on a small piece of paper, you step off the "
        "creaking gangplank onto the bustling docks of Blackwater Harbor, your future uncertain but full of promise.",
        "Follow the Address", "story_teller_1"),
    "shop": Scene(
        "portrait_shop", "Story Teller",
        "You make your way through the sleepy town and eventually enter a cramped but well-organized shop "
        "nestled between the cobbler and the blacksmith. The old trader's eyes light up with recognition as you approach.",
        "What a journey!", "story_teller_2", next="uncle"),
    "uncle": Scene(
        "portrait_merchant", "Old Merchant",
        "By the Saints, is that you? After all these years! Look how you've grown since I last saw you in Eastmere. "
        "Your father's letter said you were coming, but I hardly believed it. Welcome to Blackwater Harbor, Kid!",
        "Give him a hug", "merchant_1", next="hug"),
    "hug": Scene(
        "portrait_merchant", "Story Teller",
        "Uncle Gared pulls you into a quick embrace before stepping back, his hands trembling slightly as he "
        "leans on his gnarled oak staff. He calmly smiles at you.",
        "I will help you!", "story_teller_3"),
}

#: The scene each stage opens with, and the stage its chain's end leads to
OPENING_SCENE = {ARRIVAL: "harbour", FIND_SHOP: "shop"}
STAGE_AFTER = {ARRIVAL: FIND_SHOP, FIND_SHOP: DONE}


#: The shop's name once found: the player's first storage, the depot's starting one
SHOP_NAME = "Uncle Gared's Shop"


def is_found_shop(house: Any, intro: Optional[Any]) -> bool:
    """Whether this building is the uncle's shop and he has been found (the intro done):
    then the player rests there and keeps their first storage in it."""
    return getattr(house, "name", None) == SHOP_HOUSE and intro is not None and intro.stage == DONE


def find_shop_spot(doors: Iterable[Any]) -> Tuple[float, float]:
    """Where the player is to arrive: the doorstep of the shop's door, the door
    on the "Doors" layer nearest ``SHOP_POINT`` (within ``SHOP_DOOR_SEARCH_TILES``);
    ``SHOP_POINT`` itself if no usable door is there."""
    reach = SHOP_DOOR_SEARCH_TILES * TILE_SIZE
    best, best_d2 = None, reach * reach
    for door in doors:
        if door.step is None:
            continue
        dx, dy = door.threshold[0] - SHOP_POINT[0], door.threshold[1] - SHOP_POINT[1]
        if dx * dx + dy * dy <= best_d2:
            best, best_d2 = door, dx * dx + dy * dy
    if best is None:
        print(f"Intro: no door within {SHOP_DOOR_SEARCH_TILES} tiles of {SHOP_POINT}; arriving at the point itself")
        return SHOP_POINT
    return best.step


class Intro:
    """Where the player is in the intro (see the module)."""

    def __init__(self, stage: str = ARRIVAL, shop_spot: Tuple[float, float] = SHOP_POINT) -> None:
        self.stage: str = stage
        self.shop_spot: Tuple[float, float] = shop_spot
        self.playing: Optional[str] = None   # the scene on screen, if any

    @property
    def finding_shop(self) -> bool:
        """Whether the player is on their way to the shop (the rings and the note show)."""
        return self.stage == FIND_SHOP and self.playing is None

    def at_shop(self, feet: Tuple[float, float]) -> bool:
        dx, dy = feet[0] - self.shop_spot[0], feet[1] - self.shop_spot[1]
        reach = ARRIVAL_REACH_TILES * TILE_SIZE
        return dx * dx + dy * dy <= reach * reach

    def scene_due(self, feet: Tuple[float, float]) -> Optional[str]:
        """The scene to open now, if one is due and none is playing: the harbour's
        at once, the shop's when the player stands at its door."""
        if self.playing is not None:
            return None
        if self.stage == ARRIVAL or (self.stage == FIND_SHOP and self.at_shop(feet)):
            self.playing = OPENING_SCENE[self.stage]
            return self.playing
        return None

    def answered(self) -> Optional[str]:
        """The scene playing was answered: the next one of its chain, or None when
        the chain is over (the stage then moves on)."""
        if self.playing is None:
            return None
        nxt = SCENES[self.playing].next
        if nxt is None:
            self.stage = STAGE_AFTER.get(self.stage, DONE)
        self.playing = nxt
        return nxt

    def to_save(self) -> dict:
        # A scene on screen is not saved: on loading, its stage opens it again
        return {"stage": self.stage}

    def load(self, data: Optional[dict]) -> None:
        """Restore from a save; a save from before the intro (None) has had it."""
        stage = data.get("stage") if isinstance(data, dict) else None
        self.stage = stage if stage in STAGES else DONE
        self.playing = None
