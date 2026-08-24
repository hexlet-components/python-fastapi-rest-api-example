#!/usr/bin/env bash
# Контрактные тесты: schemathesis сам генерирует запросы из спеки и
# сверяет ответы с ней. Ловит то, чего не видят ни тесты, ни проверка
# запросов: незадокументированные статусы, 5xx на краевых входах и
# неприменённую авторизацию (ignored_auth дёргает защищённые операции без
# токена).
set -euo pipefail

PORT="${PORT:-3210}"
BASE="http://127.0.0.1:${PORT}"
EXAMPLES="${SCHEMATHESIS_EXAMPLES:-20}"

export JWT_SECRET="${JWT_SECRET:-$(openssl rand -hex 32)}"
# Ограничитель частоты в этом прогоне только мешает: schemathesis шлёт
# сотни запросов подряд и упирается в него, а не в поведение API.
export RATE_LIMIT="1000000/minute"
# Цена хеширования тоже: прогон регистрирует пользователей пачками, и
# боевая стоимость scrypt уходит в таймауты, ничего не проверяя.
export SCRYPT_COST=1024

# Порт проверяется до запуска: если на нём кто-то уже слушает, прогон
# уходил бы в чужой процесс и зеленел, не проверив текущий код. Молчаливое
# ложное зелёное хуже падения.
if curl -sf "$BASE/openapi.json" >/dev/null 2>&1; then
  echo "порт $PORT уже занят — прогон пошёл бы против чужого процесса." >&2
  echo "освободите порт или задайте другой: PORT=3211 make contract-test" >&2
  exit 1
fi

LOG=$(mktemp)
uv run fastapi run app/main.py --port "$PORT" >"$LOG" 2>&1 &
APP_PID=$!
trap 'kill "$APP_PID" 2>/dev/null || true; rm -f "$LOG"' EXIT

# Без этой проверки не поднявшееся приложение давало бы голый выход по
# set -e на следующей команде, и искать причину было бы негде.
for _ in $(seq 1 60); do
  if curl -sf "$BASE/openapi.json" >/dev/null 2>&1; then break; fi
  sleep 1
done
if ! curl -sf "$BASE/openapi.json" >/dev/null 2>&1; then
  echo "приложение не поднялось на $BASE за 60 с. Лог:" >&2
  cat "$LOG" >&2
  exit 1
fi

# Пользователь из сидов (app/db/seeds.py) с паролем по умолчанию из
# app/lib/data.py. Токен нужен, чтобы проверялись и защищённые операции,
# а не только 401 на них.
TOKEN=$(
  curl -sf -X POST "$BASE/tokens" \
    -H 'content-type: application/json' \
    -d '{"email":"support@hexlet.io","password":"correct-horse-battery-staple"}' |
    uv run python -c 'import json,sys; print(json.load(sys.stdin)["token"])'
) || {
  echo "не удалось получить токен — сиды или пароль разошлись с app/db/seeds.py" >&2
  exit 1
}

CHECKS=not_a_server_error,ignored_auth,status_code_conformance
CHECKS=$CHECKS,content_type_conformance,response_schema_conformance

# Обе версии: вторая отличается от первой полем phone у пользователя, и
# без отдельного прогона она осталась бы непроверенной.
for version in v1 v2; do
  if [ "$version" = "v1" ]; then
    document="$BASE/openapi.json"
    target="$BASE"
  else
    document="$BASE/v2/openapi.json"
    # Адрес именно с префиксом: пути внутри документа его не знают, он
    # приходит в servers, а --url перекрывает servers целиком. Без этого
    # прогон второй версии бил бы по первой и падал на её же ответах.
    target="$BASE/v2"
  fi

  echo "== контрактные тесты $version =="
  uv run st run "$document" \
    --url "$target" \
    -H "Authorization: Bearer $TOKEN" \
    -c "$CHECKS" \
    --max-examples "$EXAMPLES"
done
