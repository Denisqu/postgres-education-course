from dataclasses import dataclass
from decimal import Decimal

from commands import command, CATEGORY_PRODUCT_CATEGORIES

from dataclasses import dataclass

from prompt_toolkit import prompt
from prompt_toolkit.completion import WordCompleter
from psycopg.rows import class_row
from rich.panel import Panel
from rich.table import Table

from console import console, render_error
from db import get_conn
from validators import ChoiceValidator, NonEmptyValidator, YesNoValidator
from auth import ROLE_SALES_MANAGER, ROLE_CATALOG_MANAGER, ALL_ROLES

@dataclass
class ProductCategory:
    id: int
    name: str

def _render_product_category(category: ProductCategory) -> None:
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Поле", style="bold cyan", width=15)
    table.add_column("Значение", style="white")
    table.add_row("ID", str(category.id))
    table.add_row("Имя", category.name)
    panel = Panel(
        table,
        expand=False,
        title=f"[bold green]Категория #{category.id}[/bold green]",
        border_style="green",
    )
    console.print(panel)

@command("list product_categories", "список всех категорий", CATEGORY_PRODUCT_CATEGORIES, [ALL_ROLES])
def list_product_categories() -> None:
    conn = get_conn()
    table = Table(title="Склады", show_header=True, header_style="bold cyan")
    table.add_column("ID", style="dim", width=6, justify="right")
    table.add_column("Имя", style="green", min_width=20)

    with conn.cursor(row_factory=class_row(ProductCategory)) as cur:
        cur.execute("SELECT * FROM catalog.product_categories")
        product_categories: list[ProductCategory] = cur.fetchall()

    for category in product_categories:
        table.add_row(
            str(category.id),
            category.name
        )
    console.print(table)

@command("show product_category", "информация о категории", CATEGORY_PRODUCT_CATEGORIES, [ALL_ROLES])
def show_product_category(_id:str) -> None:
    conn = get_conn()
    with conn.cursor(row_factory=class_row(ProductCategory)) as cur:
        cur.execute("SELECT * FROM catalog.product_categories WHERE id = %s", (_id,))
        category: ProductCategory | None = cur.fetchone()

    if category is None:
        render_error(f"Категория с ID {_id} не найден")
        return

    _render_product_category(category)

@command("add product_category", "добавить новую категорию", CATEGORY_PRODUCT_CATEGORIES, [ROLE_CATALOG_MANAGER])
def add_product_category() -> None:
    conn = get_conn()
    name = prompt("Имя категории: ", validator=NonEmptyValidator()).strip()
    conn.execute(
        "INSERT INTO catalog.product_categories (name) VALUES (%s)",
        (name,),
    )
    console.print(f"[green]Категория {name} добавлена! [/green]")

@command("edit product_category", "изменение категории", CATEGORY_PRODUCT_CATEGORIES, [ROLE_CATALOG_MANAGER])
def edit_product_category(_id: str) -> None:
    conn = get_conn()
    with conn.cursor(row_factory=class_row(ProductCategory)) as cur:
        cur.execute("SELECT * FROM catalog.product_categories WHERE id = %s", (_id,))
        category: ProductCategory | None = cur.fetchone()

    if category is None:
        render_error(f"Категория с ID {_id} не найдена")
        return

    name = prompt("Имя категории: ", validator=NonEmptyValidator(), default=str(category.name)).strip()
    conn.execute(
        """UPDATE catalog.product_categories SET name = %s
        WHERE id = %s""",
        (name, _id),
    )
    console.print(f"[green]Категория товара с ID {_id} обновлена [/green]")

@command("delete product_category", "удаление категории", CATEGORY_PRODUCT_CATEGORIES, [ROLE_CATALOG_MANAGER])
def delete_product_category(_id: str) -> None:
    conn = get_conn()
    with conn.cursor(row_factory=class_row(ProductCategory)) as cur:
        cur.execute("SELECT * FROM catalog.product_categories WHERE id = %s", (_id,))
        category: ProductCategory | None = cur.fetchone()

    if category is None:
        render_error(f"Склад с ID {_id} не найден")
        return

    _render_product_category(category)

    answer = prompt("Вы уверены? (y/n, д/н): ", validator=YesNoValidator())

    if YesNoValidator.is_yes(answer):
        conn.execute("DELETE FROM catalog.product_categories WHERE id = %s", (_id,))
        console.print(f"[green]Категория {category.id} удалена [/green]")
