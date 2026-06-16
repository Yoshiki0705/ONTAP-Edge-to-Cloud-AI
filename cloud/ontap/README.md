# ONTAP Setup Scripts

CLI command templates for configuring ONTAP as the data hub.
Each script prints commands to run on the ONTAP CLI (it does not execute them remotely).

## Scripts

| Script | Purpose | Phase |
|--------|---------|-------|
| `setup-s3-backup.sh` | S3 SVM + buckets for ClickHouse backup & Parquet export | Phase 5 |
| `setup-telemetry-account.sh` | Least-privilege read-only account for telemetry collector | Phase 1-2 |

See also: per-usecase NFS volume setup in `usecases/*/ontap-setup.sh`.

## Usage

```bash
# Print the commands (review before running on ONTAP)
./setup-s3-backup.sh
./setup-telemetry-account.sh

# Then copy/paste the printed commands into the ONTAP CLI (SSH),
# replacing <...> placeholders with your environment values.
```

## Buckets Created (S3)

| Bucket | Purpose | Consumer |
|--------|---------|----------|
| `clickhouse-backup` | ClickHouse native backups | ClickHouse BACKUP command |
| `clickhouse-export` | Parquet feature export | Databricks (via DataSync) |

## Security Notes

- Telemetry account uses a custom `iot-readonly` role (least privilege)
- S3 uses HTTPS only (auto-generated cert for PoC; use CA-signed in production)
- Restrict access by source IP via firewall policy where possible
- Save S3 secret keys securely — shown only once at creation
