from ..house import House
from typing import TYPE_CHECKING, Tuple, List, Dict
from ...ui.transaction_feedback import on_money_spent
from ...config.constants import (
    POPULATION_SHARE_POOR,
    POPULATION_SHARE_COMMONS,
    POPULATION_SHARE_MIDDLING_SORT,
    POPULATION_SHARE_NOBILITY,
)

if TYPE_CHECKING:
    from ...game_state import GameState

class Town(House):
    """Represents a town hall institution in the game with donation functionality."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.treasury = 0
        self.happiness = 80
        self.max_citizens = 0
        self.citizens = 0
        self.base_groups: Dict[str, int] = {}  # map-defined 100% baseline, set by initialize_population
        self.population_groups: Dict[str, int] = {
            "Poor": 0,
            "Commons": 0,
            "Middling Sort": 0,
            "Nobility": 0,
        }
        self.happiness_groups: Dict[str, float] = {
            "Poor": 80.0,
            "Commons": 80.0,
            "Middling Sort": 80.0,
            "Nobility": 80.0,
        }

    def initialize_population(self, houses: List[House]) -> None:
        """Initialize town population statistics from already loaded houses.

        Population capacity is the sum of all residential house capacities.
        Houses without a positive ``max_inhabitants`` are treated as non-residential.
        For now, all residential houses are initialized at 100% occupancy.

        Args:
            houses: All loaded house objects from the map.
        """
        max_citizens = 0
        citizens = 0

        for house in houses:
            if house.max_inhabitants <= 0:
                continue

            house.inhabitants = round(house.max_inhabitants * 0.8)
            max_citizens += house.max_inhabitants
            citizens += house.inhabitants

        self.max_citizens = max_citizens
        self.citizens = citizens
        self.population_groups = self._split_population_into_groups(citizens)
        self.base_groups = dict(self.population_groups)

    @staticmethod
    def _split_population_into_groups(total_population: int) -> Dict[str, int]:
        """Split a total population into social groups using configured shares."""
        group_shares = [
            ("Poor", POPULATION_SHARE_POOR),
            ("Commons", POPULATION_SHARE_COMMONS),
            ("Middling Sort", POPULATION_SHARE_MIDDLING_SORT),
            ("Nobility", POPULATION_SHARE_NOBILITY),
        ]

        exact_values = [(name, total_population * share) for name, share in group_shares]
        population_groups = {name: int(value) for name, value in exact_values}

        assigned = sum(population_groups.values())
        remainder = total_population - assigned

        if remainder > 0:
            fractions_sorted = sorted(
                exact_values,
                key=lambda item: item[1] - int(item[1]),
                reverse=True
            )
            for idx in range(remainder):
                group_name = fractions_sorted[idx % len(fractions_sorted)][0]
                population_groups[group_name] += 1

        return population_groups

    def open_donation_menu(self, game_state: 'GameState', click_pos: Tuple[int, int]) -> None:
        """Opens the donation menu replacing the current menu.
        
        Args:
            game_state: The current game state.
            click_pos: The screen position where the user clicked.
        """
        # Local import to avoid circular dependency
        from ...ui.helper_modules.donation_menu import DonationMenu
        
        def donation_callback(amount: int):
            if not hasattr(game_state.game, 'depot'):
                return

            depot = game_state.game.depot
            
            if depot.book_donation(amount, category="Town Donations"):
                self.treasury += amount
                on_money_spent(game_state)
                
                # Close menu on success
                game_state.info_window = None 
                game_state.active_house_menu = None
            else:
                # Show warning and keep menu open
                if hasattr(game_state, 'show_warning'):
                    game_state.show_warning("Not enough money!")
        
        # Replace current info window with new one
        game_state.info_window = DonationMenu(
            game_state.screen, 
            self, 
            game_state, 
            click_pos=click_pos, 
            callback=donation_callback,
            category="Town Donations"
        )
        game_state.active_house_menu = self

    def open_license_view(self, game_state: 'GameState', click_pos: Tuple[int, int]) -> None:
        """Opens the full contract overview showing all trading licenses.
        
        Args:
            game_state: The current game state.
            click_pos: The screen position where the user clicked.
        """
        from ...ui.helper_modules.contract_overview import ContractOverview

        game_state.info_window = ContractOverview(
            game_state.screen,
            game_state,
            house=self
        )
        game_state.active_house_menu = self

    def open_population_stats(self, game_state: 'GameState', click_pos: Tuple[int, int]) -> None:
        """Opens the population statistics overview.
        
        Args:
            game_state: The current game state.
            click_pos: The screen position where the user clicked.
        """
        from ...ui.helper_modules.population_stats import PopulationStats

        game_state.info_window = PopulationStats(
            game_state.screen,
            game_state,
            house=self
        )
        game_state.active_house_menu = self
