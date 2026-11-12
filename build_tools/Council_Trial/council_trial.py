"""What a seat on the council costs: headless elections over many seeds.

    python build_tools/Council_Trial/council_trial.py            # 200 seeds per line
    python build_tools/Council_Trial/council_trial.py --seeds 50

A player at the least wealth and reputation of the rank a tier asks for stands for a
seat of that tier and courts a bare majority of its voters (the cheapest ones, and those
who like the holder least) with gifts of coin over two seasons; "lavish" courts every
voter and gives a banquet each season too. Printed per way of courting and seat: how
often the seat was won, and what was spent, in coins and as a share of the wealth.

Run it after changing the council's numbers in constants.py or council.json
(docs/council.md, "Balance", has the table it is meant to give).
"""

import argparse
import datetime
import os
import sys
from types import SimpleNamespace
from typing import Optional, Tuple

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

from src.config.constants import COUNCIL_TIER_RANKS, MERCHANT_RANKS    # noqa: E402
from src.models.council import Council, PLAYER, session_moment        # noqa: E402
from src.models.depot import Depot                                    # noqa: E402
from src.models.merchant_rank import rank_index                       # noqa: E402
from src.models.player import Player                                  # noqa: E402

SEASONS = 2                         # how long the seat is courted for
MIN_WEALTH = 500                    # a rank asking for less wealth is played with this much
WAYS = (("the fee alone", 0.0, False), ("1/2 means a season", 0.5, False), ("1 means a season", 1.0, False),
        ("2 means a season", 2.0, False), ("lavish: all voters, banquets", 1.5, True))


def trial(seed: int, office_key: str, gift: float, lavish: bool) -> Tuple[bool, float, float]:
    """One election; returns whether the seat was won, what was spent and the wealth started with."""
    reference = Council(None, None, None, [], seed=seed)
    tier = reference.offices[office_key].tier
    rank_name = COUNCIL_TIER_RANKS[tier]
    row = next(rank for rank in MERCHANT_RANKS if rank[0] == rank_name)
    wealth = max(row[1], MIN_WEALTH)
    depot = Depot(money=wealth, fee_rate=0.0, storage_capacity=0)
    player = Player(name="Candidate", cost_of_living=0)
    player.reputation = float(row[4])
    council = Council(depot, player, SimpleNamespace(level=rank_index(rank_name)), [], seed=seed)
    below: Optional[str] = next((key for key, office in council.offices.items() if office.tier == tier - 1), None)
    if below is not None:           # one step at a time: the candidate holds a seat of the tier below
        council.seats[below].holder = PLAYER
    council.last_session = 0

    holder = council.seats[office_key].holder
    for session in range(1, SEASONS + 1):
        date = session_moment(session) - datetime.timedelta(days=2)
        if session == SEASONS:
            council.candidacy = None            # a defence the old seat's term may have called
            council.stand(office_key, date)
        voters = council.electorate(office_key, [PLAYER, holder])
        if lavish:
            council.host_banquet(date)
            courted = voters
        else:
            courted = sorted(voters, key=lambda v: (council.means(v), council._affinity(v, holder)))
            courted = courted[:len(voters) // 2 + 1]
        for voter in courted:
            council.gift_money(voter, council.means(voter) * gift)
        if session < SEASONS:
            council.new_season(session_moment(session + 1) - datetime.timedelta(days=3))
    report = council.update(session_moment(SEASONS))
    result = next(r for r in report.results if r.concerns_player)
    return result.winner == PLAYER, wealth - depot.money, wealth


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seeds", type=int, default=200)
    args = parser.parse_args()
    offices = Council(None, None, None, [], seed=0).offices
    for label, gift, lavish in WAYS:
        print(label)
        for key, office in offices.items():
            won = spent = wealth = 0.0
            for seed in range(args.seeds):
                seat, cost, wealth = trial(seed, key, gift, lavish)
                won += seat
                spent += cost
            spent /= args.seeds
            print(f"  {office.name:22s} tier {office.tier} ({COUNCIL_TIER_RANKS[office.tier]:9s}) "
                  f"won {won / args.seeds:4.0%}   spent {spent:8,.0f} of {wealth:8,.0f} ({spent / wealth:.0%})")


if __name__ == "__main__":
    main()
