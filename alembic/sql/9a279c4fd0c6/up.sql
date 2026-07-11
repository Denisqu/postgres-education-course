GRANT ALL ON SCHEMA catalog TO catalog_manager;
GRANT ALL ON ALL TABLES IN SCHEMA catalog TO catalog_manager;
GRANT ALL ON ALL SEQUENCES IN SCHEMA catalog TO catalog_manager;
ALTER DEFAULT PRIVILEGES IN SCHEMA catalog GRANT ALL ON TABLES TO catalog_manager;
ALTER DEFAULT PRIVILEGES IN SCHEMA catalog GRANT ALL ON SEQUENCES TO catalog_manager;

GRANT ALL ON SCHEMA sales TO sales_manager;
GRANT ALL ON ALL TABLES IN SCHEMA sales TO sales_manager;
GRANT ALL ON ALL SEQUENCES IN SCHEMA sales TO sales_manager;
ALTER DEFAULT PRIVILEGES IN SCHEMA sales GRANT ALL ON TABLES TO sales_manager;
ALTER DEFAULT PRIVILEGES IN SCHEMA sales GRANT ALL ON SEQUENCES TO sales_manager;

-- Права для всех ролей (текущие и будущие)
GRANT USAGE ON SCHEMA catalog TO PUBLIC;
GRANT SELECT ON ALL TABLES IN SCHEMA catalog TO PUBLIC;
ALTER DEFAULT PRIVILEGES IN SCHEMA catalog GRANT SELECT ON TABLES TO PUBLIC;

-- Добавление колонки created_by для sales.orders:
ALTER TABLE sales.orders ADD COLUMN created_by INTEGER;

-- Заполняем нулл записи айдишником первого пользователя с ролью sales_manager
UPDATE sales.orders
SET created_by = (
    SELECT id
    FROM auth.users
    WHERE role = 'sales_manager'
    ORDER BY id ASC
    LIMIT 1
)
WHERE created_by IS NULL;

ALTER TABLE sales.orders ALTER COLUMN created_by SET NOT NULL;

ALTER TABLE sales.orders
    ADD CONSTRAINT fk_orders_created_by
FOREIGN KEY (created_by) REFERENCES auth.users(id) ON DELETE RESTRICT;