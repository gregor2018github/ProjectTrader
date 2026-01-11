import pygame
from typing import List, Dict, Any, Optional, Tuple, TYPE_CHECKING
from ..ui.helper_modules.info_window import InfoWindow

if TYPE_CHECKING:
    from ..game_state import GameState
    from ..models.good import Good
    from ..models.depot import Depot

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
    # Handle sound control clicks
    if hasattr(game_state.game, 'sound_control'):
        if game_state.game.sound_control.handle_click(pos, game_state.game):
            return

    # Handle depot time frame button clicks
    if hasattr(game_state, "depot_buttons"):
        depot_buttons = game_state.depot_buttons
        current_index = game_state.depot_time_frames.index(game_state.depot_time_frame)
        if depot_buttons["left"].collidepoint(pos) and current_index > 0:
            game_state.depot_time_frame = game_state.depot_time_frames[current_index - 1]
            # Force update of detail panel statistics
            if hasattr(game_state, "detail_panel") and game_state.detail_panel is not None:
                game_state.detail_panel.update_statistics(force=True)
            return
        elif depot_buttons["right"].collidepoint(pos) and current_index < len(game_state.depot_time_frames) - 1:
            game_state.depot_time_frame = game_state.depot_time_frames[current_index + 1]
            # Force update of detail panel statistics
            if hasattr(game_state, "detail_panel") and game_state.detail_panel is not None:
                game_state.detail_panel.update_statistics(force=True)
            return

    # Reset hover states for all goods
    for good in goods:
        good.hovered = False
        # Make sure we don't have any leftover tracking attributes
        if hasattr(good, '_external_hover'):
            good._external_hover = False

    # Handle time control clicks
    time_level = game_state.game.time_control.handle_click(pos, game_state.time_level)
    if time_level is not None:
        game_state.time_level = time_level
        return

    # Handle menu clicks first
    if hasattr(game_state, 'game') and hasattr(game_state.game, 'menu'):
        menu_action = game_state.game.menu.handle_click(pos)
        if menu_action:
            if menu_action == "Quit":
                game_state.info_window = InfoWindow(game_state.screen, 
                                                  "Do you want to quit?", 
                                                  ["Back", "Quit"], 
                                                  game_state.font,
                                                  game_state.game)  # Pass game reference
            elif menu_action == "Demo":
                from ..ui.helper_modules.dialogue import show_dialogue
                game_state.dialogue = show_dialogue(
                    game_state.screen,
                    game_state.game,
                    "portrait_harbor",      # picture parameter
                    "Story Teller",         # npc_name parameter
                    "With nothing but hopes and an address scribbled on a small piece of paper, you step off the creaking gangplank onto the bustling docks of Blackwater Harbor, your future uncertain but full of promise.",
                    ["Follow the Address"],
                    "story_teller_1"        # Sound to play
                )
                return
            elif menu_action == "Balance":
                # Handle balance action
                pass
            elif menu_action == "Map":
                # Handle map action
                pass
            elif menu_action == "Settings":
                from ..settings import SettingsWindow
                game_state.info_window = SettingsWindow(game_state.screen, game_state.font, game_state.game)
                return
            elif menu_action == "Talk Demo":
                # Handle talk demo action
                pass
            return
        
    # Handle dialogue clicks if active
    if hasattr(game_state, 'dialogue') and game_state.dialogue:
        result = game_state.dialogue.handle_click(pos)
        if result:
            if result == "Follow the Address":
                # Create a new follow-up dialogue
                from ..ui.helper_modules.dialogue import show_dialogue
                game_state.dialogue = show_dialogue(
                    game_state.screen,
                    game_state.game,
                    "portrait_shop",  # Use picture parameter
                    "Story Teller",       # Use npc_name parameter
                    """You make your way through the sleepy town and eventually enter a cramped but well-organized shop nestled between the cobbler and the blacksmith. The old trader's eyes light up with recognition as you approach.""",
                    ["What a journey!"],
                    "story_teller_2"  # Sound to play
                )                
            elif result == "What a journey!":
                # Create a new follow-up dialogue
                from ..ui.helper_modules.dialogue import show_dialogue
                game_state.dialogue = show_dialogue(
                    game_state.screen,
                    game_state.game,
                    "portrait_merchant",  # Use picture parameter
                    "Old Merchant",       # Use npc_name parameter
                    """By the Saints, is that you? After all these years! Look how you've grown since I last saw you in Eastmere. Your father's letter said you were coming, but I hardly believed it. Welcome to Blackwater Harbor, Kid!""",
                    ["Give him a hug"],
                    "merchant_1"  # Sound to play
                )
            elif result == "Give him a hug":
                # Create a new follow-up dialogue
                from ..ui.helper_modules.dialogue import show_dialogue
                game_state.dialogue = show_dialogue(
                    game_state.screen,
                    game_state.game,
                    "portrait_merchant",  # Use picture parameter
                    "Story Teller",        # Use npc_name parameter
                    """Uncle Gared pulls you into a quick embrace before stepping back, his hands trembling slightly as he leans on his gnarled oak staff. He calmly smiles at you.""",
                    ["I will help you!"],
                    "story_teller_3"  # Sound to play
                )                 
            else:
                # Close the dialogue
                game_state.dialogue = None
            return

    # Handle pictogram clicks (side menu)
    for name in ["map", "market", "depot", "politics", "trade_routes", "building"]:
        key = f"pictogram_{name}"
        if key in buttons and buttons[key].collidepoint(pos):
            # Placeholder for future menu switching logic
            # Each pictogram will eventually trigger a menu state change
            if name == "map":
                # Toggle map view
                game_state.map_state = not game_state.map_state
            elif name == "market":
                # Toggle back to market/chart view
                game_state.map_state = False
            elif name == "depot":
                pass
            elif name == "politics":
                pass
            elif name == "trade_routes":
                pass
            elif name == "building":
                pass
            return

    # Handle dropdown selection first
    if game_state.active_dropdown:
        dropdown = game_state.dropdowns[game_state.active_dropdown]
        selected = dropdown.handle_click(pos)
        if selected:
            section = game_state.active_dropdown.split('_')[1]
            game_state.input_fields[f'good_{section}'] = selected
            dropdown.is_open = False  # Make sure to close the dropdown
            game_state.active_dropdown = None
            return
        # If clicked outside, close all dropdowns
        for dropdown in game_state.dropdowns.values():
            dropdown.is_open = False
        game_state.active_dropdown = None
        return

    # Handle input field clicks
    for field_name, rect in buttons.items():
        if rect.collidepoint(pos):
            if field_name.startswith('quantity_'):
                game_state.mouse_clicked_on = field_name
                # Set cursor position to end of input when clicking field
                game_state.cursor_position = len(game_state.input_fields[field_name])
            if field_name.startswith('good_'):
                # Close all other dropdowns first
                for dropdown in game_state.dropdowns.values():
                    dropdown.is_open = False
                # Open clicked dropdown
                section = field_name.split('_')[1]
                dropdown_name = f'dropdown_{section}'
                game_state.dropdowns[dropdown_name].is_open = True
                game_state.active_dropdown = dropdown_name
                return
            elif field_name.startswith(('buy_', 'sell_')):
                _handle_trade_button(field_name, game_state, goods, depot)
            else:
                game_state.mouse_clicked_on = field_name
            return

    # Handle toggle boxes in chart
    for i, box in enumerate(game_state.image_boxes):
        if box.collidepoint(pos):
            good = goods[i]
            visible_count = sum(1 for g in goods if g.show_in_charts)
            if not (visible_count == 1 and good.show_in_charts):
                good.toggle_display()
            return

    # Check for plus button clicks in depot view detail area
    if hasattr(game_state, "depot_plus_rects") and game_state.depot_plus_rects:
        for label, rect in game_state.depot_plus_rects.items():
            if rect.collidepoint(pos):
                if hasattr(game_state, "detail_panel") and game_state.detail_panel is not None:
                    # Check if the panel is already visible for this statistic
                    if game_state.detail_panel.visible and game_state.detail_panel.current_statistic == label:
                        # Close the panel if already open for this statistic
                        game_state.detail_panel.visible = False
                    else:
                        # Open the detail panel with the specific label
                        game_state.detail_panel.show_for_statistic(label)
                return
    # For backward compatibility
    elif hasattr(game_state, "depot_plus_rect") and game_state.depot_plus_rect and game_state.depot_plus_rect.collidepoint(pos):
        if hasattr(game_state, "detail_panel") and game_state.detail_panel is not None:
            game_state.detail_panel.toggle()
        return

    # Reset mouse click if clicked elsewhere
    game_state.mouse_clicked_on = "none"

def _handle_trade_button(button_name: str, game_state: 'GameState', goods: List['Good'], depot: 'Depot') -> None:
    """Execute a trade action when a buy or sell button is clicked.
    
    Args:
        button_name: Internal name of the button (e.g., 'buy_one').
        game_state: Current state of the game engine.
        goods: List of all tradeable goods.
        depot: The player's depot/inventory model.
    """
    action, section = button_name.split('_')
    good_name = game_state.input_fields[f'good_{section}']
    try:
        quantity = int(game_state.input_fields[f'quantity_{section}'])
        for good in goods:
            if good.name == good_name:
                # Store the result of the trade attempt
                trade_successful = False
                if action == 'buy':
                    trade_successful = depot.buy(good, quantity, game_state)
                else:
                    trade_successful = depot.sell(good, quantity, game_state)
                
                # Only trigger effects if trade was successful
                if trade_successful:
                    game_state.money_effect_timer = 30  # effect lasts 30 frames
                    if action == 'buy':
                        game_state.money_effect_color = (230, 0, 0)  # red glow for buy
                    else:
                        game_state.money_effect_color = (0, 180, 10)  # green glow for sell
                    game_state.button_click_effects[f'{action}_{section}'] = 10
                break
    except (ValueError, Exception) as e:
        game_state.show_message(str(e))
