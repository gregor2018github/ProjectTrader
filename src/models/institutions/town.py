from ..house import House
from typing import TYPE_CHECKING, Optional, Tuple, List, Dict
from ...ui.transaction_feedback import on_money_donated
from ...sim.state import TownSpec
from ...sim.systems.population import starting_inhabitants

if TYPE_CHECKING:
    from ...game_state import GameState
    from ...sim import Simulation
    from ...sim.state import PopulationState

class Town(House):
    """The town hall on the map, with its menus (donations, licenses, statistics).

    Its people live in the simulation (``PopulationState``); ``citizens``,
    ``happiness``, ``population_groups`` and the rest are read from there on
    every access, so the town hall keeps none of those numbers itself. This
    view is a seam kept for P0 (see ``docs/sim_core.md``).
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.treasury = 0
        self._sim: Optional["Simulation"] = None

    def initialize_population(self, houses: List[House]) -> TownSpec:
        """Move people into the map's houses, STARTING_OCCUPANCY full, and describe the town for the simulation.

        Houses without a positive ``max_inhabitants`` are treated as non-residential.

        Args:
            houses: All loaded house objects from the map.

        Returns:
            The town as the simulation founds it (``Simulation.found_town``).
        """
        for house in houses:
            if house.max_inhabitants > 0:
                house.inhabitants = starting_inhabitants(house.max_inhabitants)
        return TownSpec(house_capacities=[h.max_inhabitants for h in houses if h.max_inhabitants > 0],
                        name=self.name or "Town")

    def attach(self, sim: "Simulation") -> None:
        """Show the people of *sim*'s town."""
        self._sim = sim

    @property
    def _population(self) -> Optional["PopulationState"]:
        return self._sim.state.population if self._sim is not None else None

    @property
    def citizens(self) -> int:
        pop = self._population
        return pop.citizens if pop is not None else 0

    @property
    def max_citizens(self) -> int:
        pop = self._population
        return pop.max_citizens if pop is not None else 0

    @property
    def happiness(self) -> float:
        pop = self._population
        return pop.happiness if pop is not None else 0.0

    @property
    def population_groups(self) -> Dict[str, int]:
        """Heads per class (a fresh dict; change the simulation, not this)."""
        pop = self._population
        return {c.name: c.count for c in pop.classes.values()} if pop is not None else {}

    @property
    def happiness_groups(self) -> Dict[str, float]:
        """Happiness per class (a fresh dict; change the simulation, not this)."""
        pop = self._population
        return {c.name: c.happiness for c in pop.classes.values()} if pop is not None else {}

    def open_donation_menu(self, game_state: 'GameState', click_pos) -> None:
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
                on_money_donated(game_state, amount)
                gain = game_state.game.merchant_rank.record_gift(amount)
                game_state.log_event("DONATION", f"Donated {amount:.0f}g to the Town (reputation +{gain:.2f})")
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

    def open_statistics_view(self, game_state: 'GameState', click_pos: Tuple[int, int]) -> None:
        """Opens the general lifetime statistics overlay.

        Args:
            game_state: The current game state.
            click_pos: The screen position where the user clicked.
        """
        from ...ui.helper_modules.statistics_view import StatisticsView

        game_state.info_window = StatisticsView(game_state.screen, game_state)
        game_state.active_house_menu = self
