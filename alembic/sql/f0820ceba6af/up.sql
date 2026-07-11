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

-- Перенос городов из текста в ссылку на таблицу catalog.cities
ALTER TABLE catalog.warehouses ADD COLUMN city_id INTEGER;

UPDATE catalog.warehouses w
    SET city_id = c.id
    FROM catalog.cities c
    WHERE w.city = c.name;
ALTER TABLE catalog.warehouses ALTER COLUMN city_id SET NOT NULL;
ALTER TABLE catalog.warehouses ADD CONSTRAINT fk_warehouses_city FOREIGN KEY (city_id) REFERENCES catalog.cities(id);
ALTER TABLE catalog.warehouses DROP COLUMN city;

ALTER TABLE sales.orders ADD COLUMN processing_by INTEGER REFERENCES auth.users(id);

-- schema inventory

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

CREATE TABLE inventory.delivery_items (
    id SERIAL PRIMARY KEY,
    delivery_id INTEGER NOT NULL REFERENCES inventory.deliveries(id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES catalog.products(id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    status VARCHAR(20) NOT NULL DEFAULT 'planned'
        CHECK (status IN ('planned', 'shipped'))
);

CREATE TABLE inventory.transfers (
    id SERIAL PRIMARY KEY,
    from_warehouse_id INTEGER NOT NULL REFERENCES catalog.warehouses(id),
    to_warehouse_id INTEGER NOT NULL REFERENCES catalog.warehouses(id),
    status VARCHAR(20) NOT NULL DEFAULT 'planned'
        CHECK (status IN ('planned', 'shipping', 'in_transit', 'arrived', 'received')),
    total_amount NUMERIC(12, 2) NOT NULL DEFAULT 0 CHECK (total_amount >= 0),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    started_at TIMESTAMP WITH TIME ZONE,
    arriving_at TIMESTAMP WITH TIME ZONE,
    received_at TIMESTAMP WITH TIME ZONE,
    CHECK (from_warehouse_id != to_warehouse_id)
);

CREATE TABLE inventory.transfer_items (
    id SERIAL PRIMARY KEY,
    transfer_id INTEGER NOT NULL REFERENCES inventory.transfers(id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES catalog.products(id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    requested_by INTEGER NOT NULL REFERENCES auth.users(id),
    reserve_id INTEGER REFERENCES inventory.reserves(id), -- NULL для перемещений "прозапас"
    status VARCHAR(20) NOT NULL DEFAULT 'planned'
        CHECK (status IN ('planned', 'shipped', 'received'))
);

-- Настройка прав доступа

-- inventory_manager
GRANT ALL ON SCHEMA inventory TO inventory_manager;
GRANT ALL ON ALL TABLES IN SCHEMA inventory TO inventory_manager;
GRANT ALL ON ALL SEQUENCES IN SCHEMA inventory TO inventory_manager;
ALTER DEFAULT PRIVILEGES IN SCHEMA inventory GRANT ALL ON TABLES TO inventory_manager;
ALTER DEFAULT PRIVILEGES IN SCHEMA inventory GRANT ALL ON SEQUENCES TO inventory_manager;

GRANT USAGE ON SCHEMA sales TO inventory_manager;
GRANT SELECT ON ALL TABLES IN SCHEMA sales TO inventory_manager;
ALTER DEFAULT PRIVILEGES IN SCHEMA sales GRANT SELECT ON TABLES TO inventory_manager;
GRANT UPDATE (status, processing_by) ON sales.orders TO inventory_manager;

-- worker
GRANT USAGE ON SCHEMA inventory TO worker;
GRANT SELECT ON ALL TABLES IN SCHEMA inventory TO worker;
ALTER DEFAULT PRIVILEGES IN SCHEMA inventory GRANT SELECT ON TABLES TO worker;
GRANT ALL ON inventory.stock TO worker;
GRANT UPDATE ON inventory.reserves TO worker;
GRANT UPDATE ON inventory.deliveries TO worker;
GRANT UPDATE ON inventory.delivery_items TO worker;
GRANT UPDATE ON inventory.transfers TO worker;
GRANT UPDATE ON inventory.transfer_items TO worker;