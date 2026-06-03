from dataclasses import dataclass
from decimal import Decimal

from commands import command, CATEGORY_PRODUCTS


@dataclass
class Product:
    id: int
    sku: str
    name: str
    price: Decimal
    category: str


def _render_product(product: Product):  # pylint: disable=unused-argument
    """
    Отображает информацию о продукте в виде таблицы внутри панели.
    Используйте rich.table.Table и rich.panel.Panel для форматирования.
    """


@command("list products", "список всех товаров", CATEGORY_PRODUCTS)
def list_products() -> None:
    """
    Выводит список всех продуктов из таблицы catalog.products.
    Используйте rich.table.Table для отображения данных.
    Колонки: ID, SKU, Название, Цена, Категория
    """


@command("show product", "информация о товаре", CATEGORY_PRODUCTS)
def show_product(_id: str) -> None:
    """
    Показывает детальную информацию о продукте по его ID.
    Если продукт не найден, выводит ошибку через _render_error.
    Используйте _render_product для отображения найденного продукта.
    """


@command("add product", "добавить товар (интерактивно)", CATEGORY_PRODUCTS)
def add_product() -> None:
    """
    Добавляет новый продукт в базу данных.
    Запрашивает у пользователя: SKU, название, цену и категорию.
    Используйте prompt с валидаторами для ввода данных.
    """


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
