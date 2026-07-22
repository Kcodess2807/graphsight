-- Runs once on first container init (mounted into /docker-entrypoint-initdb.d/).
-- Creates the two isolated databases the platform uses. Tables inside them are
-- created by the application (SQLModel init_control_plane / init_graph_store).
--
-- CREATE DATABASE has no IF NOT EXISTS, so we use the psql \gexec trick to make
-- this idempotent (safe to re-run).

--  control plane: organizations, api keys, pods, assignments, ingest jobs
SELECT 'CREATE DATABASE control_plane_db'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'control_plane_db')\gexec

--  graph store: durable EntityNode / EntityEdge (the compiled .lbug source of truth)
SELECT 'CREATE DATABASE graph_store_db'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'graph_store_db')\gexec
