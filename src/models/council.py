"""The town council: a pyramid of offices, the notables who hold them, and the player's way in.

A first piece of the roadmap's council (P6), built so that the later projects can move in:
the notables are stand-ins for the rival dynasties (P5), whose members will take their
seats, and an office's privileges are the holder's own until the town has a treasury to
steer (P6). `docs/council.md` has the design and what is still to come.

How it works. The merchant rank is the title that opens an office: each tier asks for a
rank (COUNCIL_TIER_RANKS), and one may only stand for a seat at most one tier above the
one held. Once a season the council sits (`session_moment`). Whoever put their name down
before that day (`stand`, for a fee) is voted on by the holders of the seat's own tier
and the one above it; a voter goes by how well he likes each candidate, the holder a
little ahead, with some chance on the day, so favour makes a win likely and never sure.

A notable's favour is the regard the player's reputation and office earn with everyone,
plus what courting him has won: gifts of coin or of the good he is fond of (each coin
worth less than the last, a season's gifts measured against his means, which grow with
the giver's wealth, and never above FAVOUR_GIFT_CEILING) and a banquet once a season.
What was won by courting fades each season. Before a vote a purse may be offered for it (he may refuse and
talk; PURSES_PER_ELECTION at most) and one voter may be kept from the session (it may
fail, and may be traced back): the vote is a thing that happens in the hall, and whoever
is not there does not vote.

Winning has its price: whoever the player beats bears a grudge, and a notable with a
grudge moves against the player season after season (slander, an inspection, whispers in
the council) and stands against them when their seat comes up again, COUNCIL_TERM_SEASONS
sessions later. Grudges fade, or are bought off (`make_amends`).

An office pays a stipend each day and gives its holder privileges (`Office`): a lower
market fee, cheaper licences, reputation each season, a shield against feuds.

Nothing here needs pygame, and every draw comes from a generator seeded by the game's
seed and what is being decided, so the same game plays out the same and no generator's
state has to be saved. `build_tools/Council_Trial/council_trial.py` plays elections
headless over many seeds, to balance its numbers.
"""

import datetime
import json
import math
import random
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..config.constants import (
    ABSENCE_CHANCE, AMENDS_MEANS, BANQUET_FAVOUR, BANQUET_MEANS, CHALLENGE_CHANCE,
    COUNCIL_DATA_PATH, COUNCIL_FILING_FEE, COUNCIL_SESSION_DAY, COUNCIL_SESSION_HOUR,
    COUNCIL_TERM_SEASONS, COUNCIL_TIER_RANKS, DAYS_PER_SEASON, DELAY_FAVOUR, DELAY_MEANS, DELAY_FOUND,
    DELAY_GRUDGE, DELAY_REPUTATION, DELAY_SUCCESS, FAVOUR_BASELINE_CAP, FAVOUR_DRIFT,
    FAVOUR_GIFT_CEILING, FAVOUR_GIFT_SCALE, FAVOUR_PER_OFFICE_TIER, FAVOUR_PER_REPUTATION,
    FEUD_ACTS_FROM, FEUD_FINE_CAP, FEUD_FINE_SHARE, FEUD_OUSTED, FEUD_RIVAL, FEUD_SLANDER_REPUTATION,
    FEUD_WHISPER_FAVOUR, GRUDGE_FADE, INCUMBENT_BONUS, LEANING_MARGIN, LIKED_GOOD_WORTH,
    NOTABLE_AFFINITY, NOTABLE_MEANS, NOTABLE_MEANS_WEALTH_SHARE, NPC_CHALLENGE_CHANCE, PURSE_MEANS, PURSE_PLEDGE, PURSE_REFUSED_FAVOUR,
    PURSE_REFUSED_REPUTATION, PURSE_SCANDAL_FAVOUR, PURSE_SCANDAL_REPUTATION, PURSE_TALK_CHANCE,
    PURSES_PER_ELECTION, THIRD_CANDIDATE_CHANCE, VOTE_NOISE,
)
from ..sim.calendar import EPOCH, season_number
from .merchant_rank import rank_index

PLAYER = "player"
PLAYER_NAME = "You"
FAVOUR_MIN, FAVOUR_MAX = -100.0, 100.0
GIFT_CATEGORY = "Council Gifts"             # the donation category gifts to notables are booked under
STIPEND_CATEGORY = "Council Stipend"        # the income category an office's pay is booked under
MINUTES_KEPT = 12                           # lines of the last sessions kept for the council's window

FAVOUR_WORDS = (                            # how a notable's favour reads, from this value up
    (60.0, "A friend"),
    (35.0, "Well disposed"),
    (12.0, "Friendly"),
    (-12.0, "Indifferent"),
    (-40.0, "Cold"),
    (FAVOUR_MIN, "Hostile"),
)
ABSENCES = (
    "kept to bed with a fever",
    "was away on business down the river",
    "sat with a sick child and sent word",
)
DELAYED = "was held up on the road and never reached the hall"


# ----------------------------------------------------------------------
# What the data file defines
# ----------------------------------------------------------------------

@dataclass(frozen=True)
class Office:
    """A seat on the council and what it gives its holder."""
    key: str
    name: str
    tier: int                       # 1 the lowest; the highest tier is the head of the council
    stipend: float                  # coins a day
    duty: str
    fee_discount: float = 0.0       # share of the market's fee the holder is spared
    licence_discount: float = 0.0   # share of a trading licence's price the holder is spared
    standing: float = 0.0           # reputation the office brings each season
    feud_shield: float = 0.0        # share of the moves made against the holder in a feud that come to nothing

    def privileges(self) -> List[str]:
        """What it gives, a line each, for the player to read."""
        lines = [f"{self.stipend:g} coins a day"]
        if self.fee_discount:
            lines.append(f"Market fee -{self.fee_discount:.0%}")
        if self.licence_discount:
            lines.append(f"Licences -{self.licence_discount:.0%}")
        if self.standing:
            lines.append(f"Reputation +{self.standing:g} a season")
        if self.feud_shield:
            lines.append(f"Wards off {self.feud_shield:.0%} of a feud's blows")
        return lines


@dataclass
class Notable:
    """One of the town's notables: a councillor, or one who may stand for a seat."""
    key: str
    name: str
    trade: str
    likes: str                      # the good he is fond of
    integrity: float                # 0 to 1: how surely he turns a purse down
    arms: Dict[str, Any]
    favour: float = 0.0             # what courting him has won the player (or lost them); fades each season
    grudge: float = 0.0             # a feud's depth; taken off his favour while it lasts
    gifts: float = 0.0              # this season's gifts from the player, for their falling worth


@dataclass
class Seat:
    holder: Optional[str]           # a notable's key, PLAYER, or None while empty
    since: int                      # the session it was won or confirmed at


@dataclass
class Candidacy:
    """The election the player is in: a seat they stand for, or their own being voted on again."""
    office: str
    session: int
    candidates: List[str]           # PLAYER among them
    defending: bool = False
    purses: Dict[str, bool] = field(default_factory=dict)   # voter -> whether he took it
    delayed: Optional[str] = None   # the voter to be kept away


@dataclass(frozen=True)
class Outcome:
    """What came of something the player tried, with the words to show for it."""
    ok: bool
    text: str


@dataclass(frozen=True)
class Vote:
    voter: str
    choice: Optional[str]           # None: he was not there
    reason: str = ""                # why not


@dataclass
class Result:
    """One seat decided at a session."""
    office: str
    candidates: List[str]
    votes: List[Vote]
    winner: Optional[str]
    holder_before: Optional[str]
    concerns_player: bool = False
    forfeited: bool = False         # the player's rank no longer allowed it: no vote was taken
    notes: List[str] = field(default_factory=list)

    def tally(self) -> Dict[str, int]:
        counts = {candidate: 0 for candidate in self.candidates}
        for vote in self.votes:
            if vote.choice is not None:
                counts[vote.choice] += 1
        return counts


@dataclass
class SessionReport:
    session: int
    date: datetime.datetime
    results: List[Result] = field(default_factory=list)

    @property
    def concerns_player(self) -> bool:
        return any(result.concerns_player for result in self.results)


def load_definitions(path: str = COUNCIL_DATA_PATH) -> Tuple[List[Office], List[Dict[str, Any]]]:
    """The offices and the notables as the data file has them (a notable's dict keeps its "office")."""
    with open(path, encoding="utf-8") as file:
        data = json.load(file)
    offices = [Office(**entry) for entry in data["offices"]]
    keys = {office.key for office in offices}
    for entry in data["notables"]:
        if entry.get("office") is not None and entry["office"] not in keys:
            raise ValueError(f"council.json: {entry['key']} holds an unknown office {entry['office']!r}")
    return offices, list(data["notables"])


def session_moment(session: int) -> datetime.datetime:
    """When the council sits in the season of that number."""
    day = EPOCH + datetime.timedelta(days=session * DAYS_PER_SEASON + COUNCIL_SESSION_DAY - 1)
    return datetime.datetime.combine(day, datetime.time(COUNCIL_SESSION_HOUR))


def favour_word(value: float) -> str:
    for threshold, word in FAVOUR_WORDS:
        if value >= threshold:
            return word
    return FAVOUR_WORDS[-1][1]


def _clamp(value: float) -> float:
    return max(FAVOUR_MIN, min(FAVOUR_MAX, value))


# ----------------------------------------------------------------------
# The council
# ----------------------------------------------------------------------

class Council:
    def __init__(self, depot: Any, player: Any, merchant_rank: Any, goods: List[Any], seed: int = 0,
                 definitions: Optional[Tuple[List[Office], List[Dict[str, Any]]]] = None) -> None:
        self.depot = depot
        self.player = player
        self.merchant_rank = merchant_rank
        self.goods = goods
        self.seed = seed
        offices, notables = definitions if definitions is not None else load_definitions()
        self._notable_entries: List[Dict[str, Any]] = [dict(entry) for entry in notables]
        self.offices: Dict[str, Office] = {office.key: office for office in offices}
        self.top_tier: int = max(office.tier for office in offices)
        self._reset()
        self.on_log: Callable[[str], None] = lambda text: None   # the game's ledger

    def _reset(self) -> None:
        """The council as the data file has it, before the player has had anything to do with it."""
        self.notables: Dict[str, Notable] = {}
        self.seats: Dict[str, Seat] = {key: Seat(None, 0) for key in self.offices}
        for index, entry in enumerate(self._notable_entries):
            entry = dict(entry)
            office = entry.pop("office", None)
            self.notables[entry["key"]] = Notable(**entry)
            if office is not None:
                # Terms run out at different sessions, so the seats do not all come up at once
                self.seats[office] = Seat(entry["key"], -(index % COUNCIL_TERM_SEASONS))
        self.candidacy: Optional[Candidacy] = None
        self.last_session: int = -1                 # the last session held
        self.banquet_session: Optional[int] = None  # the season the last banquet was given in
        self.minutes: List[str] = []                # what the last sessions decided, newest last

    # -- who is who --------------------------------------------------------

    def name_of(self, who: Optional[str]) -> str:
        if who is None:
            return "Nobody"
        return PLAYER_NAME if who == PLAYER else self.notables[who].name

    def office_of(self, who: str) -> Optional[Office]:
        for key, seat in self.seats.items():
            if seat.holder == who:
                return self.offices[key]
        return None

    @property
    def player_office(self) -> Optional[Office]:
        return self.office_of(PLAYER)

    def tier_of(self, who: str) -> int:
        office = self.office_of(who)
        return office.tier if office else 0

    def seatless(self) -> List[str]:
        """The notables without a seat, in the data file's order."""
        seated = {seat.holder for seat in self.seats.values()}
        return [key for key in self.notables if key not in seated]

    def means(self, key: str) -> float:
        """What this notable thinks a fair gift from the player: the more the higher his office and
        the richer the giver. Gifts are measured against it, and a purse, a delay and amends are
        multiples of it."""
        wealth = max(self.depot.net_wealth(self.goods), self.depot.money)
        return float(round(max(NOTABLE_MEANS[self._cost_tier(key)], NOTABLE_MEANS_WEALTH_SHARE * wealth)))

    def _cost_tier(self, key: str) -> int:
        return max(1, self.tier_of(key))

    def rank_needed(self, office: Office) -> str:
        return COUNCIL_TIER_RANKS[office.tier]

    def has_rank(self, office: Office) -> bool:
        return self.merchant_rank.level >= rank_index(self.rank_needed(office))

    def electorate(self, office_key: str, candidates: List[str]) -> List[str]:
        """Who votes on a seat: the holders of its tier and the one above (everyone, for the head
        of the council), but no candidate. The player does not vote: they are only ever a candidate
        here, and sit out the votes on the others' seats."""
        tier = self.offices[office_key].tier
        tiers = (tier, tier + 1) if tier < self.top_tier else tuple(range(1, self.top_tier + 1))
        return [seat.holder for key, seat in self.seats.items()
                if self.offices[key].tier in tiers and seat.holder not in (None, PLAYER)
                and seat.holder not in candidates]

    def _rng(self, *tags: Any) -> random.Random:
        return random.Random("|".join(str(part) for part in (self.seed, *tags)))

    # -- the calendar ------------------------------------------------------

    def session_open_for(self, date: datetime.datetime) -> int:
        """The session a name put down now is voted on at: this season's, until its day begins."""
        session = season_number(date)
        closes = session_moment(session).replace(hour=0)
        return session if date < closes else session + 1

    def next_session(self, date: datetime.datetime) -> datetime.datetime:
        session = season_number(date)
        return session_moment(session if self.last_session < session else session + 1)

    def term_ends(self, office_key: str) -> int:
        """The session a seat is voted on again at."""
        return self.seats[office_key].since + COUNCIL_TERM_SEASONS

    # -- favour ------------------------------------------------------------

    def baseline(self) -> float:
        """The regard every notable has for the player before any courting: their reputation, and their office."""
        from_reputation = min(FAVOUR_BASELINE_CAP, max(0.0, self.player.reputation) * FAVOUR_PER_REPUTATION)
        return from_reputation + FAVOUR_PER_OFFICE_TIER * self.tier_of(PLAYER)

    def effective_favour(self, key: str) -> float:
        """What a notable makes of the player: the council's regard for them (`baseline`), what
        courting him has won, less his grudge."""
        notable = self.notables[key]
        return _clamp(self.baseline() + notable.favour - notable.grudge)

    def in_feud(self, key: str) -> bool:
        return self.notables[key].grudge >= FEUD_ACTS_FROM

    def gift_gain(self, key: str, worth: float) -> float:
        """The favour a gift worth that much would win now: less the more was given this season,
        and nothing above FAVOUR_GIFT_CEILING."""
        notable = self.notables[key]
        if worth <= 0:
            return 0.0
        means = self.means(key)
        gain = FAVOUR_GIFT_SCALE * (math.log1p((notable.gifts + worth) / means) - math.log1p(notable.gifts / means))
        return max(0.0, min(gain, FAVOUR_GIFT_CEILING - notable.favour))

    def _credit_gift(self, key: str, worth: float) -> float:
        gain = self.gift_gain(key, worth)
        notable = self.notables[key]
        notable.favour = _clamp(notable.favour + gain)
        notable.gifts += worth
        return gain

    def gift_money(self, key: str, amount: float) -> Outcome:
        notable = self.notables[key]
        if not self.depot.book_donation(amount, category=GIFT_CATEGORY):
            return Outcome(False, "You have not the coin for such a gift.")
        gain = self._credit_gift(key, amount)
        self.on_log(f"A gift of {amount:,.0f}g to {notable.name} (favour +{gain:.1f})")
        return Outcome(True, self._thanks(notable, gain))

    def liked_lot(self, key: str) -> int:
        """How many of the good he is fond of make a fair gift at today's price."""
        price = self._price(self.notables[key].likes)
        return max(1, round(self.means(key) / LIKED_GOOD_WORTH / price)) if price > 0 else 1

    def gift_goods(self, key: str, quantity: int) -> Outcome:
        """Send him the good he is fond of, out of the stock; it counts for more than its price."""
        notable = self.notables[key]
        value = self.depot.donate_goods({notable.likes: quantity}, self.goods, GIFT_CATEGORY)
        if value is None:
            return Outcome(False, f"You have not {quantity} {notable.likes} in store.")
        gain = self._credit_gift(key, value * LIKED_GOOD_WORTH)
        self.on_log(f"{quantity} {notable.likes} sent to {notable.name} (favour +{gain:.1f})")
        return Outcome(True, self._thanks(notable, gain))

    @staticmethod
    def _thanks(notable: Notable, gain: float) -> str:
        if gain < 0.5:
            return f"{notable.name} thanks you politely. Gifts alone will win no more here."
        return f"{notable.name} is pleased. Favour +{gain:.0f}"

    def _price(self, good_name: str) -> float:
        for good in self.goods:
            if good.name == good_name:
                return good.get_price()
        return 0.0

    # -- the banquet -------------------------------------------------------

    def banquet_guests(self) -> List[str]:
        """Every notable but those with a feud, who would not sit at the player's table."""
        return [key for key in self.notables if not self.in_feud(key)]

    def banquet_cost(self) -> float:
        return float(round(BANQUET_MEANS * sum(self.means(key) for key in self.banquet_guests())))

    def banquet_given(self, date: datetime.datetime) -> bool:
        return self.banquet_session == season_number(date)

    def host_banquet(self, date: datetime.datetime) -> Outcome:
        if self.banquet_given(date):
            return Outcome(False, "You have feasted the town's notables this season already.")
        guests = self.banquet_guests()
        if not guests:
            return Outcome(False, "Nobody would come.")
        cost = self.banquet_cost()
        if not self.depot.book_miscellaneous(cost):
            return Outcome(False, "You have not the coin for a banquet.")
        for key in guests:
            self.notables[key].favour = _clamp(self.notables[key].favour + BANQUET_FAVOUR)
        self.banquet_session = season_number(date)
        self.on_log(f"A banquet for {len(guests)} notables, {cost:,.0f}g")
        return Outcome(True, f"{len(guests)} notables sat at your table. Favour +{BANQUET_FAVOUR:.0f} with each.")

    # -- standing for a seat -----------------------------------------------

    def filing_fee(self, office: Office) -> float:
        return COUNCIL_FILING_FEE[office.tier]

    def can_stand(self, office_key: str) -> Outcome:
        """Whether the player may put their name down for this seat, and if not, why."""
        office = self.offices[office_key]
        own = self.player_office
        if own is not None and own.key == office_key:
            return Outcome(False, "This seat is yours.")
        if self.candidacy is not None:
            return Outcome(False, f"Your name is down for {self.offices[self.candidacy.office].name} already.")
        if not self.has_rank(office):
            return Outcome(False, f"Asks for the rank of {self.rank_needed(office)}.")
        if office.tier > self.tier_of(PLAYER) + 1:
            return Outcome(False, "One step at a time: hold an office of the tier below first.")
        if self.depot.money < self.filing_fee(office):
            return Outcome(False, f"Putting your name down costs {self.filing_fee(office):,.0f} coins.")
        return Outcome(True, "")

    def stand(self, office_key: str, date: datetime.datetime) -> Outcome:
        allowed = self.can_stand(office_key)
        if not allowed.ok:
            return allowed
        office = self.offices[office_key]
        self.depot.book_miscellaneous(self.filing_fee(office))
        session = self.session_open_for(date)
        candidates = [PLAYER]
        holder = self.seats[office_key].holder
        if holder is not None:
            candidates.append(holder)
        rng = self._rng("third", session, office_key)
        others = self.seatless()
        if holder is not None and others and rng.random() < THIRD_CANDIDATE_CHANCE:
            candidates.append(rng.choice(others))
        self.candidacy = Candidacy(office_key, session, candidates)
        self.on_log(f"Name put down for {office.name} ({self.filing_fee(office):,.0f}g)")
        return Outcome(True, f"Your name is down for {office.name}.")

    def withdraw(self) -> Outcome:
        """Take the name off the list; the fee is not given back. A seat being defended cannot be
        withdrawn from, only resigned."""
        if self.candidacy is None or self.candidacy.defending:
            return Outcome(False, "There is nothing to withdraw from.")
        office = self.offices[self.candidacy.office]
        self.candidacy = None
        self.on_log(f"Name withdrawn from the vote on {office.name}")
        return Outcome(True, f"You no longer stand for {office.name}.")

    def resign(self) -> Outcome:
        office = self.player_office
        if office is None:
            return Outcome(False, "You hold no office.")
        if self.candidacy is not None and self.candidacy.defending:
            self.candidacy = None
        successor = self._appoint(office.key, self.last_session, self._rng("resign", self.last_session, office.key))
        self.on_log(f"Resigned as {office.name}")
        return Outcome(True, f"You lay down the office of {office.name}. {self.name_of(successor)} takes the seat.")

    def _appoint(self, office_key: str, session: int, rng: random.Random, avoid: Tuple[str, ...] = ()) -> Optional[str]:
        """Fill a seat without a vote with a notable who has none (not one of *avoid*, if there is a choice)."""
        free = self.seatless()
        choice = [key for key in free if key not in avoid] or free
        holder = rng.choice(choice) if choice else None
        self.seats[office_key] = Seat(holder, session)
        return holder

    # -- before the vote ---------------------------------------------------

    def is_voter(self, key: str) -> bool:
        return self.candidacy is not None and key in self.electorate(self.candidacy.office, self.candidacy.candidates)

    def purse_cost(self, key: str) -> float:
        return round(PURSE_MEANS * self.means(key))

    def can_offer_purse(self, key: str) -> Outcome:
        if not self.is_voter(key):
            return Outcome(False, "Has no vote in your election.")
        if key in self.candidacy.purses:
            return Outcome(False, "You have tried that already.")
        if len(self.candidacy.purses) >= PURSES_PER_ELECTION:
            return Outcome(False, "More purses than that and the whole town would know.")
        if self.depot.money < self.purse_cost(key):
            return Outcome(False, f"The purse would have to hold {self.purse_cost(key):,.0f} coins.")
        return Outcome(True, "")

    def offer_purse(self, key: str) -> Outcome:
        """Offer a voter a purse for his vote. He takes it or he does not, by his integrity and
        how he likes the player; refused, the coin stays but he thinks the less of them."""
        allowed = self.can_offer_purse(key)
        if not allowed.ok:
            return allowed
        notable = self.notables[key]
        candidacy = self.candidacy
        chance = (1.0 - notable.integrity) + self.effective_favour(key) / 200.0
        taken = notable.grudge <= 0 and self._rng("purse", candidacy.session, key).random() < chance
        candidacy.purses[key] = taken
        if taken:
            cost = self.purse_cost(key)
            self.depot.book_miscellaneous(cost)
            self.on_log(f"A purse of {cost:,.0f}g for {notable.name}, taken")
            return Outcome(True, f"{notable.name} weighs the purse and puts it away without a word.")
        notable.favour = _clamp(notable.favour - PURSE_REFUSED_FAVOUR)
        self.player.change_reputation(-PURSE_REFUSED_REPUTATION)
        self.on_log(f"A purse for {notable.name}, refused (reputation -{PURSE_REFUSED_REPUTATION:g})")
        return Outcome(False, f"{notable.name} pushes the purse back across the table, and will not keep quiet about it.")

    def delay_cost(self, key: str) -> float:
        return round(DELAY_MEANS * self.means(key))

    def can_arrange_delay(self, key: str) -> Outcome:
        if not self.is_voter(key):
            return Outcome(False, "Has no vote in your election.")
        if self.candidacy.delayed is not None:
            return Outcome(False, "One empty chair is chance. Two would be noticed.")
        if self.depot.money < self.delay_cost(key):
            return Outcome(False, f"The men for that ask {self.delay_cost(key):,.0f} coins.")
        return Outcome(True, "")

    def arrange_delay(self, key: str) -> Outcome:
        """Pay to have one voter kept from the session; what comes of it shows on the day."""
        allowed = self.can_arrange_delay(key)
        if not allowed.ok:
            return allowed
        cost = self.delay_cost(key)
        self.depot.book_miscellaneous(cost)
        self.candidacy.delayed = key
        self.on_log(f"Men paid {cost:,.0f}g to keep {self.notables[key].name} from the session")
        return Outcome(True, f"It is arranged. Whether {self.notables[key].name} reaches the hall, the day will show.")

    def amends_cost(self, key: str) -> float:
        return round(AMENDS_MEANS * self.means(key) * max(1.0, self.notables[key].grudge / 40.0))

    def make_amends(self, key: str) -> Outcome:
        notable = self.notables[key]
        if notable.grudge <= 0:
            return Outcome(False, "There is nothing between you.")
        cost = self.amends_cost(key)
        if not self.depot.book_miscellaneous(cost):
            return Outcome(False, f"Amends would cost {cost:,.0f} coins.")
        notable.grudge = 0.0
        self.on_log(f"Amends made to {notable.name}, {cost:,.0f}g")
        return Outcome(True, f"{notable.name} takes your hand. The feud is over.")

    # -- how the vote stands -----------------------------------------------

    def _affinity(self, voter: str, candidate: str) -> float:
        """How well one notable likes another: fixed for a game, within NOTABLE_AFFINITY."""
        low, high = NOTABLE_AFFINITY
        return low + (high - low) * self._rng("affinity", voter, candidate).random()

    def _score(self, voter: str, candidate: str, office_key: str, purses: Dict[str, bool]) -> float:
        """What a voter makes of a candidate, before the day's chance."""
        if candidate == PLAYER:
            score = self.effective_favour(voter) + (PURSE_PLEDGE if purses.get(voter) else 0.0)
        else:
            score = self._affinity(voter, candidate)
        if candidate == self.seats[office_key].holder:
            score += INCUMBENT_BONUS
        return score

    def leaning(self, voter: str) -> Tuple[Optional[str], float]:
        """Whom a voter leans to in the player's election (None: undecided), and by how much he
        is for the player (negative: against)."""
        candidacy = self.candidacy
        mine = self._score(voter, PLAYER, candidacy.office, candidacy.purses)
        rivals = [(self._score(voter, c, candidacy.office, candidacy.purses), c)
                  for c in candidacy.candidates if c != PLAYER]
        if not rivals:
            return PLAYER, FAVOUR_MAX
        best, rival = max(rivals)
        margin = mine - best
        if margin >= LEANING_MARGIN:
            return PLAYER, margin
        if margin <= -LEANING_MARGIN:
            return rival, margin
        return None, margin

    def forecast(self) -> Tuple[int, int, int]:
        """Voters leaning to the player, undecided, and leaning to somebody else."""
        voters = self.electorate(self.candidacy.office, self.candidacy.candidates)
        leanings = [self.leaning(voter)[0] for voter in voters]
        mine = sum(1 for who in leanings if who == PLAYER)
        open_ = sum(1 for who in leanings if who is None)
        return mine, open_, len(voters) - mine - open_

    # -- the session -------------------------------------------------------

    def update(self, date: datetime.datetime) -> Optional[SessionReport]:
        """Hold the session once its hour has come; returns what it decided."""
        session = season_number(date)
        if self.last_session >= session or date < session_moment(session):
            return None
        self._call_defence(session)
        report = self._hold_session(session, date)
        self.last_session = session
        for result in report.results:
            self._record(result, date)
        return report

    def _record(self, result: Result, date: datetime.datetime) -> None:
        office = self.offices[result.office]
        if result.forfeited:
            line = f"{office.name}: forfeited, {self.name_of(result.winner)} takes the seat"
        elif len(result.candidates) == 1:
            line = f"{office.name}: {self.name_of(result.winner)} confirmed unopposed"
        else:
            tally = result.tally()
            count = ", ".join(f"{self.name_of(c)} {tally[c]}" for c in result.candidates)
            kept = result.winner == result.holder_before
            line = f"{office.name}: {self.name_of(result.winner)} {'keeps' if kept else 'wins'} the seat ({count})"
        self.minutes.append(line)
        del self.minutes[:-MINUTES_KEPT]
        self.on_log(line)

    def _call_defence(self, session: int) -> Optional[Candidacy]:
        """When the player's term is up and they stand for nothing else, their seat is voted on:
        a notable with a feud stands against them, or with a chance some other one."""
        office = self.player_office
        if office is None or self.candidacy is not None or session < self.term_ends(office.key):
            return None
        candidates = [PLAYER]
        free = self.seatless()
        feuding = sorted((key for key in free if self.in_feud(key)), key=lambda k: -self.notables[k].grudge)
        rng = self._rng("challenge", session, office.key)
        if feuding:
            candidates.append(feuding[0])
        elif free and rng.random() < CHALLENGE_CHANCE:
            candidates.append(rng.choice(free))
        self.candidacy = Candidacy(office.key, session, candidates, defending=True)
        return self.candidacy

    def _hold_session(self, session: int, date: datetime.datetime) -> SessionReport:
        report = SessionReport(session, date)
        candidacy = self.candidacy
        if candidacy is not None and candidacy.session <= session:
            report.results.append(self._decide_player(candidacy, session))
            self.candidacy = None
        other = self._decide_others(session, skip=report.results[0].office if report.results else None)
        if other is not None:
            report.results.append(other)
        return report

    def _vote(self, office_key: str, candidates: List[str], voters: List[str], absent: Dict[str, str],
              purses: Dict[str, bool], rng: random.Random) -> Tuple[List[Vote], str]:
        """Each voter present votes for whom he makes the most of on the day; the most votes win,
        and a tie leaves the seat with its holder (else with the one the hall thinks most of)."""
        votes: List[Vote] = []
        esteem = {candidate: 0.0 for candidate in candidates}
        for voter in voters:
            if voter in absent:
                votes.append(Vote(voter, None, absent[voter]))
                continue
            seen = {c: self._score(voter, c, office_key, purses) + rng.gauss(0.0, VOTE_NOISE) for c in candidates}
            for candidate, value in seen.items():
                esteem[candidate] += value
            votes.append(Vote(voter, max(candidates, key=lambda c: seen[c])))
        counts = {c: sum(1 for vote in votes if vote.choice == c) for c in candidates}
        most = max(counts.values())
        tied = [c for c in candidates if counts[c] == most]
        holder = self.seats[office_key].holder
        if len(tied) == 1:
            winner = tied[0]
        elif holder in tied:
            winner = holder
        else:
            winner = max(tied, key=lambda c: esteem[c])
        return votes, winner

    def _others_cool(self, voters: List[str], but: str, by: float) -> None:
        for voter in voters:
            if voter != but:
                self.notables[voter].favour = _clamp(self.notables[voter].favour - by)

    def _decide_player(self, candidacy: Candidacy, session: int) -> Result:
        """The vote the player is in: what was arranged before it comes due, then the vote, then
        the seats change hands and the beaten bear their grudge."""
        office = self.offices[candidacy.office]
        seat = self.seats[office.key]
        holder = seat.holder
        rng = self._rng("session", session, office.key)
        result = Result(office.key, list(candidacy.candidates), [], holder, holder, concerns_player=True)
        rivals = [c for c in candidacy.candidates if c != PLAYER]

        if not self.has_rank(office):
            result.forfeited = True
            if candidacy.defending:
                result.winner = rivals[0] if rivals else self._appoint(office.key, session, rng)
                self.seats[office.key] = Seat(result.winner, session)
                result.notes.append(f"You are no longer a {self.rank_needed(office)}: the seat is forfeit.")
            else:
                result.notes.append(f"You are no longer a {self.rank_needed(office)}: your name was struck from the list.")
            return result

        voters = self.electorate(office.key, candidacy.candidates)
        purses = dict(candidacy.purses)
        for voter in [v for v in voters if purses.get(v)]:
            if rng.random() < PURSE_TALK_CHANCE:
                purses[voter] = False
                self.player.change_reputation(-PURSE_SCANDAL_REPUTATION)
                self._others_cool(voters, voter, PURSE_SCANDAL_FAVOUR)
                result.notes.append(f"Your purse for {self.name_of(voter)} was the talk of the hall before the vote. "
                                    f"Reputation -{PURSE_SCANDAL_REPUTATION:g}")

        absent: Dict[str, str] = {}
        target = candidacy.delayed
        if target in voters:
            if rng.random() < DELAY_SUCCESS:
                absent[target] = DELAYED
            if rng.random() < DELAY_FOUND:
                self.notables[target].grudge += DELAY_GRUDGE
                self.player.change_reputation(-DELAY_REPUTATION)
                self._others_cool(voters, target, DELAY_FAVOUR)
                result.notes.append(f"{self.name_of(target)} has learned whose men stood in the road. "
                                    f"Reputation -{DELAY_REPUTATION:g}")
        for voter in voters:
            if voter not in absent and rng.random() < ABSENCE_CHANCE:
                absent[voter] = rng.choice(ABSENCES)

        if rivals:
            result.votes, result.winner = self._vote(office.key, candidacy.candidates, voters, absent, purses, rng)
        else:
            result.winner = PLAYER

        if result.winner == PLAYER:
            old = self.player_office
            self.seats[office.key] = Seat(PLAYER, session)
            for rival in rivals:
                self.notables[rival].grudge += FEUD_OUSTED if rival == holder and not candidacy.defending else FEUD_RIVAL
                result.notes.append(f"{self.name_of(rival)} will not forget this.")
            if old is not None and old.key != office.key:
                successor = self._appoint(old.key, session, rng, avoid=tuple(rivals))
                result.notes.append(f"{self.name_of(successor)} takes your place as {old.name}.")
        else:
            self.seats[office.key] = Seat(result.winner, session)
        return result

    def _decide_others(self, session: int, skip: Optional[str]) -> Optional[Result]:
        """The council's own business: the notable longest in his seat, his term over, is confirmed
        or, with a chance, challenged by one without a seat."""
        due = [key for key, seat in self.seats.items()
               if key != skip and seat.holder not in (None, PLAYER) and session >= self.term_ends(key)]
        if not due:
            return None
        office_key = min(due, key=lambda key: self.seats[key].since)
        holder = self.seats[office_key].holder
        rng = self._rng("council", session, office_key)
        free = self.seatless()
        candidates = [holder]
        if free and rng.random() < NPC_CHALLENGE_CHANCE:
            candidates.append(rng.choice(free))
        result = Result(office_key, candidates, [], holder, holder)
        if len(candidates) > 1:
            voters = self.electorate(office_key, candidates)
            absent = {voter: rng.choice(ABSENCES) for voter in voters if rng.random() < ABSENCE_CHANCE}
            result.votes, result.winner = self._vote(office_key, candidates, voters, absent, {}, rng)
        self.seats[office_key] = Seat(result.winner, session)
        return result

    # -- daily and seasonal ------------------------------------------------

    def daily_stipend(self) -> float:
        office = self.player_office
        return office.stipend if office else 0.0

    def fee_discount(self) -> float:
        office = self.player_office
        return office.fee_discount if office else 0.0

    def licence_discount(self) -> float:
        office = self.player_office
        return office.licence_discount if office else 0.0

    def new_season(self, date: datetime.datetime) -> List[str]:
        """Favour drifts back, grudges fade, the office brings its reputation, and those with a
        feud make their move; returns what the player is to be told."""
        session = season_number(date)
        notices: List[str] = []
        office = self.player_office
        if office is not None and office.standing:
            self.player.change_reputation(office.standing)
        for notable in self.notables.values():
            notable.gifts = 0.0
            notable.favour = _clamp(notable.favour * (1.0 - FAVOUR_DRIFT))
            notable.grudge = max(0.0, notable.grudge - GRUDGE_FADE)
        shield = office.feud_shield if office else 0.0
        for key in self.notables:
            if self.in_feud(key):
                notice = self._feud_move(key, session, shield)
                if notice:
                    notices.append(notice)
        defence = self._call_defence(session)
        if defence is not None:
            held = self.offices[defence.office].name
            rivals = [self.name_of(c) for c in defence.candidates if c != PLAYER]
            against = f"{rivals[0]} stands against you." if rivals else "Nobody has put a name down against you so far."
            notices.append(f"Your term as {held} is over.\nThe council votes on your seat this season.\n**{against}**")
        return notices

    def _feud_move(self, key: str, session: int, shield: float) -> Optional[str]:
        """What a notable with a feud does to the player this season, if anything."""
        notable = self.notables[key]
        rng = self._rng("feud", session, key)
        if rng.random() >= notable.grudge / 100.0:
            return None
        if rng.random() < shield:
            self.on_log(f"{notable.name} moved against you, and your office turned it aside")
            return None
        move = rng.choice(("slander", "inspection", "whispers"))
        if move == "inspection" and self.depot.money > 0:
            fine = round(min(self.depot.money * FEUD_FINE_SHARE, FEUD_FINE_CAP[self._cost_tier(key)]))
            if fine >= 1 and self.depot.book_miscellaneous(fine):
                self.on_log(f"{notable.name} had your stores inspected: fined {fine:,.0f}g")
                return (f"{notable.name} had the wardens go through your stores.\n"
                        f"They found fault, as they were meant to.\n**Fined {fine:,.0f} coins**")
        if move == "whispers":
            for other in self.notables.values():
                if other.key != key:
                    other.favour = _clamp(other.favour - FEUD_WHISPER_FAVOUR)
            self.on_log(f"{notable.name} turned the council against you (favour -{FEUD_WHISPER_FAVOUR:g})")
            return (f"{notable.name} has had a quiet word with every notable in town.\n"
                    f"**Favour -{FEUD_WHISPER_FAVOUR:g} with each of them**")
        loss = FEUD_SLANDER_REPUTATION + notable.grudge / 20.0
        self.player.change_reputation(-loss)
        self.on_log(f"{notable.name} slandered you (reputation -{loss:.1f})")
        return f"{notable.name} has been speaking against you in the taverns.\n**Reputation -{loss:.1f}**"

    # -- saving ------------------------------------------------------------

    def to_save(self) -> Dict[str, Any]:
        candidacy = self.candidacy
        return {
            "seed": self.seed,
            "last_session": self.last_session,
            "banquet_session": self.banquet_session,
            "minutes": list(self.minutes),
            "seats": {key: {"holder": seat.holder, "since": seat.since} for key, seat in self.seats.items()},
            "notables": {key: {"favour": n.favour, "grudge": n.grudge, "gifts": n.gifts}
                         for key, n in self.notables.items()},
            "candidacy": None if candidacy is None else {
                "office": candidacy.office, "session": candidacy.session,
                "candidates": list(candidacy.candidates), "defending": candidacy.defending,
                "purses": dict(candidacy.purses), "delayed": candidacy.delayed,
            },
        }

    def load(self, saved: Optional[Dict[str, Any]], date: datetime.datetime, seed: Optional[int] = None) -> None:
        """Take over a save's council. A save from before it starts with the data file's council,
        its next session the first one still to come."""
        self._reset()
        if seed is not None:
            self.seed = seed
        if not saved:
            session = season_number(date)
            self.last_session = session if date >= session_moment(session) else session - 1
            return
        self.seed = saved.get("seed", self.seed)
        self.last_session = int(saved.get("last_session", -1))
        self.banquet_session = saved.get("banquet_session")
        self.minutes = list(saved.get("minutes", []))
        known = set(self.notables) | {PLAYER}
        for key, entry in saved.get("seats", {}).items():
            if key in self.seats:
                holder = entry.get("holder")
                self.seats[key] = Seat(holder if holder in known else None, int(entry.get("since", 0)))
        # A notable the save seats twice (the data file changed) keeps the first seat only
        seen = set()
        for key, seat in self.seats.items():
            if seat.holder in seen:
                seat.holder = None
            elif seat.holder is not None:
                seen.add(seat.holder)
        for key, entry in saved.get("notables", {}).items():
            if key in self.notables:
                notable = self.notables[key]
                notable.favour = _clamp(float(entry.get("favour", 0.0)))
                notable.grudge = max(0.0, float(entry.get("grudge", 0.0)))
                notable.gifts = max(0.0, float(entry.get("gifts", 0.0)))
        entry = saved.get("candidacy")
        self.candidacy = None
        if entry and entry.get("office") in self.offices:
            candidates = [c for c in entry.get("candidates", []) if c in known]
            if PLAYER in candidates:
                self.candidacy = Candidacy(
                    entry["office"], int(entry["session"]), candidates, bool(entry.get("defending", False)),
                    {k: bool(v) for k, v in entry.get("purses", {}).items() if k in self.notables},
                    entry.get("delayed") if entry.get("delayed") in self.notables else None)
