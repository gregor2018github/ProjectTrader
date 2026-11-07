"""Measures the game's frame times, headless, on a fixed walk through the map.

Builds a new game exactly as the loading screen does, shows the map on both
sides and walks the player at walking speed through the town and then the
densest wood (the 12x12-tile square with the most trees), timing every frame
from one clock tick to the next: simulation and drawing, without the window's
own presentation. The game is fed a fixed 1/60 s per frame, so runs compare.

    py build_tools/Perf_Probe/perf_probe.py                 # clear midday
    py build_tools/Perf_Probe/perf_probe.py --hour 22 --zoom 1.0 --wet
    py build_tools/Perf_Probe/perf_probe.py --spikes 25     # what the slow frames did
    py build_tools/Perf_Probe/perf_probe.py --profile out.prof
    py build_tools/Perf_Probe/perf_probe.py --zooms         # first frame at each zoom

See README.md for reading the results and imitating a slow PC.
"""

import argparse
import collections
import cProfile
import gc
import io
import os
import pstats
import sys
import time

PROJECT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
os.chdir(PROJECT)
sys.path.insert(0, PROJECT)

import pygame  # noqa: E402

from src.config.constants import SCREEN_WIDTH, SCREEN_HEIGHT, SIDEBAR_WIDTH  # noqa: E402

#: The fixed frame time fed to the game, in milliseconds
FRAME_MS = 16
#: Side of the squares searched for the densest wood, in tiles
WOOD_SQUARE_TILES = 12


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--hour", type=int, help="in-game hour to play at (lights, darkness)")
    parser.add_argument("--zoom", type=float, help="map zoom, e.g. 1.0 (default: the starting zoom)")
    parser.add_argument("--wet", action="store_true", help="steady rain, full cloud, fog and wet ground")
    parser.add_argument("--spikes", type=float, metavar="MS",
                        help="profile every frame and print what each one slower than MS did")
    parser.add_argument("--profile", metavar="FILE", help="write a cProfile of the whole walk")
    parser.add_argument("--save", type=int, metavar="SLOT", help="start from this save slot instead of a new game")
    parser.add_argument("--zooms", action="store_true",
                        help="instead of walking: the first frame at each zoom level, once warmed up")
    return parser.parse_args()


def build_game(screen: pygame.Surface, slot=None):
    from src.game import Game
    from src.persistence.save_manager import load_game
    Game.init_pygame()
    started = time.perf_counter()
    game = Game(save_data=load_game(slot) if slot else None, screen=screen)
    print(f"game built in {time.perf_counter() - started:.2f} s")
    # As main.py does once the loading screen is done
    gc.collect()
    gc.freeze()
    return game


def walk_plan(game):
    """(stretch name, x, y) for every frame of the walk."""
    from src.config.constants import TILE_SIZE
    from src.models.institutions.town import Town

    tmx = game.game_map.tmx_map
    player = game.game_map.map_player
    town = next(house for house in tmx.houses if isinstance(house, Town))
    square = TILE_SIZE * WOOD_SQUARE_TILES
    squares = collections.Counter((int(tree.x // square), int(tree.y // square)) for tree in tmx.trees)
    (wood_x, wood_y), trees = squares.most_common(1)[0]
    wood = ((wood_x + 0.5) * square, (wood_y + 0.5) * square)
    print(f"{len(tmx.trees)} trees, {len(tmx.houses)} houses, "
          f"{sum(len(field.sprite_placements) for field in tmx.fields)} crop sprites; "
          f"densest wood square holds {trees} trees")

    start = (town.x + 60, town.y + 80)
    stretches = [
        ("town", start, (start[0] + 900, start[1] + 300)),
        ("town2", (start[0] + 900, start[1] + 300), (start[0] - 600, start[1] - 200)),
        ("wood", (wood[0] - 500, wood[1]), (wood[0] + 500, wood[1] + 200)),
    ]
    # Across the middle of each sown field, its crop standing as it does at the start
    for field in tmx.fields:
        if field.images:
            middle = field.y + field.height / 2
            stretches.append(("field", (field.x, middle), (field.x + field.width, middle)))
    plan = []
    for name, (ax, ay), (bx, by) in stretches:
        frames = int(((bx - ax) ** 2 + (by - ay) ** 2) ** 0.5 / player.speed * 1000 / FRAME_MS)
        for i in range(frames):
            t = i / max(1, frames - 1)
            plan.append((name, ax + (bx - ax) * t, ay + (by - ay) * t))
    return plan


def set_scene(game, args) -> None:
    state = game.state
    state.left_side_mode = state.right_side_mode = "map"
    state.time_level = 3
    if args.zoom:
        game.game_map.camera.set_zoom(args.zoom)
        if args.zoom in game.game_map.zoom_levels:
            game.game_map.zoom_index = game.game_map.zoom_levels.index(args.zoom)
    if args.hour is not None:
        state.date = state.date.replace(hour=args.hour, minute=0)
    if args.wet:
        weather = game.weather
        weather.rain, weather.clouds, weather.fog, weather.wetness, weather.storm = 0.8, 1.0, 0.6, 1.0, 0.0
        weather.update = lambda date: None
        game.game_map.puddles.update(1.0)


def walk(game, args) -> None:
    plan = walk_plan(game)
    player = game.game_map.map_player
    frame_log = []      # (stretch, ms)
    slow = []           # (frame, ms, profile text)
    gc_log = []         # (frame, generation, ms)
    at = {"frame": 0, "last": None, "profile": None, "gc": 0.0}

    def on_gc(phase, info):
        if phase == "start":
            at["gc"] = time.perf_counter()
        else:
            gc_log.append((at["frame"], info["generation"], (time.perf_counter() - at["gc"]) * 1000))
    gc.callbacks.append(on_gc)

    class ProbeClock:
        """Stands in for the game's clock: times the frames, moves the player."""

        def tick(self, fps=0):
            now = time.perf_counter()
            if at["last"] is not None and at["frame"] > 0:
                ms = (now - at["last"]) * 1000
                frame_log.append((plan[at["frame"] - 1][0], ms))
                if at["profile"]:
                    at["profile"].disable()
                    if ms > args.spikes:
                        text = io.StringIO()
                        pstats.Stats(at["profile"], stream=text).sort_stats("cumtime").print_stats(16)
                        slow.append((at["frame"], ms, text.getvalue()))
            if args.spikes:
                at["profile"] = cProfile.Profile()
                at["profile"].enable()
            at["last"] = time.perf_counter()
            if at["frame"] >= len(plan):
                pygame.event.post(pygame.event.Event(pygame.QUIT))
                return FRAME_MS
            _, player.x, player.y = plan[at["frame"]]
            at["frame"] += 1
            return FRAME_MS

        def get_fps(self):
            return 0

    game.clock = ProbeClock()
    game.game_map.handle_movement_keys = lambda keys: None

    whole = cProfile.Profile() if args.profile else None
    if whole:
        whole.enable()
    game.run()
    if whole:
        whole.disable()
        whole.dump_stats(args.profile)
        print(f"profile written to {args.profile}")
    gc.callbacks.remove(on_gc)

    by_stretch = collections.defaultdict(list)
    for name, ms in frame_log:
        by_stretch[name].append(ms)
    for name, times in by_stretch.items():
        times.sort()
        print(f"{name:6s} {len(times):4d} frames  median {times[len(times) // 2]:5.1f} ms  "
              f"p95 {times[int(len(times) * 0.95)]:5.1f} ms  max {times[-1]:6.1f} ms  "
              f"over 33 ms: {sum(ms > 33 for ms in times)}")
    for generation in (0, 1, 2):
        pauses = [ms for _, gen, ms in gc_log if gen == generation]
        if pauses:
            print(f"gc generation {generation}: {len(pauses)} runs, longest {max(pauses):.1f} ms")
    for frame, ms, text in slow:
        print(f"\n--- frame {frame}: {ms:.1f} ms")
        print("\n".join(line.replace(PROJECT + os.sep, "") for line in text.splitlines()
                        if PROJECT in line or "{" in line))


def zooms(game) -> None:
    """The first frame at each zoom level, after the background warm-up has had its frames."""
    from src.ui.layout_modules.map_view import draw_map_view

    game_map = game.game_map
    for _ in range(400):
        game_map.warmup.step()
    rect = pygame.Rect(0, 60, 1650, 944)
    player = game_map.map_player
    for index in reversed(range(len(game_map.zoom_levels))):
        game_map.zoom_index = index
        game_map.camera.set_zoom(game_map.zoom_levels[index])
        game_map.camera.update(player.x + player.width / 2, player.y + player.height / 2,
                               game_map.tmx_map.width * game_map.tmx_map.tile_size,
                               game_map.tmx_map.height * game_map.tmx_map.tile_size)
        for label in ("first", "second"):
            started = time.perf_counter()
            draw_map_view(game.screen, game_map, rect, game.state)
            print(f"zoom {game_map.zoom_levels[index]:4.2f} {label} frame {(time.perf_counter() - started) * 1000:6.1f} ms")


def main() -> None:
    args = parse_args()
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_WIDTH + SIDEBAR_WIDTH, SCREEN_HEIGHT))
    game = build_game(screen, args.save)
    set_scene(game, args)
    if args.zooms:
        zooms(game)
    else:
        walk(game, args)


if __name__ == "__main__":
    main()
