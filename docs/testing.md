# Testing

```bash
pip install -r requirements-dev.txt   # the game's requirements plus pytest
python -m pytest                      # everything, from the repo root
python -m pytest tests/models/test_depot_storage.py -k pack   # a part
```

`pytest.ini` puts the repo root on the path, so tests import the game as `src.…`.
`tests/conftest.py` sets SDL's video and audio drivers to `dummy` before pygame
is imported: no window opens and nothing plays.

## Layout

`tests/` mirrors `src/`: the tests of `src/models/depot.py` are in
`tests/models/`, split by concern (`test_depot_trading.py`, `_storage`,
`_filters`, `_licenses`, `_bookkeeping`). Fixtures shared by a folder live in its
`conftest.py`; stand-ins for the game's big objects live in `tests/fakes.py`.

## How the code splits up for testing

The code falls into layers that are tested differently. Start from the top:
it is where the bugs cost most and the tests are cheapest.

1. **Pure models**: the depot, `Good` pricing (`docs/pricing.md` is its spec),
   `Statistics`, license dates, polygon insets, A* on a small grid. Plain unit
   tests, no pygame display, no map.
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
   "every trader's stall path is reachable from his door". They are slower, so
   they will get a `@pytest.mark.slow`.
5. **UI**: no unit tests. At most smoke tests that draw each view onto a
   `pygame.Surface` and check that nothing raises.

## Rules of thumb

- **Pin the constants a test relies on.** The models import balance values by
  name (`from ..config.constants import SLOT_SIZE`), so a test monkeypatches the
  module's own copy (`monkeypatch.setattr(depot_module, "SLOT_SIZE", 20)`, see
  `tests/models/conftest.py`). Rebalancing the game then does not break tests.
- **No randomness.** Set the values that matter (`good.set_price()`,
  `market_quantity`) or seed `random`.
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

1. `Good`: `volume_factor`, `quote`, `recover_volume`, the corridor of `update_price`.
2. Save round trips of the depot, goods and statistics (after the split above).
3. `GameState` time: `update()`'s `TimeChanges` across hours, days and month ends.
4. `NavGrid.find_route` on a hand-made grid, then the real-map checks.
