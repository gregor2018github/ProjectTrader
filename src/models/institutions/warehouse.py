from ..house import House


class Warehouse(House):
    """A purchasable warehouse building on the map."""

    def __init__(self, *args, buy_price: int = 0, buy_storage: int = 0,
                 buy_type: str = "Warehouse", tmx_id: int = 0, **kwargs):
        super().__init__(*args, **kwargs)
        self.buy_price: int = buy_price
        self.buy_storage: int = buy_storage
        self.buy_type: str = buy_type
        self.tmx_id: int = tmx_id
        self.is_owned: bool = False
