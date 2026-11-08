"""A test bench for the fishing minigame, without starting a game (temporary).

    python main.py --fishing [--hour 18.5] [--season autumn] [--weather rain] [--seed 3]

opens the fishing straight away, on a stand-in for the game (a purse, the
statistics, the sounds; nothing is saved). Keys, read before the minigame
gets them:

    F5   a new session in the same conditions
    F6   three hours later
    F7   the next weather (clear, cloudy, rain, storm, fog, snow)
    F8   the next season
    F10  quit (Escape leaves the session, and a new one starts)

The once-a-day rule (``open_fishing`` in ``water_click_menu.py``) does not apply here.

To be removed once the fishing spot on the map is played for real.
"""

import argparse
import datetime
import os
import random
from types import SimpleNamespace
from typing import List, Optional

import pygame

from .fishing import FishingMinigame
from ..statistics import Statistics
from ...config.constants import PICTURES_PATH

SEASONS = ("spring", "summer", "autumn", "winter")
WEATHERS = {
    "clear": dict(),
    "cloudy": dict(clouds=0.8),
    "rain": dict(clouds=0.9, rain=0.7, wind=0.3),
    "storm": dict(clouds=1.0, rain=1.0, storm=0.9, wind=0.7),
    "fog": dict(clouds=0.3, fog=0.8),
    "snow": dict(clouds=0.8, snow=0.7, snow_cover=0.6, wind=0.2),
}


class _Depot:
    def __init__(self) -> None:
        self.money = 0.0
        self.stats = Statistics()

    def book_labor_income(self, amount: float, category: str) -> None:
        self.money += amount


class _State:
    def __init__(self, screen: pygame.Surface, game, date: datetime.datetime) -> None:
        self.screen, self.game, self.date = screen, game, date
        self.coin_popups: List = []

    def log_event(self, category: str, text: str) -> None:
        print(f"[{category}] {text}")


class _Game:
    """Just enough of Game for the minigame: state, depot, weather and sounds."""

    def __init__(self, screen: pygame.Surface, sounds: dict) -> None:
        self.sounds = sounds
        self.depot = _Depot()
        self.state = _State(screen, self, datetime.datetime(1500, 1, 1))
        self.weather = SimpleNamespace()

    def play_sound(self, name: str) -> Optional[pygame.mixer.Channel]:
        sound = self.sounds.get(name)
        return sound.play() if sound is not None else None


def _load_sounds() -> dict:
    sounds = {}
    folder = os.path.join(os.path.dirname(PICTURES_PATH), "sound")
    for name in os.listdir(folder):
        path = os.path.join(folder, name)
        if os.path.isfile(path):
            try:
                sounds[os.path.splitext(name)[0]] = pygame.mixer.Sound(path)
            except pygame.error:
                pass
    return sounds


def _date(hour: float, season: int) -> datetime.datetime:
    # The clock's first day is the 1st of Spring; a season is a week of it
    return datetime.datetime(1500, 1, 1) + datetime.timedelta(days=season * 7 + 3, hours=hour)


def run(screen: pygame.Surface, argv: List[str]) -> None:
    parser = argparse.ArgumentParser(prog="main.py --fishing")
    parser.add_argument("--hour", type=float, default=10.0)
    parser.add_argument("--season", choices=SEASONS, default="autumn")
    parser.add_argument("--weather", choices=tuple(WEATHERS), default="clear")
    parser.add_argument("--seed", type=int, default=None)
    args, _ = parser.parse_known_args(argv)
    hour, season, weather = args.hour % 24, SEASONS.index(args.season), args.weather

    sounds = _load_sounds()
    game = _Game(screen, sounds)
    clock = pygame.time.Clock()
    small = pygame.font.SysFont("consolas", 16)
    ambience: List[pygame.mixer.Channel] = []

    def start() -> FishingMinigame:
        for ch in ambience:
            ch.stop()
        ambience.clear()
        game.state.date = _date(hour, season)
        game.weather = SimpleNamespace(**{k: 0.0 for k in ("rain", "snow", "clouds", "fog", "storm", "wind", "snow_cover")})
        for k, v in WEATHERS[weather].items():
            setattr(game.weather, k, v)
        mg = FishingMinigame(screen, game, random.Random(args.seed) if args.seed is not None else None)
        # The world sounding round the pond, as the map's ambience would
        loops = [("amb_river_loop", 0.25)]
        night = mg.scene.night > 0.5
        if not WEATHERS[weather].get("rain"):
            loops.append(("amb_crickets_night_loop" if night else "amb_birds_day_loop", 0.3))
        else:
            loops.append(("amb_rain_heavy_loop" if weather == "storm" else "amb_rain_medium_loop", 0.45))
        for name, vol in loops:
            if name in sounds:
                ch = sounds[name].play(loops=-1)
                if ch is not None:
                    ch.set_volume(vol)
                    ambience.append(ch)
        pygame.display.set_caption(f"Fishing test — {hour:04.1f}h, {SEASONS[season]}, {weather}")
        return mg

    mg = start()
    running = True
    while running:
        dt = clock.tick(60) / 1000.0
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
                continue
            if event.type == pygame.KEYDOWN and event.key in (pygame.K_F5, pygame.K_F6, pygame.K_F7, pygame.K_F8, pygame.K_F10):
                if event.key == pygame.K_F10:
                    running = False
                    continue
                if event.key == pygame.K_F6:
                    hour = (hour + 3) % 24
                elif event.key == pygame.K_F7:
                    names = list(WEATHERS)
                    weather = names[(names.index(weather) + 1) % len(names)]
                elif event.key == pygame.K_F8:
                    season = (season + 1) % 4
                mg = start()
                continue
            mg.handle_event(event)
        if not mg.active:
            mg = start()
        mg.update(dt)
        screen.fill((24, 20, 16))
        mg.draw()
        info = small.render(f"TEST  {hour:04.1f}h  {SEASONS[season]}  {weather}   ·   F5 new  F6 +3h  F7 weather  "
                            f"F8 season  F10 quit   ·   purse {game.depot.money:.2f}", True, (200, 190, 160))
        screen.blit(info, (10, 6))
        pygame.display.flip()
    for ch in ambience:
        ch.stop()
