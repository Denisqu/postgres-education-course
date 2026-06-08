from dataclasses import dataclass
from decimal import Decimal

from commands import command, CATEGORY_PRODUCTS

from dataclasses import dataclass

from prompt_toolkit import prompt
from prompt_toolkit.completion import WordCompleter
from psycopg.rows import class_row
from rich.panel import Panel
from rich.table import Table

from console import console, render_error
from db import get_conn
from validators import ChoiceValidator, NonEmptyValidator, YesNoValidator, PriceValidator,
from commands import command, CATEGORY_WAREHOUSES


@dataclass
class Product:
    id: int
    sku: str
    name: str
    price: Decimal
    category_id: int # TODO: как сюда замаппить сразу category ????


def _render_product(product: Product):  # pylint: disable=unused-argument
    """
    Отображает информацию о продукте в виде таблицы внутри панели.
    Используйте rich.table.Table и rich.panel.Panel для форматирования.
    """
    table = Table(show_header=False, box=None, padding=(0, 2))

    table.add_column("Поле", style="bold cyan", width=15)
    table.add_column("Значение", style="white")

    table.add_row("ID", str(product.id))
    table.add_row("SKU", product.sku)
    table.add_row("Имя", product.name)
    table.add_row("Цена", str(product.price))
    table.add_row("ID категории", str(product.category_id)) #TODO: Fixme

    panel = Panel(
        table,
        expand=False,
        title=f"[bold green]Продукт #{product.id}[/bold green]",
        border_style="green",
    )

    console.print(panel)

@command("list products", "список всех товаров", CATEGORY_PRODUCTS)
def list_products() -> None:
    """
    Выводит список всех продуктов из таблицы catalog.products.
    Используйте rich.table.Table для отображения данных.
    Колонки: ID, SKU, Название, Цена, Категория
    """
    conn = get_conn()
    table = Table(title="Товары", show_header=True, header_style="bold cyan")
    table.add_column("ID", style="dim", width=6, justify="right")
    table.add_column("SKU", style="green", min_width=20)
    table.add_column("Название", style="yellow", min_width=30)
    table.add_column("Цена", style="magenta", min_width=15)
    table.add_column("Категория", style="white", min_width=15) #TODO: FIXME

    with conn.cursor(row_factory=class_row(Product)) as cur:
        cur.execute("SELECT * FROM catalog.products")
        products: list[Product] = cur.fetchall()

    for product in products:
        table.add_row(
            str(product.id),
            product.sku,
            product.name,
            str(product.price),
            str(product.category_id) # TODO: FIXME
        )
    console.print(table)


@command("show product", "информация о товаре", CATEGORY_PRODUCTS)
def show_product(_id: str) -> None:
    """
    Показывает детальную информацию о продукте по его ID.
    Если продукт не найден, выводит ошибку через _render_error.
    Используйте _render_product для отображения найденного продукта.
    """
    conn = get_conn()
    with conn.cursor(row_factory=class_row(Product)) as cur:
        cur.execute("SELECT * FROM catalog.products WHERE id = %s", (_id,))
        product: Product | None = cur.fetchone()

    if product is None:
        render_error(f"Товар с ID {_id} не найден")
        return

    _render_product(product)

@command("add product", "добавить товар (интерактивно)", CATEGORY_PRODUCTS)
def add_product() -> None:
    """
    Добавляет новый продукт в базу данных.
    Запрашивает у пользователя: SKU, название, цену и категорию.
    Используйте prompt с валидаторами для ввода данных.
    """

    # @dataclass
    # class Product:
    #     id: int
    #     sku: str
    #     name: str
    #     price: Decimal
    #     category_id: int  # TODO: как сюда замаппить сразу category ????

    conn = get_conn()
    sku = prompt("SKU: ", validator=NonEmptyValidator()).strip()
    name = prompt("Название: ", validator=NonEmptyValidator()).strip()
    price = prompt("Метка (необязательно): ", validator=PriceValidator()).strip()
    category_id = prompt("ID категории товара: ", validator=NonEmptyValidator())

    # TODO: validate category_id

    # conn.execute(
    #     "INSERT INTO catalog.warehouses (city, address, label, is_central) VALUES (%s, %s, %s, %s)",
    #     (city, address, label, YesNoValidator.is_yes(is_central)),
    # )
    console.print(f"[green]Товар {name} добавлен [/green]")

@command("edit product", "редактировать товар", CATEGORY_PRODUCTS)
def edit_product(_id: str) -> None:
    """
    Редактирует существующий продукт.
    Сначала проверяет существование продукта по ID.
    Предлагает текущие значения как default при вводе новых данных.
    """


@command("delete product", "удалить товар", CATEGORY_PRODUCTS)
def delete_product(_id: str) -> None:
    """
    Удаляет продукт из базы данных.
    Сначала показывает информацию о продукте.
    Запрашивает подтверждение перед удалением.
    """
