-- Run against the "postgres" database as the Entra ID administrator.
-- Creates a regular (non-admin) Postgres role mapped to the pipeline's
-- user-assigned managed identity. Idempotent.
--   psql ... -v role=<managed identity name> -f bootstrap_pipeline_role_admin.sql
select 1 as already_exists from pg_roles where rolname = :'role' \gset
\if :{?already_exists}
  \echo role :role already exists
\else
  select * from pgaadauth_create_principal(:'role', false, false);
\endif
