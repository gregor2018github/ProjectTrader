import pygame

def handle_keyboard_input(event, game_state, goods, depot):
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


def _handle_function_key(key, game_state, goods, depot):
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
        quantity = int(game_state.input_fields[f'quantity_{section}'])
        
        for good in goods:
            if good.name == good_name:
                try:
                    if action == 'buy':
                        depot.buy(good, quantity, game_state)
                    else:
                        depot.sell(good, quantity, game_state)
                except Exception as e:
                    game_state.show_message(str(e))
                break
