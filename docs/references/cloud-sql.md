# Cloud SQL Scaling and Reliability

Scaling, backup, high availability, and monitoring guidance for Cloud SQL Postgres beyond the baseline template configuration.

The template provisions a minimal Cloud SQL instance (`db-custom-1-3840`, Enterprise edition, private IP only, IAM database auth). This document covers what to change as your workload grows, and when each option becomes worth the cost.

## Baseline Configuration

The template's `database.tf` creates:

- **Instance tier:** `db-custom-1-3840` (1 shared vCPU, 3.84 GB RAM)
- **Edition:** Enterprise
- **Availability:** Zonal (single zone, no automatic failover)
- **Backups:** None configured (Cloud SQL default)
- **Connection pooling:** None (application connects directly through Auth Proxy sidecar)
- **Networking:** Private IP only, enforced Auth Proxy, enforced TLS, IAM database auth

All scaling options below are additive changes to `database.tf`. The template does not include them because the right configuration depends on your workload, budget, and availability requirements.

## Instance Tier Scaling

**When to upgrade:** CPU or memory utilization consistently exceeds 70%, query latency increases, or connection count approaches the tier's limit.

### Tier Options

Cloud SQL uses custom machine types with the format `db-custom-{vCPUs}-{memoryMB}`:

| Tier | vCPUs | RAM | Max Connections | Approximate Monthly Cost |
|---|---|---|---|---|
| `db-custom-1-3840` (baseline) | 1 (shared) | 3.84 GB | ~100 | ~$50 |
| `db-custom-2-7680` | 2 | 7.68 GB | ~200 | ~$100 |
| `db-custom-4-15360` | 4 | 15.36 GB | ~400 | ~$200 |
| `db-custom-8-30720` | 8 | 30.72 GB | ~800 | ~$400 |

> [!NOTE]
> Costs are approximate for `us-central1` with Enterprise edition. Actual costs vary by region and sustained use discounts. Check [Cloud SQL pricing](https://cloud.google.com/sql/pricing) for current rates.

**Connection limits** are approximate and depend on available memory. PostgreSQL reserves ~10 MB per connection, so the practical limit scales with RAM.

### How to Change

Update the `tier` field in your `database.tf`:

```hcl
settings {
  edition = "ENTERPRISE"
  tier    = "db-custom-2-7680"  # 2 vCPUs, 7.68 GB RAM
  # ...
}
```

**Recommendation:** Start by upgrading the instance tier before adding connection pooling or high availability. Tier upgrades are the simplest scaling lever and take effect after a brief restart.

## Automated Backups

**When to enable:** Any environment where data loss is unacceptable. Enable for production immediately. Consider for staging if it holds test data worth preserving.

Cloud SQL supports automated daily backups and point-in-time recovery (PITR). PITR uses write-ahead logs to restore to any point within the retention window.

### How to Enable

Add a `backup_configuration` block inside `settings`:

```hcl
settings {
  # ... existing settings ...

  backup_configuration {
    enabled                        = true
    point_in_time_recovery_enabled = true

    # Backup window — choose a low-traffic period (UTC)
    start_time = "03:00"

    # Retain backups for 14 days (default is 7)
    transaction_log_retention_days = 14
    backup_retention_settings {
      retained_backups = 14
    }
  }
}
```

**Cost impact:** Backup storage is billed at the standard Cloud SQL storage rate. PITR retains transaction logs, which adds storage proportional to write volume. For a low-traffic session database, expect minimal additional cost.

**Retention trade-offs:**

- **7 days (default):** Sufficient for most workloads. Covers accidental deletes or corruption discovered within a week.
- **14 days:** Better safety margin for issues discovered late. Recommended for production.
- **Longer retention:** Increases storage cost linearly. Rarely needed for session data — consider database exports for long-term archival instead.

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
- **Compatible with IAM database auth** — the proxy routes pooled connections through port 3307 automatically when `--auto-iam-authn` is set

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

3. **No application code changes needed.** The Auth Proxy detects the pooling endpoint and routes connections through port 3307 automatically. The application still connects to `localhost:5432`.

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
- [Managed connection pooling](https://cloud.google.com/sql/docs/postgres/managed-connection-pooling)
- [Cloud SQL machine series overview](https://cloud.google.com/sql/docs/postgres/machine-series-overview)
- [Cloud Monitoring metrics for Cloud SQL](https://cloud.google.com/monitoring/api/metrics_gcp#gcp-cloudsql)

---

← [Back to References](README.md) | [Documentation](../README.md)
