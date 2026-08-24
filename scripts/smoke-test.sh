#!/usr/bin/env bash
# Проверка собранного образа, а не исходников. Часть поломок видна только
# в боевой установке: например, сиды тянут faker из группы dev, которой в
# образе нет, — со статическим импортом такой образ не поднялся бы вовсе.
set -euo pipefail

IMAGE="${IMAGE:-python-fastapi-rest-api-example:smoke}"
PORT="${PORT:-3300}"
NAME="${NAME:-pfrae-smoke}"
BASE="http://127.0.0.1:${PORT}"

docker build -t "$IMAGE" .

docker rm -f "$NAME" >/dev/null 2>&1 || true
docker run -d --name "$NAME" -p "${PORT}:8000" \
  -e JWT_SECRET=smoke-secret-not-for-production-0123456789 \
  "$IMAGE" >/dev/null
trap 'docker logs "$NAME" 2>&1 | tail -30; docker rm -f "$NAME" >/dev/null 2>&1 || true' EXIT

for _ in $(seq 1 60); do
  if curl -sf "$BASE/health" >/dev/null 2>&1; then break; fi
  sleep 1
done
if ! curl -sf "$BASE/health" >/dev/null 2>&1; then
  echo "контейнер не стал здоровым за 60 с" >&2
  exit 1
fi

# Обе версии и документация: именно они ломаются, если в образ не попали
# миграции или часть пакета.
for path in /health /courses /openapi.json /v2/openapi.json /v2/courses; do
  code=$(curl -s -o /dev/null -w '%{http_code}' "$BASE$path")
  echo "$path -> $code"
  if [ "$code" != "200" ]; then
    echo "ожидался 200 на $path" >&2
    exit 1
  fi
done

# Авторизация должна работать и в образе, а не только в тестах.
code=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/users")
echo "/users без токена -> $code"
if [ "$code" != "401" ]; then
  echo "ожидался 401 на /users без токена" >&2
  exit 1
fi

# В боевом окружении сиды не применяются, поэтому база пуста: если тут
# окажутся выдуманные курсы, значит фикстуры уехали в бой.
total=$(curl -sf "$BASE/courses" | python3 -c 'import json,sys; print(json.load(sys.stdin)["meta"]["total"])')
echo "курсов в боевом образе: $total"
if [ "$total" != "0" ]; then
  echo "в боевом окружении применились сиды" >&2
  exit 1
fi

echo "smoke-тест пройден"
