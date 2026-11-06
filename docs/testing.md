# Testing

```bash
pip install -r requirements-dev.txt   # the game's requirements plus pytest
python -m pytest                      # everything, from the repo root
python -m pytest tests/models/test_depot_storage.py -k pack   # a part
python -m pytest -m "not slow"        # without the tests that load the real map
```

`pytest.ini` puts the repo root on the path, so tests import the game as `src.…`.
`tests/conftest.py` sets SDL's video and audio drivers to `dummy` before pygame
is imported: no window opens and nothing plays.

## Layout

`tests/` mirrors `src/`: the tests of `src/models/depot.py` are in
`tests/models/`, split by concern (`test_depot_trading.py`, `_storage`,
`_filters`, `_licenses`, `_bookkeeping`). Fixtures shared by a folder live in its
`conftest.py`; stand-ins for the game's big objects live in `tests/fakes.py`.
Tests that load the real map or the whole game are marked `@pytest.mark.slow`
(registered in `pytest.ini`); they run by default. So far only
`tests/sim/test_run.py` is (the runner reads the town from `Map1.tmx`).

## How the code splits up for testing

The code falls into layers that are tested differently. Start from the top:
it is where the bugs cost most and the tests are cheapest.

0. **The simulation core** (`src/sim/`, `tests/sim/`, see `docs/sim_core.md`):
   plain state and functions, no pygame at all. Test the systems on hand-made
   `GoodState` / `PopulationState` with a `random.Random(seed)` of the test's
   own, the scheduler on hand-picked moments, the data loaders on small dicts.
   These kinds of test guard the core:
   - **Goldens** (`test_golden.py`): a fixed scenario (the economy run ahead, a
     year, scripted player trades and well wishes) snapshotted to
     `tests/sim/golden/` for two seeds. On the platform that wrote them
     (`written_on`, Windows so far) they are matched to the last bit, digests
     of the float histories included; everywhere else (the maths library's last
     bits differ on Linux) every number and a sample of each float history to
     a relative 1e-12, and that bit-exact test is skipped. They run on
     their own frozen copy of the data (`tests/sim/golden/data/`), so tuning
     `assets/data/` does not break them; they were regenerated at each phase of
     P1 (P1.1 to P1.3). When behaviour is meant to change, regenerate with
     `python -m tests.sim.golden_harness --write` and say so in the commit;
     otherwise a failing golden is a bug.
   - **Rules one by one** (`test_market.py`, `test_households.py`,
     `test_production.py`) on small definitions from `tests/sim/builders.py`, and
     the whole economy on a toy town (`test_simulation.py`: the player buying up
     the bread leaves the town short; `test_production.py`: a bakery feeding its
     town, paying its workers and its owner's surplus, and shrinking when it
     cannot pay its way).
   - **The parts the rest stands on**: the calendar (`test_calendar.py`), the
     scheduler (`test_scheduler.py`) and the data loaders (`test_data.py`).
   - **The health report** (`test_health.py`): every check on hand-made rows
     (each threshold pinned, the edge on both sides), the tradability measure,
     and the checks and the sweep's table on two real half-year runs of a
     small town (no map).
   - **The views** (`test_views.py`): `Good`, `Town` and `PopulationManager`
     show what the simulation holds, after a change to its state or a load.
   - **Determinism** (`test_run.py`): the same seed writes byte-identical CSVs,
     another seed different ones.
   - **Save round trip** (`test_simulation_save.py`): a saved and loaded
     simulation goes on exactly like the unsaved one; the saves in `saves/`
     still load.
   - **Headless** (`test_no_pygame.py`): every module imports with
     `sys.modules["pygame"] = None` and none of the game; no global `random` calls.
1. **Pure models**: plain unit tests, no pygame display, no map. Covered: the
   depot (its licence dates included), the weather, the lightning, the daylight,
   the crops' growth, the merchant rank, the tavern menu, and the coughs, owls
   and dogs (when and how they sound). Not yet: `Statistics`, polygon insets, A*
   on a small grid. The depot's goods are `Good` views of a one-good
   `Simulation` each (`make_good` in `tests/models/conftest.py`).
2. **Models that talk to `GameState`**: give them a `FakeGameState`
   (`tests/fakes.py`). It has only the members the code under test uses and
   records warnings and ledger entries so tests can check them. When the code
   under test starts using another member of `GameState`, add it to the fake.
3. **Saving and loading**: round trips (build a state, save it, load it, compare)
   and loading the old saves in `saves/` without errors. `save_manager` reads the
   whole `Game`. Before it can be tested in parts, each object needs its own
   `to_dict` / `from_dict`.
4. **Map-dependent code** (`TMXMap`, `NavGrid`, `Door`, `Cover`): integration
   tests that load the real `Map1.tmx` headless, e.g. "every door has a step",
   "every trader's stall path is reachable from his door". None yet. They are
   slower, so they will get a `@pytest.mark.slow`.
5. **UI**: mostly no unit tests; where a piece of UI holds logic of its own, it
   is tested apart from the drawing (`tests/ui/test_view_transition.py`: which
   part of the screen the parchment rolls over, for how long, and which page
   turn is heard). Otherwise at most smoke tests that draw each view onto a
   `pygame.Surface` and check that nothing raises.

## Rules of thumb

- **Pin the constants a test relies on.** The models import balance values by
  name (`from ..config.constants import SLOT_SIZE`), so a test monkeypatches the
  module's own copy (`monkeypatch.setattr(depot_module, "SLOT_SIZE", 20)`, see
  `tests/models/conftest.py`). Rebalancing the game then does not break tests.
- **No randomness.** Set the values that matter (`good.set_price()`,
  `market_quantity`) or seed it: in the sim, pass a `random.Random(seed)`;
  elsewhere, seed `random`.
- **Pick numbers that make the expected result obvious.** The goods in the
  fixtures cost 10g with 1,000 on the market, so small orders keep the price flat
  and `10 units = 100g`.
- **Test refusals as well as successes.** For each refusal, check that nothing
  changed and that the right warning was shown.

## Known seams

- The depot calls `on_money_spent` / `on_money_received`
  (`src/ui/transaction_feedback.py`) directly. They read the mouse and spawn a
  popup, which needs a display. The `game_state` fixture swaps them for
  recorders (`FakeGameState.money_feedback`). A cleaner design would have the
  depot report what happened and the caller do the feedback.

## Next areas, in order

1. Save round trips of the depot and statistics (after the split above; the
   simulation's block has its own already).
2. `GameState.update()`'s `TimeChanges` against the scheduler's ticks.
3. `NavGrid.find_route` on a hand-made grid, then the real-map checks.
