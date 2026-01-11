import pygame
from typing import List, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from ..game_state import GameState
    from ..models.good import Good
    from ..models.depot import Depot

def handle_keyboard_input(event: pygame.event.Event, game_state: 'GameState', goods: List['Good'], depot: 'Depot') -> None:
    """Process pygame keyboard events for text input and hotkeys.
    
    Args:
        event: The pygame event to process.
        game_state: Current state of the game engine.
        goods: List of all tradeable goods.
        depot: The player's depot/inventory model.
    """
    # Handle input fields
    if game_state.mouse_clicked_on.startswith("quantity_"):
        field = game_state.mouse_clicked_on
        current_value = game_state.input_fields[field]
        
        if event.key == pygame.K_RETURN or event.key == pygame.K_ESCAPE:
            # Accept input and deselect field
            game_state.mouse_clicked_on = "none"
            game_state.cursor_position = 0
        elif event.key == pygame.K_BACKSPACE:
            if game_state.cursor_position > 0:
                # Remove character at cursor position
                game_state.input_fields[field] = (current_value[:game_state.cursor_position-1] + 
                                                current_value[game_state.cursor_position:])
                game_state.cursor_position -= 1
        elif event.key == pygame.K_LEFT:
            game_state.cursor_position = max(0, game_state.cursor_position - 1)
        elif event.key == pygame.K_RIGHT:
            game_state.cursor_position = min(len(current_value), game_state.cursor_position + 1)
        elif event.unicode.isnumeric():
            # Insert number at cursor position
            game_state.input_fields[field] = (current_value[:game_state.cursor_position] + 
                                            event.unicode + 
                                            current_value[game_state.cursor_position:])
            game_state.cursor_position += 1

    # Handle function keys
    elif event.key in [pygame.K_F1, pygame.K_F2, pygame.K_F3, pygame.K_F4, pygame.K_F5, pygame.K_F6]:
        _handle_function_key(event.key, game_state, goods, depot)
    # Add time control hotkeys
    elif event.key == pygame.K_SPACE:
        # Toggle between pause and normal speed
        if game_state.time_level == 1:  # If paused
            game_state.time_level = 3   # Set to normal speed
        else:
            game_state.time_level = 1   # Pause
    elif event.key in [pygame.K_MINUS, pygame.K_KP_MINUS]:
        # When map is active, control zoom; otherwise control time
        if game_state.map_state and hasattr(game_state.game, 'game_map'):
            game_state.game.game_map.handle_zoom(-1)  # Zoom out
        else:
            # Slow down time (decrease level)
            game_state.time_level = max(1, game_state.time_level - 1)
    elif event.key in [pygame.K_PLUS, pygame.K_KP_PLUS, pygame.K_EQUALS]:
        # When map is active, control zoom; otherwise control time
        if game_state.map_state and hasattr(game_state.game, 'game_map'):
            game_state.game.game_map.handle_zoom(1)  # Zoom in
        else:
            # Speed up time (increase level)
            game_state.time_level = min(5, game_state.time_level + 1)


def _handle_function_key(key: int, game_state: 'GameState', goods: List['Good'], depot: 'Depot') -> None:
    """Dispatch actions for F1-F6 trading hotkeys.
    
    Args:
        key: The key code (e.g., pygame.K_F1).
        game_state: Current state of the game engine.
        goods: List of all tradeable goods.
        depot: The player's depot/inventory model.
    """
    key_actions = {
        pygame.K_F1: ('one', 'buy'),
        pygame.K_F2: ('one', 'sell'),
        pygame.K_F3: ('two', 'buy'),
        pygame.K_F4: ('two', 'sell'),
        pygame.K_F5: ('three', 'buy'),
        pygame.K_F6: ('three', 'sell')
    }
    
    if key in key_actions:
        section, action = key_actions[key]
        good_name = game_state.input_fields[f'good_{section}']
        try:
            quantity = int(game_state.input_fields[f'quantity_{section}'])
        except ValueError:
            game_state.show_message("Invalid quantity input")
            return
        
        for good in goods:
            if good.name == good_name:
                try:
                    trade_successful = False
                    if action == 'buy':
                        trade_successful = depot.buy(good, quantity, game_state)
                    else:
                        trade_successful = depot.sell(good, quantity, game_state)
                    
                    if trade_successful:
                        game_state.money_effect_timer = 30  # effect lasts 30 frames
                        if action == 'buy':
                            game_state.money_effect_color = (230, 0, 0)  # red glow for buy
                        else:
                            game_state.money_effect_color = (0, 180, 10)  # green glow for sell
                        game_state.button_click_effects[f'{action}_{section}'] = 10
                except Exception as e:
                    game_state.show_message(str(e))
                break
