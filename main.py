from src.game import Game
from src.ui.main_menu import MainMenu

def main() -> None:
    """Start the game."""
    while True:
        menu = MainMenu()
        choice, save_data = menu.run()

        if choice == "exit":
            break
        elif choice == "new_game":
            result = Game(save_data=None).run()
        elif choice == "load_game" and save_data is not None:
            result = Game(save_data=save_data).run()
        else:
            break

        if result != "main_menu":
            break

if __name__ == "__main__":
    main()
