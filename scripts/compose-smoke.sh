#!/bin/sh

set -eu

export API_PORT="${API_PORT:-18000}"
export FRONTEND_PORT="${FRONTEND_PORT:-13000}"

cleanup() {
  docker compose -f compose.yml down
}

trap cleanup EXIT INT TERM

docker compose -f compose.yml config --quiet
docker compose -f compose.yml up --build --detach --wait

curl --fail --silent --show-error \
  "http://127.0.0.1:${FRONTEND_PORT}/api/health" \
  | grep '"status":"healthy"'

docker compose -f compose.yml exec -T api \
  python -m alembic current \
  | grep 'f3c7d18a42b9 (head)'

docker compose -f compose.yml exec -T redis \
  redis-cli ping \
  | grep 'PONG'

docker compose -f compose.yml exec -T frontend nginx -t
