#!/bin/sh
set -eu

while true; do
  /scripts/backup-db.sh
  /scripts/backup-objects.sh
  sleep 86400
done
