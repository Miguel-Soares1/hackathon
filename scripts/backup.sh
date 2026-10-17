#!/usr/bin/env bash
# Backup do MySQL de produção (compactado). Mantém os últimos 14 dias.
# Uso: ./scripts/backup.sh            (agende no cron: 0 3 * * * cd /caminho/Hackathon && ./scripts/backup.sh)
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p backups
ARQ="backups/hackathon-$(date +%Y-%m-%d-%H%M).sql.gz"
docker compose -f docker-compose.prod.yml --env-file .env.production exec -T db \
  sh -c 'mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" --single-transaction --routines hackathon' | gzip > "$ARQ"
find backups -name 'hackathon-*.sql.gz' -mtime +14 -delete
echo "Backup salvo em $ARQ ($(du -h "$ARQ" | cut -f1))"
