# Cloud SQL Scaling and Reliability

Scaling, backup, high availability, and monitoring guidance for Cloud SQL Postgres beyond the baseline template configuration.

The template provisions a minimal Cloud SQL instance (`db-custom-1-3840`, Enterprise edition, private IP only, IAM database auth). This document covers what to change as your workload grows, and when each option becomes worth the cost.

## Baseline Configuration

The template's `database.tf` creates:

- **Instance tier:** `db-custom-1-3840` (1 shared vCPU, 3.75 GB RAM)
- **Edition:** Enterprise
- **Availability:** Zonal (single zone, no automatic failover)
- **Backups:** Daily at 03:00 UTC, 7-day retention, point-in-time recovery enabled
- **Maintenance window:** Sunday 06:00 UTC, stable update track (offset from backup window)
- **Connection pooling:** None (application connects directly through Auth Proxy sidecar)
- **Networking:** Private IP only, enforced Auth Proxy, enforced TLS, IAM database auth

All scaling options below are additive changes to `database.tf`. The template does not include them because the right configuration depends on your workload, budget, and availability requirements.

## Instance Tier Scaling

**When to upgrade:** CPU or memory utilization consistently exceeds 70%, query latency increases, or connection count approaches the tier's limit.

### Tier Options

Cloud SQL uses custom machine types with the format `db-custom-{vCPUs}-{memoryMB}`:

| Tier | vCPUs | RAM | Max Connections | Approximate Monthly Cost |
|---|---|---|---|---|
| `db-custom-1-3840` (baseline) | 1 (shared) | 3.75 GB | ~100 | ~$50 |
| `db-custom-2-7680` | 2 | 7.5 GB | ~200 | ~$100 |
| `db-custom-4-15360` | 4 | 15 GB | ~400 | ~$200 |
| `db-custom-8-30720` | 8 | 30 GB | ~800 | ~$400 |

> [!NOTE]
> Costs are approximate for `us-central1` with Enterprise edition. Actual costs vary by region and sustained use discounts. Check [Cloud SQL pricing](https://cloud.google.com/sql/pricing) for current rates.

**Connection limits** are approximate. Cloud SQL imposes its own per-tier limits below the theoretical maximum (RAM / ~10 MB per connection) due to reserved memory for system processes, shared buffers, and background workers.

### How to Change

Update the `tier` field in your `database.tf`:

```hcl
settings {
  edition = "ENTERPRISE"
  tier    = "db-custom-2-7680"  # 2 vCPUs, 7.5 GB RAM
  # ...
}
```

**Recommendation:** Start by upgrading the instance tier before adding connection pooling or high availability. Tier upgrades are the simplest scaling lever and typically complete in under 5 minutes (brief restart required).

## Automated Backups

The template enables daily backups with 7-day retention and point-in-time recovery (PITR) by default. PITR uses write-ahead logs to restore to any point within the retention window.

### Backup and Maintenance Window Scheduling

The backup window (`start_time`) defines the start of a [4-hour window](https://cloud.google.com/sql/docs/postgres/backup-recovery/backing-up) during which the backup begins. The template sets backups at 03:00 UTC and maintenance at 06:00 UTC Sunday to avoid overlap — maintenance involves a [brief restart](https://cloud.google.com/sql/docs/postgres/maintenance) (~5–10 minutes, <30s connectivity loss for Enterprise edition) that could interrupt a backup in progress. Google's documentation does not explicitly address this interaction, but the [maintenance overview](https://cloud.google.com/sql/docs/postgres/maintenance) states that "maintenance is canceled if an instance operation, such as an export, is ongoing" and advises to "ensure that no other instance operations are planned when maintenance is scheduled." Whether an automated backup qualifies as an "instance operation" in this context is unstated — offsetting the windows avoids the question entirely. For large databases where backups may exceed the 4-hour window, consider increasing the offset.

### Adjusting Retention

The template's 7-day retention covers most workloads. To increase retention for production, update `database.tf`:

Update the `backup_configuration` block inside `settings` in your `database.tf`:

```hcl
settings {
  # ... existing settings ...

  backup_configuration {
    enabled                        = true
    point_in_time_recovery_enabled = true
    start_time                     = "03:00"

    # Increase retention for production
    transaction_log_retention_days = 14
    backup_retention_settings {
      retained_backups = 14
    }
  }
}
```

**Cost impact:** Backup storage is billed at the standard Cloud SQL storage rate. PITR retains transaction logs, which adds storage proportional to write volume. For a low-traffic session database, expect minimal additional cost.

**Retention trade-offs:**

- **7 days (template default):** Sufficient for most workloads. Covers accidental deletes or corruption discovered within a week.
- **14 days:** Better safety margin for issues discovered late. Recommended for production.
- **Longer retention:** Increases storage cost linearly. Rarely needed for session data — consider database exports for long-term archival instead.

## Scheduled Session Cleanup

Unlike the scaling levers above (all opt-in), this is provisioned **by default**. `DatabaseSessionService` has no built-in server-side TTL, so the `sessions` and `events` tables grow without bound. A scheduled `pg_cron` job deletes old rows so storage and backup size stay bounded as the database ages.

### What runs

A daily job named `session-cleanup` (03:30 UTC, offset from the 03:00 backup window) runs:

```sql
DELETE FROM sessions WHERE update_time < (now() AT TIME ZONE 'UTC') - interval '90 days';
```

`events` rows cascade away via the `ON DELETE CASCADE` foreign key, so deleting a stale session reclaims its events in one statement. `user:`-scoped state lives in a separate table with no FK to `sessions`, so it is unaffected. `update_time` is `timestamp without time zone` (naive UTC) in the ADK schema, so the predicate compares in the UTC domain explicitly via `now() AT TIME ZONE 'UTC'`.

**Locking and scan cost.** `DELETE` acquires a `ROW EXCLUSIVE` table-level lock, which conflicts only with `SHARE` and stronger modes, plus `FOR UPDATE` row-level locks on just the rows it deletes, so concurrent reads and writes on other rows proceed unblocked (see [PostgreSQL explicit locking](https://www.postgresql.org/docs/current/explicit-locking.html)). `update_time` is unindexed in the ADK schema, so each run is a sequential scan, and the cleanup itself bounds the table: the scan covers at most the retention window of sessions, once daily, offset from peak hours.

### How it is provisioned (no application code)

- **Flag:** `cloudsql.enable_pg_cron = on` in `terraform/main/database.tf`.
- **Bootstrap:** the bastion's cloud-init writes `/etc/pg-cron-bootstrap.sh` and a oneshot systemd unit that runs it after the Auth Proxy is up. The script connects through the local proxy as the app SA (`cloudsqlsuperuser`), creates the extension in the `postgres` database (Cloud SQL pins `cron.database_name` there), and schedules the job into `agent_sessions` via `cron.schedule_in_database`. See `terraform/main/templates/bastion-cloud-init.yaml`.
- **Idempotent:** COS re-runs cloud-init on every boot; `CREATE EXTENSION IF NOT EXISTS` is a no-op and the named job upserts, so reboots re-assert exactly one job. The job lives in the database, not on the bastion, so the bootstrap needs to succeed only once per database lifetime: a failed run on a later boot leaves the existing job intact, and the at-risk runs (first provision, post-edit replacement) are operator-attended moments where verification is the one `cron.job` query below.
- **Ordering:** the bastion's cloud-init references `google_sql_user.app.name`, which transitively orders the bastion creation after the database and the IAM DB user. These intentional resource graph dependencies prevent the cloud-init bootstrap from running before `agent_sessions` exists, and avoids a `cron.schedule_in_database` error on a missing database.
- **Replacement on change:** the bastion's rendered cloud-init is tracked by `terraform_data.bastion_user_data` and wired to the instance via `lifecycle.replace_triggered_by`, so editing the payload (retention, schedule, anything in the script) recreates the bastion gce instance rather than updating it in place. This mirrors the `ForceNew` behavior the provider gives the `metadata_startup_script` attribute on standard VMs, and for the same reason: an instance runs its startup script (or COS cloud-init) only on boot, so the metadata must be replaced, not patched, for a change to take effect. COS exposes cloud-init only through the in-place `user-data` metadata key with no force-replace convenience attribute, so the terraform_data + lifecycle strategy reconstructs that behavior explicitly.

### Changing retention or schedule

Both are named constants at the top of the bootstrap script in `bastion-cloud-init.yaml` (`RETENTION_INTERVAL` and `CLEANUP_SCHEDULE`). Edit them and `terraform apply`; the bastion is recreated (see Replacement on change above) so cloud-init re-runs and re-asserts the job at the new value.

The default is 90 days. The floor is the backup window (7 days by default): retention shorter than that leaves a deleted session beyond what a backup could restore. 90 days clears the floor and sits past the 30-day default Cloud Logging retention, so the session database doubles as a recovery window for sessions that have aged off logs, while still bounding table growth. Shorten it if storage outweighs that window for your workload, or lengthen it for richer session histories worth keeping.

### Observing runs and failures

Two surfaces expose job activity, and they carry different information, so a complete view uses both.

`cron.job_run_details` (in-database, authoritative). Connect through the bastion tunnel (see [Docker Compose Workflow](docker-compose-workflow.md)) to the `postgres` database:

```sql
-- the scheduled job
SELECT jobid, jobname, schedule, command, database FROM cron.job;

-- recent runs; return_message holds the row count ("DELETE 5") on success or the Postgres error on failure
SELECT d.jobid, j.jobname, d.status, d.return_message, d.start_time
FROM cron.job_run_details d JOIN cron.job j USING (jobid)
ORDER BY d.start_time DESC LIMIT 10;
```

This is the only surface that ties an outcome to a job by name, with `status` (`succeeded` or `failed`) and the full `return_message`. It is a table, not a log, so Cloud Logging cannot read it directly.

`postgres.log` (Cloud Logging, real-time). pg_cron logs job activity to the Postgres server log by default (`cron.log_run` and `cron.log_statement` are both on), and Cloud SQL ingests that log into Cloud Logging under `cloudsql.googleapis.com/postgres.log`, mapping the Postgres log level to the entry severity. Three line shapes appear:

- INFO `LOG: cron job N starting: <command>` — logged by the pg_cron scheduler. Identifies the job by id and includes the full command text.
- INFO `LOG: cron job N COMMAND completed: <result>` — logged by the scheduler on success, with the affected-row count ("DELETE 5 5"). A failed run produces no completed line.
- ERROR `ERROR: <message>` — logged by the background worker that executed the statement. This is the real-time failure signal. Its payload is only the Postgres error, with no job id, name, or command.

Correlation shape (general; settle specifics when wiring alerting). The worker ERROR line and the scheduler `starting` line are emitted by different processes, so they share no PID, but they land in the same second. Join the ERROR to the nearest preceding `cron job N starting` line on timestamp to recover the job identity, and treat the `cron.job_run_details` row at the same `start_time` as the authoritative confirmation. In practice a real-time monitor keys off ERROR-severity `postgres.log` entries while a periodic check reads `cron.job_run_details` for `status = 'failed'` directly.

## High Availability

**When to enable:** Production environments where downtime is unacceptable. Do not enable for dev or staging unless you are testing HA failover behavior.

Regional high availability creates a standby instance in a different zone within the same region. If the primary fails, Cloud SQL automatically promotes the standby. Failover typically completes in under 60 seconds.

### How to Enable

Change `availability_type` in your `database.tf`:

```hcl
resource "google_sql_database_instance" "sessions" {
  # ... existing config ...

  settings {
    availability_type = "REGIONAL"  # default is "ZONAL"
    # ... existing settings ...
  }
}
```

> [!WARNING]
> Regional HA approximately doubles the instance cost because Cloud SQL runs a full standby replica. A `db-custom-1-3840` instance goes from ~$50/month to ~$100/month.

**What HA covers:**

- Zone-level outages (hardware failure, zone maintenance)
- Instance crashes (automatic restart on standby)
- Planned maintenance (minimal downtime with maintenance windows)

**What HA does not cover:**

- Data corruption (use backups for this)
- Region-level outages (use cross-region read replicas if needed)
- Application-level errors (bad queries, accidental deletes)

**Application impact:** Failover causes a brief connection interruption. The Auth Proxy sidecar reconnects automatically. ADK's `DatabaseSessionService` uses `pool_pre_ping=True` (auto-set for non-SQLite), which validates connections before use and discards stale ones. No application code changes are needed.

## Managed Connection Pooling

**When to enable:** When autoscaling Cloud Run to many concurrent instances (roughly 10+) causes connection exhaustion. Not needed for single-instance or low-scale deployments.

Each Cloud Run instance runs its own Auth Proxy sidecar, and each sidecar opens a separate connection pool to Cloud SQL. With ADK's default SQLAlchemy settings (`pool_size=5`, `max_overflow=10`), each instance can open up to 15 connections. At 10 Cloud Run instances, that is 150 connections — which may exceed the tier's limit.

### Prerequisites

Managed connection pooling has specific requirements:

- **Cloud SQL Enterprise Plus edition** (not Enterprise) — higher base cost
- **Cloud SQL Auth Proxy >= 2.15.2** — earlier versions do not support the pooling endpoint
- **Compatible with IAM database auth** — pooling is transparent to the application, which continues connecting to `localhost:5432` through the Auth Proxy

### How to Enable

1. **Upgrade to Enterprise Plus edition** in `database.tf`:

```hcl
settings {
  edition = "ENTERPRISE_PLUS"
  tier    = "db-custom-2-16384"  # Enterprise Plus requires minimum 2 vCPUs, 16 GB RAM
  # ...
}
```

2. **Enable connection pooling** via the Cloud SQL console or Terraform:

```hcl
settings {
  # ... existing settings ...

  managed_connection_pooling {
    enabled = true
  }
}
```

3. **No application code changes needed.** Managed connection pooling is transparent to the application and proxy configuration. Continue connecting to `localhost:5432`.

> [!IMPORTANT]
> Enterprise Plus edition has a significantly higher base cost than Enterprise. Evaluate whether upgrading the instance tier (more connections per instance) is sufficient before switching editions. For many workloads, a `db-custom-4-15360` on Enterprise (~$200/month) handles more connections than a minimum Enterprise Plus instance.

### Decision Framework

Use this sequence to address connection scaling:

1. **Upgrade instance tier** — cheapest, simplest. Increase RAM to support more connections.
2. **Tune SQLAlchemy pool settings** — reduce `pool_size` and `max_overflow` in application code if connections are underutilized.
3. **Enable managed connection pooling** — when tier upgrades are no longer cost-effective or you need 50+ Cloud Run instances.

## Monitoring

Track these Cloud SQL metrics in Cloud Monitoring to anticipate scaling needs before they become incidents.

### Key Metrics

**Connections:**

- `cloudsql.googleapis.com/database/postgresql/num_backends` — active connection count. Compare against the tier's max connections. Alert at 70% utilization.
- `cloudsql.googleapis.com/database/network/connections` — total connection attempts including failed ones. Spikes indicate connection exhaustion.

**CPU:**

- `cloudsql.googleapis.com/database/cpu/utilization` — CPU usage as a fraction (0.0 to 1.0). Sustained values above 0.7 indicate a tier upgrade is needed.
- `cloudsql.googleapis.com/database/cpu/reserved_cores` — number of vCPUs reserved. Useful for confirming tier configuration.

**Memory:**

- `cloudsql.googleapis.com/database/memory/utilization` — memory usage fraction. PostgreSQL uses memory for shared buffers, connection overhead, and sort/hash operations. Alert at 80%.
- `cloudsql.googleapis.com/database/memory/usage` — absolute bytes used.

**Disk:**

- `cloudsql.googleapis.com/database/disk/utilization` — disk usage fraction. Cloud SQL auto-grows storage by default, but monitor to avoid surprises.
- `cloudsql.googleapis.com/database/disk/write_ops_count` — write IOPS. High values may indicate insufficient disk throughput.

**Replication (if using HA):**

- `cloudsql.googleapis.com/database/replication/replica_lag` — lag between primary and standby in seconds. Should be near zero under normal operation.

### Alerting Recommendations

Create Cloud Monitoring alert policies for production:

| Metric | Condition | Action |
|---|---|---|
| CPU utilization | > 0.7 for 15 minutes | Evaluate tier upgrade |
| Memory utilization | > 0.8 for 15 minutes | Evaluate tier upgrade |
| Connection count | > 70% of tier max for 5 minutes | Check for connection leaks, evaluate scaling |
| Disk utilization | > 80% | Review storage growth, consider cleanup |
| Replica lag (HA only) | > 10 seconds for 5 minutes | Investigate replication health |

## Sources

- [Cloud SQL pricing](https://cloud.google.com/sql/pricing)
- [Cloud SQL HA configuration](https://cloud.google.com/sql/docs/postgres/high-availability)
- [Cloud SQL backup overview](https://cloud.google.com/sql/docs/postgres/backup-recovery/backups)
- [Configure standard backups](https://cloud.google.com/sql/docs/postgres/backup-recovery/backing-up)
- [Cloud SQL maintenance overview](https://cloud.google.com/sql/docs/postgres/maintenance)
- [Set a maintenance window](https://cloud.google.com/sql/docs/postgres/set-maintenance-window)
- [Managed connection pooling](https://cloud.google.com/sql/docs/postgres/managed-connection-pooling)
- [Cloud SQL machine series overview](https://cloud.google.com/sql/docs/postgres/machine-series-overview)
- [Cloud Monitoring metrics for Cloud SQL](https://cloud.google.com/monitoring/api/metrics_gcp#gcp-cloudsql)

---

← [Back to References](README.md) | [Documentation](../README.md)
