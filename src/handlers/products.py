from dataclasses import dataclass
from decimal import Decimal

from commands import command, CATEGORY_PRODUCTS

from dataclasses import dataclass

from prompt_toolkit import prompt
from prompt_toolkit.completion import WordCompleter
from psycopg.rows import class_row
from psycopg import sql
from rich.panel import Panel
from rich.table import Table

from console import console, render_error
from db import get_conn
from validators import ChoiceValidator, NonEmptyValidator, YesNoValidator, PriceValidator
from commands import command, CATEGORY_WAREHOUSES
from auth import ROLE_SALES_MANAGER, ROLE_CATALOG_MANAGER, ALL_ROLES, ROLE_INVENTORY_MANAGER
from prompt_toolkit.shortcuts import choice


@dataclass
class Product:
    id: int
    sku: str
    name: str
    price: Decimal
    category_id: int
    category_name: str | None = None


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
    table.add_row("Категория", product.category_name or "Не указана")

    panel = Panel(
        table,
        expand=False,
        title=f"[bold green]Продукт #{product.id}[/bold green]",
        border_style="green",
    )

    console.print(panel)


def _enrich_products_with_categories(conn, products: list[Product]) -> None:
    category_ids = list({p.category_id for p in products if p.category_id is not None})

    if not category_ids:
        return

    placeholders = sql.SQL(', ').join(sql.Placeholder() for _ in category_ids)
    query = sql.SQL("SELECT id, name FROM catalog.product_categories WHERE id IN ({})").format(placeholders)

    with conn.cursor() as cur:
        cur.execute(query, category_ids)
        category_map = {row[0]: row[1] for row in cur.fetchall()}

    for product in products:
        if product.category_id:
            product.category_name = category_map.get(product.category_id)

def _get_category_name(conn, category_id: int | None) -> str | None:
    if category_id is None:
        return None

    with conn.cursor() as cur:
        cur.execute("SELECT name FROM catalog.product_categories WHERE id = %s", (category_id,))
        result = cur.fetchone()
        return result[0] if result else None

@command("list products", "список всех товаров", CATEGORY_PRODUCTS, [ALL_ROLES])
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
    table.add_column("Категория", style="white", min_width=15)

    with conn.cursor(row_factory=class_row(Product)) as cur:
        cur.execute("SELECT * FROM catalog.products")
        products: list[Product] = cur.fetchall()

    _enrich_products_with_categories(conn, products)

    for product in products:
        table.add_row(
            str(product.id),
            product.sku,
            product.name,
            str(product.price),
            product.category_name or "Не указана"
        )
    console.print(table)


@command("show product", "информация о товаре", CATEGORY_PRODUCTS, [ALL_ROLES])
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

    product.category_name = _get_category_name(conn, product.category_id)

    _render_product(product)

@command("add product", "добавить товар (интерактивно)", CATEGORY_PRODUCTS, [ROLE_CATALOG_MANAGER])
def add_product() -> None:
    """
    Добавляет новый продукт в базу данных.
    Запрашивает у пользователя: SKU, название, цену и категорию.
    Используйте prompt с валидаторами для ввода данных.
    """
    conn = get_conn()

    with conn.cursor() as cur:
        cur.execute("SELECT id, name FROM catalog.product_categories ORDER BY name")
        categories = cur.fetchall()

    if not categories:
        render_error("Не найдено ни одной категории. Сначала создайте категорию товаров.")
        return

    category_name_to_id = {cat[1]: cat[0] for cat in categories}
    category_names = list(category_name_to_id.keys())

    category_completer = WordCompleter(category_names, ignore_case=True)
    category_validator = ChoiceValidator(
        category_names,
        message="Название категории должно быть из списка. Используйте Tab для автодополнения."
    )

    sku = prompt("SKU: ", validator=NonEmptyValidator()).strip()
    name = prompt("Название: ", validator=NonEmptyValidator()).strip()
    price = prompt("Цена: ", validator=PriceValidator()).strip()

    console.print("[yellow]Доступные категории:[/yellow]")
    for cat_name in category_names:
        console.print(f"  - {cat_name}")

    category_name_str = prompt(
        "Название категории: ",
        validator=category_validator,
        completer=category_completer
    ).strip()

    category_id = category_name_to_id[category_name_str]
    conn.execute(
        "INSERT INTO catalog.products (sku, name, price, category_id) VALUES (%s, %s, %s, %s)",
        (sku, name, price, category_id),
    )
    console.print(f"[green]Товар {name} (SKU: {sku}) добавлен [/green]")

@command("edit product", "редактировать товар", CATEGORY_PRODUCTS, [ROLE_CATALOG_MANAGER])
def edit_product(_id: str) -> None:
    """
    Редактирует существующий продукт.
    Сначала проверяет существование продукта по ID.
    Предлагает текущие значения как default при вводе новых данных.
    """
    conn = get_conn()

    with conn.cursor(row_factory=class_row(Product)) as cur:
        cur.execute("SELECT id, sku, name, price, category_id FROM catalog.products WHERE id = %s", (_id,))
        product: Product | None = cur.fetchone()

    if product is None:
        render_error(f"Товар с ID {_id} не найден")
        return

    product.category_name = _get_category_name(conn, product.category_id)
    _render_product(product)

    with conn.cursor() as cur:
        cur.execute("SELECT id, name FROM catalog.product_categories ORDER BY name")
        categories = cur.fetchall()

    category_name_to_id = {cat[1]: cat[0] for cat in categories}
    category_names = list(category_name_to_id.keys())

    category_completer = WordCompleter(category_names, ignore_case=True)
    category_validator = ChoiceValidator(
        category_names,
        message="Название категории должно быть из списка. Используйте Tab для автодополнения."
    )

    sku = prompt("SKU: ", default=product.sku, validator=NonEmptyValidator()).strip()
    name = prompt("Название: ", default=product.name, validator=NonEmptyValidator()).strip()
    price = prompt("Цена: ", default=str(product.price), validator=PriceValidator()).strip()

    console.print("[yellow]Доступные категории:[/yellow]")
    for cat_name in category_names:
        console.print(f"  - {cat_name}")

    default_category_name = product.category_name or ""

    category_name_str = prompt(
        "Название категории: ",
        default=default_category_name,
        validator=category_validator,
        completer=category_completer
    ).strip()

    category_id = category_name_to_id[category_name_str]

    conn.execute(
        """UPDATE catalog.products 
           SET sku = %s, name = %s, price = %s, category_id = %s
           WHERE id = %s""",
        (sku, name, price, category_id, _id),
    )
    console.print(f"[green]Товар {name} (SKU: {sku}) обновлен [/green]")


@command("delete product", "удалить товар", CATEGORY_PRODUCTS, [ROLE_CATALOG_MANAGER])
def delete_product(_id: str) -> None:
    """
    Удаляет продукт из базы данных.
    Сначала показывает информацию о продукте.
    Запрашивает подтверждение перед удалением.
    """
    conn = get_conn()

    with conn.cursor(row_factory=class_row(Product)) as cur:
        cur.execute("SELECT id, sku, name, price, category_id FROM catalog.products WHERE id = %s", (_id,))
        product: Product | None = cur.fetchone()

    if product is None:
        render_error(f"Товар с ID {_id} не найден")
        return

    product.category_name = _get_category_name(conn, product.category_id)
    _render_product(product)

    answer = prompt("Вы уверены? (y/n, д/н): ", validator=YesNoValidator())

    if YesNoValidator.is_yes(answer):
        conn.execute("DELETE FROM catalog.products WHERE id = %s", (_id,))
        console.print(f"[green]Товар {product.name} (SKU: {product.sku}) удален [/green]")

@command("view product stock", "остатки по продукту", CATEGORY_PRODUCTS, [ROLE_INVENTORY_MANAGER])
def view_product_stock() -> None:
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT id, sku, name FROM catalog.products ORDER BY name")
        products = cur.fetchall()

    if not products:
        render_error("Каталог пуст.")
        return

    options = [(p[0], f"{p[2]} ({p[1]})") for p in products]
    selected_id = choice(message="Выберите продукт:", options=options)

    product_name = next(p[2] for p in products if p[0] == selected_id)

    with conn.cursor() as cur:
        cur.execute("""
            SELECT c.name || ', ' || w.address || COALESCE(', ' || w.label, '') AS wh_info,
                   COALESCE(st.quantity, 0) AS stock_qty,
                   COALESCE(res.quantity, 0) AS reserve_qty,
                   COALESCE(st.quantity, 0) + COALESCE(res.quantity, 0) AS total
            FROM catalog.warehouses w
            JOIN catalog.cities c ON w.city_id = c.id
            LEFT JOIN inventory.stock st ON st.warehouse_id = w.id AND st.product_id = %s
            LEFT JOIN (
                SELECT warehouse_id, SUM(quantity) as quantity
                FROM inventory.reserves
                WHERE product_id = %s
                GROUP BY warehouse_id
            ) res ON res.warehouse_id = w.id
            ORDER BY stock_qty DESC
        """, (selected_id, selected_id))
        rows = cur.fetchall()

    table = Table(title=f"Остатки продукта '{product_name}' по складам", show_header=True, header_style="bold cyan")
    table.add_column("Склад", style="green", min_width=30)
    table.add_column("Сток", style="yellow", justify="right")
    table.add_column("Резерв", style="magenta", justify="right")
    table.add_column("Всего", style="bold white", justify="right")

    for row in rows:
        wh_info, stock, reserve, total = row
        table.add_row(wh_info, str(stock), str(reserve), str(total))

    console.print(table)