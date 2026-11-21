"""A little quest: Flip, the shepherdess's black sheep, runs off through a gate the player left open.

How it goes:

1. **Quiet.** The flock grazes in the fold south-west of the market, a walled
   pen with a gate north and south. If the player opens one of those gates
   (``gate_opened_by_player``), leaves it open, and is gone, far from the fold
   (``AWAY_TILES``) and with the fold out of sight, at some time of the evening
   or night (by the daylight, ``EVENING_FROM`` to ``MORNING_FROM``; slept
   through counts as well), Flip slips out (``check_escape``). A gate shut again, by the player or anyone passing
   through it, undoes the danger (``note_gates``). It happens once a game.
2. **Escaped.** Flip grazes on the island between the two rivers, west of the
   River Fork, over the West Bridge. From the next morning (``missed_on``) the
   shepherdess no longer minds her stall at the market: she keeps the fold by
   day instead (``on_meadow``) and goes home in the evening. She has news for
   the player (``has_news``), so a marker bobs over her head.
3. **Searching.** Her talk asks who left the gate open. Feigning surprise
   ("Oh no, who would do this?") costs ``LIE_REPUTATION``, since the farmer saw
   them; owning up costs only ``CONFESS_REPUTATION``. Either way she asks the
   player to bring Flip back. Flip is shy: only a piece of Bread lures him
   (``lure``). Without one the player says so to themselves (``needs_bread``),
   and the shepherdess then gives them one, once (``BREAD_GIFT``).
4. **Leading.** One Bread is used up and Flip follows the player on a leash
   (leash.py), the player walking ``LEASH_SLOWDOWN`` slower and kept from the
   buildings until he is home.
5. **Returned.** Once Flip is back inside the fold (``bring_home``) he grazes
   with the others. Brought by day, the shepherdess is there to thank the
   player; at night she is at home and the player puts him back with the flock
   themselves (``at_night``), and she thanks them the next morning.
6. **Done.** Her thanks: ``THANKS_GIFT`` of her wool, or, turned down,
   ``THANKS_REPUTATION``. She keeps the fold to the day's end and is back at
   the market the next morning.

No pygame: the game tells it what happens on the map (game.py) and the UI plays
its talks (src/ui/helper_modules/lost_sheep_talks.py). Saved under
``"lost_sheep"`` (``to_save`` / ``load``); a save without it has not seen it
start. The texts are not voiced.
"""

import datetime
from typing import Dict, Optional

from .daylight import sun_hour
from .talks import Answer, Page

QUIET = "quiet"            # Flip with the flock, nothing has happened
ESCAPED = "escaped"        # Flip run off to the island; the shepherdess has not told the player yet
SEARCHING = "searching"    # she has asked the player to bring him back
LEADING = "leading"        # Flip on the player's leash
RETURNED = "returned"      # Flip back with the flock, her thanks waiting
DONE = "done"              # thanked; it is over
STAGES = (QUIET, ESCAPED, SEARCHING, LEADING, RETURNED, DONE)

#: Where Flip is: with the flock, on the island, or on the leash
AT_FOLD, ON_ISLAND, ON_LEASH = "fold", "island", "leash"

#: The black sheep's name: the Tiled "Name" property of his "Sheep" rectangle
FLIP = "Flip"
#: Objects on the Tiled "Movements" layer: the inside of the walled fold (a rectangle), Flip's
#: grazing strip on the island (a rectangle, as any sheep's) and the shepherdess's round in the
#: fold (a polygon, walked like a stall's)
FOLD_AREA = "Sheep_Fold"
ISLAND_ZONE = "Flip_Island"
SHEPHERDESS_ROUND = "Shepherdess_Fold"
#: The fold's gates on the Houses layer
FOLD_GATES = ("Gate_Sheep_Yard_North", "Gate_Sheep_Yard_South")

#: The evening and night Flip may slip out in, in sun hours (daylight.sun_hour): from dusk to dawn
EVENING_FROM = 18.0
MORNING_FROM = 5.0
#: How far (in tiles) the player's feet must be from the fold to have gone away
AWAY_TILES = 12
#: A jump of the clock (a rest, a minigame) is searched for an evening in steps this long, and at
#: most this far back
EVENING_SEARCH_STEP = datetime.timedelta(minutes=10)
EVENING_SEARCH_SPAN = datetime.timedelta(days=2)

#: Reputation for feigning surprise (the farmer saw them), and for owning up
LIE_REPUTATION = -3.0
CONFESS_REPUTATION = -0.5
#: What the shepherdess gives the player to lure Flip with, once
BREAD_GIFT: Dict[str, int] = {"Bread": 1}
#: What luring him uses up
LURE_GOODS: Dict[str, int] = {"Bread": 1}
#: Her thanks: her wool, or this reputation for turning it down
THANKS_GIFT: Dict[str, int] = {"Wool": 3}
THANKS_REPUTATION = 1.0
#: How much slower the player walks with Flip on the leash
LEASH_SLOWDOWN = 0.2

# The shepherdess's talks, by first page. The UI does an answer's `does`: "lie" and
# "confess" start the search, "bread" hands over BREAD_GIFT, "accept" / "decline" her thanks.
MISSING, SEARCH, BREAD, NO_BREAD, LEADING_TALK, THANKS, THANKS_NIGHT = (
    "missing", "search", "bread", "no_bread", "leading", "thanks", "thanks_night")
#: The talks that are news, with a marker over her head while they wait
NEWS = (MISSING, BREAD, THANKS, THANKS_NIGHT)

PAGES: Dict[str, Page] = {
    MISSING: Page(
        "Flip is gone! My little black one. Somebody left the gate of the fold open last evening, and "
        "when I came at first light there were only the two of them in the pen. Who would do such a thing?",
        (Answer("Oh no, who would do this?", "lie", does="lie"),
         Answer("It might have been me...", "confess", does="confess"))),
    "lie": Page(
        "Don't you look at me like that. The farmer saw you, plain as day: in through the gate and out "
        "again, and the gate left swinging behind you. He ran over to shut it, but it was too late. Flip "
        "was already gone, and nobody saw which way.",
        (Answer("I'm sorry", "ask"),)),
    "confess": Page(
        "You? Well... at least you say it to my face, that's more than most would. The farmer saw the "
        "gate swinging and ran over to shut it, but it was too late. Flip was already gone, "
        "and nobody saw which way.",
        (Answer("I'll set it right", "ask"),)),
    "ask": Page(
        "Then find him and bring him home to me. I don't know where he's got to, and that's what frightens "
        "me: he's forever wandering down to the water's edge after the green grass, and he can't swim, the "
        "silly thing. If he slips into the river... Please, look for him. He's shy of strangers, mind. "
        "Bring him back into the fold, where he belongs.",
        (Answer("I'll find Flip"),)),
    SEARCH: Page(
        "Have you seen him? I keep thinking of the rivers, and him not able to swim. Bring him back into "
        "the fold, and shut the gate behind you this time.",
        (Answer("I'm on my way"),)),
    BREAD: Page(
        "He won't come to you? No, he's shy, that one. Here, a heel of bread: he'd follow it to the end "
        "of the world. Hold it out low and let him come to you.",
        (Answer("Take the bread", does="bread"),)),
    NO_BREAD: Page(
        "I gave you my last heel of bread! The baker at the market will sell you another. Flip will "
        "follow any bread, the greedy thing.",
        (Answer("I'll buy some"),)),
    LEADING_TALK: Page(
        "Flip! Oh, you found him! Bring him in, through the gate into the fold, there's a good soul.",
        (Answer("Right away"),)),
    THANKS: Page(
        "There he is, burrs in his wool and not a care in the world! Thank you. Here, take some of my "
        "wool for your trouble. It's the best in the valley.",
        (Answer("Accept the wool", "accepted", does="accept"),
         Answer("Keep it, it was my doing", "declined", does="decline"))),
    THANKS_NIGHT: Page(
        "So it was you who put Flip back in the fold last night! I came at dawn and there he was, as if "
        "he'd never been gone. Thank you. Here, take some of my wool for your trouble.",
        (Answer("Accept the wool", "accepted", does="accept"),
         Answer("Keep it, it was my doing", "declined", does="decline"))),
    "accepted": Page(
        "And mind the gate next time, eh? I'll sleep easier tonight, knowing he's back with the others.",
        (Answer("Farewell"),)),
    "declined": Page(
        "Then I'll tell everyone at the market how you set it right. Not everyone would have gone "
        "looking for him.",
        (Answer("Farewell"),)),
}

#: What the player says to themselves, in their own speech bubble
SAY_NO_BREAD = "He won't come near me. If only I had something with me he likes to eat..."
SAY_LEASHED = "There's a good lad. Come on, Flip, let's get you home."
SAY_HOME_DAY = "Back with the others, little one. Now to tell the shepherdess."
SAY_HOME_NIGHT = "Back with the flock, little one. I'll tell the shepherdess in the morning."
#: The warning while Flip is on the leash and the player clicks a building
WARN_BUILDINGS = "Bring Flip home to the fold first."


def is_evening(moment: datetime.datetime) -> bool:
    """Whether it is evening or night by the daylight: the time Flip may slip out."""
    hour = sun_hour(moment)
    return hour >= EVENING_FROM or hour < MORNING_FROM


def first_evening(since: Optional[datetime.datetime], now: datetime.datetime) -> Optional[datetime.datetime]:
    """The first moment of evening or night after `since` up to `now` (None if there is none).

    The clock may jump (a rest through the night, a minigame), so the evening may lie between
    two updates; without `since`, only `now` counts.
    """
    if since is not None and since < now:
        moment = max(since, now - EVENING_SEARCH_SPAN) + EVENING_SEARCH_STEP
        while moment < now:
            if is_evening(moment):
                return moment
            moment += EVENING_SEARCH_STEP
    return now if is_evening(now) else None


def morning_after(moment: datetime.datetime) -> datetime.date:
    """The morning the shepherdess finds him gone: the next day's, or today's if it is past midnight."""
    return moment.date() if moment.hour < 12 else moment.date() + datetime.timedelta(days=1)


class LostSheep:
    """Where the quest for Flip has got (see the module)."""

    def __init__(self) -> None:
        self.stage: str = QUIET
        #: A fold gate the player opened is still open (not saved: the gates are shut on loading)
        self.gate_left_open: bool = False
        #: The morning the shepherdess finds him gone, and keeps the fold from
        self.missed_on: Optional[datetime.date] = None
        #: Whether the player owned up to leaving the gate open (None: not asked yet)
        self.confessed: Optional[bool] = None
        #: The player has found out that Flip will not come without bread
        self.needs_bread: bool = False
        #: The shepherdess has given them her bread
        self.bread_given: bool = False
        #: Flip was brought home while she was not there, and put back with the flock by the player
        self.at_night: bool = False
        #: The day she thanked them, which she still spends at the fold
        self.done_on: Optional[datetime.date] = None
        #: When check_escape last looked (not saved), so an evening jumped over still counts
        self.checked_at: Optional[datetime.datetime] = None

    # ------------------------------------------------------------------
    # Where things are
    # ------------------------------------------------------------------

    @property
    def flip_at(self) -> str:
        """Where Flip is: AT_FOLD, ON_ISLAND or ON_LEASH."""
        if self.stage in (ESCAPED, SEARCHING):
            return ON_ISLAND
        if self.stage == LEADING:
            return ON_LEASH
        return AT_FOLD

    @property
    def leading(self) -> bool:
        return self.stage == LEADING

    @property
    def flip_named(self) -> bool:
        """Whether the player knows him by his name (she has told them)."""
        return self.stage not in (QUIET, ESCAPED)

    def on_meadow(self, day: datetime.date) -> bool:
        """Whether the shepherdess keeps the fold on `day` instead of minding her stall."""
        if self.missed_on is None or day < self.missed_on:
            return False
        if self.stage == DONE:
            return self.done_on is not None and day <= self.done_on
        return self.stage in (ESCAPED, SEARCHING, LEADING, RETURNED)

    # ------------------------------------------------------------------
    # Flip slipping out
    # ------------------------------------------------------------------

    def gate_opened_by_player(self) -> None:
        """The player opened one of the fold's gates."""
        if self.stage == QUIET:
            self.gate_left_open = True

    def note_gates(self, any_open: bool) -> None:
        """Whether any of the fold's gates stands open now: once all are shut, the danger is past."""
        if not any_open:
            self.gate_left_open = False

    def check_escape(self, now: datetime.datetime, player_away: bool, fold_seen: bool) -> bool:
        """Let Flip slip out if the gate the player opened stands open in the evening while they are
        gone and the fold is out of sight; whether he did, just now. An evening the clock jumped
        over since the last check (a rest through the night) counts too (``first_evening``)."""
        since, self.checked_at = self.checked_at, now
        if self.stage != QUIET or not self.gate_left_open or not player_away or fold_seen:
            return False
        evening = first_evening(since, now)
        if evening is None:
            return False
        self.stage = ESCAPED
        self.gate_left_open = False
        self.missed_on = morning_after(evening)
        return True

    # ------------------------------------------------------------------
    # The shepherdess's talks
    # ------------------------------------------------------------------

    def talk(self, has_bread: bool) -> Optional[str]:
        """Her talk for the player now, by its first page; None if she has none."""
        if self.stage == ESCAPED:
            return MISSING
        if self.stage == SEARCHING:
            if self.needs_bread and not has_bread:
                return NO_BREAD if self.bread_given else BREAD
            return SEARCH
        if self.stage == LEADING:
            return LEADING_TALK
        if self.stage == RETURNED:
            return THANKS_NIGHT if self.at_night else THANKS
        return None

    def has_news(self, has_bread: bool) -> bool:
        """Whether her talk is news to the player (a marker over her head)."""
        return self.talk(has_bread) in NEWS

    def answer_missing(self, confess: bool) -> float:
        """The player lied or owned up: the search is on. Returns the reputation it costs (negative)."""
        if self.stage != ESCAPED:
            return 0.0
        self.stage = SEARCHING
        self.confessed = confess
        return CONFESS_REPUTATION if confess else LIE_REPUTATION

    def give_bread(self) -> None:
        self.bread_given = True

    # ------------------------------------------------------------------
    # Flip
    # ------------------------------------------------------------------

    def can_lure(self) -> bool:
        return self.stage == SEARCHING

    def lure(self, has_bread: bool) -> bool:
        """Hold out bread to Flip: with some he follows on the leash; without, the player learns they
        need it. Returns whether he is on the leash now."""
        if self.stage != SEARCHING:
            return False
        if not has_bread:
            self.needs_bread = True
            return False
        self.stage = LEADING
        return True

    def bring_home(self, shepherdess_there: bool) -> bool:
        """Flip is back inside the fold; whether that ended the leading just now."""
        if self.stage != LEADING:
            return False
        self.stage = RETURNED
        self.at_night = not shepherdess_there
        return True

    def finish(self, day: datetime.date) -> None:
        """She has thanked them; she spends the rest of `day` at the fold."""
        if self.stage == RETURNED:
            self.stage = DONE
            self.done_on = day

    # ------------------------------------------------------------------
    # The save
    # ------------------------------------------------------------------

    def to_save(self) -> dict:
        return {
            "stage": self.stage,
            "missed_on": self.missed_on.isoformat() if self.missed_on else None,
            "confessed": self.confessed,
            "needs_bread": self.needs_bread,
            "bread_given": self.bread_given,
            "at_night": self.at_night,
            "done_on": self.done_on.isoformat() if self.done_on else None,
        }

    def load(self, data: Optional[dict]) -> None:
        """Restore from a save; without one (an older save) nothing has happened yet."""
        self.__init__()
        if not isinstance(data, dict):
            return
        stage = data.get("stage")
        self.stage = stage if stage in STAGES else QUIET
        self.missed_on = _date(data.get("missed_on"))
        confessed = data.get("confessed")
        self.confessed = confessed if isinstance(confessed, bool) else None
        self.needs_bread = bool(data.get("needs_bread", False))
        self.bread_given = bool(data.get("bread_given", False))
        self.at_night = bool(data.get("at_night", False))
        self.done_on = _date(data.get("done_on"))
        if self.stage != QUIET and self.missed_on is None:
            self.stage = QUIET     # a broken entry: start over rather than strand her at the fold


def _date(text) -> Optional[datetime.date]:
    try:
        return datetime.date.fromisoformat(text) if text else None
    except (TypeError, ValueError):
        return None
