from src.game import Game
from src.ui.main_menu import MainMenu

def main() -> None:
    """Start the game."""
    while True:
        menu = MainMenu()
        choice = menu.run()

        if choice != "new_game":
            break

        result = Game().run()

        if result != "main_menu":
            break

if __name__ == "__main__":
    main()
