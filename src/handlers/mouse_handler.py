import pygame
from ..ui.info_window import InfoWindow  # Add this import

def handle_mouse_click(pos, buttons, game_state, goods, depot):
    # Reset hover states for all goods
    for good in goods:
        good.hovered = False

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
                from ..ui.dialogue import show_dialogue
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
                # Handle settings action
                pass
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
                from ..ui.dialogue import show_dialogue
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
                from ..ui.dialogue import show_dialogue
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
                from ..ui.dialogue import show_dialogue
                game_state.dialogue = show_dialogue(
                    game_state.screen,
                    game_state.game,
                    "portrait_merchant",  # Use picture parameter
                    "Uncle Gared",        # Use npc_name parameter
                    """Uncle Gared pulls you into a quick embrace before stepping back, his hands trembling slightly as he leans on his gnarled oak staff. He calmly smiles at you.""",
                    ["I will help you!"],
                    "story_teller_3"  # Sound to play
                )                 
            else:
                # Close the dialogue
                game_state.dialogue = None
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

    # Reset mouse click if clicked elsewhere
    game_state.mouse_clicked_on = "none"

def _handle_trade_button(button_name, game_state, goods, depot):
    action, section = button_name.split('_')
    good_name = game_state.input_fields[f'good_{section}']
    try:
        quantity = int(game_state.input_fields[f'quantity_{section}'])
        for good in goods:
            if good.name == good_name:
                if action == 'buy':
                    depot.buy(good, quantity, game_state)
                else:
                    depot.sell(good, quantity, game_state)
                break
    except (ValueError, Exception) as e:
        game_state.show_message(str(e))
