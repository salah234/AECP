# Managed Postgres for the Task Graph, State, and Observability schemas.
# Encryption at rest via module.kms, encryption in transit enforced
# (require SSL), automated backups, and least-privilege per-service DB
# roles (see /security/THREAT_MODEL.md) provisioned here rather than by
# application migrations.
