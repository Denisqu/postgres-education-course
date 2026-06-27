from dataclasses import dataclass
from decimal import Decimal

from prompt_toolkit import prompt
from prompt_toolkit.completion import WordCompleter
from psycopg.rows import class_row
from rich.panel import Panel
from rich.table import Table

from console import console, render_error
from db import get_conn
from validators import ChoiceValidator, NonEmptyValidator, YesNoValidator, PositiveIntValidator
from commands import command, CATEGORY_ORDERS

# ------------------------------------------------------------
# Константы и валидаторы
# ------------------------------------------------------------

ORDER_STATUSES = [
    "unpublished", "new", "processing", "pending", "packing", "shipped"
]
status_validator = ChoiceValidator(
    ORDER_STATUSES,
    message=f"Статус должен быть одним из: {', '.join(ORDER_STATUSES)}",
)


@dataclass
class Order:
    id: int
    status: str
    total_amount: Decimal
    created_at: str
    warehouse_id: int

@dataclass
class OrderItem:
    order_id: int
    product_id: int
    product_name: str
    price: Decimal
    quantity: int

@dataclass
class Product:
    id: int
    sku: str
    name: str
    price: Decimal


def _get_all_products() -> list[Product]:
    """Получить все товары из каталога."""
    conn = get_conn()
    with conn.cursor(row_factory=class_row(Product)) as cur:
        cur.execute("SELECT id, sku, name, price FROM catalog.products ORDER BY name")
        return cur.fetchall()


def _get_order_items(order_id: int) -> list[OrderItem]:
    """Получить позиции заказа с названиями товаров."""
    conn = get_conn()
    with conn.cursor(row_factory=class_row(OrderItem)) as cur:
        cur.execute("""
            SELECT oi.order_id, oi.product_id,
                   p.name AS product_name, oi.price, oi.quantity
            FROM sales.order_items oi
            JOIN catalog.products p ON p.id = oi.product_id
            WHERE oi.order_id = %s
            ORDER BY p.name
        """, (order_id,))
        return cur.fetchall()


def _recalculate_total(order_id: int) -> None:
    """Пересчитать total_amount заказа на основе его позиций."""
    conn = get_conn()
    conn.execute("""
        UPDATE sales.orders
        SET total_amount = COALESCE(
            (SELECT SUM(price * quantity) FROM sales.order_items WHERE order_id = %s),
            0
        )
        WHERE id = %s
    """, (order_id, order_id))


def _render_order(order: Order) -> None:
    """Красивый вывод информации о заказе."""
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Поле", style="bold cyan", width=18)
    table.add_column("Значение", style="white")

    table.add_row("ID", str(order.id))
    table.add_row("Статус", f"[bold]{order.status}[/bold]")
    table.add_row("Сумма", f"{order.total_amount:.2f}")
    table.add_row("Создан", str(order.created_at))
    table.add_row("Склад ID", str(order.warehouse_id))

    panel = Panel(
        table,
        expand=False,
        title=f"[bold green]Заказ #{order.id}[/bold green]",
        border_style="green",
    )
    console.print(panel)


def _render_order_items(items: list[OrderItem]) -> None:
    """Вывод позиций заказа в виде таблицы."""
    if not items:
        console.print("[yellow]В заказе нет товаров.[/yellow]")
        return

    table = Table(title="Позиции заказа", show_header=True, header_style="bold cyan")
    table.add_column("Товар", style="green", min_width=20)
    table.add_column("Цена", style="yellow", justify="right")
    table.add_column("Кол-во", style="magenta", justify="right")
    table.add_column("Сумма", style="bold white", justify="right")

    for item in items:
        table.add_row(
            item.product_name,
            f"{item.price:.2f}",
            str(item.quantity),
            f"{item.price * item.quantity:.2f}",
        )
    console.print(table)


def _get_order_or_fail(order_id: str) -> Order | None:
    """Получить заказ по ID или вывести ошибку."""
    conn = get_conn()
    with conn.cursor(row_factory=class_row(Order)) as cur:
        cur.execute("SELECT * FROM sales.orders WHERE id = %s", (order_id,))
        order: Order | None = cur.fetchone()

    if order is None:
        render_error(f"Заказ с ID {order_id} не найден")
    return order


def _check_editable(order: Order, action: str) -> bool:
    """Проверить, можно ли редактировать/удалять заказ."""
    if order.status != "unpublished":
        render_error(
            f"Нельзя {action} заказ в статусе '{order.status}'. "
            f"Редактирование и удаление разрешены только для статуса 'unpublished'."
        )
        return False
    return True


def _prompt_product_choice(
    products: list[Product],
    exclude_ids: set[int],
) -> Product | None:
    """
    Интерактивный выбор товара с автокомплитом.
    Исключает товары, уже добавленные в заказ.
    """
    available = [p for p in products if p.id not in exclude_ids]
    if not available:
        render_error("Нет доступных товаров для добавления (все уже в заказе или каталог пуст).")
        return None

    # Автокомплит по "SKU | Название | Цена"
    choices = [f"{p.name} ({p.sku}, {p.price:.2f})" for p in available]
    completer = WordCompleter(choices, ignore_case=True, sentence=True)
    validator = ChoiceValidator(
        choices,
        message="Выберите товар из списка. Используйте Tab для автодополнения.",
    )

    raw = prompt("Товар: ", completer=completer, validator=validator).strip()

    # Найти выбранный товар по индексу в отфильтрованном списке
    try:
        idx = choices.index(raw)
        return available[idx]
    except ValueError:
        return None


# ------------------------------------------------------------
# Интерактивное добавление позиций заказа
# ------------------------------------------------------------

def _add_items_interactively(order_id: int) -> None:
    """Цикл добавления товаров в заказ до отказа пользователя."""
    # TODO: При выборе продукта в order_item следует дать возможность пользователю выбрать продукт с помощью автокомплита. Все-таки потенциально продуктов может быть много, поэтому выбирать из списка не совсем корректно с точки зрения UX.
    products = _get_all_products()
    if not products:
        console.print("[yellow]Каталог товаров пуст. Добавьте товары перед созданием заказа.[/yellow]")
        return

    while True:
        existing = _get_order_items(order_id)
        exclude_ids = {item.product_id for item in existing}

        console.print("\n[bold cyan]Добавление товара в заказ[/bold cyan]")
        product = _prompt_product_choice(products, exclude_ids)
        if product is None:
            break

        quantity_str = prompt(
            "Количество: ",
            validator=PositiveIntValidator(),
        ).strip()
        quantity = int(quantity_str)

        conn = get_conn()
        conn.execute(
            """
            INSERT INTO sales.order_items (order_id, product_id, price, quantity)
            VALUES (%s, %s, %s, %s)
            """,
            (order_id, product.id, product.price, quantity),
        )
        _recalculate_total(order_id)
        console.print(
            f"[green]Добавлено: {product.name} × {quantity} по {product.price:.2f}[/green]"
        )

        more = prompt("Добавить ещё товар? (y/n, д/н): ", validator=YesNoValidator()).strip()
        if not YesNoValidator.is_yes(more):
            break


# ------------------------------------------------------------
# CRUD: Orders
# ------------------------------------------------------------

@command("list orders", "список всех заказов", CATEGORY_ORDERS)
def list_orders() -> None:
    conn = get_conn()
    table = Table(title="Заказы", show_header=True, header_style="bold cyan")

    table.add_column("ID", style="dim", width=6, justify="right")
    table.add_column("Статус", style="magenta", min_width=15)
    table.add_column("Сумма", style="yellow", justify="right")
    table.add_column("Создан", style="green", min_width=20)
    table.add_column("Склад ID", style="white", justify="right")

    with conn.cursor(row_factory=class_row(Order)) as cur:
        cur.execute("SELECT * FROM sales.orders ORDER BY id")
        orders: list[Order] = cur.fetchall()

    for o in orders:
        table.add_row(
            str(o.id),
            o.status,
            f"{o.total_amount:.2f}",
            str(o.created_at),
            str(o.warehouse_id),
        )
    console.print(table)


@command("show order", "информация о заказе", CATEGORY_ORDERS)
def show_order(order_id: str) -> None:
    order = _get_order_or_fail(order_id)
    if order is None:
        return

    _render_order(order)
    items = _get_order_items(int(order_id))
    _render_order_items(items)


@command("add order", "добавить заказ (интерактивно)", CATEGORY_ORDERS)
def add_order() -> None:
    conn = get_conn()

    # Находим центральный склад
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM catalog.warehouses WHERE is_central = True")
        central_warehouse = cur.fetchone()

    if not central_warehouse:
        render_error("Центральный склад не найден. Сначала создайте центральный склад.")
        return

    warehouse_id = central_warehouse[0]

    # Создаём заказ
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO sales.orders (status, warehouse_id)
            VALUES ('unpublished', %s)
            RETURNING id
            """,
            (warehouse_id,),
        )
        new_order_id: int = cur.fetchone()[0]

    console.print(f"[green]Заказ #{new_order_id} создан (отгрузка с центрального склада).[/green]")

    # Сразу предлагаем добавить товары
    add_now = prompt("Добавить товары в заказ сейчас? (y/n, д/н): ", validator=YesNoValidator()).strip()
    if YesNoValidator.is_yes(add_now):
        _add_items_interactively(new_order_id)

    # Финальный вывод
    order = _get_order_or_fail(str(new_order_id))
    if order:
        _render_order(order)
        _render_order_items(_get_order_items(new_order_id))


@command("edit order", "редактировать заказ", CATEGORY_ORDERS)
def edit_order(order_id: str) -> None:
    order = _get_order_or_fail(order_id)
    if order is None:
        return
    if not _check_editable(order, "редактировать"):
        return

    conn = get_conn()

    # Выбор нового склада
    with conn.cursor() as cur:
        cur.execute("SELECT id, city, address, label FROM catalog.warehouses ORDER BY id")
        warehouses = cur.fetchall()

    if not warehouses:
        render_error("Нет доступных складов.")
        return

    wh_choices = [
        f"{w[0]} | {w[1]} | {w[2]}" + (f" | {w[3]}" if w[3] else "")
        for w in warehouses
    ]
    wh_completer = WordCompleter(wh_choices, ignore_case=True, sentence=True)
    wh_validator = ChoiceValidator(wh_choices, message="Выберите склад из списка.")

    wh_raw = prompt(
        "Склад: ",
        completer=wh_completer,
        validator=wh_validator,
        default=next(
            (c for c, w in zip(wh_choices, warehouses) if w[0] == order.warehouse_id),
            wh_choices[0],
        ),
    ).strip()

    try:
        idx = wh_choices.index(wh_raw)
        new_warehouse_id = warehouses[idx][0]
    except ValueError:
        render_error("Не удалось определить склад.")
        return

    conn.execute(
        "UPDATE sales.orders SET warehouse_id = %s WHERE id = %s",
        (new_warehouse_id, order_id),
    )
    console.print(f"[green]Заказ #{order_id} обновлён.[/green]")


@command("delete order", "удалить заказ", CATEGORY_ORDERS)
def delete_order(order_id: str) -> None:
    order = _get_order_or_fail(order_id)
    if order is None:
        return
    if not _check_editable(order, "удалять"):
        return

    _render_order(order)
    _render_order_items(_get_order_items(int(order_id)))

    answer = prompt("Вы уверены? (y/n, д/н): ", validator=YesNoValidator())
    if YesNoValidator.is_yes(answer):
        conn = get_conn()
        conn.execute("DELETE FROM sales.orders WHERE id = %s", (order_id,))
        console.print(f"[green]Заказ #{order_id} удалён.[/green]")


@command("publish order", "опубликовать заказ (unpublished -> new)", CATEGORY_ORDERS)
def publish_order(order_id: str) -> None:
    order = _get_order_or_fail(order_id)
    if order is None:
        return

    if order.status != "unpublished":
        render_error(
            f"Заказ уже имеет статус '{order.status}'. "
            f"Публикация возможна только из статуса 'unpublished'."
        )
        return

    items = _get_order_items(int(order_id))
    if not items:
        render_error("Нельзя опубликовать пустой заказ. Добавьте хотя бы один товар.")
        return

    conn = get_conn()
    conn.execute(
        "UPDATE sales.orders SET status = 'new' WHERE id = %s",
        (order_id,),
    )
    console.print(f"[green]Заказ #{order_id} опубликован (статус: new).[/green]")


# ------------------------------------------------------------
# CRUD: Order Items
# ------------------------------------------------------------

def _prompt_order_item_choice(order_id: int) -> OrderItem | None:
    """Выбор позиции заказа через prompt_toolkit choice."""
    items = _get_order_items(order_id)
    if not items:
        render_error("В заказе нет позиций.")
        return None

    choices = [
        f"{it.product_name} | {it.price:.2f} × {it.quantity}"
        for it in items
    ]
    completer = WordCompleter(choices, ignore_case=True, sentence=True)
    validator = ChoiceValidator(choices, message="Выберите позицию из списка.")

    raw = prompt("Позиция: ", completer=completer, validator=validator).strip()
    try:
        idx = choices.index(raw)
        return items[idx]
    except ValueError:
        return None


@command("add order_item", "добавить товар в заказ", CATEGORY_ORDERS)
def add_order_item(order_id: str) -> None:
    order = _get_order_or_fail(order_id)
    if order is None:
        return
    if not _check_editable(order, "добавлять товары в"):
        return

    products = _get_all_products()
    if not products:
        render_error("Каталог товаров пуст.")
        return

    existing = _get_order_items(int(order_id))
    exclude_ids = {item.product_id for item in existing}

    product = _prompt_product_choice(products, exclude_ids)
    if product is None:
        return

    quantity_str = prompt(
        "Количество: ",
        validator=PositiveIntValidator(),
    ).strip()
    quantity = int(quantity_str)

    conn = get_conn()
    conn.execute(
        """
        INSERT INTO sales.order_items (order_id, product_id, price, quantity)
        VALUES (%s, %s, %s, %s)
        """,
        (order_id, product.id, product.price, quantity),
    )
    _recalculate_total(int(order_id))
    console.print(
        f"[green]Добавлено: {product.name} × {quantity} по {product.price:.2f}[/green]"
    )


@command("edit order_item", "редактировать позицию заказа", CATEGORY_ORDERS)
def edit_order_item(order_id: str) -> None:
    order = _get_order_or_fail(order_id)
    if order is None:
        return
    if not _check_editable(order, "редактировать позиции"):
        return

    item = _prompt_order_item_choice(int(order_id))
    if item is None:
        return

    quantity_str = prompt(
        f"Количество (было {item.quantity}): ",
        default=str(item.quantity),
        validator=PositiveIntValidator(),
    ).strip()
    new_quantity = int(quantity_str)

    conn = get_conn()
    conn.execute(
        """
        UPDATE sales.order_items 
        SET quantity = %s 
        WHERE order_id = %s AND product_id = %s
        """,
        (new_quantity, order_id, item.product_id),
    )
    _recalculate_total(int(order_id))
    console.print(f"[green]Позиция '{item.product_name}' обновлена: количество = {new_quantity}.[/green]")

@command("delete order_item", "удалить позицию из заказа", CATEGORY_ORDERS)
def delete_order_item(order_id: str) -> None:
    order = _get_order_or_fail(order_id)
    if order is None:
        return
    if not _check_editable(order, "удалять позиции из"):
        return

    item = _prompt_order_item_choice(int(order_id))
    if item is None:
        return

    answer = prompt("Удалить эту позицию? (y/n, д/н): ", validator=YesNoValidator())
    if YesNoValidator.is_yes(answer):
        conn = get_conn()
        conn.execute(
            """
            DELETE FROM sales.order_items 
            WHERE order_id = %s AND product_id = %s
            """,
            (order_id, item.product_id),
        )
        _recalculate_total(int(order_id))
        console.print(f"[green]Позиция '{item.product_name}' удалена.[/green]")