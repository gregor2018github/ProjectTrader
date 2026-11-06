# Merchant's Rise — Roadmap

The long-term direction of the game's mechanics: what kind of game this is meant to become, the decisions already taken, and the big projects that get it there. The visuals grow iteratively alongside; this page is about the systems under the hood.

Small ideas live in `idea_reservoir.md` and `brainstorm.md`, concrete tasks in `TODO.md`. This page is the frame they hang in. When a project starts, it gets its own design document in `docs/` and a link from here.

---

## The vision in one paragraph

A cozy-looking medieval town that is a monster under the hood. The player starts with nothing and founds a **dynasty** whose members grow into the economy and politics of the town, until they steer what it builds, how it is taxed and how public money is spent. Inside the walls it plays like **Die Gilde 2** (families, workshops, council, rivals); beyond them like **Der Patrizier** (an abstract map of towns, convoys, trading posts); underneath runs an **Anno-style** economy of needs and production chains. The emotional core is the **rise from nothing**.

Inspirations: Anno 1503, Der Patrizier IV, Die Gilde 2, Banished, Songs of Syx, Stardew Valley, Medieval II: Total War.

---

## Decisions taken

| Topic | Decision |
|---|---|
| Player role | Head of a dynasty, woven into the town's economy and politics; the further it rises, the more it can steer and build, up to deciding how public money is spent |
| World | One walkable home town (the diorama) plus an abstract strategic map of other towns |
| Simulation model | Citizens aggregated per class with needs (Anno). **Businesses are real actors**: every workshop has an owner, cash, stock and workers |
| Time span | Generations: characters age, die and are succeeded by heirs |
| Calendar | A year is 4 seasons of 7 days (28 days; a day takes 8 real minutes at normal speed, so a year almost four real hours), so a 40–80 hour playthrough spans 10–20 game years at normal speed, more on the faster speeds. Characters age once a year. Built: `src/sim/calendar.py` |
| Building | Pre-made plots on the hand-made map; buy a plot, choose what stands on it |
| Workers | A named key person per business (master, foreman, factor) plus an abstract crowd of labourers |
| Goods | Grow from 15 to about 40–60, in chains up to three tiers deep (30 since P1) |
| Seasons & fields | **Under reconsideration.** Decided as cosmetic: production does not depend on harvests or weather. Since then the crops on the map grow with the seasons, households want more firewood and candles in winter, and many goods' outside prices have a season factor, but no workshop's output follows the fields or the weather yet. Whether it should is open (see "Open questions") |
| Rivals | AI dynasties (3–5 families) playing by the player's rules |
| Politics | A council with offices and real levers |
| Danger | Wars on the abstract map, plus bandits, thieves, fires, plague and building decay. All can be insured against, and some can be turned into profit |
| Failure | A bankrupt dynasty is game over |
| Hands-on vs. management | Early game: walk, haggle and carry yourself. Late game: family members, factors and stewards act for you |
| Information | Earned. Spies, couriers, guild contacts, the town crier and literacy reveal more |
| Trade routes | Manual convoys first, automated routes unlocked later |
| Prestige | Its own currency next to money |
| Family | Marriage and children, heirs chosen from them |
| Expansion | Trading posts (Kontore) in other towns, managed abstractly |
| Council powers | Taxes & tolls, public buildings, licenses & laws, military & war |
| Engine | Stay on Python + pygame for now. Move only when a real limit is hit; the sim core is kept free of pygame so that stays possible |
| Contributors | Code contributors. Needs clean module boundaries, tests and documentation |

---

## Design pillars

**1. Same rules for everyone.** The player, the AI dynasties and the town itself are all *owners*. They buy plots, run workshops, pay wages, take loans and go bankrupt through the same code. A rule written once applies to all, so AI families can never cheat and the player is never special-cased. The town counts as an owner too: it holds the workshops nobody else runs and the public buildings.

**2. Citizens aggregate, businesses individual.** A class (Poor, Commons, Middling Sort, Nobility) is a count of heads, a purse, a needs basket and a happiness. A business is an object: owner, building, recipe, stock, cash, master, workers. That keeps the simulation cheap and readable while giving the player things to own and rivals things to fight over.

**3. The core loop climbs.**

```
Gold ──spent on visible status──▶ Prestige ──wins──▶ Influence ──wins──▶ Power
  ▲                                                                        │
  └──────────────── laws, taxes, public contracts earn more ◀──────────────┘
```

Gold comes from trade, workshops and trading posts. Prestige comes from spending it where the town can see: the house, clothes, servants, feasts, patronage. Prestige wins marriages into good families and seats on the council. Office lets the dynasty set taxes, grant licenses, place public buildings and award contracts, which earn gold. Higher standing raises the cost of keeping it, so standing still means slipping back.

**4. Everything visible in the world.** A system is only done when it shows on the map: empty stalls when a good runs short, grumbling townsfolk when needs go unmet, a new building on a plot, a burnt-out house after a fire.

**5. Balance with data, not with hours of play.** Every system runs headless and can be simulated for decades in seconds, with its numbers written out for analysis.

---

## Projects

Each project is one big system. Usually two run side by side, and any of them can be returned to later when something else feels more lacking.

### Status

| Project | Status |
|---|---|
| P0 · Sim core | **Done** |
| P1 · The living market | **In progress** on the branch `p1-living-market`: P1.1–P1.4 built, P1.5 (minimal UI) open, then a playtest and the merge to `master` |
| P2 · Prestige & household | **Next** |
| P3 · Plots & workshops | Later, after P2 |
| P4 · The dynasty, P5 · Rival dynasties | Later |
| P6 · Council & treasury | Later (the town's treasury already fills in the sim, see P6) |
| P7 · Beyond the walls, P8 · Risk & insurance | Later |
| P9 · Earned information | Later, threaded through the others; nothing built yet |

### P0 · Sim core

**Status: done.** The foundation every later project builds on (design: `sim_core.md`). P1 fills it with needs, workshops and buildings.

- A `src/sim/` package that imports nothing from pygame. The game drives it; the sim never draws.
- A scheduler with price-tick (every 30 game minutes), hour, day, week, season and year ticks. Plans are made per day; the market trades in hourly slices during market hours (P1).
- One seeded random generator per run, so a simulation can be repeated exactly (tests, bug reports, balancing).
- Goods, needs, recipes, buildings and scenarios defined in JSON data files (`assets/data/`), not in code.
- A headless runner: `python -m src.sim.run --years 20 --seed 1 --out runs/<name>` writes daily CSVs of the goods, the classes, the workshops and the town's money for analysis with pandas; `python -m src.sim.health runs/<name>` checks a run, and `python -m src.sim.sweep` checks 20 seeds × 50 years at once.
- Tests in `tests/sim/` following `docs/testing.md`: goldens pinning the economy to the last bit, determinism, the scheduler, the data files, the save block, and that it imports without pygame.

Plugs into: `Good`, `Town` and `PopulationManager` (now pass-through views of the sim's state), and `Game.run()`, which calls `sim.advance_to()` each update.

### P1 · The living market

**Status: in progress** (design and progress: `p1_living_market.md`). Its internal phases are numbered P1.1–P1.5 so they don't clash with the roadmap's projects:

- **P1.1 Demand and the outside world**: built.
- **P1.2 Production**: built.
- **P1.3 Goods to 30**: built.
- **P1.4 Runner and health**: built. Every check of the design's health table is in, plus a check that every recipe can run flat out at outside prices, and 20 seeds × 50 years run clean (no seed fails). Its sweep found Wood held back by labour; hands of a short class are now shared by workers wanted × margin (a stand-in for P3's wage offers), growth and shrinking count days in a window, and the charcoal, mill and bakery recipes were fixed.
- **P1.5 Minimal UI**: open. Need fulfilment per class and tier in the town hall, daily demand and supply per good in the market view.

Then a playtest and the merge to `master`.

Real supply and demand in place of the placeholder random walk and `recover_volume()`.

- Each class has a needs basket per head: the Poor want bread, fish and beer; the Nobility wine, candles and fine cloth. Baskets are tiered, so basic needs are bought before luxuries.
- Wages from the workshops flow into the class purses; the purses buy from the market; how well each tier of needs is met drives happiness; happiness drives people moving in and out. This replaces today's random happiness drift.
- Goods grow to about 30 in this project, with real chains: wheat → flour → bread, wool → cloth → garments, hide → leather, iron → tools. Tools wear out, which keeps a steady demand for them.
- The volume factor stays. `normal_quantity` becomes *days of demand* the market holds, so a growing town needs more stock to feel normal.
- The random walk shrinks to a small noise on top. The player's trades keep moving the price through slippage.
- Shortages and gluts are visible: empty or overflowing stalls, and remarks from the townsfolk. *Not built yet:* P1.5 only adds numbers to the town hall and the market view; the map shows nothing of the market's state (see "Known issues and loose ends").

### P2 · Prestige & household

**Status: next.** The quick answer to "there is nothing worth spending money on".

- Prestige as its own currency, replacing the gift-based reputation in `MerchantRank`. Ranks ask for prestige from then on.
- Sources: residence tiers, clothing tiers, servants, feasts (the church feasts already consume goods), patronage of public works, alms (already in place for the poor).
- Prestige decays over time, and every tier of household raises the daily cost of living. That is the Gilde treadmill: holding a rank costs money.
- The dynasty's residence is the first building the player really cares about.

### P3 · Plots & workshops

**Status: later, after P2.** Things to own and build. The sim already runs workshops for an owner (`OwnerState`, `WorkshopState`; only the town so far), so P3 gives the player an owner of their own: `Depot.money` becomes the player's `Owner.cash` (`p1_living_market.md`, open question 16).

- Pre-made plots on the map: empty lots and ruins that can be bought. A building mode shows them, and shows what belongs to whom.
- Building a workshop costs money and materials (wood, stone, iron), so the player becomes a customer of the market they trade on. Missing materials can be bought on the spot at a premium.
- Each workshop has a named master with skill, loyalty and wage, plus labourers drawn from the Commons and Poor.
- Upkeep consumes materials. A neglected building decays, loses capacity and finally falls into ruin.
- One `Workshop` class serves the player, the AI dynasties and the town.
- **Wage offers per workshop**, replacing P1's stand-in. Since P1.4 a class short of hands shares them by workers wanted × margin (`production.share_hands`), a shortcut for "a profitable workshop can pay more". P3 lets each workshop offer its own wage, so the player can say "I'll pay more" and win hands from the town's farms; the hands then go to the best offers, and the class's one wage (`ClassState.wage`) gives way to the offers made (`p1_living_market.md`, "P1.4").

### P4 · The dynasty

**Status: later.**

- Characters with age, traits and four skills: trade, craft, rhetoric and stewardship.
- Marriage brings a dowry and an alliance with another family. Children grow up, and their education costs money and shapes their skills (school, apprenticeship, university).
- Death and succession: the player picks the heir. The game ends when the house goes bankrupt.
- Family members are how the late game is managed: one runs a workshop, one a trading post, one sits on the council.

### P5 · Rival dynasties

**Status: later.**

- 3–5 AI families acting through the same actions as the player: buy, build, trade, marry, stand for office.
- A simple utility AI to start with: each family weighs its options by expected gain and its own character (cautious, greedy, pious, ambitious).
- They are competitors, marriage partners, creditors and voters at the same time.

### P6 · Council & treasury

**Status: later.** A first piece is in the sim since P1: the town, as the owner of its workshops, keeps their profits in a treasury up to `TREASURY_CAP_DAYS` of its income and pays the rest to the lord as tribute (`surplus_to: treasury_with_tribute`). Nothing spends it yet. (The donations to the town still go to a separate `Town.treasury` in the game, outside the sim.)

- The town treasury collects taxes per class, market tolls, import duties and license fees. The existing trading licenses become a council policy.
- It pays for public buildings on plots (walls, roads, well, hospital, school), the militia and upkeep.
- Offices with real levers: treasurer, market master, master builder, captain of the watch, mayor.
- Laws are proposals put to a vote. AI dynasties vote by their interests and can be won over by favours, marriages and bribes.
- This is where the player decides how public money is spent.

### P7 · Beyond the walls

**Status: later.** Until then the "outside" is each good's outside price, walking slowly around its mean, with merchants importing and exporting against it (P1).

- A strategic map of 8–12 towns. Each runs the same sim on a cheaper weekly tick.
- At first, convoys are sent by hand: choose the cargo, the escort and the risk. Later, trading posts and automated routes with buy and sell rules take over.
- Lords wage wars on the map: they shift demand (iron, grain, cloth), cause blockades, and let the player fund mercenaries or side with one party.

### P8 · Risk & insurance

**Status: later.**

- Fires, theft, plague, bandits and decay, with odds driven by the sim rather than pure chance: wooden houses and no fire watch raise fire risk, crowding and port traffic raise plague risk, hungry poor raise theft.
- Protection: stone buildings, guards, insurance, and public works through the council.
- The player can become the underwriter and earn from other people's risk.

### P9 · Earned information

**Status: later**, threaded through all the others rather than built at once. Nothing of it is built yet: every price is known everywhere.

- Prices are known only where the dynasty has been or has a factor; news from other towns arrives late by courier.
- The town crier, the scribe and the newspaper (see `idea_reservoir.md`), guild contacts, spies on rival families.

---

## Suggested order

The first plan paired P0 with P2. In the event P1 followed P0 straight away, as the living market was what the sim core was built for, and P2 waits for it. The order from here:

| Wave | Projects | Why together |
|---|---|---|
| done | P0 | The foundation |
| now | P1 | The economy comes alive: finish P1.5, playtest, merge to `master` |
| next | P2 | Something worth spending money on, built on hooks that already exist (donations, feasts, merchant rank) |
| then | P3 | The player gets things to own in the economy, as an owner like the town |
| then | P4 + P5 | The Gilde layer: families, heirs, rivals |
| then | P6 | Power |
| then | P7 + P8 | The world beyond the walls and its dangers |
| always | P9 | Grows a piece at a time as each system lands |

---

## Open questions

- **Engine.** Python and pygame stay until a real limit is hit. Rendering is the likelier limit than the sim. Watch it as the town grows.
- **Early-game safety.** With bankruptcy as game over, the rise from nothing needs a floor in the first hours (for example woodhacking always pays enough to live on).
- **Seasons and production.** Should harvests (and weather) drive what the farms make, now that the crops on the map grow with the seasons? Today the seasons reach the economy only through demand (firewood, candles) and the outside prices' season factors; the farms produce the same all year.

**Resolved**

- **Calendar.** A day took about 4 real minutes, a year about 24 real hours: far too long for a game spanning generations. Built: a year of four seasons (Spring, Summer, Autumn, Winter) of 7 days each (`src/sim/calendar.py`); a day takes 8 real minutes at normal speed, so a year almost four real hours, and a 40–80 hour playthrough spans 10–20 game years. The clock stays a `datetime`; only what a day is called comes from the calendar. Durations sold to the player (licences) are in seasons. The weather, the daylight and the light's colour, and the crops follow the seasons.
- **Goods list.** P1.3 added 15 goods in chains, 30 in all (`p1_living_market.md`, "Goods").

---

## Known issues and loose ends

- **Cheap goods aren't worth trading.** The transaction fee is flat (`INITIAL_TRANSACTION_COST`, 2 per trade), so on a cheap good (Bread, Clay, Charcoal, Flax, Pottery) a small lot's swings never pay for its round trip (`python -m src.sim.health`, tradability). Later: a percentage fee with a minimum.
- **Labour.** The poor's wage sits at its cap (`wage_cap` in `needs.json`) nearly all the time, since their workshops always want more hands than there are. No building hires from the middling sort, so its labour share is never used and it lives on base income alone.
- **Wine at its import limit.** Wine is import-only and, since the Wood fix (P1.4) left the town richer, is imported at its limit on about 64 % of days (the health sweep's structural shortage warning). Its `import_limit` or the baskets would move it; not decided.
- **The smithy** is the thinnest recipe at outside prices (+0.30 at base income) and idles for over a year on 8 of 20 seeds of the sweep.
- **The town is always full.** Migration settles at about 100 % of the housing, so the town can't grow: that needs new housing, from plots (P3) or public building (P6).
- **Shortages aren't visible on the map** (pillar 4). Empty or overflowing stalls and townsfolk remarks are still to come; P1.5 only shows numbers.
- **Next candidates for the sim** (`sim_core.md`): the depot's daily books (cost of living, loans, overdraft, wealth history), the weather, and the crops' growth.
