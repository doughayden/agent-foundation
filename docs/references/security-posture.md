# Security Posture

Rationale behind key security decisions, organized by defense layer. Each section explains *why* a choice was made and points to the authoritative source — the focused guides and Terraform files that implement and maintain the details.

## Defense-in-Depth Model

The project enforces security at every layer of the stack, from network topology down to application code. No single layer is relied upon alone — each compensates for potential weaknesses in the others.

```text
┌─────────────────────────────────────────────────────┐
│  Network           VPC, private IP, IAP, firewalls  │
├─────────────────────────────────────────────────────┤
│  Identity          WIF, IAM database auth, no keys  │
├─────────────────────────────────────────────────────┤
│  Database          Private-only, enforced proxy/TLS │
├─────────────────────────────────────────────────────┤
│  Compute           COS bastion, Cloud Run Gen2      │
├─────────────────────────────────────────────────────┤
│  Container         Non-root, multi-stage, pinned    │
├─────────────────────────────────────────────────────┤
│  Storage           Public access prevention, UBLA   │
├─────────────────────────────────────────────────────┤
│  Application       CORS validation, Pydantic, ruff  │
└─────────────────────────────────────────────────────┘
```

## Network Layer

**Private IP only, no public database endpoint.** Cloud SQL has `ipv4_enabled = false` — the instance is unreachable from the public internet. All database traffic stays within the VPC via Private Services Access peering. This eliminates the largest attack surface (a publicly routable database) entirely, rather than relying on allowlists or firewall rules that can be misconfigured.

**IAP-gated access, no SSH keys or VPN.** The bastion has no public IP. All access routes through Identity-Aware Proxy, which authenticates via Google identity before any TCP connection is established. Firewall rules restrict the bastion's inbound traffic to Google's IAP CIDR range (`35.235.240.0/20`) on only ports 22 (SSH) and 5432 (proxy). This means a compromised bastion IP is useless without a valid Google identity — there is no network path to reach it otherwise.

**Direct VPC egress from Cloud Run.** Cloud Run uses `PRIVATE_RANGES_ONLY` egress to reach Cloud SQL through the VPC, avoiding a Serverless VPC Access connector (which adds cost and another component to secure).

- Source: `terraform/main/network.tf` (VPC, firewall rules, Private Services Access)
- Source: `terraform/main/main.tf` (Cloud Run VPC egress)
- GCP docs: [Private Services Access](https://cloud.google.com/sql/docs/postgres/configure-private-services-access), [IAP TCP forwarding](https://cloud.google.com/iap/docs/using-tcp-forwarding), [Direct VPC egress](https://cloud.google.com/run/docs/configuring/vpc-direct-vpc)
- Guide: [Infrastructure](../infrastructure.md)

## Identity Layer

**Workload Identity Federation (WIF), no service account keys.** CI/CD authenticates to GCP using GitHub's OIDC tokens federated through WIF. No long-lived credentials exist — there are no JSON key files to leak, rotate, or revoke. The identity trust chain is: GitHub OIDC token, verified by GCP's WIF provider, scoped to a specific repository via attribute conditions.

**IAM database authentication, no passwords.** The application service account authenticates to Cloud SQL using IAM identity (`CLOUD_IAM_SERVICE_ACCOUNT` user type, `--auto-iam-authn` proxy flag). No database password is stored, transmitted, or rotatable. The built-in postgres superuser has a random 30-character password with a strict validation policy — it exists only as a locked fallback, not for routine access.

**Cross-project promotion uses WIF principals, not service accounts.** Stage reads from dev's Artifact Registry, prod reads from stage's — but the IAM binding uses the WIF pool principal, not a service account. This avoids org policies that restrict cross-project service account usage and keeps the trust boundary at the identity pool level.

- Source: `terraform/bootstrap/module/gcp/main.tf` (WIF pool, provider, attribute conditions)
- Source: `terraform/main/database.tf` (IAM database user, password policy)
- GCP docs: [Workload Identity Federation](https://cloud.google.com/iam/docs/workload-identity-federation), [IAM database authentication](https://cloud.google.com/sql/docs/postgres/iam-authentication)
- Guide: [Infrastructure](../infrastructure.md), Reference: [Bootstrap](bootstrap.md)

## Database Layer

**Enforced Auth Proxy and TLS.** `connector_enforcement = "REQUIRED"` rejects any connection not made through the Cloud SQL Auth Proxy. `ssl_mode = "TRUSTED_CLIENT_CERTIFICATE_REQUIRED"` enforces mutual TLS on every connection. These are server-side enforcements — a misconfigured client cannot bypass them.

**Why both proxy enforcement and TLS?** They protect different things. Connector enforcement ensures every connection is authenticated and authorized through GCP's control plane. TLS enforcement ensures the data channel is encrypted even within the VPC. Together, they prevent both unauthorized access and network-level eavesdropping.

**Deletion protection and operational safety.** Deletion protection is enabled for stage and prod environments, preventing accidental destruction of the database via Terraform or the console. Dev is left unprotected for easy teardown. Automated daily backups with point-in-time recovery provide a recovery path for data corruption or accidental deletes. The maintenance window is offset from the backup window to avoid contention — see [Cloud SQL Scaling and Reliability](cloud-sql.md) for scheduling details. SQL Studio (`data_api_access`) is enabled in dev for debugging and disabled in stage/prod.

**OAuth data protected in session state.** Session state is safe for storing sensitive values like OAuth access and refresh tokens because it inherits all database-layer protections:

- **Encryption at rest** — Cloud SQL encrypts all data at rest with AES-256 using [Google-managed keys by default](https://cloud.google.com/sql/docs/postgres/cmek) (see also [GCP default encryption](https://cloud.google.com/docs/security/encryption/default-encryption)). No configuration needed.
- **User isolation** — ADK scopes sessions by `user_id`. One user's state keys are never visible to another user's session.
- **Value-safe logging** — all credential-related logging uses key names and operation labels (`Persisted`, `Restored`, `Marked expired`), never token values. Token contents do not appear in application logs, OTel traces, or debug output.
- **Automatic rotation** — OAuth tokens rotate via ADK's built-in [`OAuth2CredentialRefresher`](https://github.com/google/adk-python/blob/main/src/google/adk/auth/refresher/oauth2_credential_refresher.py). No manual rotation needed.

- Source: `terraform/main/database.tf` (connector enforcement, SSL mode, IAM auth flag, deletion protection, backups, maintenance)
- Agent logging: `LoggingCallbacks._log_state_debug` logs key names only (checks truthiness and discards values); additional lifecycle callbacks log key names and operation labels, never token values; `LoggingCallbacks.after_tool` logs `tool_response` (API data, not credentials — tokens live in state, not tool responses). Audit all `logger.*` calls in `src/` when adding new logging.
- GCP docs: [Enforce Cloud SQL Auth Proxy](https://cloud.google.com/sql/docs/postgres/configure-connectivity#enforce-cloud-sql-auth-proxy), [Configure SSL/TLS](https://cloud.google.com/sql/docs/postgres/configure-ssl-instance), [Default encryption at rest](https://cloud.google.com/sql/docs/postgres/cmek)
- Reference: [Cloud SQL Scaling and Reliability](cloud-sql.md)

## Compute Layer

**Container-Optimized OS (COS) for the bastion.** COS was chosen over a general-purpose Linux image (Ubuntu, Debian) for several properties that reduce the bastion's attack surface:

- **Verified boot with read-only root filesystem** — the root filesystem is always mounted read-only, and its checksum is verified by the kernel on each boot. Malware cannot persist by modifying system binaries.
- **No package manager** — containers package their own dependencies, so COS trims unnecessary packages to minimize the attack surface. An attacker with shell access cannot install additional software.
- **Minimal userland** — COS includes only what is needed to run Docker containers. No compilers, interpreters, or network utilities that aid lateral movement.
- **Automatic security updates** — the OS image is updated in its entirety (including the kernel) on an active-passive partition, not package-by-package. Updates take effect on reboot. COS requires explicit opt-in for automatic updates — the template sets `cos-update-strategy = "update_enabled"` in instance metadata to enable them.
- **Default-deny firewall** — COS drops all incoming TCP/UDP connections except SSH on port 22. The cloud-init configuration explicitly opens only port 5432 for Auth Proxy traffic.
- **Docker-native** — the Auth Proxy runs as a Docker container managed by systemd, not as a binary installed on the host. This provides process isolation and consistent versioning. The proxy image uses a floating major-version tag (`cloud-sql-proxy:2`) intentionally — this is a deliberate exception to the pinning principle, allowing automatic security patch pickup on container restart.

The bastion's sole purpose is running the Auth Proxy for developer access to Cloud SQL. COS enforces that constraint at the OS level — there is almost nothing else the instance *can* do.

**Cloud Run Gen2 execution environment.** Gen2 uses a full Linux VM with hardware-level isolation (KVM), providing stronger syscall compatibility than Gen1's gVisor-based sandbox.

- Source: `terraform/main/bastion.tf` (COS image, no public IP, metadata)
- Source: `terraform/main/templates/bastion-cloud-init.yaml` (iptables, systemd proxy service)
- GCP docs: [COS features and benefits](https://cloud.google.com/container-optimized-os/docs/concepts/features-and-benefits), [COS security overview](https://cloud.google.com/container-optimized-os/docs/concepts/security) (verified boot, read-only rootfs, default-deny firewall), [COS automatic updates](https://cloud.google.com/container-optimized-os/docs/concepts/auto-update) (active-passive partition scheme), [COS host firewall](https://cloud.google.com/container-optimized-os/docs/how-to/firewall), [Cloud Run execution environments](https://cloud.google.com/run/docs/about-execution-environments)
- Guide: [Infrastructure](../infrastructure.md)

## Container Layer

**Non-root execution.** The Dockerfile creates a system user (`app:app`) and switches to it before CMD. A container escape from a non-root process grants no host-level privileges.

**Multi-stage build.** The builder stage (compilers, build tools, full source) is discarded. The runtime image contains only the Python runtime, installed packages, and application code — approximately 200MB. Fewer binaries means fewer CVEs to track.

**Pinned toolchain.** `uv` is pinned to a specific version in the Dockerfile (`COPY --from=ghcr.io/astral-sh/uv:0.10.11`), and dependencies are installed with `--locked` to enforce exact versions from `uv.lock`. No floating tags or unconstrained resolution in production builds.

**Immutable deployment by digest.** CI/CD deploys Cloud Run revisions by image digest, not tag. A tag can be repointed; a digest cannot. This guarantees the exact image that was built and tested is what runs in production.

- Source: `Dockerfile` (multi-stage build, non-root user, pinned uv)
- Reference: [Dockerfile Strategy](dockerfile-strategy.md)

## Storage Layer

**GCS public access prevention.** The artifact service bucket enforces `public_access_prevention = "enforced"` and `uniform_bucket_level_access = true`, preventing accidental public exposure through object-level ACLs. Versioning is enabled for recovery from accidental overwrites.

- Source: `terraform/main/main.tf` (GCS bucket configuration)
- GCP docs: [Public access prevention](https://cloud.google.com/storage/docs/public-access-prevention), [Uniform bucket-level access](https://cloud.google.com/storage/docs/uniform-bucket-level-access)

## Application Layer

**Origin validation.** ADK's origin check middleware blocks cross-origin state-changing requests (POST, PUT, DELETE) by validating the `Origin` header via exact string matching. This works alongside Starlette's CORS middleware. `ALLOW_ORIGINS` is validated at startup via a Pydantic field validator that rejects malformed JSON, non-array types, and empty values.

**Fail-fast configuration.** All environment variables are validated at startup through Pydantic's `model_validate()`. Missing or malformed configuration causes an immediate `sys.exit(1)` — the application never starts in a partially configured state.

**Static analysis with security rules.** Ruff's `S` rule set (flake8-bandit) runs in CI and locally, catching common security mistakes: hardcoded credentials, insecure function usage, and binding patterns. Suppressions require specific codes and justification (`# noqa: S105 — test mock`).

- Source: `src/<package>/utils/config.py` (Pydantic validation, ALLOW_ORIGINS)
- GCP docs: [Ruff flake8-bandit rules](https://docs.astral.sh/ruff/rules/#flake8-bandit-s)
- Reference: [ADK Origin Check Middleware](adk-origin-check-middleware.md), [Code Quality](code-quality.md)

## Consumer Guidance

### Customer-Managed Encryption Keys (CMEK)

The template uses Google-managed encryption for all data at rest — Cloud SQL, GCS buckets, and Terraform state buckets. This is the GCP default and provides AES-256 encryption with Google-managed key rotation.

For organizations that require control over encryption key lifecycle (creation, rotation, revocation, access logging), GCP offers Customer-Managed Encryption Keys via Cloud KMS. CMEK gives you:

- **Key access auditing** — Cloud Audit Logs record every use of the key, providing a trail for compliance
- **Key revocation** — disabling or destroying the key renders encrypted data permanently inaccessible, useful for data disposal requirements
- **Key rotation control** — set your own rotation schedule rather than relying on Google's
- **Separation of duties** — key management and data access are controlled by different IAM roles

**Where to apply CMEK in this project:**

| Resource | Terraform Field | Documentation |
|---|---|---|
| Cloud SQL instance | `settings.disk_encryption_key_name` | [Cloud SQL CMEK](https://cloud.google.com/sql/docs/postgres/configure-cmek) |
| GCS buckets (artifact service) | `encryption.default_kms_key_name` | [GCS CMEK](https://cloud.google.com/storage/docs/encryption/using-customer-managed-keys) |
| Terraform state buckets | `encryption.default_kms_key_name` | Same as GCS |
| Bastion boot disk (COS) | `boot_disk.kms_key_self_link` | [Compute Engine CMEK](https://cloud.google.com/compute/docs/disks/customer-managed-encryption) |
| Artifact Registry (bootstrap) | `kms_key_name` | [Artifact Registry CMEK](https://cloud.google.com/artifact-registry/docs/cmek) |
| Vertex AI Agent Engine | `encryption_spec` | [Vertex AI CMEK](https://cloud.google.com/vertex-ai/docs/general/cmek) |

**Getting started:** Create a Cloud KMS keyring and crypto key in the same region as your resources, grant the relevant service agents the `roles/cloudkms.cryptoKeyEncrypterDecrypter` role, then reference the key in the Terraform fields above. Each GCP service uses a different service agent — consult the linked documentation for the specific principal.

> [!IMPORTANT]
> CMEK adds operational complexity: key deletion is irreversible (data loss), key rotation requires planning, and cross-region keys have latency implications. Evaluate whether your compliance requirements mandate CMEK before adopting it.

---

← [Back to References](README.md) | [Documentation](../README.md)
