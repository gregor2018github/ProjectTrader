"""The quest for Flip in the UI: the shepherdess's talks, coaxing Flip home, and what the player says.

The quest itself is models/lost_sheep.py (its stages, texts and numbers) and
models/lost_sheep_map.py (Flip, the fold and the shepherdess on the map); here
is what the player does with it:

* ``shepherdess_talk`` / ``open_shepherdess_talk`` -- her talk at the fold
  (its marker and glow, ``has_news``, only once she is on her round there), in
  her speech bubble (figurine_bubbles.FigurineConversation), pages of
  ``lost_sheep.PAGES``; an answer's ``does`` lies or owns up (reputation lost,
  not shown beforehand, only rising from the player's head once answered), takes her bread,
  or takes or turns down her thanks;
* ``coax_flip`` -- "Coax Flip Home" in Flip's menu: with a Bread he follows on
  the leash, one Bread used up; without, he shies away from the player along
  his strip and the player says what they lack in their own bubble
  (``player_says``);
* ``blocks_buildings`` -- while he is on the leash no building is to be used
  (house_click_menu.show_house_menu warns instead).

figurine_click_menu.py offers the options; the marker over her and the rope
are drawn by the map view.
"""

import random
from typing import Dict, List, Optional, TYPE_CHECKING

import pygame

from ...config.constants import MODULE_WIDTH, SCREEN_HEIGHT, SHEEP_VOLUME
from ...models import lost_sheep
from ...models.figurines.humans.npcs.trader import WORKING
from ...models.talks import Page
from ..transaction_feedback import on_goods_received, on_reputation_gained, on_reputation_lost
from .figurine_bubbles import (
    Badge, FigurineConversation, FigurineSpeech, figurine_screen_rect, good_badge_icon, reputation_badge_icon,
)

if TYPE_CHECKING:
    from ...models.figurines.animals.sheep import Sheep
    from ...models.figurines.figurine import Figurine
    from ...models.figurines.humans.npcs.npc import NPC
    from ...game_state import GameState

#: Flip's option while he is to be brought home
COAX_OPTION = "Coax Flip Home"
#: The shepherdess's option while she has a talk for the player: "Talk" at first, and once she has
#: told them his name, "About Flip..." (talk_option)
TALK_OPTION = "Talk"
ABOUT_FLIP_OPTION = "About Flip..."


def _quest_map(game_state: 'GameState'):
    game = getattr(game_state, "game", None)
    return getattr(game, "lost_sheep_map", None)


def has_bread(game_state: 'GameState') -> bool:
    """Whether the player has what it takes to lure Flip."""
    depot = game_state.game.depot
    return not depot.missing_goods(lost_sheep.LURE_GOODS)


def is_shepherdess(game_state: 'GameState', figurine: 'Figurine') -> bool:
    on_map = _quest_map(game_state)
    return on_map is not None and figurine is on_map.shepherdess


def is_flip(game_state: 'GameState', figurine: 'Figurine') -> bool:
    on_map = _quest_map(game_state)
    return on_map is not None and on_map.ready and figurine is on_map.flip


def shepherdess_talk(game_state: 'GameState', figurine: 'Figurine') -> Optional[str]:
    """The first page of the talk the shepherdess has for the player now, if this is her, at the fold."""
    on_map = _quest_map(game_state)
    if on_map is None or not on_map.ready or figurine is not on_map.shepherdess:
        return None
    if not getattr(figurine, "at_fold", False):
        return None
    return on_map.quest.talk(has_bread(game_state))


def talk_option(game_state: 'GameState') -> str:
    """The label of her option in her menu: "About Flip..." once the player knows him by name."""
    on_map = _quest_map(game_state)
    return ABOUT_FLIP_OPTION if on_map is not None and on_map.quest.flip_named else TALK_OPTION


def has_news(game_state: 'GameState', figurine: 'Figurine') -> bool:
    """Whether she has news for the player at the fold: a marker over her head, and a glow.

    Only once she is on her round in the fold, not on her way out to it or home.
    """
    if getattr(figurine, "state", None) != WORKING:
        return False
    talk = shepherdess_talk(game_state, figurine)
    return talk is not None and talk in lost_sheep.NEWS


def blocks_buildings(game_state: 'GameState') -> bool:
    """Whether Flip on the leash keeps the player from the buildings."""
    on_map = _quest_map(game_state)
    return on_map is not None and on_map.quest.leading


def can_coax(game_state: 'GameState', figurine: 'Figurine') -> bool:
    on_map = _quest_map(game_state)
    return is_flip(game_state, figurine) and on_map.quest.can_lure()


# ── The shepherdess ──────────────────────────────────────────────────────────

def talk_badges(page: Page) -> Dict[str, List[Badge]]:
    """What each answer on a page brings or costs, by its label.

    Lying and owning up show nothing: what honesty costs is not to be weighed
    beforehand, and is only seen once answered (rising from the player's head).
    """
    badges: Dict[str, List[Badge]] = {}
    for answer in page.answers:
        if answer.does == "bread":
            badges[answer.label] = [(f"+{n}", good_badge_icon(name)) for name, n in lost_sheep.BREAD_GIFT.items()]
        elif answer.does == "accept":
            badges[answer.label] = [(f"+{n}", good_badge_icon(name)) for name, n in lost_sheep.THANKS_GIFT.items()]
        elif answer.does == "decline":
            badges[answer.label] = [(f"+{lost_sheep.THANKS_REPUTATION:g}", reputation_badge_icon())]
    return badges


def open_shepherdess_talk(game_state: 'GameState', npc: 'NPC', page_name: str,
                          map_content_rect: pygame.Rect) -> None:
    """Open a page of the shepherdess's talk in her speech bubble.

    Args:
        game_state: The current game state.
        npc: The shepherdess.
        page_name: The page to show (lost_sheep.PAGES).
        map_content_rect: The map's drawing area on screen.
    """
    page = lost_sheep.PAGES[page_name]

    def answered(label: str) -> None:
        answer = next(a for a in page.answers if a.label == label)
        if answer.does is not None and not _do(game_state, npc, answer.does, map_content_rect):
            game_state.info_window.close()
            return
        if answer.next is not None:
            open_shepherdess_talk(game_state, npc, answer.next, map_content_rect)
        else:
            game_state.info_window.close()

    game_state.info_window = FigurineConversation(
        game_state.screen, npc, page.text, [a.label for a in page.answers], answered,
        game_state, map_content_rect, badges=talk_badges(page))
    game_state.active_house_menu = None


def _do(game_state: 'GameState', npc: 'NPC', does: str, map_content_rect: pygame.Rect) -> bool:
    """Do what an answer does; False if it could not be done (no room for a gift: the talk waits)."""
    game = game_state.game
    quest = game.lost_sheep
    if does in ("lie", "confess"):
        change = quest.answer_missing(confess=does == "confess")
        if change:
            game.player.change_reputation(change)
            what = "Owned up to" if does == "confess" else "Was found out after denying"
            game_state.log_event("RANK", f"{what} leaving the sheep fold's gate open (reputation {change:g})")
            on_reputation_lost(game_state, -change, _player_head(game_state, map_content_rect))
        game.lost_sheep_map.sync(game.game_map.map_player.feet)
        return True
    if does == "bread":
        if not _receive(game_state, npc, lost_sheep.BREAD_GIFT, "to lure Flip home with"):
            return False
        quest.give_bread()
        return True
    if does == "accept":
        if not _receive(game_state, npc, lost_sheep.THANKS_GIFT, "for bringing Flip home"):
            return False
        quest.finish(game_state.date.date())
        return True
    if does == "decline":
        quest.finish(game_state.date.date())
        game.player.change_reputation(lost_sheep.THANKS_REPUTATION)
        game_state.log_event("RANK", f"Turned down the shepherdess's wool for bringing Flip home "
                                     f"(reputation +{lost_sheep.THANKS_REPUTATION:g})")
        on_reputation_gained(game_state, lost_sheep.THANKS_REPUTATION, _player_head(game_state, map_content_rect))
        return True
    return True


def _receive(game_state: 'GameState', npc: 'NPC', goods: Dict[str, int], why: str) -> bool:
    """Put goods she gives into the player's storage or pack, "+2" rising over the cursor; False, with a
    warning, without room for them."""
    depot = game_state.game.depot
    if any(depot.room_to_receive(name) < quantity for name, quantity in goods.items()):
        what = ", ".join(f"{quantity} {name}" for name, quantity in goods.items())
        game_state.show_warning(f"No room for {what} in your storage or your pack. Make some room first.")
        return False
    for name, quantity in goods.items():
        depot.receive_goods(name, quantity, game_state.date)
        game_state.log_event("TRADE", f"Received {quantity}x {name} from {npc.display_name}, {why}")
    on_goods_received(game_state, goods)
    return True


# ── Flip ─────────────────────────────────────────────────────────────────────

def coax_flip(game_state: 'GameState', flip: 'Sheep', map_content_rect: pygame.Rect) -> None:
    """Hold out bread to Flip: with some he follows on the leash, without the player says what they lack."""
    game = game_state.game
    quest, on_map = game.lost_sheep, game.lost_sheep_map
    player = game.game_map.map_player
    if not quest.lure(has_bread(game_state)):
        # Nothing to offer: he shies away from the empty hand
        flip.shy_away(player.x + player.width / 2)
        player_says(game_state, lost_sheep.SAY_NO_BREAD, map_content_rect)
        return
    flip.pet(player.x + player.width / 2)
    game.depot.use_goods(lost_sheep.LURE_GOODS)
    game_state.log_event("TRADE", "Fed a piece of Bread to Flip, the shepherdess's black sheep")
    on_map.put_on_leash(player.feet)
    _bleat(game)
    player_says(game_state, lost_sheep.SAY_LEASHED, map_content_rect)


def _bleat(game) -> None:
    sounds = getattr(game, "sheep_sounds", None)
    if sounds:
        channel = random.choice(sounds).play()
        if channel:
            channel.set_volume(SHEEP_VOLUME)


# ── The player ───────────────────────────────────────────────────────────────

def player_says(game_state: 'GameState', text: str, map_content_rect: Optional[pygame.Rect] = None) -> None:
    """The player says something to themselves, in a speech bubble over their own head."""
    rect = map_content_rect or map_content_area(game_state)
    if rect is None:
        return
    player = game_state.game.game_map.map_player
    game_state.info_window = FigurineSpeech(game_state.screen, player, text, game_state, rect)
    game_state.active_house_menu = None


def map_content_area(game_state: 'GameState') -> Optional[pygame.Rect]:
    """The map's drawing area on screen as the modules are laid out now; None if no side shows it."""
    left, right = game_state.left_side_mode == "map", game_state.right_side_mode == "map"
    if left and right:
        view = pygame.Rect(0, 60, MODULE_WIDTH * 2, SCREEN_HEIGHT - 120)
    elif left:
        view = pygame.Rect(0, 60, MODULE_WIDTH, SCREEN_HEIGHT - 120)
    elif right:
        view = pygame.Rect(MODULE_WIDTH, 60, MODULE_WIDTH, SCREEN_HEIGHT - 120)
    else:
        return None
    return view.inflate(-10, -10)


def _player_head(game_state: 'GameState', map_content_rect: pygame.Rect):
    game = game_state.game
    player = game.game_map.map_player
    return figurine_screen_rect(player, game.game_map.camera, map_content_rect).midtop
