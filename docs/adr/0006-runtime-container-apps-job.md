# ADR-0006: Azure Container Apps Job as the runtime, GHCR as the registry

- Status: accepted
- Date: 2026-10-24

## Context

The pipeline runs once a day for a few minutes. Paying for an always-on VM,
AKS cluster or orchestrator service would cost far more than the work itself.

## Decision

- Run the pipeline as a **scheduled Azure Container Apps Job** (consumption
  workload profile, cron trigger, 1 vCPU / 2 GiB, one retry, one hour timeout).
  One execution runs `lakehouse run`: landing, dlt load, dbt build into the
  audit schemas, asset checks, publish.
- Authenticate everything with one **user-assigned managed identity**:
  Storage Blob Data Contributor on the two containers only, Key Vault Secrets
  User, a non-admin PostgreSQL role (created by `deploy.yml` via
  `pgaadauth_create_principal`) and, optionally, AcrPull.
- Publish the image to **GHCR** from `ci.yml` on `main`, signed with cosign
  keyless (GitHub OIDC), with SBOM and provenance attestations from BuildKit.
  `deploy.yml` verifies the signature before rolling the digest. An optional
  private ACR (`create_acr = true`) is available for clients who require it.
- Images are referenced **by digest only**; the Terraform variable validation
  rejects tags.

## Consequences

- Cost scales with runtime (a few cents per day). The Container Apps
  environment itself has no standing charge on the consumption profile.
- Console output goes to Log Analytics, which powers the KQL alert rules
  (ADR-0007).
- A public GHCR package must stay public for anonymous pulls; for private
  images use ACR with the managed identity.
