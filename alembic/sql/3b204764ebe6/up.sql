CREATE SCHEMA IF NOT EXISTS sales;

CREATE TYPE sales.order_status AS ENUM (
    'unpublished', 'new', 'processing', 'pending', 'packing', 'shipped'
);

CREATE TABLE sales.orders (
    id           SERIAL PRIMARY KEY,
    status       sales.order_status NOT NULL DEFAULT 'unpublished',
    total_amount NUMERIC(12, 2)     NOT NULL DEFAULT 0 CHECK (total_amount >= 0),
    created_at   TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    warehouse_id INTEGER            NOT NULL
        REFERENCES catalog.warehouses(id) ON DELETE RESTRICT
);

CREATE TABLE sales.order_items (
    order_id   INTEGER        NOT NULL
        REFERENCES sales.orders(id) ON DELETE CASCADE,
    product_id INTEGER        NOT NULL
        REFERENCES catalog.products(id) ON DELETE RESTRICT
);