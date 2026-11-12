# The town council

A first piece of the roadmap's council (P6), built ahead of its turn: a pyramid of offices, the notables who hold them, and the player's way into them. It closes a step of the core loop (pillar 3): gold buys favour, favour wins a seat, and the seat pays back in coin, in lower costs and in reputation.

Code: `src/models/council.py` (the rules, no pygame), `assets/data/council.json` (the offices and the notables), `src/ui/helper_modules/council_window.py` (the window at the town hall), `session_window.py` (a session's vote played out), `src/ui/heraldry.py` (the arms). Balance values: the `COUNCIL_*`, `FAVOUR_*`, `PURSE_*`, `DELAY_*`, `FEUD_*` block in `constants.py`. Tests: `tests/models/test_council.py`, `tests/ui/test_council_window.py`.

## How it fits the rest

| Roadmap | What the council does now | What moves in later |
|---|---|---|
| Merchant rank, P2 prestige | The rank is the title that opens an office (`COUNCIL_TIER_RANKS`): no second ladder of bought titles. The player's reputation is the regard every notable has for them. | When P2 turns reputation into prestige, the ranks ask for prestige and the council follows without a change. |
| P4 dynasty | One person, one office. | Family members hold seats of their own; rhetoric becomes a skill that shifts a vote. |
| P5 rival dynasties | The 11 notables of `council.json` are stand-ins: fixed characters with a trade, a liking, an integrity and arms, who like each other more or less (`_affinity`) and challenge each other's seats. | The dynasties' members take the seats, vote by their interests, and a feud becomes a family's. |
| P6 council & treasury | An office's privileges are the holder's own (stipend, market fee, licence price, reputation, a shield in feuds). | Offices get levers on the town (taxes, tolls, public building) once the treasury can be spent; the stipends are then paid from it. |
| P8 risk | Feuds cost reputation, coin (an inspection's fine) and favour. | Courts, charges and immunity; sabotage of workshops. |
| Pillar 4, visible in the world | Not yet: a session is shown as a sheet, not on the map. | The voters walking to the town hall on the session's morning, and being met on the road. |

Deliberately left out of this first piece: courts and trials (nothing to charge anybody with yet), bought titles (the rank is the title), violence against voters (a delay is the only interference).

## The offices

Eight seats in three tiers (`council.json`). A seat pays its stipend every day (booked as income under "Council Stipend") and gives its privileges for as long as it is held.

| Tier | Rank asked | Offices | Privileges |
|---|---|---|---|
| 3 | Merchant | Mayor | 90 a day, market fee -50 %, licences -30 %, reputation +6 a season, wards off half of a feud's blows |
| 2 | Trader | Treasurer, Market Master, Master Builder, Captain of the Watch | 25 to 30 a day; licences -30 % (Treasurer), market fee -50 % (Market Master), reputation +4 (Master Builder), a feud shield (Captain) |
| 1 | Chapman | Market Warden, Town Clerk, Gate Warden | 8 to 11 a day; market fee -25 % (Warden), licences -15 % (Clerk), reputation +1 |

The ranks asked are the ones the economy can reach today (trading alone tops out near 100 coins a day, `pricing.md` §10); they are meant to move up as workshops (P3) make the higher ranks reachable.

Rules of the ladder:

- A seat asks for its tier's rank, the rank *held*: a rank lost loses the right to stand, and a seat whose holder has lost the rank is forfeit when it is next voted on.
- One step at a time: a seat may be at most one tier above the one held.
- One office per person. Winning a higher seat hands the old one to a notable without one.
- A term lasts `COUNCIL_TERM_SEASONS` (4) sessions. Then the seat is voted on again: the holder defends it (no fee), a notable with a feud stands against them, or with `CHALLENGE_CHANCE` some other one.

## Sessions and votes

The council sits once a season, on its 4th day at 10 o'clock (`session_moment`). A name must be down before that day begins (`stand`, for the tier's filing fee); the days until then are the campaign.

A seat is voted on by the holders of **its own tier and the tier above** (the mayor's by the whole council), never by a candidate. Each voter present votes for the candidate he makes the most of:

- the player: `effective_favour` (below), plus `PURSE_PLEDGE` if he took their purse;
- a notable: how well the voter likes him (`NOTABLE_AFFINITY`, fixed for a game);
- the holder of the seat: `INCUMBENT_BONUS` on top;
- everyone: the day's chance, `VOTE_NOISE`.

The most votes win; a tie leaves the seat with its holder. So favour makes a win likely and never certain, and a challenger needs a clear majority. Before the vote the window shows how each voter leans (to the player, undecided, to a rival) but not the numbers.

At a session the council also goes about its own business: the notable longest in his seat, his term over, is confirmed or, with `NPC_CHALLENGE_CHANCE`, challenged by one without a seat. The seats therefore change hands without the player too. (The player has no vote on the others' seats yet.)

## Favour

`effective_favour` = the regard everybody has for the player (`baseline`: reputation × `FAVOUR_PER_REPUTATION`, capped, plus `FAVOUR_PER_OFFICE_TIER` for a colleague) + what courting that notable has won − his grudge.

Courting:

- **A gift of coin.** A season's gifts to one notable earn `FAVOUR_GIFT_SCALE × ln(1 + given / means)`: each coin less than the last, the same shape as reputation from donations. His *means* are what he thinks a fair gift: a floor by his tier (`NOTABLE_MEANS`) or `NOTABLE_MEANS_WEALTH_SHARE` (2 %) of the giver's net wealth, whichever is more. So courting costs a share of what one has, at every stage of the game.
- **The good he is fond of**, out of the stock: worth `LIKED_GOOD_WORTH` (1.5) times its market price. The trader who has the right goods in store courts cheapest.
- **A banquet**, once a season, for every notable not at feud: `BANQUET_FAVOUR` with each.
- Gifts lift the courted favour no higher than `FAVOUR_GIFT_CEILING`; and `FAVOUR_DRIFT` of it fades each season. A seat is therefore not bought once and for all.

What the sketch warned of, and how it is answered:

| Weakness | Answer |
|---|---|
| Flat bribery without a cap | Gifts fall in worth and stop at a ceiling; costs scale with the giver's wealth; at most `PURSES_PER_ELECTION` (2) purses, each only +30 with one voter for one vote, refused by the upright (favour and reputation lost) and with `PURSE_TALK_CHANCE` talked of in the hall (pledge void, reputation and favour lost). |
| Blocking voters almost for free | One voter per election, for 2.5 times his means; it fails with 30 %, and with `DELAY_FOUND` (35 %) he learns who was behind it: a feud at once, reputation and favour lost. |
| Erratic AI | The notables do not scheme; they vote by fixed likings and the day's chance, and every draw is seeded (`Council._rng`), so a game replays the same. |

## What winning costs: feuds

Whoever the player beats bears a grudge (`FEUD_OUSTED` for a holder voted out, `FEUD_RIVAL` otherwise); so does a voter who finds out he was kept from a session. A grudge is taken off that notable's favour. From `FEUD_ACTS_FROM` on it is a feud: each season, with a chance of grudge / 100, he moves against the player:

- slander in the taverns (reputation),
- an inspection of the player's stores (a fine, a share of their money up to a cap by his tier),
- a word with every other notable (favour with all of them).

A notable at feud without a seat stands against the player when their seat is voted on again. Grudges fade by `GRUDGE_FADE` a season, or are bought off at once (`make_amends`, 4 times his means, more for a deep one). Some offices ward off a share of the blows (`feud_shield`).

## Balance

`python build_tools/Council_Trial/council_trial.py` plays headless elections over 200 seeds: a player at the least wealth and reputation of the rank a tier asks for, courting a bare majority of the voters over two seasons with gifts of coin only. Run it after changing the council's numbers. It gives:

| Courting each season | Tier 1 (Chapman) | Tier 2 (Trader) | Mayor (Merchant) |
|---|---|---|---|
| nothing but the fee | 1 % won | 6 % | 10 % |
| 1 means each | 44 % won, 17 % of wealth | 63 %, 14 % | 82 %, 17 % |
| 2 means each | 77 % won, 32 % of wealth | 91 %, 24 % | 96 %, 30 % |
| every voter and banquets | 98 %, 48 % of wealth | 100 %, 34 % | 100 %, 42 % |

The good a notable is fond of, a purse where the vote is close, and more reputation make it cheaper. A seat is meant to cost about a sixth of one's wealth for an even chance and a third for a likely win, and to pay that back over a term or two: the first tier's 8 coins a day are 900 coins over a term, against 300 to 600 spent at a Chapman's wealth.

## Loose ends

- Nothing of it shows on the map (pillar 4).
- The player has no vote on the other seats, and no way to back another candidate.
- The stipends come from nowhere; with P6 they are paid from the town's treasury.
- The privileges are personal; an office does not yet steer the town.
- Gifts to notables are booked as donations ("Council Gifts"), fees, purses, banquets and fines as miscellaneous: the depot's books have no category for politics.
- No courts, charges or immunity.
