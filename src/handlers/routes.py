from dataclasses import dataclass

from prompt_toolkit import prompt
from prompt_toolkit.completion import WordCompleter
from psycopg.rows import class_row
from rich.panel import Panel
from rich.table import Table

from console import console, render_error
from db import get_conn
from validators import ChoiceValidator, NonEmptyValidator, YesNoValidator
from commands import command
from auth import ROLE_SALES_MANAGER, ROLE_CATALOG_MANAGER, ROLE_INVENTORY_MANAGER
from commands import CATEGORY_ROUTES


def get_cities() -> list[str]:
    """Получает список городов из базы данных."""
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT name FROM catalog.cities ORDER BY name")
        return [row[0] for row in cur.fetchall()]


@dataclass
class Route:
    from_city_id: int
    from_city_name: str
    to_city_id: int
    to_city_name: str
    duration: int
    total_threshold: float


def _render_route(route: Route) -> None:
    table = Table(show_header=False, box=None, padding=(0, 2))

    table.add_column("Поле", style="bold cyan", width=20)
    table.add_column("Значение", style="white")

    table.add_row("Откуда (ID)", str(route.from_city_id))
    table.add_row("Откуда (Город)", route.from_city_name)
    table.add_row("Куда (ID)", str(route.to_city_id))
    table.add_row("Куда (Город)", route.to_city_name)
    table.add_row("Длительность", str(route.duration))
    table.add_row("Порог", str(route.total_threshold))

    panel = Panel(
        table,
        expand=False,
        title=f"[bold green]Маршрут {route.from_city_name} -> {route.to_city_name}[/bold green]",
        border_style="green",
    )

    console.print(panel)


@command("list routes", "список всех маршрутов", CATEGORY_ROUTES, [ROLE_SALES_MANAGER, ROLE_CATALOG_MANAGER])
def list_routes() -> None:
    conn = get_conn()
    table = Table(title="Маршруты", show_header=True, header_style="bold cyan")

    table.add_column("Откуда", style="green", min_width=20)
    table.add_column("Куда", style="green", min_width=20)
    table.add_column("Длительность", style="yellow", min_width=15, justify="right")
    table.add_column("Порог", style="magenta", min_width=15, justify="right")

    query = """
        SELECT 
            r.from_city_id, c1.name AS from_city_name,
            r.to_city_id, c2.name AS to_city_name,
            r.duration, r.total_threshold
        FROM inventory.routes r
        JOIN catalog.cities c1 ON r.from_city_id = c1.id
        JOIN catalog.cities c2 ON r.to_city_id = c2.id
    """

    with conn.cursor(row_factory=class_row(Route)) as cur:
        cur.execute(query)
        routes: list[Route] = cur.fetchall()

    for route in routes:
        table.add_row(
            route.from_city_name,
            route.to_city_name,
            str(route.duration),
            str(route.total_threshold)
        )
    console.print(table)

@command("show route", "информация о маршруте", CATEGORY_ROUTES,
         [ROLE_SALES_MANAGER, ROLE_CATALOG_MANAGER, ROLE_INVENTORY_MANAGER])
def show_route() -> None:
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT c1.name || ' -> ' || c2.name 
            FROM inventory.routes r
            JOIN catalog.cities c1 ON r.from_city_id = c1.id
            JOIN catalog.cities c2 ON r.to_city_id = c2.id
        """)
        existing_routes = [row[0] for row in cur.fetchall()]

    if not existing_routes:
        render_error("Нет созданных маршрутов.")
        return

    completer = WordCompleter(existing_routes, ignore_case=True, sentence=True)
    validator = ChoiceValidator(existing_routes, message="Выберите маршрут из списка.")

    selected = prompt("Выберите маршрут: ", validator=validator, completer=completer).strip()
    from_city, to_city = selected.split(" -> ")

    query = """
            SELECT 
                r.from_city_id, c1.name AS from_city_name,
                r.to_city_id, c2.name AS to_city_name,
                r.duration, r.total_threshold
            FROM inventory.routes r
            JOIN catalog.cities c1 ON r.from_city_id = c1.id
            JOIN catalog.cities c2 ON r.to_city_id = c2.id
            WHERE c1.name = %s AND c2.name = %s
        """
    with conn.cursor(row_factory=class_row(Route)) as cur:
        cur.execute(query, (from_city, to_city))
        route: Route | None = cur.fetchone()

    if route is None:
        render_error(f"Маршрут из {from_city} в {to_city} не найден")
        return

    _render_route(route)


@command("add route", "добавить маршрут (интерактивно)", CATEGORY_ROUTES, [ROLE_INVENTORY_MANAGER])
def add_route() -> None:
    conn = get_conn()
    query_available = """
        SELECT 
            c1.name AS from_city_name,
            c2.name AS to_city_name
        FROM catalog.cities c1
        CROSS JOIN catalog.cities c2
        WHERE c1.id != c2.id
          AND NOT EXISTS (
              SELECT 1 
              FROM inventory.routes r
              WHERE r.from_city_id = c1.id 
                AND r.to_city_id = c2.id
          )
        ORDER BY c1.name, c2.name
    """

    with conn.cursor() as cur:
        cur.execute(query_available)
        available_pairs = cur.fetchall()

    if not available_pairs:
        render_error("Нет доступных пар городов для создания нового маршрута.")
        return

    pair_labels = [f"{row[0]} -> {row[1]}" for row in available_pairs]
    pair_completer = WordCompleter(pair_labels, ignore_case=True, sentence=True)
    pair_validator = ChoiceValidator(
        pair_labels, message="Пара городов должна быть из списка. Используйте Tab для автодополнения."
    )

    selected_pair = prompt("Выберите пару городов: ", validator=pair_validator, completer=pair_completer).strip()

    from_city_name, to_city_name = selected_pair.split(" -> ")
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM catalog.cities WHERE name = %s", (from_city_name,))
        from_city_id = cur.fetchone()[0]
        cur.execute("SELECT id FROM catalog.cities WHERE name = %s", (to_city_name,))
        to_city_id = cur.fetchone()[0]

    duration_str = prompt("Длительность: ", validator=NonEmptyValidator()).strip()
    try:
        duration = int(duration_str)
    except ValueError:
        render_error("Длительность должна быть целым числом.")
        return

    threshold_str = prompt("Общий порог (total_threshold): ", validator=NonEmptyValidator()).strip()
    try:
        total_threshold = float(threshold_str)
    except ValueError:
        render_error("Порог должен быть числом.")
        return

    conn.execute(
        "INSERT INTO inventory.routes (from_city_id, to_city_id, duration, total_threshold) VALUES (%s, %s, %s, %s)",
        (from_city_id, to_city_id, duration, total_threshold),
    )
    console.print(f"[green]Маршрут {from_city_name} -> {to_city_name} добавлен [/green]")


@command("edit route", "редактировать маршрут", CATEGORY_ROUTES, [ROLE_INVENTORY_MANAGER])
def edit_route(from_city: str, to_city: str) -> None:
    conn = get_conn()

    query = """
        SELECT 
            r.from_city_id, c1.name AS from_city_name,
            r.to_city_id, c2.name AS to_city_name,
            r.duration, r.total_threshold
        FROM inventory.routes r
        JOIN catalog.cities c1 ON r.from_city_id = c1.id
        JOIN catalog.cities c2 ON r.to_city_id = c2.id
        WHERE c1.name = %s AND c2.name = %s
    """

    with conn.cursor(row_factory=class_row(Route)) as cur:
        cur.execute(query, (from_city, to_city))
        route: Route | None = cur.fetchone()

    if route is None:
        render_error(f"Маршрут из {from_city} в {to_city} не найден")
        return

    _render_route(route)

    duration_str = prompt(
        "Длительность: ",
        default=str(route.duration),
        validator=NonEmptyValidator()
    ).strip()
    try:
        duration = int(duration_str)
    except ValueError:
        render_error("Длительность должна быть целым числом.")
        return

    threshold_str = prompt(
        "Общий порог: ",
        default=str(route.total_threshold),
        validator=NonEmptyValidator()
    ).strip()
    try:
        total_threshold = float(threshold_str)
    except ValueError:
        render_error("Порог должен быть числом.")
        return

    conn.execute(
        """UPDATE inventory.routes 
           SET duration = %s, total_threshold = %s
           WHERE from_city_id = %s AND to_city_id = %s""",
        (duration, total_threshold, route.from_city_id, route.to_city_id),
    )
    console.print(f"[green]Маршрут {route.from_city_name} -> {route.to_city_name} обновлен [/green]")


@command("delete route", "удалить маршрут", CATEGORY_ROUTES, [ROLE_INVENTORY_MANAGER])
def delete_route(from_city: str, to_city: str) -> None:
    conn = get_conn()

    query = """
        SELECT 
            r.from_city_id, c1.name AS from_city_name,
            r.to_city_id, c2.name AS to_city_name,
            r.duration, r.total_threshold
        FROM inventory.routes r
        JOIN catalog.cities c1 ON r.from_city_id = c1.id
        JOIN catalog.cities c2 ON r.to_city_id = c2.id
        WHERE c1.name = %s AND c2.name = %s
    """

    with conn.cursor(row_factory=class_row(Route)) as cur:
        cur.execute(query, (from_city, to_city))
        route: Route | None = cur.fetchone()

    if route is None:
        render_error(f"Маршрут из {from_city} в {to_city} не найден")
        return

    _render_route(route)

    answer = prompt("Вы уверены? (y/n, д/н): ", validator=YesNoValidator())

    if YesNoValidator.is_yes(answer):
        conn.execute(
            "DELETE FROM inventory.routes WHERE from_city_id = %s AND to_city_id = %s",
            (route.from_city_id, route.to_city_id)
        )
        console.print(
            f"[green]Маршрут {route.from_city_name} -> {route.to_city_name} удален [/green]"
        )