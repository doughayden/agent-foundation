# Environment Teardown

Destroy one environment's deployed resources (`terraform/main`) while its bootstrap root, registry, state bucket and Workload Identity setup stay in place.

Stage and prod keep deletion protection in the shared configuration. A deliberate teardown turns it off with temporary local edits that are applied to Terraform state only and never committed.

Claude Code runs this procedure through the `teardown-environment` skill (`.claude/skills/teardown-environment/`), which stops for approval before each step that changes state.

> [!CAUTION]
> A teardown permanently deletes the environment's session database and its automated backups, Memory Bank memories, and every artifact object version. None of it can be restored afterwards.

## What Blocks a Destroy

| Resource | Failure without a fix | Handled by |
|---|---|---|
| Cloud SQL instance (stage, prod) | Terraform refuses: `deletion_protection` is set | Temporary edit |
| Cloud SQL user `app` | `role ... cannot be dropped because some objects depend on it` | `deletion_policy = "ABANDON"` in `database.tf` |
| Service networking connection | `Failed to delete connection; Producer services (e.g. CloudSQL, Cloud Memstore, etc.) are still using this connection.` | `deletion_policy = "REMOVE_PEERING"` in `network.tf` |
| Artifact bucket | `Error trying to delete bucket ... without force_destroy set to true` when it holds objects | Temporary edit |
| Agent Engine (Memory Bank) | `contains child resources: memories` when it holds memories | Temporary edit |
| Subnetwork | `already being used by .../addresses/serverless-ipv4-cloudrun-...` | Wait and destroy again (step 7) |

The SQL user owns objects in the `postgres` database because the bastion's boot script creates the pg_cron extension (for session cleanup) as that user ([Bastion and IAP Tunnel](bastion.md) pg_cron Bootstrap). Deleting the instance removes the user, so Terraform only drops it from state.

Cloud SQL keeps using the connection for a while after its instance is deleted. `REMOVE_PEERING` deletes the VPC peering when the API refuses to delete the connection, so the network can go. It only acts when Terraform deletes the connection, which in this configuration follows the instance's deletion.

## Before You Start

- Permission to delete every resource in the environment's project (project Owner covers it) and Application Default Credentials (`gcloud auth application-default login`)
- No deploy to that environment while the teardown runs: hold merges to `main` for dev and stage, and promotion tags for prod. A merge run against a half-destroyed environment recreates what is missing
- The environment's values from its GitHub Environment Variables (`gh variable list --env <environment>`)

## Tear Down

1. Work in a separate checkout or worktree, so the temporary edits cannot reach a commit:

    ```bash
    git fetch origin
    git worktree add ../teardown origin/main
    cd ../teardown/terraform/main
    ```

2. Write a var file for the environment outside the repository. Values come from the GitHub Environment Variables, mapped as the deploy workflow maps them (`TF_VAR_*` in `.github/workflows/terraform-plan-apply.yml`). Pass it with `-var-file`: command-line variables beat a `terraform.tfvars` in the directory, while `TF_VAR_*` environment variables lose to it ([Terraform: Assign values to variables](https://developer.hashicorp.com/terraform/language/values/variables#assign-values-to-variables)).

    ```hcl
    environment                                 = "stage"
    project                                     = "<GOOGLE_CLOUD_PROJECT>"
    region                                      = "<REGION>"
    zone                                        = "<ZONE>"
    google_cloud_location                       = "<GOOGLE_CLOUD_LOCATION>"
    agent_name                                  = "<IMAGE_NAME>"
    terraform_state_bucket                      = "<TERRAFORM_STATE_BUCKET>"
    workload_identity_pool_principal_identifier = "<WORKLOAD_IDENTITY_POOL_PRINCIPAL_IDENTIFIER>"
    ```

3. Initialize against the environment's state and confirm the var file matches what is deployed. The plan should report no changes:

    ```bash
    terraform init -reconfigure -backend-config="bucket=<TERRAFORM_STATE_BUCKET>"
    terraform plan -var-file=/path/to/stage.tfvars
    ```

4. Make the temporary edits:

    - `database.tf`, `google_sql_database_instance.sessions`: `deletion_protection = false`
    - `main.tf`, `google_storage_bucket.artifact_service`: add `force_destroy = true`
    - `main.tf`, `google_vertex_ai_reasoning_engine.session_and_memory`: add `deletion_policy = "FORCE"`

5. Apply them to the three resources only. The plan should show three in-place updates. All three settings control what Terraform may delete, not how the resources are configured:

    ```bash
    terraform apply -var-file=/path/to/stage.tfvars \
      -target=google_sql_database_instance.sessions \
      -target=google_storage_bucket.artifact_service \
      -target=google_vertex_ai_reasoning_engine.session_and_memory
    ```

6. Destroy, with a placeholder image:

    ```bash
    terraform destroy -var-file=/path/to/stage.tfvars -var docker_image=teardown-placeholder
    ```

    The image is unused by a destroy, but the configuration still evaluates it. Without a value it falls back to the image recorded in state, and that output is gone once Cloud Run is deleted, so every plan after a partial destroy fails in `coalesce` without the placeholder.

7. If the destroy stops on the subnetwork with `serverless-ipv4-cloudrun-...`, wait 1-2 hours and run the same `terraform destroy` again. Cloud Run Direct VPC egress holds addresses in the subnet after the service is deleted, and they cannot be deleted by hand ([Cloud Run: Direct VPC egress](https://docs.cloud.google.com/run/docs/configuring/vpc-direct-vpc)). Only the subnetwork and network are left at that point.

8. From the original checkout, remove the worktree, which discards the temporary edits:

    ```bash
    git worktree remove --force ../teardown
    ```

Dev has no deletion protection, so skip that edit there; the bucket and Memory Bank edits still apply when they hold data.

## Recreate

The environment's next normal deploy recreates it: a merge run for dev and stage, a promotion tag for prod. The deploy passes the image digest, so the placeholder never reaches a real apply.

---

← [Back to References](README.md) | [Documentation](../README.md)
