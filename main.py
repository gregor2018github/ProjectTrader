import pygame
from src.game import Game
from src.ui.main_menu import MainMenu
from src.ui.loading_screen import run_loading_screen


def main() -> None:
    """Start the game."""
    while True:
        menu = MainMenu()
        choice, save_data = menu.run()

        if choice == "exit":
            break
        elif choice not in ("new_game", "load_game"):
            break
        elif choice == "load_game" and save_data is None:
            break

        screen = pygame.display.get_surface()
        run_loading_screen(screen)

        result = Game(save_data=save_data, screen=screen).run()

        if result != "main_menu":
            break


if __name__ == "__main__":
    main()
