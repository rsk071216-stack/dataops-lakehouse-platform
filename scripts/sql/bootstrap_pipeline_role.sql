-- Run against the "lakehouse" database as the Entra ID administrator.
-- Least privilege for the pipeline identity: it may create schemas (dlt raw,
-- dbt audit schemas, the WAP swap) in this database and nothing else.
grant connect, create on database lakehouse to :"role";
grant usage, create on schema public to :"role";
