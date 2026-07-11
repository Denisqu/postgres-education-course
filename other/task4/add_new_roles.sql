CREATE ROLE catalog_manager WITH LOGIN PASSWORD 'catalog_manager_pass';
CREATE ROLE sales_manager WITH LOGIN PASSWORD 'sales_manager_pass';
CREATE ROLE supervisor WITH LOGIN PASSWORD 'supervisor_pass';

-- Делаем supervisor членом других ролей
GRANT catalog_manager TO supervisor;
GRANT sales_manager TO supervisor;