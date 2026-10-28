from ..house import House


class Warehouse(House):
    """A purchasable warehouse building on the map.

    It stores goods in buy_slots slots of buy_slot_size units each, every slot
    holding one good only (Tiled properties Buy_slots and Buy_slot_size).
    """

    def __init__(self, *args, buy_price: int = 0, buy_slots: int = 0, buy_slot_size: int = 0,
                 buy_type: str = "Warehouse", tmx_id: int = 0, **kwargs):
        super().__init__(*args, **kwargs)
        self.buy_price: int = buy_price
        self.buy_slots: int = buy_slots
        self.buy_slot_size: int = buy_slot_size
        self.buy_type: str = buy_type
        self.tmx_id: int = tmx_id
        self.is_owned: bool = False

    @property
    def buy_storage(self) -> int:
        """How many units the warehouse holds when every slot is full."""
        return self.buy_slots * self.buy_slot_size
