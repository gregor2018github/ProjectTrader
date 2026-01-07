from typing import Tuple

class Player:
    """Represents the player in the game, managing their status, reputation, and finances.
    
    The Player class tracks the player's name, score, reputation, cost of living,
    and their current position in the game world.
    """
    
    def __init__(self, name: str, cost_of_living: float) -> None:
        """Initialize the player with basic stats.
        
        Args:
            name: The player's name.
            cost_of_living: The initial daily cost of living.
        """
        self.name: str = name
        self.score: int = 0
        self.reputation: int = 0
        self.daily_cost_of_living: float = cost_of_living
        self.position: Tuple[int, int] = (0, 0)  # Default position, can be updated later

    def add_score(self, score: int) -> None:
        """Add points to the player's total score.
        
        Args:
            score: The number of points to add.
        """
        self.score += score
    
    def change_reputation(self, reputation: int) -> None:
        """Modify the player's reputation score.
        
        Args:
            reputation: The amount to change reputation by (positive or negative).
        """
        self.reputation += reputation

    def change_daily_cost_of_living(self, cost: float) -> None:
        """Update the player's daily cost of living expenses.
        
        Args:
            cost: The amount to change the daily cost by.
        """
        self.daily_cost_of_living += cost

    def __str__(self) -> str:
        """Return a string representation of the player's status."""
        return f"{self.name} has {self.score} points"