#!/bin/bash
# AIP Platform - MongoDB Backup Script
# Usage: ./backup_mongodb.sh [environment]
# Cron:  0 2 * * * /path/to/backup_mongodb.sh production

set -euo pipefail

ENV="${1:-development}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/backups/mongodb/${ENV}/${TIMESTAMP}"
RETENTION_DAYS=30

# Load env-specific config
case "$ENV" in
  production)
    MONGO_URI="${AIP_MONGO_URI:-mongodb://root:example@aip-mongodb.aip-infra.svc:27017}"
    S3_BUCKET="aip-backups-prod"
    ;;
  staging)
    MONGO_URI="${AIP_MONGO_URI:-mongodb://root:example@localhost:27017}"
    S3_BUCKET="aip-backups-staging"
    ;;
  *)
    MONGO_URI="mongodb://root:example@localhost:27017"
    S3_BUCKET=""
    ;;
esac

echo "[$(date)] Starting MongoDB backup for ${ENV}..."
mkdir -p "${BACKUP_DIR}"

# Dump all databases
mongodump --uri="${MONGO_URI}" --out="${BACKUP_DIR}" --gzip

BACKUP_SIZE=$(du -sh "${BACKUP_DIR}" | cut -f1)
echo "[$(date)] Backup completed: ${BACKUP_DIR} (${BACKUP_SIZE})"

# Upload to S3/MinIO if configured
if [ -n "${S3_BUCKET}" ]; then
  ARCHIVE="${BACKUP_DIR}.tar.gz"
  tar -czf "${ARCHIVE}" -C "$(dirname ${BACKUP_DIR})" "$(basename ${BACKUP_DIR})"
  
  if command -v mc &> /dev/null; then
    mc cp "${ARCHIVE}" "minio/${S3_BUCKET}/mongodb/${TIMESTAMP}.tar.gz"
    echo "[$(date)] Uploaded to MinIO: ${S3_BUCKET}/mongodb/${TIMESTAMP}.tar.gz"
  elif command -v aws &> /dev/null; then
    aws s3 cp "${ARCHIVE}" "s3://${S3_BUCKET}/mongodb/${TIMESTAMP}.tar.gz"
    echo "[$(date)] Uploaded to S3: ${S3_BUCKET}/mongodb/${TIMESTAMP}.tar.gz"
  fi
  
  rm -f "${ARCHIVE}"
fi

# Cleanup old backups
find /backups/mongodb/${ENV}/ -maxdepth 1 -type d -mtime +${RETENTION_DAYS} -exec rm -rf {} \;
echo "[$(date)] Cleaned up backups older than ${RETENTION_DAYS} days"
echo "[$(date)] Backup job finished successfully"
