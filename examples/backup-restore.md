# Backup and Restore

Dakera stores all persistent data in S3-compatible storage (MinIO by default). Backups protect against data loss from hardware failure, accidental deletion, or corrupted upgrades.

## What to Back Up

| Component | Location | Contains |
|-----------|----------|----------|
| MinIO data | `minio-data` Docker volume | All memory vectors, metadata, and namespace data |
| RocksDB cache | `dakera-rocksdb` Docker volume | L2 warm-tier cache (rebuilds automatically from S3) |
| Environment config | `docker/.env` | API keys, MinIO credentials, custom settings |

**MinIO data is the critical backup target.** RocksDB is a cache that rebuilds from S3 on startup.

## Backup Procedures

### Option 1: MinIO Client (`mc`)

The MinIO client can mirror the entire bucket to a local directory or another S3-compatible target.

```bash
# Install mc (if not already available)
# https://min.io/docs/minio/linux/reference/minio-mc.html

# Configure the MinIO alias
mc alias set dakera-local http://localhost:9000 minioadmin minioadmin

# Mirror to a local directory
mc mirror dakera-local/dakera /backups/dakera-$(date +%Y%m%d)

# Mirror to another S3 bucket (offsite backup)
mc alias set backup-s3 https://s3.amazonaws.com ACCESS_KEY SECRET_KEY
mc mirror dakera-local/dakera backup-s3/dakera-backup
```

### Option 2: Docker Volume Backup

```bash
# Stop Dakera to ensure consistency
docker compose down

# Back up the MinIO volume
docker run --rm \
  -v dakera_minio-data:/source:ro \
  -v /backups:/backup \
  alpine tar czf /backup/minio-data-$(date +%Y%m%d).tar.gz -C /source .

# Restart
docker compose up -d
```

### Option 3: Scheduled Backups with Cron

```bash
# Add to crontab: daily backup at 2 AM
0 2 * * * mc mirror --overwrite dakera-local/dakera /backups/dakera-daily 2>&1 | logger -t dakera-backup
```

## Restore Procedures

### Restore from `mc` Mirror

```bash
# Stop Dakera
docker compose down

# Restore the bucket contents
mc mirror /backups/dakera-20260514 dakera-local/dakera

# Restart
docker compose up -d
```

### Restore from Volume Backup

```bash
# Stop Dakera
docker compose down

# Remove the old volume and recreate
docker volume rm dakera_minio-data
docker volume create dakera_minio-data

# Restore
docker run --rm \
  -v dakera_minio-data:/target \
  -v /backups:/backup:ro \
  alpine tar xzf /backup/minio-data-20260514.tar.gz -C /target

# Restart
docker compose up -d

# Verify health
curl http://localhost:3000/health
```

## Best Practices

- **Test restores regularly** — a backup you haven't tested is not a backup
- **Keep offsite copies** — mirror to a separate S3 provider or physical location
- **Retain multiple snapshots** — keep at least 7 daily and 4 weekly backups
- **Back up `.env` separately** — losing your `DAKERA_ROOT_API_KEY` means losing access to encrypted data
- **Monitor backup size** — sudden changes in backup size may indicate data corruption or unexpected growth
