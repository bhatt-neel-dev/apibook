# APILens — GCP Infrastructure

Terraform that stands up the production cloud footprint for APILens on GCP.

## What this provisions

Everything runs on **one all-in-one Compute Engine VM** behind Caddy — there's no Cloud Run or Cloud SQL here.

| Resource | Name pattern | Purpose |
|----------|--------------|---------|
| Compute Engine VM | `apilens-<env>-app` | Runs the whole stack via docker-compose: Caddy, web, api, identity, ingest, opa, postgres, clickhouse, redis |
| Persistent data disk | `apilens-<env>-data` (`pd-ssd`) | Postgres + ClickHouse volumes. Survives VM recreation (`prevent_destroy`) |
| VPC + subnet + firewall | `apilens-<env>-vpc` / `-subnet` | Public 80/443, SSH on 22 (restrictable via `ssh_source_ranges`), plus an IAP-only SSH rule |
| Artifact Registry | `apilens` (Docker repo) | Container images for backend, identity, ingest, frontend |
| Secret Manager | 7 secrets | `django-secret-key`, `session-secret`, auto-generated `postgres-password` + `clickhouse-password` + `introspect-secret`, plus `resend-api-key` and `jwt-private-key` (both manual, post-apply) |
| Service accounts | 2 | VM runtime, GitHub-deploy |
| Workload Identity Federation | pool `github-actions` | Keyless GitHub Actions → GCP auth |

The deploy workflow in `.github/workflows/deploy.yml` builds images, pushes them to Artifact Registry, then SSHes onto the VM (over IAP) to run `/opt/apilens/deploy.sh <sha>`. Terraform owns the VM, its metadata (the baked-in `docker-compose.prod.yml` / `Caddyfile` / `deploy.sh` / OPA policy), and the secrets; it doesn't touch running containers.

## What this does NOT provision

- **ClickHouse Cloud / managed database** — ClickHouse runs as a container on the same VM (`clickhouse/clickhouse-server`, data on the persistent disk at `/mnt/data/clickhouse`), not as an external managed service.
- **Email provider credentials** — `apilens-resend-api-key` is created empty; populate it manually post-apply (it's a third-party credential, not generated here).
- **JWT signing keypair** — `apilens-jwt-private-key` is also created empty. With no version, the backend falls back to HS256 (safe default); populate it to switch to RS256.
- **Custom domain DNS records** — you point `app_domain`/`api_domain`/`ingest_domain`/`auth_domain` at the `instance_ip` output yourself; Caddy then auto-issues Let's Encrypt certs for whichever domains are set (this part *is* automated, just not by Terraform).

## First-time bootstrap

You need:
- `gcloud` CLI, authenticated against an account with `roles/owner` on the project.
- `terraform` ≥ 1.5.
- A target GCP project (create one with `gcloud projects create` if needed) and its **project number** (`gcloud projects describe <id> --format='value(projectNumber)'`).

### 1. Create the state bucket

Terraform stores its state in GCS so apply is safe from anywhere:

```bash
PROJECT=apilens-prod
gcloud auth application-default login
gcloud config set project "$PROJECT"
gsutil mb -p "$PROJECT" -l us-central1 "gs://$PROJECT-tfstate"
gsutil versioning set on "gs://$PROJECT-tfstate"
```

### 2. Configure variables

```bash
cd infra/gcp/terraform
cp terraform.tfvars.example terraform.tfvars
$EDITOR terraform.tfvars   # fill in project_id, project_number, github_repo, domains
```

Leave `app_domain`/`api_domain`/`ingest_domain`/`auth_domain` empty to serve plain HTTP on the raw IP first; add them (and their DNS A records) once you know the `instance_ip` output.

### 3. Init + apply

```bash
terraform init -backend-config="bucket=$PROJECT-tfstate"
terraform plan
terraform apply
```

First apply takes a couple of minutes — the VM boot + startup script (which writes the docker-compose stack from instance metadata) is the slow step.

### 4. Populate the secrets Terraform doesn't own

`postgres-password`, `clickhouse-password`, and `introspect-secret` are auto-generated. These three still need manual values after apply:

```bash
# Django app secret (used to sign JWTs, session tokens, etc.)
openssl rand -base64 64 | tr -d '\n' | \
  gcloud secrets versions add apilens-django-secret-key --data-file=-

# Frontend session cookie key (AES-256-GCM, raw bytes / hex)
openssl rand -hex 32 | tr -d '\n' | \
  gcloud secrets versions add apilens-session-secret --data-file=-

# Resend API key (transactional email — magic links, verification)
printf %s 're_xxx' | gcloud secrets versions add apilens-resend-api-key --data-file=-

# Optional: RS256 JWT signing key (base64 PEM). Skip to stay on HS256.
# base64 -w0 private_key.pem | gcloud secrets versions add apilens-jwt-private-key --data-file=-
```

### 5. Point DNS and confirm the app is up

```bash
terraform output instance_ip
```

Create A records for whichever of `app_domain`/`api_domain`/`ingest_domain`/`auth_domain` you set, pointing at that IP, then:

```bash
terraform output app_url
terraform output api_url
```

### 6. Set GitHub repo secrets for the deploy workflow

Terraform emits everything you need via the `github_secrets_to_set` output:

```bash
terraform output -json github_secrets_to_set | \
  jq -r 'to_entries[] | "\(.key)=\(.value)"' | \
  while IFS='=' read -r k v; do
    gh secret set "$k" --body "$v"
  done
```

Verify in the GitHub UI under **Settings → Secrets and variables → Actions**.

## Adding a new environment

`var.environment` is baked into resource names. To spin up staging with its own state:

```bash
terraform workspace new staging
terraform apply -var environment=staging -var machine_type=e2-standard-2
```

## Routine operations

- **SSH onto the VM:** `terraform output ssh_command` (tunnels through IAP, no public SSH needed).
- **Rotate the Django secret key:** `openssl rand -base64 64 | gcloud secrets versions add apilens-django-secret-key --data-file=-`, then redeploy (the VM reads the secret at container start, not continuously).
- **Roll the deployed image:** handled by `.github/workflows/deploy.yml`, not Terraform — it re-runs `deploy.sh <sha>` over SSH.
- **Resize the VM:** change `machine_type` in `terraform.tfvars`, `terraform apply` (uses `allow_stopping_for_update`, so it restarts rather than recreates).
- **Destroy everything (dev only!):** the data disk has `prevent_destroy = true` — remove that lifecycle block first if you actually want to drop Postgres/ClickHouse data, then `terraform destroy`.

## File map

```
infra/gcp/terraform/
├── providers.tf              Provider pins, GCS remote state config
├── variables.tf               Inputs (VM sizing, domains, environment)
├── locals.tf                  Name prefixes, Caddy site addresses, ALLOWED_HOSTS/CSRF derivation, WebAuthn RP ID
├── apis.tf                    Enable required Google APIs
├── artifact_registry.tf       Docker repo + cleanup policies
├── compute.tf                 The all-in-one VM + its persistent data disk
├── network.tf                 VPC, subnet, static IP, firewall rules (web + SSH + IAP-SSH)
├── secrets.tf                 Secret Manager entries (3 auto-generated, 2 manual, 2 app-config)
├── service_accounts.tf        VM runtime + GitHub-deploy service accounts
├── workload_identity.tf       WIF pool + provider, GitHub trust
├── iam.tf                     IAM bindings (secret access, artifact pull, actAs)
├── outputs.tf                 instance IP/SSH command, image paths, github-secrets dump
└── terraform.tfvars.example   Starter values
```
