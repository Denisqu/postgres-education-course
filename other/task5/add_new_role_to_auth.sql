ALTER TABLE auth.users DROP CONSTRAINT users_role_check;

ALTER TABLE auth.users ADD CONSTRAINT users_role_check
    CHECK (role IN ('catalog_manager', 'sales_manager', 'inventory_manager', 'worker'));