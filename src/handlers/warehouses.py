from dataclasses import dataclass

from prompt_toolkit import prompt
from prompt_toolkit.shortcuts import choice
from prompt_toolkit.completion import WordCompleter
from psycopg.rows import class_row
from rich.panel import Panel
from rich.table import Table

from console import console, render_error
from db import get_conn
from validators import ChoiceValidator, NonEmptyValidator, YesNoValidator
from commands import command, CATEGORY_WAREHOUSES
from auth import ROLE_SALES_MANAGER, ROLE_CATALOG_MANAGER, ROLE_INVENTORY_MANAGER


def get_cities() -> list[str]:
    """Получает список городов из базы данных."""
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT name FROM catalog.cities ORDER BY name")
        return [row[0] for row in cur.fetchall()]


@dataclass
class Warehouse:
    id: int
    city: str
    address: str
    label: str | None
    is_central: bool


def _render_warehouse(warehouse: Warehouse) -> None:
    table = Table(show_header=False, box=None, padding=(0, 2))

    table.add_column("Поле", style="bold cyan", width=15)
    table.add_column("Значение", style="white")

    table.add_row("ID", str(warehouse.id))
    table.add_row("Город", warehouse.city)
    table.add_row("Адрес", warehouse.address)
    table.add_row("Метка", warehouse.label or "")

    panel = Panel(
        table,
        expand=False,
        title=f"[bold green]Склад #{warehouse.id}[/bold green]",
        border_style="green",
    )

    console.print(panel)


@command("list warehouses", "список всех складов", CATEGORY_WAREHOUSES, [ROLE_SALES_MANAGER, ROLE_CATALOG_MANAGER])
def list_warehouses() -> None:
    conn = get_conn()
    table = Table(title="Склады", show_header=True, header_style="bold cyan")

    table.add_column("ID", style="dim", width=6, justify="right")
    table.add_column("Город", style="green", min_width=20)
    table.add_column("Адрес", style="yellow", min_width=30)
    table.add_column("Метка", style="magenta", min_width=15)
    table.add_column("Центральный?", style="white", min_width=15)

    with conn.cursor(row_factory=class_row(Warehouse)) as cur:
        cur.execute("SELECT * FROM catalog.warehouses")
        warehouses: list[Warehouse] = cur.fetchall()

    for warehouse in warehouses:
        table.add_row(
            str(warehouse.id),
            warehouse.city,
            warehouse.address,
            warehouse.label or "",
            str(warehouse.is_central)
        )
    console.print(table)


@command("show warehouse", "информация о складе", CATEGORY_WAREHOUSES, [ROLE_SALES_MANAGER, ROLE_CATALOG_MANAGER])
def show_warehouse(_id: str) -> None:
    conn = get_conn()
    with conn.cursor(row_factory=class_row(Warehouse)) as cur:
        cur.execute("SELECT * FROM catalog.warehouses WHERE id = %s", (_id,))
        warehouse: Warehouse | None = cur.fetchone()

    if warehouse is None:
        render_error(f"Склад с ID {_id} не найден")
        return

    _render_warehouse(warehouse)


def isCentralWarehouseExists() -> bool:
    conn = get_conn()
    with conn.cursor(row_factory=class_row(Warehouse)) as cur:
        cur.execute("SELECT * FROM catalog.warehouses WHERE is_central = True")
        warehouse: Warehouse | None = cur.fetchone()
    if warehouse is None:
        return False
    return True


def isCentralWarehouseExistsWithDifferentId(_id: str) -> bool:
    conn = get_conn()
    with conn.cursor(row_factory=class_row(Warehouse)) as cur:
        cur.execute("SELECT * FROM catalog.warehouses WHERE id != %s AND is_central = True", (_id,))
        warehouse: Warehouse | None = cur.fetchone()
    if warehouse is None:
        return False
    return True


@command("add warehouse", "добавить склад (интерактивно)", CATEGORY_WAREHOUSES, [ROLE_CATALOG_MANAGER])
def add_warehouse() -> None:
    conn = get_conn()

    cities = get_cities()
    city_completer = WordCompleter(cities, ignore_case=True, sentence=True)
    city_validator = ChoiceValidator(
        cities, message="Город должен быть из списка. Используйте Tab для автодополнения."
    )

    city = prompt("Город: ", validator=city_validator, completer=city_completer).strip()
    address = prompt("Адрес: ", validator=NonEmptyValidator()).strip()
    label = prompt("Метка (необязательно): ").strip() or None

    is_central = True
    is_need_change_central_warehouse = False
    if isCentralWarehouseExists():
        is_central = YesNoValidator.is_yes(prompt("Центральный склад уже существует. Сделать новый склад центральным? ",
                                                  validator=YesNoValidator())
                                           .strip())
        is_need_change_central_warehouse = is_central

    if is_need_change_central_warehouse:
        with conn.cursor(row_factory=class_row(Warehouse)) as cur:
            cur.execute("""
                UPDATE catalog.warehouses 
                SET is_central = False 
                WHERE is_central
            """)

    conn.execute(
        "INSERT INTO catalog.warehouses (city, address, label, is_central) VALUES (%s, %s, %s, %s)",
        (city, address, label, is_central),
    )
    if label:
        console.print(f"[green]Склад в городе {city} ({label}) добавлен [/green]")
    else:
        console.print(f"[green]Склад в городе {city} добавлен [/green]")


@command("edit warehouse", "редактировать склад", CATEGORY_WAREHOUSES, [ROLE_CATALOG_MANAGER])
def edit_warehouse(_id: str) -> None:
    conn = get_conn()

    cities = get_cities()
    city_completer = WordCompleter(cities, ignore_case=True, sentence=True)
    city_validator = ChoiceValidator(
        cities, message="Город должен быть из списка. Используйте Tab для автодополнения."
    )

    with conn.cursor(row_factory=class_row(Warehouse)) as cur:
        cur.execute("SELECT * FROM catalog.warehouses WHERE id = %s", (_id,))
        warehouse: Warehouse | None = cur.fetchone()

    if warehouse is None:
        render_error(f"Склад с ID {_id} не найден")
        return

    make_central = False
    if not warehouse.is_central:
        is_central_input = prompt(
            "Сделать этот склад центральным? ",
            validator=YesNoValidator(),
            default= "yes" if warehouse.is_central else "no"
        ).strip()
        make_central = YesNoValidator.is_yes(is_central_input)
    old_central_warehouse = None

    if make_central:
        with conn.cursor(row_factory=class_row(Warehouse)) as cur:
            cur.execute(
                "SELECT * FROM catalog.warehouses WHERE is_central = True",
            )
            old_central_warehouse = cur.fetchone()

        if old_central_warehouse:
            console.print(
                f"[yellow]Внимание: Центральным уже является склад в г. {old_central_warehouse.city} (ID: {old_central_warehouse.id}).[/yellow]"
            )
            confirm_replace = YesNoValidator.is_yes(
                prompt("Снять статус центрального со старого склада и назначить этот? ",
                       validator=YesNoValidator()).strip()
            )
            if not confirm_replace:
                make_central = False
                console.print("[yellow]Статус центрального склада не изменен.[/yellow]")

    city = prompt(
        "Город: ",
        default=warehouse.city,
        validator=city_validator,
        completer=city_completer,
    ).strip()

    address = prompt(
        "Адрес: ", default=warehouse.address, validator=NonEmptyValidator()
    ).strip()

    label = (
            prompt("Метка (необязательно): ", default=warehouse.label or "").strip() or None
    )

    if old_central_warehouse and make_central:
        conn.execute(
            "UPDATE catalog.warehouses SET is_central = False WHERE id = %s",
            (old_central_warehouse.id,)
        )
    conn.execute(
        """UPDATE catalog.warehouses 
           SET city = %s, address = %s, label = %s, is_central = %s
           WHERE id = %s""",
        (city, address, label, make_central, _id),
    )
    if label:
        console.print(f"[green]Склад в городе {city} ({label}) обновлен [/green]")
    else:
        console.print(f"[green]Склад в городе {city} обновлен [/green]")


@command("delete warehouse", "удалить склад", CATEGORY_WAREHOUSES, [ROLE_CATALOG_MANAGER])
def delete_warehouse(_id: str) -> None:
    conn = get_conn()
    with conn.cursor(row_factory=class_row(Warehouse)) as cur:
        cur.execute("SELECT * FROM catalog.warehouses WHERE id = %s", (_id,))
        warehouse: Warehouse | None = cur.fetchone()

    if warehouse is None:
        render_error(f"Склад с ID {_id} не найден")
        return

    _render_warehouse(warehouse)

    answer = prompt("Вы уверены? (y/n, д/н): ", validator=YesNoValidator())

    if YesNoValidator.is_yes(answer):
        conn.execute("DELETE FROM catalog.warehouses WHERE id = %s", (_id,))
        if warehouse.label:
            console.print(
                f"[green]Склад в городе {warehouse.city} ({warehouse.label}) удален [/green]"
            )
        else:
            console.print(f"[green]Склад в городе {warehouse.city} удален [/green]")

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

@command("view warehouse stock", "остатки по складу", CATEGORY_WAREHOUSES, [ROLE_INVENTORY_MANAGER])
def view_warehouse_stock() -> None:
    warehouse_id = _prompt_warehouse_choice()
    if warehouse_id is None:
        return

    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT p.name, p.sku,
                   COALESCE(st.quantity, 0) AS stock_qty,
                   COALESCE(res.quantity, 0) AS reserve_qty
            FROM catalog.products p
            LEFT JOIN inventory.stock st ON st.product_id = p.id AND st.warehouse_id = %s
            LEFT JOIN (
                SELECT product_id, SUM(quantity) as quantity
                FROM inventory.reserves
                WHERE warehouse_id = %s
                GROUP BY product_id
            ) res ON res.product_id = p.id
            ORDER BY p.name
        """, (warehouse_id, warehouse_id))
        rows = cur.fetchall()

    table = Table(title=f"Остатки на складе #{warehouse_id}", show_header=True, header_style="bold cyan")
    table.add_column("Товар", style="green", min_width=20)
    table.add_column("Артикул", style="dim", min_width=10)
    table.add_column("Сток", style="yellow", justify="right")
    table.add_column("Резерв", style="magenta", justify="right")
    table.add_column("Всего", style="bold white", justify="right")

    for row in rows:
        name, sku, stock, reserve = row
        total = stock + reserve
        table.add_row(name, sku, str(stock), str(reserve), str(total))

    console.print(table)