#!/usr/bin/env bash
set -euo pipefail
trap '[[ $? -eq 0 ]] || echo "Installazione interrotta." >&2' EXIT

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$root_dir"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "Questo installer funziona solo su macOS." >&2
  exit 1
fi

if [[ -f "$root_dir/.env.local" ]]; then
  source "$root_dir/.env.local"
fi

python_ok() {
  "$1" -c 'import sys; raise SystemExit(not ((3, 10) <= sys.version_info < (3, 15)))' >/dev/null 2>&1
}

find_python() {
  local candidate path
  for candidate in python3.14 python3.13 python3.12 python3.11 python3.10 python3 python; do
    path="$(command -v "$candidate" 2>/dev/null || true)"
    if [[ -n "$path" ]] && python_ok "$path"; then
      printf '%s\n' "$path"
      return
    fi
  done
  return 1
}

find_brew() {
  local path
  path="$(command -v brew 2>/dev/null || true)"
  if [[ -n "$path" ]]; then
    printf '%s\n' "$path"
    return
  fi

  echo "Homebrew non trovato: installazione in corso..." >&2
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" >&2
  for path in /opt/homebrew/bin/brew /usr/local/bin/brew; do
    if [[ -x "$path" ]]; then
      printf '%s\n' "$path"
      return
    fi
  done
  echo "Homebrew installato ma non trovato. Riapri il Terminale e rilancia lo script." >&2
  exit 1
}

brew_install() {
  local brew_bin="$1" formula="$2"
  if "$brew_bin" list --versions "$formula" >/dev/null 2>&1; then
    "$brew_bin" upgrade "$formula"
  else
    "$brew_bin" install "$formula"
  fi
}

python_bin="${BOOK_DOWNLOADER_PYTHON:-$(find_python || true)}"
brew_bin=""
if [[ -z "$python_bin" ]]; then
  echo "Python compatibile non trovato: installazione di Python 3.14..."
  brew_bin="$(find_brew)"
  brew_install "$brew_bin" python@3.14
  python_bin="$("$brew_bin" --prefix python@3.14)/bin/python3.14"
fi

if ! python_ok "$python_bin"; then
  echo "Python non trovato o non compatibile (3.10-3.14): $python_bin" >&2
  exit 1
fi

node_ok() {
  "$1" -e 'const n=Number(process.versions.node.split(".")[0]); process.exit(n < 22 || n % 2)' >/dev/null 2>&1
}

node_bin="$(command -v node 2>/dev/null || true)"
npm_bin="$(command -v npm 2>/dev/null || true)"
if [[ -z "$node_bin" || -z "$npm_bin" ]] || ! node_ok "$node_bin"; then
  echo "Node.js supportato non trovato: installazione di Node.js 24 LTS..."
  [[ -n "$brew_bin" ]] || brew_bin="$(find_brew)"
  brew_install "$brew_bin" node@24
  export PATH="$("$brew_bin" --prefix node@24)/bin:$PATH"
  node_bin="$(command -v node)"
  npm_bin="$(command -v npm)"
fi

echo "Uso $("$python_bin" --version 2>&1) e Node $($node_bin --version)."

if [[ -z "${BOOK_DOWNLOADER_PYTHON:-}" ]]; then
  if [[ ! -x "$root_dir/.venv/bin/python" ]] || ! python_ok "$root_dir/.venv/bin/python"; then
    "$python_bin" -m venv --clear "$root_dir/.venv"
  fi
  python_bin="$root_dir/.venv/bin/python"
fi

"$python_bin" -m pip install -r "$root_dir/sidecar/requirements.txt"
"$python_bin" -m playwright install chromium
"$npm_bin" ci --prefix "$root_dir/app"

echo "Installazione completata. Avvio Book Downloader..."
trap 'echo "Server chiuso."' EXIT
/bin/bash "$root_dir/start_app.sh"
