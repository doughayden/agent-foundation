# Bastion and IAP Tunnel

How developers reach the private-IP Cloud SQL instance, what the bastion host runs, and what it does to the database.

## Purpose

Cloud SQL has no public IP (`ipv4_enabled = false`), so nothing outside the VPC can connect to it. Cloud Run reaches it through direct VPC egress and its Auth Proxy sidecar. Developers reach it through a small bastion VM: an IAP tunnel carries `localhost:5432` on your machine to the bastion, and the Cloud SQL Auth Proxy on the bastion forwards it to the instance's private IP.

```text
Your machine (localhost:5432) ──► IAP ──► Bastion VM (Auth Proxy :5432) ──► Cloud SQL private IP
```

Docker Compose and `uv run server` both use this path; Compose runs the tunnel in a container ([Docker Compose Workflow](docker-compose-workflow.md)), `uv run server` needs it started by hand ([Cloud Backend Options](cloud-backend-options.md)).

## Architecture

All of it lives in `terraform/main/`:

| Piece | Where | What it does |
|---|---|---|
| Bastion VM | `bastion.tf` | `e2-micro`, Container-Optimized OS (`cos-cloud/cos-stable`), no public IP, OS Login enabled (`enable-oslogin = TRUE`), automatic COS updates |
| Bastion service account | `bastion.tf` | Its own identity with `roles/cloudsql.client`, `roles/logging.logWriter` and `roles/monitoring.metricWriter`, plus `roles/iam.serviceAccountTokenCreator` on the app service account |
| Cloud SQL Auth Proxy | `templates/bastion-cloud-init.yaml` | A systemd unit runs `gcr.io/cloud-sql-connectors/cloud-sql-proxy:2` with the flags shared with the Cloud Run sidecar (`local.cloud_sql_proxy_args` in `main.tf`: `--private-ip`, `--port=5432`, `--auto-iam-authn`), plus two bastion-only flags: `--address=0.0.0.0` and `--impersonate-service-account=<app SA>` |
| Host firewall | `templates/bastion-cloud-init.yaml` | COS drops inbound traffic by default; `runcmd` adds an `iptables` rule that accepts port 5432 |
| IAP firewall rules | `network.tf` | `iap-ssh` (22) and `iap-postgres` (5432), source `35.235.240.0/20` (Google's IAP range), target the bastion service account |
| Cloud NAT | `network.tf` | Outbound access for the bastion, which has no public IP: pulls the proxy and Postgres images and reaches the Cloud SQL Admin API |

The proxy binds `0.0.0.0` because tunneled connections arrive on the VM's network interface, not on loopback. The Cloud Run sidecar keeps the default loopback binding and runs as the app service account directly, so it needs neither bastion-only flag.

The job summary of a deploy run lists the bastion's instance name and zone, as do the `bastion_instance` and `bastion_zone` outputs of `terraform/main`. Both go into `.env` as `BASTION_INSTANCE` and `BASTION_ZONE` ([Environment Variables: Cloud Resources](../environment-variables.md#cloud-resources)).

## Identity in the Database

The bastion's proxy impersonates the app service account and logs in with IAM database authentication. Every connection through the tunnel therefore acts in Cloud SQL as the app's database user (`<app-sa-email>` without `.gserviceaccount.com`), whoever opened the tunnel. No password exists or is needed, and database-side audit shows the app user, not the developer.

Connect with `sslmode=disable`: the proxy encrypts the hop to Cloud SQL, and the hop to the bastion runs inside the IAP tunnel.

```bash
psql "host=127.0.0.1 port=5432 user=<app-sa-email-without-.gserviceaccount.com> dbname=agent_sessions sslmode=disable"
```

## Developer Access

| To... | Needs | Verified |
|---|---|---|
| Open the tunnel to port 5432 (`gcloud compute start-iap-tunnel <bastion> 5432 --zone=<zone>`) | `roles/iap.tunnelResourceAccessor` | Yes: a principal holding only this role opened the tunnel and queried `agent_sessions` |
| SSH to the bastion (`gcloud compute ssh <bastion> --zone=<zone> --tunnel-through-iap`) | `roles/iap.tunnelResourceAccessor` plus an OS Login role (`roles/compute.osLogin`), since the instance enables OS Login | No: from Google's documentation |

Google's [IAP TCP forwarding](https://docs.cloud.google.com/iap/docs/using-tcp-forwarding) permission table also lists `compute.instances.get` and `compute.instances.list` for `start-iap-tunnel`; with `--zone` passed, the tunnel opened without them. Project Owners hold every role above already. Grant the tunnel role to other developers with `gcloud projects add-iam-policy-binding` or in the Console.

## pg_cron Bootstrap

The bastion also provisions the session-cleanup job ([Cloud SQL Scaling and Reliability: Scheduled Session Cleanup](cloud-sql.md#scheduled-session-cleanup)), because it is the one host with a standing database connection outside Cloud Run.

- **Script:** cloud-init writes `/etc/pg-cron-bootstrap.sh` and a oneshot systemd unit that runs it after the proxy starts. The script waits up to about 60 seconds for the proxy, then connects through it as the app's database user to the `postgres` database and runs `CREATE EXTENSION IF NOT EXISTS pg_cron` and `cron.schedule_in_database('session-cleanup', ...)`, which schedules the delete in `agent_sessions`
- **Why `postgres`:** Cloud SQL runs pg_cron in the `postgres` database by default; the `cron.database_name` flag changes that ([Cloud SQL extensions](https://docs.cloud.google.com/sql/docs/postgres/extensions)). The template keeps the default
- **Idempotent:** COS re-runs cloud-init on every boot. `CREATE EXTENSION IF NOT EXISTS` is a no-op and the named job upserts, so a reboot re-asserts exactly one job. The job lives in the database, so the bootstrap only has to succeed once per database lifetime
- **Ordering:** the cloud-init template references `google_sql_user.app.name`, so Terraform creates the bastion after the database and the IAM database user exist
- **Replacement on change:** `terraform_data.bastion_user_data` hashes the rendered cloud-init and the instance's `lifecycle.replace_triggered_by` points at it. Any edit to the template, retention or schedule included, recreates the bastion on the next apply, since COS reads cloud-init only at boot

### What the App User Owns

Because the app's database user creates the extension, it owns pg_cron's objects in the `postgres` database. On a deployed environment, `pg_shdepend` lists 19 entries for that user there: 13 ownership entries (`deptype` `o`) and 6 initial-privilege entries (`deptype` `i`) that pg_cron records on objects it grants access to:

| Object | Entries |
|---|---|
| Extension `pg_cron` | 1 owner |
| Schema `cron` | 1 owner |
| Functions `cron.alter_job`, `cron.job_cache_invalidate`, `cron.schedule` (2 signatures), `cron.schedule_in_database`, `cron.unschedule` (2 signatures) | 7 owner + 2 initial privilege (`alter_job`, `schedule_in_database`) |
| Tables `cron.job`, `cron.job_run_details` | 2 owner + 2 initial privilege |
| Sequences `cron.jobid_seq`, `cron.runid_seq` | 2 owner + 2 initial privilege |

Postgres refuses to drop a role that owns objects, so destroying the environment cannot drop this user on its own. `google_sql_user.app` uses `deletion_policy = "ABANDON"`: Terraform drops it from state, and deleting the instance removes it.

To list the entries yourself, connect to the `postgres` database through the tunnel and run:

```sql
SELECT pg_describe_object(classid, objid, objsubid) AS object, deptype
FROM pg_shdepend
WHERE refobjid = (SELECT oid FROM pg_roles WHERE rolname = current_user)
  AND dbid = (SELECT oid FROM pg_database WHERE datname = current_database())
ORDER BY 1;
```

## Health and Recovery

**Symptom:** the tunnel connects but queries fail or hang.

1. Confirm the VM is running: `gcloud compute instances describe <bastion> --zone=<zone> --format='value(status)'`
2. SSH in (see Developer Access for the roles): `gcloud compute ssh <bastion> --zone=<zone> --tunnel-through-iap`
3. Check the proxy container and its logs: `docker ps`, then `docker logs cloud-sql-proxy`
4. Check the host firewall accepts 5432: `sudo iptables -L INPUT -n | grep 5432` shows an `ACCEPT` rule
5. Check the proxy listens on every interface: `sudo ss -tlnp | grep 5432` shows `*:5432`, not `127.0.0.1:5432`
6. Check the bootstrap ran: `sudo journalctl -u pg-cron-bootstrap.service`

`InvalidAuthorizationSpecificationError: Cloud SQL IAM service account authentication failed` in the proxy logs means the bastion service account cannot impersonate the app service account: check its `roles/iam.serviceAccountTokenCreator` binding (`google_service_account_iam_member.bastion_impersonate_app`).

To recover a broken bastion, reboot it (`gcloud compute instances reset <bastion> --zone=<zone>`): COS re-runs cloud-init on boot, restarting the proxy and re-asserting the cleanup job. To rebuild it from scratch, run a Terraform apply with `-replace=google_compute_instance.bastion` against the environment.

---

← [Back to References](README.md) | [Documentation](../README.md)
