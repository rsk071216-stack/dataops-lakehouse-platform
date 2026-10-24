# ADR-0005: Slim CI with deferral and a schema per pull request

- Status: accepted
- Date: 2026-10-24

## Context

Building the entire warehouse for every pull request does not scale, and
reviewers cannot see what a change actually produces. dbt Cloud solves this
with a paid feature; we want the same with GitHub Actions only.

## Decision

- Every green `main` run uploads a `prod-manifest` artifact: the dbt manifest
  compiled against the production schemas, plus the commit SHA.
- The `pr-environment` job downloads the manifest of the last successful
  `main` run with `gh run download`, hydrates a production replica from that
  exact commit (a git worktree running the real WAP flow) in the job's
  PostgreSQL service container, then builds only
  `state:modified+` into `pr_<number>_*` with `--defer`, so unchanged parents
  are read from the replica instead of being rebuilt.
- If no manifest exists (first run, expired artifact), it falls back to a full
  build into `pr_<number>_*` and says so in the comment.
- A sticky PR comment (one comment, updated on every push) lists models built,
  tests and unit tests passed or failed, row counts per built model and the
  ingestion contract status.

## Consequences

- The PR environment is ephemeral: it disappears with the job, so there is no
  cleanup job and no shared database that drifts.
- Against a real shared warehouse the same commands work unchanged; then a
  scheduled job should drop `pr_*` schemas of closed PRs.
- Artifacts are kept 90 days; after that the first PR falls back to a full build.
