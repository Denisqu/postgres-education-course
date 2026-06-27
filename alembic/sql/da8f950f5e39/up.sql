CREATE SCHEMA IF NOT EXISTS catalog;

CREATE TABLE catalog.product_categories (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE catalog.products (
    id SERIAL PRIMARY KEY,
    sku VARCHAR(30) NOT NULL UNIQUE,
    name TEXT NOT NULL,
    price NUMERIC(12,2) NOT NULL CHECK (price > 0),
    category_id INTEGER NOT NULL REFERENCES catalog.product_categories(id)
);

CREATE TABLE catalog.warehouses (
    id SERIAL PRIMARY KEY,
    city TEXT NOT NULL,
    address TEXT NOT NULL,
    label TEXT,
    is_central BOOLEAN NOT NULL
);