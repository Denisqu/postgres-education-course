from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime

from prompt_toolkit import prompt
from prompt_toolkit.completion import WordCompleter
from psycopg.rows import class_row
from rich.panel import Panel
from rich.table import Table

from console import console, render_error
from db import get_conn
from validators import ChoiceValidator, NonEmptyValidator, YesNoValidator
from commands import command, CATEGORY_ORDERS
from handlers.warehouses import Warehouse


ORDER_STATUSES = ['unpublished', 'new', 'processing', 'pending', 'packing', 'shipped']
status_completer = WordCompleter(ORDER_STATUSES, ignore_case=True)
status_validator = ChoiceValidator(ORDER_STATUSES, message="Статус должен быть из списка. Используйте Tab.")


@dataclass
class Order:
    id: int
    status: str
    total_amount: Decimal
    created_at: datetime
    warehouse_id: int


@dataclass
class Product:
    id: int
    sku: str
    name: str
    price: Decimal
    category_id: int


def get_warehouses():
    conn = get_conn()
    with conn.cursor(row_factory=class_row(Warehouse)) as cur:
        cur.execute("SELECT * FROM catalog.warehouses")
        return cur.fetchall()


def _recalculate_order_total(conn, order_id: int) -> None:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT COALESCE(SUM(p.price), 0)
            FROM sales.order_items oi
            JOIN catalog.products p ON oi.product_id = p.id
            WHERE oi.order_id = %s
        """, (order_id,))
        total = cur.fetchone()[0]

    conn.execute("""
        UPDATE sales.orders SET total_amount = %s WHERE id = %s
    """, (total, order_id))


def _add_order_item_interactive(conn, order_id: int) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT product_id FROM sales.order_items WHERE order_id = %s", (order_id,))
        existing_ids = {row[0] for row in cur.fetchall()}

    with conn.cursor(row_factory=class_row(Product)) as cur:
        cur.execute("SELECT * FROM catalog.products")
        all_products = cur.fetchall()

    available_products = [p for p in all_products if p.id not in existing_ids]

    if not available_products:
        console.print("[yellow]Все товары уже добавлены в этот заказ или в каталоге нет товаров.[/yellow]")
        return

    sku_to_product = {p.sku: p for p in available_products}
    skus = list(sku_to_product.keys())

    sku_completer = WordCompleter(skus, ignore_case=True)
    sku_validator = ChoiceValidator(skus, message="Артикул должен быть из списка. Используйте Tab.")

    # TODO: в промпте не использовать id товара, а его наименование. id использовать только в SQL
    sku = prompt("Артикул товара: ", validator=sku_validator, completer=sku_completer).strip()
    product = sku_to_product[sku]

    conn.execute("""
        INSERT INTO sales.order_items (order_id, product_id) VALUES (%s, %s)
    """, (order_id, product.id))

    console.print(f"[green]Товар '{product.name}' (ID: {product.id}) добавлен в заказ #{order_id}.[/green]")


@command("list orders", "список всех заказов", CATEGORY_ORDERS)
def list_orders() -> None:
    conn = get_conn()
    table = Table(title="Заказы", show_header=True, header_style="bold cyan")

    table.add_column("ID", style="dim", width=6, justify="right")
    table.add_column("Статус", style="green", min_width=15)
    table.add_column("Сумма", style="yellow", min_width=10, justify="right")
    table.add_column("Создан", style="magenta", min_width=20)
    table.add_column("Склад ID", style="white", min_width=10, justify="right")

    with conn.cursor(row_factory=class_row(Order)) as cur:
        cur.execute("SELECT * FROM sales.orders ORDER BY id")
        orders: list[Order] = cur.fetchall()

    for order in orders:
        table.add_row(
            str(order.id),
            order.status,
            str(order.total_amount),
            order.created_at.strftime("%Y-%m-%d %H:%M"),
            str(order.warehouse_id)
        )
    console.print(table)


@command("show order", "информация о заказе", CATEGORY_ORDERS)
def show_order(_id: str) -> None:
    conn = get_conn()
    with conn.cursor(row_factory=class_row(Order)) as cur:
        cur.execute("SELECT * FROM sales.orders WHERE id = %s", (_id,))
        order: Order | None = cur.fetchone()

    if order is None:
        render_error(f"Заказ с ID {_id} не найден")
        return

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Поле", style="bold cyan", width=15)
    table.add_column("Значение", style="white")

    table.add_row("ID", str(order.id))
    table.add_row("Статус", order.status)
    table.add_row("Сумма", str(order.total_amount))
    table.add_row("Создан", order.created_at.strftime("%Y-%m-%d %H:%M:%S"))
    table.add_row("Склад ID", str(order.warehouse_id))

    panel = Panel(
        table,
        expand=False,
        title=f"[bold green]Заказ #{order.id}[/bold green]",
        border_style="green",
    )
    console.print(panel)

    with conn.cursor() as cur:
        cur.execute("""
            SELECT oi.product_id, p.name, p.sku, p.price 
            FROM sales.order_items oi
            JOIN catalog.products p ON oi.product_id = p.id
            WHERE oi.order_id = %s
        """, (_id,))
        items = cur.fetchall()

    if items:
        items_table = Table(title="Товары в заказе", show_header=True, header_style="bold cyan")
        items_table.add_column("ID товара", justify="right")
        items_table.add_column("Артикул")
        items_table.add_column("Название")
        items_table.add_column("Цена", justify="right")
        for item in items:
            items_table.add_row(str(item[0]), item[2], item[1], str(item[3]))
        console.print(items_table)
    else:
        console.print("[yellow]В заказе нет товаров.[/yellow]")


@command("add order", "добавить заказ (интерактивно)", CATEGORY_ORDERS)
def add_order() -> None:
    conn = get_conn()

    warehouses = get_warehouses()
    if not warehouses:
        render_error("Сначала добавьте хотя бы один склад.")
        return

    wh_ids = [str(w.id) for w in warehouses]
    wh_completer = WordCompleter(wh_ids, ignore_case=True)
    wh_validator = ChoiceValidator(wh_ids, message="ID склада должен быть из списка. Используйте Tab.")

    warehouse_id = prompt("ID склада: ", validator=wh_validator, completer=wh_completer).strip()
    status = "unpublished"

    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO sales.orders (status, warehouse_id) 
            VALUES (%s, %s) RETURNING id
        """, (status, warehouse_id))
        order_id = cur.fetchone()[0]

    console.print(f"[green]Заказ #{order_id} успешно создан.[/green]")

    while True:
        add_more = prompt("Добавить товар в заказ? (y/n, д/н): ", validator=YesNoValidator()).strip()
        if not YesNoValidator.is_yes(add_more):
            break
        _add_order_item_interactive(conn, order_id)

    _recalculate_order_total(conn, order_id)


@command("edit order", "редактировать заказ", CATEGORY_ORDERS)
def edit_order(_id: str) -> None:
    conn = get_conn()
    with conn.cursor(row_factory=class_row(Order)) as cur:
        cur.execute("SELECT * FROM sales.orders WHERE id = %s", (_id,))
        order: Order | None = cur.fetchone()

    if order is None:
        render_error(f"Заказ с ID {_id} не найден")
        return

    warehouses = get_warehouses()
    wh_ids = [str(w.id) for w in warehouses]
    wh_completer = WordCompleter(wh_ids, ignore_case=True)
    wh_validator = ChoiceValidator(wh_ids, message="ID склада должен быть из списка. Используйте Tab.")

    warehouse_id = prompt("ID склада: ", default=str(order.warehouse_id), validator=wh_validator,
                          completer=wh_completer).strip()
    status = prompt("Статус: ", default=order.status, validator=status_validator, completer=status_completer).strip()

    conn.execute("""
        UPDATE sales.orders SET status = %s, warehouse_id = %s WHERE id = %s
    """, (status, warehouse_id, _id))

    console.print(f"[green]Заказ #{_id} успешно обновлен.[/green]")


@command("delete order", "удалить заказ", CATEGORY_ORDERS)
def delete_order(_id: str) -> None:
    conn = get_conn()
    with conn.cursor(row_factory=class_row(Order)) as cur:
        cur.execute("SELECT * FROM sales.orders WHERE id = %s", (_id,))
        order: Order | None = cur.fetchone()

    if order is None:
        render_error(f"Заказ с ID {_id} не найден")
        return

    answer = prompt("Вы уверены? (y/n, д/н): ", validator=YesNoValidator())

    if YesNoValidator.is_yes(answer):
        conn.execute("DELETE FROM sales.orders WHERE id = %s", (_id,))
        console.print(f"[green]Заказ #{_id} удален.[/green]")


@command("add order_item", "добавить товар в заказ", CATEGORY_ORDERS)
def add_order_item_cmd(order_id: str) -> None:
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM sales.orders WHERE id = %s", (order_id,))
        if not cur.fetchone():
            render_error(f"Заказ с ID {order_id} не найден.")
            return

    _add_order_item_interactive(conn, int(order_id))
    _recalculate_order_total(conn, int(order_id))


@command("edit order_item", "редактировать товар в заказе", CATEGORY_ORDERS)
def edit_order_item_cmd(order_id: str) -> None:
    conn = get_conn()

    with conn.cursor() as cur:
        cur.execute("""
            SELECT oi.product_id, p.name, p.sku 
            FROM sales.order_items oi
            JOIN catalog.products p ON oi.product_id = p.id
            WHERE oi.order_id = %s
        """, (order_id,))
        items = cur.fetchall()

    if not items:
        render_error(f"В заказе #{order_id} нет товаров для редактирования.")
        return

    choices = []
    product_ids = []
    for i, (prod_id, name, sku) in enumerate(items, 1):
        choice_str = f"{i} - {name} ({sku})"
        choices.append(choice_str)
        product_ids.append(prod_id)

    choice_validator = ChoiceValidator(choices, message="Выберите товар из списка. Используйте Tab.")
    choice_completer = WordCompleter(choices, ignore_case=True)

    selected = prompt("Выберите товар для редактирования:\n" + "\n".join(choices) + "\nВаш выбор: ",
                      validator=choice_validator, completer=choice_completer).strip()

    idx = choices.index(selected)
    old_product_id = product_ids[idx]

    with conn.cursor() as cur:
        cur.execute("SELECT product_id FROM sales.order_items WHERE order_id = %s AND product_id != %s",
                    (order_id, old_product_id))
        existing_ids = {row[0] for row in cur.fetchall()}

    with conn.cursor(row_factory=class_row(Product)) as cur:
        cur.execute("SELECT id, sku, name, price FROM catalog.products")
        all_products = cur.fetchall()

    available_products = [p for p in all_products if p.id not in existing_ids]

    if not available_products:
        render_error("Нет доступных товаров для замены.")
        return

    sku_to_product = {p.sku: p for p in available_products}
    skus = list(sku_to_product.keys())

    sku_completer = WordCompleter(skus, ignore_case=True)
    sku_validator = ChoiceValidator(skus, message="Артикул должен быть из списка. Используйте Tab.")

    new_sku = prompt("Новый артикул товара: ", validator=sku_validator, completer=sku_completer).strip()
    new_product = sku_to_product[new_sku]

    conn.execute("""
        UPDATE sales.order_items SET product_id = %s 
        WHERE order_id = %s AND product_id = %s
    """, (new_product.id, order_id, old_product_id))

    _recalculate_order_total(conn, int(order_id))
    console.print(f"[green]Товар в заказе #{order_id} успешно заменен на '{new_product.name}'.[/green]")


@command("delete order_item", "удалить товар из заказа", CATEGORY_ORDERS)
def delete_order_item_cmd(order_id: str) -> None:
    conn = get_conn()

    with conn.cursor() as cur:
        cur.execute("""
            SELECT oi.product_id, p.name, p.sku 
            FROM sales.order_items oi
            JOIN catalog.products p ON oi.product_id = p.id
            WHERE oi.order_id = %s
        """, (order_id,))
        items = cur.fetchall()

    if not items:
        render_error(f"В заказе #{order_id} нет товаров для удаления.")
        return

    choices = []
    product_ids = []
    for i, (prod_id, name, sku) in enumerate(items, 1):
        choice_str = f"{i} - {name} ({sku})"
        choices.append(choice_str)
        product_ids.append(prod_id)

    choice_validator = ChoiceValidator(choices, message="Выберите товар из списка. Используйте Tab.")
    choice_completer = WordCompleter(choices, ignore_case=True)

    selected = prompt("Выберите товар для удаления:\n" + "\n".join(choices) + "\nВаш выбор: ",
                      validator=choice_validator, completer=choice_completer).strip()

    idx = choices.index(selected)
    product_id = product_ids[idx]

    answer = prompt("Вы уверены? (y/n, д/н): ", validator=YesNoValidator()).strip()
    if YesNoValidator.is_yes(answer):
        conn.execute("""
            DELETE FROM sales.order_items 
            WHERE order_id = %s AND product_id = %s
        """, (order_id, product_id))
        _recalculate_order_total(conn, int(order_id))
        console.print(f"[green]Товар удален из заказа #{order_id}.[/green]")
