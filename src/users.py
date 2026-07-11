from dataclasses import dataclass

from db import get_conn
from psycopg.rows import class_row


@dataclass
class User:
    id: int
    username: str
    role: str


def find_user_by_login_and_pass(username: str, password: str) -> User | None:
    """Реализуйте запрос к БД с проверкой пароля через crypt"""
    conn = get_conn()
    with conn.cursor(row_factory=class_row(User)) as cur:
        cur.execute(
            "SELECT id, username, role FROM auth.users "
            "WHERE username = %s AND password = crypt(%s, password)",
            (username, password),
        )
        return cur.fetchone()


def get_user(id_: int) -> User | None:
    """Реализуйте получение пользователя по ID"""
    conn = get_conn()
    with conn.cursor(row_factory=class_row(User)) as cur:
        cur.execute(
            "SELECT id, username, role FROM auth.users WHERE id = %s",
            (id_,),
        )
        return cur.fetchone()