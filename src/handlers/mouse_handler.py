import pygame
import random
from typing import List, Dict, Any, Optional, Tuple, TYPE_CHECKING
from ..ui.helper_modules.info_window import InfoWindow
from ..ui.helper_modules.contract_acquisition import ContractView
from ..ui.helper_modules.house_click_menu import show_house_menu
from ..ui.helper_modules.figurine_click_menu import get_hovered_map_object, show_figurine_menu
from ..models.figurines.figurine import Figurine
from ..ui.helper_modules.water_click_menu import get_hovered_water, show_water_menu
from ..ui.helper_modules.ledger_window import LedgerWindow
from ..ui.layout_modules.depot_view_chart import handle_click as handle_depot_chart_click
from ..ui.layout_modules.depot_view import handle_click as handle_depot_list_click

if TYPE_CHECKING:
    from ..game_state import GameState
    from ..models.good import Good
    from ..models.depot import Depot


VIEW_MODES = ["map", "market", "depot", "politics", "trade_routes", "building"]

def set_view_fullscreen(game_state: 'GameState', name: str) -> None:
    """Show ``name`` on both sides at once (same effect as clicking its main pictogram).

    Toggles back to whatever was showing before if ``name`` is already
    full-screen on both sides.
    """
    if game_state.left_side_mode == name and game_state.right_side_mode == name:
        game_state.left_side_mode = game_state.left_side_prev_mode
        game_state.right_side_mode = game_state.right_side_prev_mode
    else:
        if game_state.left_side_mode != name:
            game_state.left_side_prev_mode = game_state.left_side_mode
            game_state.left_side_mode = name

        if game_state.right_side_mode != name:
            game_state.right_side_prev_mode = game_state.right_side_mode
            game_state.right_side_mode = name


def _toggle_chart_good(good: 'Good', goods: List['Good'], game_state: 'GameState') -> None:
    """Toggle a good's chart visibility, enforcing a maximum of 3 visible goods.

    When turning ON a 4th good, the most recently added good (order[2]) is closed
    first.  If the order list has fewer than 3 entries (legacy/startup state), the
    visible good with the highest index is closed instead.
    Turning OFF is always allowed unless it would leave zero goods visible.
    """
    order: List[str] = game_state.chart_selection_order

    if good.show_in_charts:
        # Turning OFF — prevent closing the last visible good
        visible_count = sum(1 for g in goods if g.show_in_charts)
        if visible_count == 1:
            return
        good.show_in_charts = False
        if good.name in order:
            order.remove(good.name)
    else:
        # Turning ON
        visible = [g for g in goods if g.show_in_charts]
        if len(visible) >= 3:
            # Determine which good to close: the one at position 2 in the order,
            # or the visible good with the highest index if order is incomplete.
            order_visible = [name for name in order if any(g.name == name and g.show_in_charts for g in goods)]
            if len(order_visible) >= 3:
                to_close_name = order_visible[2]
            else:
                to_close_name = max(visible, key=lambda g: g.index).name
            for g in goods:
                if g.name == to_close_name:
                    g.show_in_charts = False
                    break
            if to_close_name in order:
                order.remove(to_close_name)
        good.show_in_charts = True
        if good.name not in order:
            order.append(good.name)

    # The trade desk's cards follow the chart, and the market square the player is at remembers them
    game_state.mouse_clicked_on = "none"
    game_state.remember_market_goods()
    game_state.sync_quicktrade_fields()


def handle_mouse_click(pos: Tuple[int, int],
                       buttons: Dict[str, pygame.Rect],
                       game_state: 'GameState',
                       goods: List['Good'],
                       depot: 'Depot') -> None:
    """Process left mouse button clicks on various UI elements.

    This function handles clicks for sound controls, time controls, menus,
    dialogues, pictograms, dropdowns, input fields, and chart toggle boxes.

    Args:
        pos: The (x, y) coordinates of the mouse click.
        buttons: Dictionary of UI element names mapped to their hitboxes.
        game_state: Current state of the game engine.
        goods: List of all tradeable goods.
        depot: The player's depot/inventory model.
    """
    # Handle dialogue clicks first if active - blocks all other UI interactions
    if hasattr(game_state, 'dialogue') and game_state.dialogue:
        result = game_state.dialogue.handle_click(pos)
        if result:
            from ..ui.helper_modules.dialogue import answer_dialogue
            answer_dialogue(game_state, result)
        # Always return when dialogue is active - block all other UI interactions
        return

    # Handle sound control clicks
    if hasattr(game_state.game, 'sound_control'):
        if game_state.game.sound_control.handle_click(pos, game_state.game):
            return

    # Handle map object clicks (houses) if map is visible and not paused
    if game_state.is_map_visible and game_state.time_level > 1:
        # Check if we clicked on a house that is hoverable (in range)
        # We need the map view rect for this. The map view takes up the remaining space
        # after sidebar (SIDEBAR_WIDTH) is removed from left.
        # But wait, looking at game.py/render_module, it seems modules render into full_module_rect
        # We need to construct the view_rect here or access it from somewhere.
        # The game renders modules side-by-side or full view.
        # Let's approximate: if map is left module, rect is there. If right module...
        # Better: Iterate all potential view areas.

        # Simplified approach: Since we don't have the exact rects easily available here without passed args,
        # we can reconstruct them based on game_state layout logic or just check if the click hits any house
        # assuming the mouse pos is correct.
        # get_hovered_house checks if pos is within passed view_rect.
        # We'll try passing the screen rect as fallback or calculate properly?

        # Let's try to find the map rect based on current layout modes
        from ..config.constants import SCREEN_HEIGHT, MODULE_WIDTH

        map_rects = []
        left_module_rect = pygame.Rect(0, 60, MODULE_WIDTH, SCREEN_HEIGHT - 120)
        right_module_rect = pygame.Rect(MODULE_WIDTH, 60, MODULE_WIDTH, SCREEN_HEIGHT - 120)
        full_module_rect = pygame.Rect(0, 60, MODULE_WIDTH * 2, SCREEN_HEIGHT - 120)

        if game_state.left_side_mode == "map" and game_state.right_side_mode == "map":
            map_rects.append(full_module_rect)
        else:
            if game_state.left_side_mode == "map":
                map_rects.append(left_module_rect)
            if game_state.right_side_mode == "map":
                map_rects.append(right_module_rect)

        # The circles of what acts on the player only show their tooltip: the map under them takes no click
        if any(rect.collidepoint(pos) for rect in getattr(game_state, "effect_circle_rects", [])):
            map_rects = []

        for view_rect in map_rects:
            if view_rect.collidepoint(pos):
                hovered = get_hovered_map_object(pos, game_state.game.game_map, view_rect)
                if isinstance(hovered, Figurine):
                    # Figurines without options still absorb the click; don't click through them
                    show_figurine_menu(game_state, hovered, view_rect)
                    return
                if hovered is not None:
                    show_house_menu(game_state, hovered, pos)
                    return

                hovered_water = get_hovered_water(pos, game_state.game.game_map, view_rect)
                if hovered_water:
                    show_water_menu(game_state, hovered_water, pos)
                    return

    # Reset hover states for all goods
    for good in goods:
        good.hovered = False
        # Make sure we don't have any leftover tracking attributes
        if hasattr(good, '_external_hover'):
            good._external_hover = False

    # Handle info window clicks first - blocks all other UI interactions
    if getattr(game_state, 'info_window', None) and hasattr(game_state.info_window, 'handle_click'):
        game_state.info_window.handle_click(pos)
        return

    # Handle time control clicks
    time_level = game_state.game.time_control.handle_click(pos, game_state.time_level)
    if time_level is not None:
        # Enforce map view time restriction: only paused (1) or normal (3) allowed
        if game_state.is_map_visible and time_level not in [1, 3]:
            # If map is visible, we force invalid speeds to Normal (3)
            game_state.time_level = 3
        else:
            game_state.time_level = time_level
        return

    # Handle menu clicks first
    if hasattr(game_state, 'game') and hasattr(game_state.game, 'menu'):
        menu_action = game_state.game.menu.handle_click(pos)
        if menu_action == "_menu_toggled":
            # Menu was opened/closed, consume the click to prevent other buttons from activating
            return
        if menu_action:
            if menu_action == "Save Game":
                from ..ui.helper_modules.save_load_dialog import SaveDialog
                game_state.info_window = SaveDialog(game_state.screen, game_state.font, game_state.game)
                return
            elif menu_action == "Load Game":
                from ..ui.helper_modules.save_load_dialog import LoadDialog
                game_state.info_window = LoadDialog(game_state.screen, game_state.font, game_state.game)
                return
            elif menu_action == "Quit":
                game_state.info_window = InfoWindow(game_state.screen,
                                                  "Do you want to quit?",
                                                  ["Back", "Quit"],
                                                  game_state.font,
                                                  game_state.game)  # Pass game reference
            elif menu_action == "Main Menu":
                game_state.info_window = InfoWindow(game_state.screen,
                                                  "Return to main menu?",
                                                  ["No", "Yes"],
                                                  game_state.font,
                                                  game_state.game)
            elif menu_action == "Settings":
                from ..settings import SettingsWindow
                game_state.info_window = SettingsWindow(game_state.screen, game_state.font, game_state.game)
                return
            return

    # Top bar goods scroll arrows: one column per click
    for key, step in (('top_bar_left', -1), ('top_bar_right', 1)):
        if key in buttons and buttons[key].collidepoint(pos):
            from ..ui.general_layout.layout import scroll_top_bar
            scroll_top_bar(game_state, step)
            return

    # Merchant rank title (top bar) opens the rank overview
    if 'merchant_rank' in buttons and buttons['merchant_rank'].collidepoint(pos):
        from ..ui.helper_modules.rank_window import open_rank_window
        open_rank_window(game_state)
        return

    # Handle town population statistics panel click (Bottom bar)
    if 'town_population' in buttons and buttons['town_population'].collidepoint(pos):
        from ..ui.general_layout.layout import _get_town_for_stats
        town = _get_town_for_stats(game_state)
        if town:
            town.open_population_stats(game_state, pos)
            return

    # Ledger modal button — opens the event log, no left/right sub-buttons
    if "pictogram_ledger" in buttons and buttons["pictogram_ledger"].collidepoint(pos):
        game_state.info_window = LedgerWindow(game_state.screen, game_state)
        return

    # Handle pictogram sub-button clicks (left/right buttons)
    for name in VIEW_MODES:
        left_key = f"picto_{name}_left"
        right_key = f"picto_{name}_right"
        main_key = f"pictogram_{name}"

        # Handle Left Button Click
        if left_key in buttons and buttons[left_key].collidepoint(pos):
            if game_state.left_side_mode == name:
                # If clicking the active mode, fall back to previous
                game_state.left_side_mode = game_state.left_side_prev_mode
            else:
                # If clicking a new mode, update previous and set new current
                game_state.left_side_prev_mode = game_state.left_side_mode
                game_state.left_side_mode = name
            return

        # Handle Right Button Click
        if right_key in buttons and buttons[right_key].collidepoint(pos):
            if game_state.right_side_mode == name:
                # If clicking the active mode, fall back to previous
                game_state.right_side_mode = game_state.right_side_prev_mode
            else:
                # If clicking a new mode, update previous and set new current
                game_state.right_side_prev_mode = game_state.right_side_mode
                game_state.right_side_mode = name
            return

        # Handle Main Pictogram Button Click (Full View)
        if main_key in buttons and buttons[main_key].collidepoint(pos):
            set_view_fullscreen(game_state, name)
            return

    # The trade desk's cards and whatever else has a hitbox
    for field_name, rect in buttons.items():
        if rect.collidepoint(pos):
            part, _, section = field_name.rpartition('_')
            good_name = game_state.input_fields.get(f'good_{section}', '')
            if part == 'quantity':
                # A click takes the field with its whole text marked, so typing replaces it
                text = game_state.input_fields[field_name]
                game_state.mouse_clicked_on = field_name
                game_state.cursor_position = len(text)
                game_state.input_text_selected = bool(text)
                return
            game_state.mouse_clicked_on = "none"
            if part in ('half', 'minus', 'plus', 'double', 'maxbuy', 'maxsell') and good_name:
                _step_trade_quantity(part, section, good_name, game_state)
            elif part in ('buy', 'sell') and good_name:
                trade_card_order(part, section, game_state, goods, depot, quiet=True)
            else:
                game_state.mouse_clicked_on = field_name
            return

    # Handle toggle boxes in chart
    for box, target in game_state.image_boxes:
        if box.collidepoint(pos):
            if isinstance(target, int):
                game_state.chart_goods_offset = target  # a scroll arrow
            else:
                _toggle_chart_good(target, goods, game_state)
            return

    # Check for clicks on Depot Chart buttons
    if game_state.depot_chart_buttons and handle_depot_chart_click(game_state, pos):
        return

    # The depot's accounts: a time frame's tab, or a row whose details open
    if handle_depot_list_click(game_state, pos):
        return

    # Reset mouse click if clicked elsewhere
    game_state.mouse_clicked_on = "none"

def _step_trade_quantity(part: str, section: str, good_name: str, game_state: 'GameState') -> None:
    """Change a trade card's quantity with one of its steps, or take the most it could buy or sell."""
    text = game_state.input_fields.get(f'quantity_{section}', '')
    quantity = int(text) if text.isdigit() else 0
    max_buy, max_sell = game_state.trade_limits.get(section, (0, 0))
    if part == 'maxbuy' and max_buy <= 0 or part == 'maxsell' and max_sell <= 0:
        return
    game_state.set_trade_quantity(good_name, {
        'half': quantity // 2,
        'minus': quantity - 1,
        'plus': quantity + 1,
        'double': quantity * 2,
        'maxbuy': max_buy,
        'maxsell': max_sell,
    }[part])


def trade_card_order(action: str, section: str, game_state: 'GameState', goods: List['Good'], depot: 'Depot',
                     quiet: bool = False) -> bool:
    """Place a trade card's order ('buy' or 'sell'), as its button or its F key does.

    Nothing is traded away from the market squares or while the game is
    paused; whatever else stands in the way, the depot says in a warning.
    With *quiet* (a click on the button, which is greyed and says why on its
    card) an order that cannot be placed is dropped without that warning.

    Returns:
        Whether the trade went through.
    """
    from ..models.trade_offer import MAX_QUANTITY, buy_offer, sell_offer

    player = getattr(game_state.game, 'player', None)
    if (player is not None and not player.in_market_area) or game_state.time_level == 1:
        return False
    good_name = game_state.input_fields.get(f'good_{section}', '')
    good = next((g for g in goods if g.name == good_name), None)
    text = game_state.input_fields.get(f'quantity_{section}', '')
    if good is None or not text.isdigit():
        return False
    quantity = min(int(text), MAX_QUANTITY)
    if quiet and (buy_offer if action == 'buy' else sell_offer)(good, quantity, depot, game_state).blocked:
        return False
    traded = depot.buy(good, quantity, game_state) if action == 'buy' else depot.sell(good, quantity, game_state)
    if traded:
        game_state.money_effect_timer = 30  # effect lasts 30 frames
        game_state.money_effect_color = (230, 0, 0) if action == 'buy' else (0, 180, 10)  # red for buy, green for sell
        game_state.button_click_effects[f'{action}_{section}'] = 10
    return traded
