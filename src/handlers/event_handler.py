import pygame
from typing import List, Dict, Any, Optional
from .keyboard_handler import handle_keyboard_input
from .mouse_handler import handle_mouse_click
from ..ui.helper_modules.info_window import InfoWindow

class EventHandler:
    """Handles all user input and system events for the game.
    
    This class dispatches events to keyboard and mouse handlers, manages
    the game's running state, and handles specialized events like music transitions.
    """
    
    def __init__(self) -> None:
        """Initialize the event handler."""
        self.running: bool = True

    def handle_events(self, 
                      event: pygame.event.Event, 
                      game_state: Any, 
                      goods: List[Any], 
                      depot: Any, 
                      buttons: Dict[str, pygame.Rect]) -> bool:
        """Process a single pygame event and update game state accordingly.
        
        Args:
            event: The pygame event to process.
            game_state: The current game state object.
            goods: List of all interactive goods in the market.
            depot: The player's depot/inventory object.
            buttons: A dictionary of interactive UI button rectangles.
            
        Returns:
            bool: The current running state of the game (False if quit).
        """
        if event.type == pygame.QUIT:
            self.running = False

        # Handle music end event to play the next song
        if hasattr(game_state.game, 'sound_control') and event.type == game_state.game.sound_control.MUSIC_END_EVENT:
            game_state.game.sound_control.handle_music_end_event(game_state.game)
            return self.running

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_q and not game_state.info_window:
                game_state.info_window = InfoWindow(game_state.screen, 
                                                    "Do you want to quit?", 
                                                    ["Back", "Quit"], 
                                                    game_state.font,
                                                    game_state.game)
            else:
                handle_keyboard_input(event, game_state, goods, depot)
                
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if game_state.info_window:
                choice = game_state.info_window.handle_click(event.pos)
                if choice == "Quit":
                    self.running = False
                elif choice in ("Back", "Save and Close"):
                    game_state.info_window = None
            else:
                handle_mouse_click(pygame.mouse.get_pos(), buttons, game_state, goods, depot)
                
        elif event.type == pygame.MOUSEWHEEL:
            mouse_pos = pygame.mouse.get_pos()
            scroll_speed = 20
            
            # Check if map is active and mouse is over map area
            if game_state.map_view_mode and hasattr(game_state.game, 'game_map'):
                from ..config.constants import SCREEN_WIDTH, SCREEN_HEIGHT, MODULE_WIDTH
                # Determine map view rect based on mode
                if game_state.map_view_mode == 'full':
                    map_view_rect = pygame.Rect(0, 60, MODULE_WIDTH * 2, SCREEN_HEIGHT - 120)
                elif game_state.map_view_mode == 'left':
                    map_view_rect = pygame.Rect(0, 60, MODULE_WIDTH, SCREEN_HEIGHT - 120)
                elif game_state.map_view_mode == 'right':
                    map_view_rect = pygame.Rect(MODULE_WIDTH, 60, MODULE_WIDTH, SCREEN_HEIGHT - 120)
                else:
                    map_view_rect = None
                    
                if map_view_rect and map_view_rect.collidepoint(mouse_pos):
                    # Handle zoom with mouse wheel on map
                    game_state.game.game_map.handle_zoom(event.y)
                    return self.running
            
            # Check if detail panel is visible and mouse is over it
            if hasattr(game_state, "detail_panel") and game_state.detail_panel is not None and game_state.detail_panel.visible and game_state.detail_panel.rect.collidepoint(mouse_pos):
                game_state.detail_panel.scroll_offset = max(0, min(game_state.detail_panel.scroll_offset - event.y * scroll_speed, game_state.detail_panel.max_scroll))
            else:
                # Otherwise check depot view
                screen = game_state.screen
                width = screen.get_width() // 2 - 42
                height = screen.get_height() - 120
                x = screen.get_width() - width
                y = 60
                depot_rect = pygame.Rect(x, y, width, height)
                if depot_rect.collidepoint(mouse_pos):
                    game_state.depot_scroll_offset = getattr(game_state, "depot_scroll_offset", 0) - event.y * scroll_speed

        return self.running
