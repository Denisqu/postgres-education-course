from dataclasses import dataclass
from decimal import Decimal

from commands import command, CATEGORY_PRODUCT_CATEGORIES

@dataclass
class ProductCategory:
    id: int
    name: str

@command("list product_categories", "список всех складов", CATEGORY_PRODUCT_CATEGORIES)
def list_product_categories() -> None:
    table = Table(title="Склады", show_header=True, header_style="bold cyan")
    table.add_column("ID", style="dim", width=6, justify="right")
    table.add_column("Город", style="green", min_width=20)
    table.add_column("Адрес", style="yellow", min_width=30)
    table.add_column("Метка", style="magenta", min_width=15)
    table.add_column("Центральный?", style="white", min_width=15)
    pass

def show_product_category(_id:str) -> None:
    pass

def add_product_category() -> None:
    pass

def edit_product_category(_id: str) -> None:
    pass

def delete_product_category(_id: str) -> None:
    pass