from typing import Final, Sequence

from prompt_toolkit import prompt

from console import console
from users import User, find_user_by_login_and_pass

ROLE_CATALOG_MANAGER: Final[str] = "catalog_manager"
ROLE_SALES_MANAGER: Final[str] = "sales_manager"

ALL_ROLES: Final[Sequence[str]] = (
    ROLE_SALES_MANAGER,
    ROLE_CATALOG_MANAGER,
)

_USER: User | None = None

def login(username: str | None = None, password: str | None = None) -> None:
    global _USER
    # Try CLI auth if both provided
    if username and password:
        user = find_user_by_login_and_pass(username, password)
        if user:
            if user.role not in ALL_ROLES:
                raise ValueError("Invalid user role")
            console.print(
                f"\n[green]✓ Вход выполнен как {user.username} ({user.role})[/green]\n"
            )
            _USER = user
            return

        console.print("\n[red]✗ Неверные учетные данные из CLI[/red]")
        console.print("[yellow]Попробуйте ввести вручную:[/yellow]\n")

    # Interactive prompt
    console.print("\n[bold cyan]═══════════════════════════════════════[/bold cyan]")
    console.print("[bold cyan]   Вход в систему[/bold cyan]")
    console.print("[bold cyan]═══════════════════════════════════════[/bold cyan]\n")

    while True:
        username = prompt("Имя пользователя: ").strip()
        password = prompt("Пароль: ", is_password=True).strip()
        user = find_user_by_login_and_pass(username, password)

        if user:
            if user.role not in ALL_ROLES:
                raise ValueError("Invalid user role")
            console.print(
                f"\n[green]✓ Вход выполнен как {user.username} ({user.role})[/green]\n"
            )
            _USER = user
            return

        console.print("\n[red]✗ Неверное имя пользователя или пароль[/red]\n")


def auth_user() -> User:
    """
    Вернет аутентифицированного юзера
    """
    if _USER is None:
        raise RuntimeError("Not authenticated")
    return _USER