#!/bin/sh
# Runs as root so we can chown the mounted staticfiles volume (often root-owned).
set -e

mkdir -p /app/staticfiles
chown -R app:app /app/staticfiles

exec gosu app /app/docker-app.sh
