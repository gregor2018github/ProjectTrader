import sys
import os

# Add the project root to the path to make relative imports work
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from src.game import Game

def main():
    game = Game()
    game.run()

if __name__ == "__main__":
    main()
