#!/usr/bin/env bash
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$root_dir"

api_pid=""
trap '[[ -z "$api_pid" ]] || kill "$api_pid" 2>/dev/null || true' EXIT

if ! curl -fsS --max-time 1 http://127.0.0.1:8923/health >/dev/null 2>&1; then
  python_bin="$root_dir/.venv/bin/python"
  [[ -x "$python_bin" ]] || python_bin="$(command -v python || true)"
  if [[ -z "$python_bin" ]]; then
    echo "Python non trovato. Segui la sezione macOS del README." >&2
    exit 1
  fi

  (cd sidecar && "$python_bin" sidecar_api.py) &
  api_pid=$!
  for _ in {1..20}; do
    if curl -fsS --max-time 1 http://127.0.0.1:8923/health >/dev/null 2>&1; then
      break
    fi
    if ! kill -0 "$api_pid" 2>/dev/null; then
      wait "$api_pid" || true
      echo "Il servizio Python non si è avviato." >&2
      exit 1
    fi
    sleep 0.5
  done
  if ! curl -fsS --max-time 1 http://127.0.0.1:8923/health >/dev/null 2>&1; then
    echo "Il servizio Python non risponde sulla porta 8923." >&2
    exit 1
  fi
fi

if curl -fsS --max-time 1 http://localhost:1420/ >/dev/null 2>&1; then
  open http://localhost:1420/
  [[ -z "$api_pid" ]] || wait "$api_pid"
else
  npm run dev --prefix app -- --open
fi
