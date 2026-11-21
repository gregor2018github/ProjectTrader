"""Figurine hover detection and click menu for the map.

The counterpart of house_click_menu for everything that walks around: the
player, human NPCs and animals. A figurine under the mouse and within
interaction range of the player gets the same hover glow as a house, and
clicking it opens a FigurineMenu, a small speech bubble pointing at the
figurine that is deliberately lighter than the framed HouseMenu. The bubbles
themselves are in figurine_bubbles.py, the scripted talks some NPCs give (a
minigame's introduction, a thanks with a gift) in figurine_talks.py, the quest
for the shepherdess's black sheep in lost_sheep_talks.py.
"""

import random
from typing import Iterator, List, Optional, Tuple, Union, TYPE_CHECKING

import pygame

from ...config import settings_store
from ...config.constants import ALMS_CATEGORY, ALMS_COIN, SHEEP_PET_REPUTATION, SHEEP_VOLUME
from ..transaction_feedback import on_money_donated, on_reputation_gained
from .figurine_bubbles import (  # noqa: F401  (figurine_screen_pos and FigurineMenu are used from here too)
    FigurineBubble, FigurineMenu, FigurineSpeech, figurine_screen_pos, figurine_screen_rect,
)
from .figurine_talks import (
    introduction_of, lend_a_hand, minigame_introduced, open_introduction, open_thanks, waiting_thanks,
)
from .house_click_menu import get_hovered_house, is_player_near
from .lost_sheep_talks import (
    COAX_OPTION, TALK_OPTION, can_coax, coax_flip, open_shepherdess_talk, shepherdess_talk,
)

if TYPE_CHECKING:
    from ...models.figurines.figurine import Figurine
    from ...models.figurines.humans.npcs.npc import NPC
    from ...models.figurines.animals.sheep import Sheep
    from ...models.house import House
    from ...models.map import GameMap
    from ...game_state import GameState


# Label of the alms option, used both to offer it and to recognise the choice
GIVE_COIN_OPTION = "Give a Coin"
PET_SHEEP_OPTION = "Pet Sheep"


def iter_figurines(game_map: 'GameMap') -> Iterator['Figurine']:
    """Yield every figurine in sight on the map, in render-queue order (player last)."""
    for figurine in (*game_map.tmx_map.sheep, *game_map.tmx_map.npcs, game_map.map_player):
        if not figurine.is_hidden:
            yield figurine



def get_hovered_figurine(
    mouse_pos: Tuple[int, int],
    game_map: 'GameMap',
    view_rect: pygame.Rect
) -> Optional['Figurine']:
    """Determine which figurine (if any) the mouse is hovering over.

    Only considers figurines within interaction distance of the player (the
    player always is). The test is pixel-precise, because a figurine's sprite
    box is mostly transparent. When several overlap, the topmost wins.

    Args:
        mouse_pos: Screen coordinates of the mouse cursor (x, y).
        game_map: The GameMap instance containing figurines and camera.
        view_rect: The rectangle defining the map viewport on screen.

    Returns:
        The Figurine being hovered, or None.
    """
    map_content_rect = view_rect.inflate(-10, -10)
    if not map_content_rect.collidepoint(mouse_pos):
        return None

    camera = game_map.camera
    player = game_map.map_player
    hovered = None

    for figurine in iter_figurines(game_map):
        if not is_player_near(player, figurine):
            continue

        sprite = figurine._get_scaled_sprite(camera.zoom)
        draw_x, draw_y = figurine_screen_pos(figurine, camera)
        local = (mouse_pos[0] - map_content_rect.x - draw_x,
                 mouse_pos[1] - map_content_rect.y - draw_y)
        if not sprite.get_rect().collidepoint(local) or sprite.get_at(local).a == 0:
            continue

        # >= because later figurines are drawn on top at equal depth
        if hovered is None or figurine.y_sort >= hovered.y_sort:
            hovered = figurine

    return hovered


def get_hovered_map_object(
    mouse_pos: Tuple[int, int],
    game_map: 'GameMap',
    view_rect: pygame.Rect
) -> Optional[Union['House', 'Figurine']]:
    """Return the hoverable house or figurine under the mouse, whichever is drawn on top.

    Args:
        mouse_pos: Screen coordinates of the mouse cursor (x, y).
        game_map: The GameMap instance.
        view_rect: The rectangle defining the map viewport on screen.

    Returns:
        The hovered House or Figurine, or None.
    """
    house = get_hovered_house(mouse_pos, game_map, view_rect)
    figurine = get_hovered_figurine(mouse_pos, game_map, view_rect)
    if figurine is None:
        return house
    if house is None:
        return figurine
    return figurine if figurine.y_sort >= house.y_sort else house


def show_figurine_menu(
    game_state: 'GameState',
    figurine: 'Figurine',
    view_rect: pygame.Rect
) -> bool:
    """Open the interaction bubble for a clicked figurine, if it has any options.

    Args:
        game_state: The current game state.
        figurine: The clicked figurine.
        view_rect: The map viewport the figurine was clicked in.

    Returns:
        True if a menu was opened.
    """
    from ...models.figurines.animals.sheep import Sheep
    from ...models.figurines.humans.npcs.npc import NPC

    options: List[str] = []
    if figurine is game_state.game.game_map.map_player:
        options.append("Inventory")
    introduction = introduction_of(figurine)
    thanks = waiting_thanks(game_state, figurine)
    if introduction is not None:
        introduced = minigame_introduced(game_state, figurine.introduces)
        options.append(introduction.lend_option if introduced else introduction.talk_option)
    if thanks is not None:
        options.append(thanks.talk_option)
    # The quest for the shepherdess's black sheep (lost_sheep_talks.py)
    quest_talk = shepherdess_talk(game_state, figurine)
    if quest_talk is not None:
        options.append(TALK_OPTION)
    if isinstance(figurine, Sheep) and can_coax(game_state, figurine):
        options.append(COAX_OPTION)
    if isinstance(figurine, NPC):
        options.append("Chat")
        # Only the town's poor are offered a coin; the rest would take it ill
        if figurine.SOCIAL_CLASS == "Poor":
            options.append(GIVE_COIN_OPTION)
    if isinstance(figurine, Sheep):
        options.append(PET_SHEEP_OPTION)
    # Inspect is a debugging aid, only offered with the debug overlay on
    if settings_store.get("show_map_debug"):
        options.append("Inspect")

    if not options:
        return False

    def menu_callback(option_text: str) -> None:
        if option_text == "Inventory":
            from .player_inventory import open_player_inventory
            open_player_inventory(game_state)
            return
        if option_text == "Inspect":
            from .info_window import InfoWindow
            lines = figurine.inspect_lines(observer=game_state.game.game_map.map_player)
            game_state.info_window = InfoWindow(game_state.screen, "\n".join(lines),
                                                ["OK"], game_state.font, game_state.game)
            game_state.active_house_menu = None
            return
        if option_text == "Chat" and isinstance(figurine, NPC):
            # The speech bubble takes the menu's place. It follows the NPC and
            # closes itself once the player walks away or they leave the view
            game_state.info_window = FigurineSpeech(game_state.screen, figurine, figurine.chat_line(),
                                                    game_state, map_content_rect)
            game_state.active_house_menu = None
            return
        if quest_talk is not None and option_text == TALK_OPTION:
            open_shepherdess_talk(game_state, figurine, quest_talk, map_content_rect)
            return
        if option_text == COAX_OPTION and isinstance(figurine, Sheep):
            coax_flip(game_state, figurine, map_content_rect)
            return
        if thanks is not None and option_text == thanks.talk_option:
            open_thanks(game_state, figurine, thanks, thanks.first, map_content_rect)
            return
        if introduction is not None and option_text == introduction.talk_option:
            open_introduction(game_state, figurine, introduction.first, map_content_rect)
            return
        if introduction is not None and option_text == introduction.lend_option:
            lend_a_hand(game_state, figurine, map_content_rect)
            return
        if option_text == PET_SHEEP_OPTION and isinstance(figurine, Sheep):
            _pet_sheep(game_state, figurine, map_content_rect)
        if option_text == GIVE_COIN_OPTION and isinstance(figurine, NPC):
            if _give_coin(game_state, figurine):
                # As with a chat, the bubble takes the menu's place; the coin's
                # popup is drawn over it
                game_state.info_window = FigurineSpeech(game_state.screen, figurine, figurine.thanks_line(),
                                                        game_state, map_content_rect)
                game_state.active_house_menu = None
                return
        menu.close()

    # The tail points at the top centre of the sprite, or its bottom if the bubble flips below
    map_content_rect = view_rect.inflate(-10, -10)
    sprite_rect = figurine_screen_rect(figurine, game_state.game.game_map.camera, map_content_rect)

    menu = FigurineMenu(game_state.screen, figurine, options, game_state, sprite_rect, menu_callback)
    game_state.info_window = menu
    # Keeps the hover glow on and closes the menu when the player walks away
    game_state.active_house_menu = figurine
    return True



def release_ended_conversations(game_state: 'GameState', game_map: 'GameMap') -> None:
    """Let every NPC get on with their day whose bubble is no longer open.

    A bubble holds its figurine still from the moment it opens and lets go in
    close(), but it can also be dropped without that — the map view takes one
    away when the player walks off, and a menu can be replaced by another
    window. Called once a frame, this makes sure nobody is left standing.

    Args:
        game_state: The current game state.
        game_map: The map holding the NPCs.
    """
    window = game_state.info_window
    talking = window.figurine if isinstance(window, FigurineBubble) else None
    for npc in game_map.tmx_map.npcs:
        if npc is not talking:
            npc.talking_to = None


def _give_coin(game_state: 'GameState', npc: 'NPC') -> bool:
    """Hand one of the poor a coin, booked as alms.

    The player gets the donation feedback for it: a single coin heard flipped or dropped and
    the rising amount above the cursor.

    Args:
        game_state: The current game state.
        npc: The townsperson receiving the coin.

    Returns:
        True if the coin was given, False if the player could not spare it.
    """
    depot = game_state.game.depot
    if not depot.book_donation(ALMS_COIN, category=ALMS_CATEGORY):
        game_state.show_warning("You have not a coin to spare.")
        return False
    on_money_donated(game_state, ALMS_COIN)
    gain = game_state.game.merchant_rank.record_gift(ALMS_COIN)
    game_state.log_event("DONATION", f"Gave {ALMS_COIN:.0f}g to {npc.display_name} (reputation +{gain:.2f})")
    return True


def sheep_pet_pays(game_state: 'GameState') -> bool:
    """Whether petting a sheep still earns reputation today (once a game day)."""
    return game_state.game.depot.stats.last_sheep_pet_day != game_state.date.date().isoformat()


def _pet_sheep(game_state: 'GameState', sheep: 'Sheep', map_content_rect: pygame.Rect) -> None:
    """Make the sheep bleat and stand still; the day's first petting earns a little reputation,
    shown as "+0.2" and the laurel rising from the player's head."""
    game = game_state.game
    player = game.game_map.map_player
    sheep.pet(player.x + player.width / 2)
    if game.sheep_sounds:
        channel = random.choice(game.sheep_sounds).play()
        if channel:
            channel.set_volume(SHEEP_VOLUME)
    if sheep_pet_pays(game_state):
        game.depot.stats.last_sheep_pet_day = game_state.date.date().isoformat()
        game.player.change_reputation(SHEEP_PET_REPUTATION)
        game_state.log_event("RANK", f"Petted a sheep (reputation +{SHEEP_PET_REPUTATION:g})")
        head = figurine_screen_rect(player, game.game_map.camera, map_content_rect).midtop
        on_reputation_gained(game_state, SHEEP_PET_REPUTATION, head)
