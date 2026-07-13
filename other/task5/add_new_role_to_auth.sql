ALTER TABLE auth.users DROP CONSTRAINT users_role_check;

ALTER TABLE auth.users ADD CONSTRAINT users_role_check
    CHECK (role IN ('catalog_manager', 'sales_manager', 'inventory_manager', 'worker'));

-- новые юзеры
INSERT INTO auth.users (username, password, role)
VALUES ('inv_man', crypt('inv_man_pass', gen_salt('bf')), 'inventory_manager');

INSERT INTO auth.users (username, password, role)
VALUES ('worker', crypt('worker_pass', gen_salt('bf')), 'worker');