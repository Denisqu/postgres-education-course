-- Создание таблицы городов
CREATE TABLE IF NOT EXISTS catalog.cities (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE
);
INSERT INTO catalog.cities (name) VALUES 
    ('Москва'),
    ('Санкт-Петербург'),
    ('Новосибирск'),
    ('Екатеринбург'),
    ('Казань'),
    ('Нижний Новгород'),
    ('Челябинск'),
    ('Самара'),
    ('Омск'),
    ('Ростов-на-Дону'),
    ('Уфа'),
    ('Красноярск'),
    ('Воронеж'),
    ('Пермь'),
    ('Волгоград');

-- inventory

CREATE SCHEMA inventory;

CREATE TABLE inventory.routes (
    from_city_id INT REFERENCES catalog.cities(id),
    to_city_id INT REFERENCES catalog.cities(id),
    duration INTERVAL NOT NULL,
    total_threshold DECIMAL(10, 2) NOT NULL,
    PRIMARY KEY (from_city_id, to_city_id),
    CHECK (from_city_id != to_city_id)
);

CREATE TABLE inventory.stock (
    warehouse_id INT REFERENCES catalog.warehouses(id),
    product_id INT REFERENCES catalog.products(id),
    quantity INT NOT NULL DEFAULT 0 CHECK (quantity >= 0),
    PRIMARY KEY (warehouse_id, product_id)
);

CREATE TABLE inventory.reserves (
    id SERIAL PRIMARY KEY,
    order_id INT REFERENCES sales.orders(id),
    product_id INT REFERENCES catalog.products(id),
    warehouse_id INT REFERENCES catalog.warehouses(id),
    quantity INT NOT NULL CHECK (quantity > 0),
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE inventory.deliveries (
    id SERIAL PRIMARY KEY,
    order_id INT UNIQUE REFERENCES sales.orders(id),
    status VARCHAR(20) NOT NULL DEFAULT 'planned' 
        CHECK (status IN ('planned', 'shipping', 'shipped')),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    shipped_at TIMESTAMP
);

-- TODO....