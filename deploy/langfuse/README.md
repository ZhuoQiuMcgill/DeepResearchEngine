# Self-hosted Langfuse

`docker-compose.yml` is based on the official Langfuse compose file from release
`v4.55.0`. This branch binds public ports to loopback, permits an optional MinIO
volume override, and pins the tested Langfuse 4.57.0 web/worker images by digest.
Secrets and the headless initialisation (organisation,
project, API keys, admin user) come from `deploy/langfuse/.env`, which Git
ignores and each machine generates for itself.

See [local baseline demo](../../docs/local-langfuse-demo.md) for generated local
setup, offline papers, the optional WSL storage mount and trace export.

## First start

1. Create `deploy/langfuse/.env` with random values for `SALT`,
   `ENCRYPTION_KEY` (64 hex characters), `NEXTAUTH_SECRET`, `POSTGRES_PASSWORD`,
   `CLICKHOUSE_PASSWORD`, `MINIO_ROOT_PASSWORD` and `REDIS_AUTH`. Then set
   `DATABASE_URL` and the three `LANGFUSE_S3_*_SECRET_ACCESS_KEY` values to match
   them, along with the `LANGFUSE_INIT_*` values. The compose file lists every
   variable and marks the secrets with `CHANGEME`.
2. Start the stack from this directory: `docker compose -p langfuse up -d`.
   The UI is at http://localhost:3000. Log in with `LANGFUSE_INIT_USER_EMAIL` and
   `LANGFUSE_INIT_USER_PASSWORD` from the env file.
3. Copy `LANGFUSE_INIT_PROJECT_PUBLIC_KEY` and `LANGFUSE_INIT_PROJECT_SECRET_KEY`
   into the repository root `.env` as `LANGFUSE_PUBLIC_KEY` and
   `LANGFUSE_SECRET_KEY`, with `LANGFUSE_BASE_URL=http://localhost:3000`.

Research runs send traces whenever these three variables are set. Without them,
runs work normally and only write local run records.

## Stop

`docker compose -p langfuse down` stops the stack and keeps the data volumes.
Add `-v` to delete the volumes as well. The containers use `restart: always`,
so they come back with Docker unless the stack is stopped.
