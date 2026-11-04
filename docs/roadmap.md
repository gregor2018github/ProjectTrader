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
| Calendar | A year is 4 seasons of 7 days (28 days; a day takes 8 real minutes at normal speed, so a year almost four real hours), so a 40–80 hour playthrough spans 10–20 game years at normal speed, more on the faster speeds. Characters age once a year. Built: `src/models/game_calendar.py` |
| Building | Pre-made plots on the hand-made map; buy a plot, choose what stands on it |
| Workers | A named key person per business (master, foreman, factor) plus an abstract crowd of labourers |
| Goods | Grow from 15 to about 40–60, in chains up to three tiers deep |
| Seasons & fields | Cosmetic. Production does not depend on harvests or weather |
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

### P0 · Sim core

The foundation every later project builds on.

- A `src/sim/` package that imports nothing from pygame. The game drives it; the sim never draws.
- A scheduler with day, week, season and year ticks. Prices, production and consumption run per day, not per hour.
- One seeded random generator per run, so a simulation can be repeated exactly (tests, bug reports, balancing).
- Goods, recipes, needs and buildings defined in data files (JSON or CSV), not in code.
- A headless runner: `python -m src.sim.run --years 20 --seed 1` writes CSVs of prices, stocks, populations and treasuries for analysis with pandas.
- Tests in `tests/sim/` following `docs/testing.md`.

Plugs into: `Good`, `PopulationManager`, the hourly and daily blocks in `Game.run()`.

### P1 · The living market

Real supply and demand in place of the placeholder random walk and `recover_volume()` (see `pricing.md` §9).

- Each class has a needs basket per head: the Poor want bread, fish and beer; the Nobility wine, candles and fine cloth. Baskets are tiered, so basic needs are bought before luxuries.
- Wages from the workshops flow into the class purses; the purses buy from the market; how well each tier of needs is met drives happiness; happiness drives people moving in and out. This replaces today's random happiness drift.
- Goods grow to about 30 in this project, with real chains: wheat → flour → bread, wool → cloth → garments, hide → leather, iron → tools. Tools wear out, which keeps a steady demand for them.
- The volume factor stays. `normal_quantity` becomes *days of demand* the market holds, so a growing town needs more stock to feel normal.
- The random walk shrinks to a small noise on top. The player's trades keep moving the price through slippage.
- Shortages and gluts are visible: empty or overflowing stalls, and remarks from the townsfolk.

### P2 · Prestige & household

The quick answer to "there is nothing worth spending money on".

- Prestige as its own currency, replacing the gift-based reputation in `MerchantRank`. Ranks ask for prestige from then on.
- Sources: residence tiers, clothing tiers, servants, feasts (the church feasts already consume goods), patronage of public works, alms (already in place for the poor).
- Prestige decays over time, and every tier of household raises the daily cost of living. That is the Gilde treadmill: holding a rank costs money.
- The dynasty's residence is the first building the player really cares about.

### P3 · Plots & workshops

Things to own and build.

- Pre-made plots on the map: empty lots and ruins that can be bought. A building mode shows them, and shows what belongs to whom.
- Building a workshop costs money and materials (wood, stone, iron), so the player becomes a customer of the market they trade on. Missing materials can be bought on the spot at a premium.
- Each workshop has a named master with skill, loyalty and wage, plus labourers drawn from the Commons and Poor.
- Upkeep consumes materials. A neglected building decays, loses capacity and finally falls into ruin.
- One `Workshop` class serves the player, the AI dynasties and the town.

### P4 · The dynasty

- Characters with age, traits and four skills: trade, craft, rhetoric and stewardship.
- Marriage brings a dowry and an alliance with another family. Children grow up, and their education costs money and shapes their skills (school, apprenticeship, university).
- Death and succession: the player picks the heir. The game ends when the house goes bankrupt.
- Family members are how the late game is managed: one runs a workshop, one a trading post, one sits on the council.

### P5 · Rival dynasties

- 3–5 AI families acting through the same actions as the player: buy, build, trade, marry, stand for office.
- A simple utility AI to start with: each family weighs its options by expected gain and its own character (cautious, greedy, pious, ambitious).
- They are competitors, marriage partners, creditors and voters at the same time.

### P6 · Council & treasury

- The town treasury collects taxes per class, market tolls, import duties and license fees. The existing trading licenses become a council policy.
- It pays for public buildings on plots (walls, roads, well, hospital, school), the militia and upkeep.
- Offices with real levers: treasurer, market master, master builder, captain of the watch, mayor.
- Laws are proposals put to a vote. AI dynasties vote by their interests and can be won over by favours, marriages and bribes.
- This is where the player decides how public money is spent.

### P7 · Beyond the walls

- A strategic map of 8–12 towns. Each runs the same sim on a cheaper weekly tick.
- At first, convoys are sent by hand: choose the cargo, the escort and the risk. Later, trading posts and automated routes with buy and sell rules take over.
- Lords wage wars on the map: they shift demand (iron, grain, cloth), cause blockades, and let the player fund mercenaries or side with one party.

### P8 · Risk & insurance

- Fires, theft, plague, bandits and decay, with odds driven by the sim rather than pure chance: wooden houses and no fire watch raise fire risk, crowding and port traffic raise plague risk, hungry poor raise theft.
- Protection: stone buildings, guards, insurance, and public works through the council.
- The player can become the underwriter and earn from other people's risk.

### P9 · Earned information

Threaded through all the others rather than built at once.

- Prices are known only where the dynasty has been or has a factor; news from other towns arrives late by courier.
- The town crier, the scribe and the newspaper (see `idea_reservoir.md`), guild contacts, spies on rival families.

---

## Suggested order

| Wave | Projects | Why together |
|---|---|---|
| 1 | P0 + P2 | The foundation, next to something fun built on hooks that already exist (donations, feasts, merchant rank) |
| 2 | P1 + P3 | The economy comes alive and the player gets things to own in it |
| 3 | P4 + P5 | The Gilde layer: families, heirs, rivals |
| 4 | P6 | Power |
| 5 | P7 + P8 | The world beyond the walls and its dangers |
| always | P9 | Grows a piece at a time as each system lands |

---

## Open questions

- **Engine.** Python and pygame stay until a real limit is hit. Rendering is the likelier limit than the sim. Watch it as the town grows.
- **Goods list.** Which 15 goods are added in P1, and which chains they form.
- **Early-game safety.** With bankruptcy as game over, the rise from nothing needs a floor in the first hours (for example woodhacking always pays enough to live on).
