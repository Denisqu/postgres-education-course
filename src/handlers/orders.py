from dataclasses import dataclass
from decimal import Decimal

from prompt_toolkit import prompt
from prompt_toolkit.shortcuts import choice
from psycopg.rows import class_row
from rich.panel import Panel
from rich.table import Table

from console import console, render_error
from db import get_conn
from validators import ChoiceValidator, NonEmptyValidator, YesNoValidator, PositiveIntValidator
from commands import command, CATEGORY_ORDERS
from auth import ROLE_SALES_MANAGER, ROLE_CATALOG_MANAGER, ROLE_INVENTORY_MANAGER, auth_user

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
    created_by_username: str
    warehouse_info: str = ""
    processing_by_username: str | None = None


@dataclass
class OrderItem:
    order_id: int
    product_id: int
    product_name: str
    price: Decimal
    quantity: int


@dataclass
class OrderItemInv:
    order_id: int
    product_id: int
    product_name: str
    price: Decimal
    quantity: int
    item_status: str


@dataclass
class Product:
    id: int
    sku: str
    name: str
    price: Decimal


def _get_available_products(order_id: int) -> list[Product]:
    conn = get_conn()
    with conn.cursor(row_factory=class_row(Product)) as cur:
        cur.execute("""
            SELECT id, sku, name, price 
            FROM catalog.products 
            WHERE id NOT IN (
                SELECT product_id FROM sales.order_items WHERE order_id = %s
            )
            ORDER BY name
        """, (order_id,))
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


def _get_order_items_inv(order_id: int, order_status: str, warehouse_id: int) -> list[OrderItemInv]:
    """Получить позиции заказа с вычисляемым статусом для inventory_manager."""
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
        items = cur.fetchall()

    if not items:
        return []

    product_ids = [it.product_id for it in items]

    # Получаем резервы
    with conn.cursor() as cur:
        cur.execute("""
            SELECT product_id, SUM(quantity) as qty
            FROM inventory.reserves
            WHERE order_id = %s AND product_id = ANY(%s)
            GROUP BY product_id
        """, (order_id, product_ids))
        reserves = {row[0]: row[1] for row in cur.fetchall()}

    # Получаем накладные на доставку
    with conn.cursor() as cur:
        cur.execute("""
            SELECT di.product_id, di.status, SUM(di.quantity) as qty
            FROM inventory.delivery_items di
            JOIN inventory.deliveries d ON di.delivery_id = d.id
            WHERE d.order_id = %s AND di.product_id = ANY(%s)
            GROUP BY di.product_id, di.status
        """, (order_id, product_ids))
        deliveries = {}
        for row in cur.fetchall():
            pid, status, qty = row
            if pid not in deliveries:
                deliveries[pid] = {'planned': 0, 'shipped': 0}
            deliveries[pid][status] += qty

    # Получаем перемещения в пути
    with conn.cursor() as cur:
        cur.execute("""
            SELECT ti.product_id, c.name as from_city, t.arriving_at, SUM(ti.quantity) as qty
            FROM inventory.transfer_items ti
            JOIN inventory.transfers t ON ti.transfer_id = t.id
            JOIN inventory.reserves r ON ti.reserve_id = r.id
            JOIN catalog.warehouses w ON t.from_warehouse_id = w.id
            JOIN catalog.cities c ON w.city_id = c.id
            WHERE r.order_id = %s AND ti.product_id = ANY(%s)
              AND t.status IN ('planned', 'shipping', 'in_transit')
            GROUP BY ti.product_id, c.name, t.arriving_at
        """, (order_id, product_ids))
        transfers = {}
        for row in cur.fetchall():
            pid, from_city, arriving_at, qty = row
            if pid not in transfers:
                transfers[pid] = []
            transfers[pid].append({
                'from_city': from_city,
                'arriving_at': arriving_at,
                'qty': qty
            })

    inv_items = []
    for it in items:
        status_str = "ожидает обработки"
        if order_status != "new":
            # Проверяем накладную на доставку
            del_info = deliveries.get(it.product_id)
            if del_info:
                if del_info.get('shipped', 0) >= it.quantity:
                    status_str = "отгружено"
                elif del_info.get('planned', 0) > 0 or del_info.get('shipped', 0) > 0:
                    status_str = "запланирована отгрузка"

            # Проверяем резерв
            if status_str == "ожидает обработки":
                res_qty = reserves.get(it.product_id, 0)
                if res_qty >= it.quantity:
                    status_str = "в резерве"

            # Проверяем перемещения
            if status_str == "ожидает обработки":
                trans_info = transfers.get(it.product_id)
                if trans_info:
                    details = []
                    for t in trans_info:
                        arr = f", ожидание: {t['arriving_at']}" if t['arriving_at'] else ""
                        details.append(f"из {t['from_city']}{arr}")
                    status_str = "в пути (" + "; ".join(details) + ")"

        inv_items.append(OrderItemInv(
            order_id=it.order_id,
            product_id=it.product_id,
            product_name=it.product_name,
            price=it.price,
            quantity=it.quantity,
            item_status=status_str
        ))

    return inv_items


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
    table.add_row("Склад отгрузки", order.warehouse_info)
    table.add_row("Создал", order.created_by_username)
    if order.processing_by_username:
        table.add_row("В обработке у", order.processing_by_username)

    panel = Panel(
        table,
        expand=False,
        title=f"[bold green]Заказ #{order.id}[/bold green]",
        border_style="green",
    )
    console.print(panel)


def _render_order_items(items: list[OrderItem] | list[OrderItemInv]) -> None:
    """Вывод позиций заказа в виде таблицы."""
    if not items:
        console.print("[yellow]В заказе нет товаров.[/yellow]")
        return

    has_status = hasattr(items[0], 'item_status')

    table = Table(title="Позиции заказа", show_header=True, header_style="bold cyan")
    table.add_column("Товар", style="green", min_width=20)
    table.add_column("Цена", style="yellow", justify="right")
    table.add_column("Кол-во", style="magenta", justify="right")
    table.add_column("Сумма", style="bold white", justify="right")
    if has_status:
        table.add_column("Статус", style="cyan", min_width=20)

    for item in items:
        row = [
            item.product_name,
            f"{item.price:.2f}",
            str(item.quantity),
            f"{item.price * item.quantity:.2f}",
        ]
        if has_status:
            row.append(item.item_status)
        table.add_row(*row)
    console.print(table)


def _get_order_or_fail(order_id: str) -> Order | None:
    """Получить заказ по ID или вывести ошибку."""
    conn = get_conn()
    with conn.cursor(row_factory=class_row(Order)) as cur:
        cur.execute("""
            SELECT o.id, o.status, o.total_amount, o.created_at, o.warehouse_id, 
                   u.username AS created_by_username,
                   c.name || ', ' || w.address || COALESCE(', ' || w.label, '') AS warehouse_info,
                   pu.username AS processing_by_username
            FROM sales.orders o
            JOIN auth.users u ON o.created_by = u.id
            JOIN catalog.warehouses w ON o.warehouse_id = w.id
            JOIN catalog.cities c ON w.city_id = c.id
            LEFT JOIN auth.users pu ON o.processing_by = pu.id
            WHERE o.id = %s
        """, (order_id,))
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


def _prompt_product_choice(products: list[Product]) -> Product | None:
    """Интерактивный выбор товара через компонент choice."""
    if not products:
        return None

    options = [(p.id, f"{p.name} ({p.sku}, {p.price:.2f})") for p in products]

    selected_id = choice(
        message="Выберите товар:",
        options=options,
    )

    for p in products:
        if p.id == selected_id:
            return p
    return None


def _prompt_warehouse_choice(default_warehouse_id: int | None = None) -> int | None:
    """Интерактивный выбор склада."""
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT w.id, c.name, w.address, w.label, w.is_central 
            FROM catalog.warehouses w
            JOIN catalog.cities c ON w.city_id = c.id
            ORDER BY w.id
        """)
        warehouses = cur.fetchall()

    if not warehouses:
        render_error("Нет доступных складов. Сначала создайте хотя бы один склад.")
        return None

    options = []
    central_wh_id = None
    for w in warehouses:
        label = f"{w[0]} | {w[1]} | {w[2]}"
        if w[3]:
            label += f" | {w[3]}"
        if w[4]:
            label += " (Центральный)"
            central_wh_id = w[0]
        options.append((w[0], label))

    if default_warehouse_id is None:
        default_warehouse_id = central_wh_id if central_wh_id is not None else warehouses[0][0]
    elif default_warehouse_id not in [w[0] for w in warehouses]:
        default_warehouse_id = warehouses[0][0]

    selected_wh_id = choice(
        message="Выберите склад:",
        options=options,
        default=default_warehouse_id,
    )
    return selected_wh_id


def _add_items_interactively(order_id: int) -> None:
    """Цикл добавления товаров в заказ до отказа пользователя."""
    while True:
        available_products = _get_available_products(order_id)
        if not available_products:
            console.print("[yellow]Нет доступных товаров для добавления (все уже в заказе или каталог пуст).[/yellow]")
            break

        console.print("\n[bold cyan]Добавление товара в заказ[/bold cyan]")
        product = _prompt_product_choice(available_products)
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


@command("list orders", "список всех заказов", CATEGORY_ORDERS, [ROLE_SALES_MANAGER])
def list_orders() -> None:
    conn = get_conn()
    table = Table(title="Заказы", show_header=True, header_style="bold cyan")

    table.add_column("ID", style="dim", width=6, justify="right")
    table.add_column("Статус", style="magenta", min_width=15)
    table.add_column("Сумма", style="yellow", justify="right")
    table.add_column("Создан", style="green", min_width=20)
    table.add_column("Склад", style="white", min_width=20)
    table.add_column("Создал", style="cyan", min_width=15)

    with conn.cursor(row_factory=class_row(Order)) as cur:
        cur.execute("""
            SELECT o.id, o.status, o.total_amount, o.created_at, o.warehouse_id, 
                   u.username AS created_by_username,
                   c.name || ', ' || w.address || COALESCE(', ' || w.label, '') AS warehouse_info,
                   pu.username AS processing_by_username
            FROM sales.orders o
            JOIN auth.users u ON o.created_by = u.id
            JOIN catalog.warehouses w ON o.warehouse_id = w.id
            JOIN catalog.cities c ON w.city_id = c.id
            LEFT JOIN auth.users pu ON o.processing_by = pu.id
            ORDER BY o.id
        """)
        orders: list[Order] = cur.fetchall()

    for o in orders:
        table.add_row(
            str(o.id),
            o.status,
            f"{o.total_amount:.2f}",
            str(o.created_at),
            o.warehouse_info,
            o.created_by_username,
        )
    console.print(table)


@command("show order", "информация о заказе", CATEGORY_ORDERS, [ROLE_SALES_MANAGER, ROLE_INVENTORY_MANAGER])
def show_order(order_id: str) -> None:
    order = _get_order_or_fail(order_id)
    if order is None:
        return

    _render_order(order)

    if auth_user().role == ROLE_INVENTORY_MANAGER:
        items = _get_order_items_inv(int(order_id), order.status, order.warehouse_id)
    else:
        items = _get_order_items(int(order_id))

    _render_order_items(items)


@command("add order", "добавить заказ (интерактивно)", CATEGORY_ORDERS, [ROLE_SALES_MANAGER])
def add_order() -> None:
    warehouse_id = _prompt_warehouse_choice()
    if warehouse_id is None:
        return

    conn = get_conn()

    current_user_id = auth_user().id

    # Создаём заказ
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO sales.orders (status, warehouse_id, created_by)
            VALUES ('unpublished', %s, %s)
            RETURNING id
            """,
            (warehouse_id, current_user_id),
        )
        new_order_id: int = cur.fetchone()[0]

    console.print(f"[green]Заказ #{new_order_id} создан.[/green]")

    # Сразу предлагаем добавить товары
    add_now = prompt("Добавить товары в заказ сейчас? (y/n, д/н): ", validator=YesNoValidator()).strip()
    if YesNoValidator.is_yes(add_now):
        _add_items_interactively(new_order_id)

    order = _get_order_or_fail(str(new_order_id))
    if order:
        _render_order(order)
        _render_order_items(_get_order_items(new_order_id))


@command("edit order", "редактировать заказ", CATEGORY_ORDERS, [ROLE_SALES_MANAGER])
def edit_order(order_id: str) -> None:
    order = _get_order_or_fail(order_id)
    if order is None:
        return
    if not _check_editable(order, "редактировать"):
        return

    warehouse_id = _prompt_warehouse_choice(default_warehouse_id=order.warehouse_id)
    if warehouse_id is None:
        return

    conn = get_conn()
    conn.execute(
        "UPDATE sales.orders SET warehouse_id = %s WHERE id = %s",
        (warehouse_id, order_id),
    )
    console.print(f"[green]Заказ #{order_id} обновлён.[/green]")


@command("delete order", "удалить заказ", CATEGORY_ORDERS, [ROLE_SALES_MANAGER])
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


@command("publish order", "опубликовать заказ (unpublished -> new)", CATEGORY_ORDERS, [ROLE_SALES_MANAGER])
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


def _prompt_order_item_choice(order_id: int) -> OrderItem | None:
    """Выбор позиции заказа через компонент choice."""
    items = _get_order_items(order_id)
    if not items:
        render_error("В заказе нет позиций.")
        return None

    options = [
        (it.product_id, f"{it.product_name} | {it.price:.2f} × {it.quantity}")
        for it in items
    ]

    selected_product_id = choice(
        message="Выберите позицию:",
        options=options,
    )

    for it in items:
        if it.product_id == selected_product_id:
            return it
    return None


@command("add order_item", "добавить товар в заказ", CATEGORY_ORDERS, [ROLE_SALES_MANAGER])
def add_order_item(order_id: str) -> None:
    order = _get_order_or_fail(order_id)
    if order is None:
        return
    if not _check_editable(order, "добавлять товары в"):
        return

    _add_items_interactively(int(order_id))


@command("edit order_item", "редактировать позицию заказа", CATEGORY_ORDERS, [ROLE_SALES_MANAGER])
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


@command("delete order_item", "удалить позицию из заказа", CATEGORY_ORDERS, [ROLE_SALES_MANAGER])
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


# =========================================
# Команды для inventory_manager (Задание 6)
# =========================================

def _list_orders(status: str | None = None, my: bool = False) -> None:
    """Вспомогательная функция для вывода списка заказов с фильтрами."""
    conn = get_conn()
    query = """
        SELECT o.id, o.status, o.total_amount, o.created_at, o.warehouse_id, 
               u.username AS created_by_username,
               c.name || ', ' || w.address || COALESCE(', ' || w.label, '') AS warehouse_info,
               pu.username AS processing_by_username
        FROM sales.orders o
        JOIN auth.users u ON o.created_by = u.id
        JOIN catalog.warehouses w ON o.warehouse_id = w.id
        JOIN catalog.cities c ON w.city_id = c.id
        LEFT JOIN auth.users pu ON o.processing_by = pu.id
        WHERE 1=1
    """
    params = []
    if status:
        query += " AND o.status = %s"
        params.append(status)
    if my:
        query += " AND o.processing_by = %s"
        params.append(auth_user().id)

    query += " ORDER BY o.id"

    with conn.cursor(row_factory=class_row(Order)) as cur:
        cur.execute(query, params)
        orders: list[Order] = cur.fetchall()

    table = Table(title="Заказы", show_header=True, header_style="bold cyan")
    table.add_column("ID", style="dim", width=6, justify="right")
    table.add_column("Статус", style="magenta", min_width=5)
    table.add_column("Сумма", style="yellow", justify="right")
    table.add_column("Создан", style="green", min_width=20)
    table.add_column("Склад", style="white", min_width=20)
    table.add_column("Создал", style="cyan", min_width=15)
    table.add_column("В обработке у", style="bold cyan", min_width=15)

    for o in orders:
        table.add_row(
            str(o.id),
            o.status,
            f"{o.total_amount:.2f}",
            str(o.created_at),
            o.warehouse_info,
            o.created_by_username,
            o.processing_by_username or "-",
        )
    console.print(table)


@command("list orders new", "список новых заказов", CATEGORY_ORDERS, [ROLE_INVENTORY_MANAGER])
def list_orders_new() -> None:
    _list_orders(status="new")


@command("list orders processing", "список заказов в обработке", CATEGORY_ORDERS, [ROLE_INVENTORY_MANAGER])
def list_orders_processing() -> None:
    _list_orders(status="processing")


@command("list orders my", "список моих заказов", CATEGORY_ORDERS, [ROLE_INVENTORY_MANAGER])
def list_orders_my() -> None:
    _list_orders(my=True)


@command("mark order processing", "взять заказ в обработку", CATEGORY_ORDERS, [ROLE_INVENTORY_MANAGER])
def mark_order_processing(order_id: str) -> None:
    if not order_id.isdigit():
        render_error("ID заказа должен быть числом.")
        return

    order = _get_order_or_fail(order_id)
    if order is None:
        return

    if order.status != "new":
        render_error(
            f"Заказ #{order_id} имеет статус '{order.status}'. Взять в обработку можно только заказы со статусом 'new'.")
        return

    _render_order(order)
    _render_order_items(_get_order_items(int(order_id)))

    answer = prompt("Взять этот заказ в обработку? (y/n, д/н): ", validator=YesNoValidator()).strip()
    if YesNoValidator.is_yes(answer):
        conn = get_conn()
        conn.execute(
            "UPDATE sales.orders SET status = 'processing', processing_by = %s WHERE id = %s",
            (auth_user().id, order_id)
        )
        console.print(f"[green]Заказ #{order_id} взят в обработку.[/green]")