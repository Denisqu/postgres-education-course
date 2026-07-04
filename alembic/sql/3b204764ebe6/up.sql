CREATE SCHEMA IF NOT EXISTS sales;

CREATE TABLE sales.orders (
    id           SERIAL PRIMARY KEY,
    status       VARCHAR(20) NOT NULL DEFAULT 'unpublished'
        CHECK (status IN ('unpublished', 'new', 'processing', 'pending', 'packing', 'shipped')),
    total_amount NUMERIC(12, 2)     NOT NULL DEFAULT 0 CHECK (total_amount >= 0),
    created_at   TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    warehouse_id INTEGER            NOT NULL
        REFERENCES catalog.warehouses(id) ON DELETE RESTRICT
);

CREATE TABLE sales.order_items (
    order_id   INTEGER        NOT NULL REFERENCES sales.orders(id) ON DELETE CASCADE,
    product_id INTEGER        NOT NULL REFERENCES catalog.products(id) ON DELETE RESTRICT,
    price      NUMERIC(12, 2) NOT NULL CHECK (price > 0),
    quantity   INTEGER        NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (order_id, product_id)
);