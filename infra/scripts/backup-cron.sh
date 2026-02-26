#!/bin/sh
set -eu

while true; do
  /scripts/backup-db.sh
  /scripts/backup-objects.sh
  /scripts/backup-config.sh
  sleep 86400
done
