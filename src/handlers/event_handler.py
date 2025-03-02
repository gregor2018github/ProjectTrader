import pygame
from .keyboard_handler import handle_keyboard_input
from .mouse_handler import handle_mouse_click
from ..ui.info_window import InfoWindow

class EventHandler:
    def __init__(self):
        self.running = True

    def handle_events(self, event, game_state, goods, depot, buttons):
        if event.type == pygame.QUIT:
            self.running = False
            
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_q and not game_state.info_window:
                game_state.info_window = InfoWindow(game_state.screen, 
                                                    "Do you want to quit?", 
                                                    ["Back", "Quit"], 
                                                    game_state.font,
                                                    game_state.game)  # Pass game reference
            else:
                handle_keyboard_input(event, game_state, goods, depot)
                
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if game_state.info_window:
                choice = game_state.info_window.handle_click(event.pos)
                if choice == "Quit":
                    self.running = False
                elif choice == "Back":
                    game_state.info_window = None
            else:
                handle_mouse_click(pygame.mouse.get_pos(), buttons, game_state, goods, depot)

        return self.running
