from src.game import Game
from src.ui.main_menu import MainMenu

def main() -> None:
    """Start the game."""
    menu = MainMenu()
    choice = menu.run()

    if choice == "new_game":
        game = Game()
        game.run()

if __name__ == "__main__":
    main()
