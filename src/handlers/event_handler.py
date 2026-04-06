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

        # Handle Contract View
        if game_state.contract_acquisition:
            game_state.contract_acquisition.handle_event(event)
            if not game_state.contract_acquisition.active:
                game_state.contract_acquisition = None
                game_state.time_level = game_state.previous_time_level
            
            # Consume input events if contract is active
            if event.type in [pygame.KEYDOWN, pygame.KEYUP, pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEMOTION, pygame.MOUSEWHEEL]:
                return self.running

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
            elif not (game_state.info_window and hasattr(game_state.info_window, 'handle_event')):
                handle_keyboard_input(event, game_state, goods, depot)
                
        # Pass event to info_window if it supports handle_event
        if game_state.info_window and hasattr(game_state.info_window, 'handle_event'):
            game_state.info_window.handle_event(event)
            
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if game_state.info_window:
                if hasattr(game_state.info_window, 'handle_click'):
                    choice = game_state.info_window.handle_click(event.pos)
                    if choice == "Quit":
                        self.running = False
                    elif choice == "Yes":
                        game_state.return_to_main_menu = True
                        self.running = False
                    elif choice in ("Back", "No", "Save and Close", "OK", "Cancel"):
                        game_state.info_window = None
                    elif isinstance(choice, str) and choice.startswith("save_slot_"):
                        from ..persistence.save_manager import save_game as _save
                        slot = int(choice[-1])
                        save_name = getattr(game_state.info_window, "save_name", "")
                        try:
                            _save(slot, game_state, game_state.game.player,
                                  game_state.game.depot, game_state.game.goods,
                                  save_name=save_name,
                                  population_manager=game_state.game.population_manager)
                            game_state.info_window = None
                            game_state.show_warning(f"Game saved to Slot {slot}.")
                        except Exception as e:
                            game_state.info_window = None
                            game_state.show_warning(f"Save failed: {e}")
                    elif isinstance(choice, str) and choice.startswith("load_slot_"):
                        slot = int(choice[-1])
                        game_state._pending_load_slot = slot
                        game_state.info_window = InfoWindow(
                            game_state.screen,
                            "Load game?\nCurrent progress will be lost.",
                            ["No", "Load"],
                            game_state.font,
                            game_state.game,
                        )
                    elif choice == "Load":
                        slot = getattr(game_state, "_pending_load_slot", None)
                        if slot:
                            from ..persistence.save_manager import load_game as _load, apply_save_data
                            try:
                                data = _load(slot)
                                apply_save_data(data, game_state, game_state.game.player,
                                               game_state.game.depot, game_state.game.goods,
                                               population_manager=game_state.game.population_manager)
                                game_state.game.game_map.map_player.x = game_state.game.player.position[0]
                                game_state.game.game_map.map_player.y = game_state.game.player.position[1]
                                game_state.info_window = None
                                game_state._pending_load_slot = None
                                game_state.show_warning("Game loaded.")
                            except Exception as e:
                                game_state.info_window = None
                                game_state._pending_load_slot = None
                                game_state.show_warning(f"Load failed: {e}")
            else:
                handle_mouse_click(pygame.mouse.get_pos(), buttons, game_state, goods, depot)
                
        elif event.type == pygame.MOUSEWHEEL:
            mouse_pos = pygame.mouse.get_pos()
            scroll_speed = 20

            # Don't zoom the map when a scrollable dialog has consumed the event
            if game_state.info_window and hasattr(game_state.info_window, '_max_scroll'):
                return self.running

            # Check if map is active and mouse is over map area
            if game_state.is_map_visible and hasattr(game_state.game, 'game_map'):
                from ..config.constants import SCREEN_WIDTH, SCREEN_HEIGHT, MODULE_WIDTH
                
                # Check for map on left side (includes full screen if left is map)
                if game_state.left_side_mode == 'map':
                    left_rect = pygame.Rect(0, 60, MODULE_WIDTH, SCREEN_HEIGHT - 120)
                    if game_state.left_side_mode == game_state.right_side_mode:
                        left_rect.width = MODULE_WIDTH * 2
                    
                    if left_rect.collidepoint(mouse_pos):
                        game_state.game.game_map.handle_zoom(event.y)
                        return self.running
                
                # Check for map on right side
                if game_state.right_side_mode == 'map':
                    right_rect = pygame.Rect(MODULE_WIDTH, 60, MODULE_WIDTH, SCREEN_HEIGHT - 120)
                    if right_rect.collidepoint(mouse_pos):
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
