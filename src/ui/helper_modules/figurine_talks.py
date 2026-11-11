"""The scripted talks some NPCs give in their speech bubble, and what their answers do.

Two kinds so far, their texts in their own model modules (the pieces of a talk
in models/talks.py):

* an introduction (models/introductions.py): the NPC whose profile names a
  minigame as ``"introduces"`` shows it to the player; agreeing introduces it,
  and afterwards the NPC starts it (``lend_a_hand``);
* a thanks (models/thanks.py): once the player has done what it is for, a trader
  thanks them and offers a gift, taken into their storage or turned down; after
  either it is over for good.

figurine_click_menu.py offers them in an NPC's menu; the bubble they are played
in is figurine_bubbles.py's FigurineConversation.
"""

from typing import Callable, Dict, List, Optional, Tuple, TYPE_CHECKING

import pygame

from ...models.introductions import INTRODUCTIONS, Introduction, WOODHACKING
from ...models.talks import Page
from ...models.thanks import Thanks, thanks_for
from .figurine_bubbles import (
    Badge, FigurineConversation, FigurineSpeech, good_badge_icon, reputation_badge_icon,
)
from ..transaction_feedback import on_goods_received
from .house_click_menu import minigame_introduced, open_woodhacking, woodhacking_available  # noqa: F401

if TYPE_CHECKING:
    from ...models.figurines.figurine import Figurine
    from ...models.figurines.humans.npcs.npc import NPC
    from ...game_state import GameState


#: What starts each minigame an NPC introduces, and whether it may still be played today
MINIGAME_OPENERS: Dict[str, Tuple[Callable[['GameState'], bool], Callable[['GameState'], bool]]] = {
    WOODHACKING: (open_woodhacking, woodhacking_available),
}


def introduction_of(figurine: 'Figurine') -> Optional[Introduction]:
    """The minigame introduction an NPC gives (models/introductions.py), or None."""
    minigame = getattr(figurine, 'introduces', None)
    if minigame not in MINIGAME_OPENERS:
        return None
    return INTRODUCTIONS.get(minigame)


def open_introduction(game_state: 'GameState', npc: 'NPC', page_name: str,
                      map_content_rect: pygame.Rect) -> None:
    """Open a page of the NPC's introduction in their speech bubble.

    Args:
        game_state: The current game state.
        npc: The NPC introducing their minigame.
        page_name: The page to show.
        map_content_rect: The map's drawing area on screen.
    """
    introduction = INTRODUCTIONS[npc.introduces]
    page = introduction.page(page_name)

    def answered(label: str) -> None:
        answer = next(a for a in page.answers if a.label == label)
        introduced = game_state.game.depot.stats.minigames_introduced
        if answer.agrees and npc.introduces not in introduced:
            introduced.append(npc.introduces)
        if answer.starts:
            lend_a_hand(game_state, npc, map_content_rect)
        elif answer.next is not None:
            open_introduction(game_state, npc, answer.next, map_content_rect)
        else:
            game_state.info_window.close()

    game_state.info_window = FigurineConversation(
        game_state.screen, npc, page.text, [a.label for a in page.answers], answered,
        game_state, map_content_rect)
    game_state.active_house_menu = None


def lend_a_hand(game_state: 'GameState', npc: 'NPC', map_content_rect: pygame.Rect) -> None:
    """Start the minigame the NPC introduced, or have them say it was played today."""
    opener, available = MINIGAME_OPENERS[npc.introduces]
    if available(game_state):
        npc.talking_to = None
        opener(game_state)
        return
    game_state.info_window = FigurineSpeech(game_state.screen, npc, INTRODUCTIONS[npc.introduces].done_today,
                                            game_state, map_content_rect)
    game_state.active_house_menu = None


def waiting_thanks(game_state: 'GameState', figurine: 'Figurine') -> Optional[Thanks]:
    """The thanks this figurine has for the player now (models/thanks.py), or None."""
    giver = getattr(figurine, 'TILED_PREFIX', None)
    game = getattr(game_state, 'game', None)
    if not giver or game is None:
        return None
    return thanks_for(giver, game.depot.stats)


def open_thanks(game_state: 'GameState', npc: 'NPC', thanks: Thanks, page_name: str,
                map_content_rect: pygame.Rect) -> None:
    """Open a page of the NPC's thanks in their speech bubble.

    Accepting hands the player the gift; without room for all of it a warning
    says so, nothing is taken and the thanks waits for another time.

    Args:
        game_state: The current game state.
        npc: The NPC thanking the player.
        thanks: Their thanks.
        page_name: The page to show.
        map_content_rect: The map's drawing area on screen.
    """
    page = thanks.page(page_name)

    def answered(label: str) -> None:
        answer = next(a for a in page.answers if a.label == label)
        stats = game_state.game.depot.stats
        if answer.accepts:
            if not _take_gift(game_state, npc, thanks):
                game_state.info_window.close()
                return
            stats.talks_done.append(thanks.key)
        elif answer.declines:
            stats.talks_done.append(thanks.key)
            _earn_modesty(game_state, npc, thanks)
        if answer.next is not None:
            open_thanks(game_state, npc, thanks, answer.next, map_content_rect)
        else:
            game_state.info_window.close()

    game_state.info_window = FigurineConversation(
        game_state.screen, npc, page.text, [a.label for a in page.answers], answered,
        game_state, map_content_rect, badges=thanks_badges(thanks, page))
    game_state.active_house_menu = None


def thanks_badges(thanks: Thanks, page: Page) -> Dict[str, List[Badge]]:
    """What each answer on a page of a thanks brings, by its label: the gift's goods
    beside taking it, the reputation beside turning it down."""
    badges: Dict[str, List[Badge]] = {}
    for answer in page.answers:
        if answer.accepts:
            badges[answer.label] = [(f"+{quantity}", good_badge_icon(name)) for name, quantity in thanks.gift.items()]
        elif answer.declines and thanks.reputation > 0:
            badges[answer.label] = [(f"+{thanks.reputation:g}", reputation_badge_icon())]
    return badges


def _earn_modesty(game_state: 'GameState', npc: 'NPC', thanks: Thanks) -> None:
    """Credit the reputation for turning a gift down."""
    if thanks.reputation <= 0:
        return
    game_state.game.player.change_reputation(thanks.reputation)
    game_state.log_event("RANK", f"Turned down a gift from {npc.display_name} "
                                 f"(reputation +{thanks.reputation:g})")


def _take_gift(game_state: 'GameState', npc: 'NPC', thanks: Thanks) -> bool:
    """Put the gift into the player's storage or pack, with its "+3" rising over the cursor;
    False, with a warning, without room for it."""
    depot = game_state.game.depot
    goods = list(thanks.gift.items())
    if any(depot.room_to_receive(name) < quantity for name, quantity in goods):
        what = ", ".join(f"{quantity} {name}" for name, quantity in goods)
        game_state.show_warning(f"No room for {what} in your storage or your pack. Make some room first.")
        return False
    for name, quantity in goods:
        depot.receive_goods(name, quantity, game_state.date)
        game_state.log_event("TRADE", f"Received {quantity}× {name} from {npc.display_name}, a gift")
    on_goods_received(game_state, thanks.gift)
    return True

