CREATE ROLE inventory_manager WITH LOGIN PASSWORD 'inventory_manager_pass';
CREATE ROLE worker WITH LOGIN PASSWORD 'worker_pass';

GRANT worker TO supervisor;
GRANT inventory_manager TO supervisor;