/** Create machine-local secrets without printing them or replacing existing files. */
import { randomBytes } from "node:crypto";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
const target = "deploy/langfuse/.env";
if (existsSync(target)) throw new Error("Langfuse .env already exists; reuse its configuration.");
const secret = () => randomBytes(32).toString("hex");
const postgres = secret(), clickhouse = secret(), minio = secret();
const publicKey = `pk-lf-${secret()}`, secretKey = `sk-lf-${secret()}`;
const env: Record<string, string> = {
  SALT: secret(), ENCRYPTION_KEY: secret(), NEXTAUTH_SECRET: secret(),
  POSTGRES_PASSWORD: postgres, DATABASE_URL: `postgresql://postgres:${postgres}@postgres:5432/postgres`,
  CLICKHOUSE_PASSWORD: clickhouse, MINIO_ROOT_PASSWORD: minio, REDIS_AUTH: secret(),
  LANGFUSE_S3_EVENT_UPLOAD_SECRET_ACCESS_KEY: minio,
  LANGFUSE_S3_MEDIA_UPLOAD_SECRET_ACCESS_KEY: minio,
  LANGFUSE_S3_BATCH_EXPORT_SECRET_ACCESS_KEY: minio,
  TELEMETRY_ENABLED: "false", NEXTAUTH_URL: "http://localhost:3000",
  LANGFUSE_INIT_ORG_ID: "inse691", LANGFUSE_INIT_ORG_NAME: "INSE 691",
  LANGFUSE_INIT_PROJECT_ID: "inse691-baseline", LANGFUSE_INIT_PROJECT_NAME: "Baseline demo",
  LANGFUSE_INIT_PROJECT_PUBLIC_KEY: publicKey, LANGFUSE_INIT_PROJECT_SECRET_KEY: secretKey,
  LANGFUSE_INIT_USER_EMAIL: "local@inse691.invalid", LANGFUSE_INIT_USER_NAME: "Local researcher",
  LANGFUSE_INIT_USER_PASSWORD: secret(),
};
writeFileSync(target, Object.entries(env).map(([k,v]) => `${k}=${v}`).join("\n") + "\n", { flag: "wx", mode: 0o600 });
const root = existsSync(".env") ? readFileSync(".env", "utf8") : "";
if (/^LANGFUSE_(PUBLIC_KEY|SECRET_KEY|BASE_URL)=.+$/m.test(root)) throw new Error("Existing tracing settings retained; connect the generated project manually.");
writeFileSync(".env", root.replace(/^LANGFUSE_\w+=.*$/gm, "") + `\nLANGFUSE_PUBLIC_KEY=${publicKey}\nLANGFUSE_SECRET_KEY=${secretKey}\nLANGFUSE_BASE_URL=http://localhost:3000\nLANGFUSE_PROJECT_ID=inse691-baseline\n`);
console.log("Created ignored Langfuse configuration. Login credentials are in deploy/langfuse/.env.");
