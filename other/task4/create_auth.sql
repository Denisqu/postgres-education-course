CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE SCHEMA auth;

CREATE TABLE auth.users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password VARCHAR(100) NOT NULL,
    role VARCHAR(50) NOT NULL CHECK (role IN ('catalog_manager', 'sales_manager'))
);

-- Права для всех текущих и будущих пользователей
GRANT USAGE ON SCHEMA auth TO PUBLIC;
GRANT SELECT ON ALL TABLES IN SCHEMA auth TO PUBLIC;
ALTER DEFAULT PRIVILEGES IN SCHEMA auth GRANT SELECT ON TABLES TO PUBLIC;

-- разрешаем создание ссылок на auth.users для app_user
GRANT REFERENCES ON auth.users TO app_user;

-- Первые пользователи
INSERT INTO auth.users (username, password, role) 
VALUES ('cat_man', crypt('cat_man_pass', gen_salt('bf')), 'catalog_manager');

INSERT INTO auth.users (username, password, role) 
VALUES ('sales_man', crypt('sales_man_pass', gen_salt('bf')), 'sales_manager');