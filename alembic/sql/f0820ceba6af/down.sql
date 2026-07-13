REVOKE UPDATE (status) ON inventory.transfer_items FROM worker;
REVOKE UPDATE (status, started_at, arriving_at, received_at) ON inventory.transfers FROM worker;
REVOKE UPDATE (status) ON inventory.delivery_items FROM worker;
REVOKE UPDATE (status, shipped_at) ON inventory.deliveries FROM worker;
REVOKE UPDATE (quantity) ON inventory.reserves FROM worker;
REVOKE ALL ON inventory.stock FROM worker;

ALTER DEFAULT PRIVILEGES IN SCHEMA inventory REVOKE SELECT ON TABLES FROM worker;
REVOKE SELECT ON ALL TABLES IN SCHEMA inventory FROM worker;
REVOKE USAGE ON SCHEMA inventory FROM worker;

REVOKE UPDATE (status, processing_by) ON sales.orders FROM inventory_manager;

ALTER DEFAULT PRIVILEGES IN SCHEMA sales REVOKE SELECT ON TABLES FROM inventory_manager;
REVOKE SELECT ON ALL TABLES IN SCHEMA sales FROM inventory_manager;
REVOKE USAGE ON SCHEMA sales FROM inventory_manager;

ALTER DEFAULT PRIVILEGES IN SCHEMA inventory REVOKE ALL ON SEQUENCES FROM inventory_manager;
ALTER DEFAULT PRIVILEGES IN SCHEMA inventory REVOKE ALL ON TABLES FROM inventory_manager;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA inventory FROM inventory_manager;
REVOKE ALL ON ALL TABLES IN SCHEMA inventory FROM inventory_manager;
REVOKE ALL ON SCHEMA inventory FROM inventory_manager;

DROP SCHEMA IF EXISTS inventory CASCADE;

ALTER TABLE sales.orders DROP COLUMN IF EXISTS processing_by;

ALTER TABLE catalog.warehouses ADD COLUMN city TEXT;

UPDATE catalog.warehouses w
SET city = c.name
FROM catalog.cities c
WHERE w.city_id = c.id;

ALTER TABLE catalog.warehouses ALTER COLUMN city SET NOT NULL;

ALTER TABLE catalog.warehouses DROP CONSTRAINT IF EXISTS fk_warehouses_city;
ALTER TABLE catalog.warehouses DROP COLUMN IF EXISTS city_id;

DROP TABLE IF EXISTS catalog.cities;