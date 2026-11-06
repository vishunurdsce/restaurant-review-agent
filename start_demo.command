#!/bin/zsh
set -e
cd "$(dirname "$0")"

if ! command -v python3.11 >/dev/null 2>&1; then
  echo "Python 3.11 is required. Install it, then run this launcher again."
  read
  exit 1
fi

if [[ -x .venv/bin/python ]] && ! .venv/bin/python -c 'import sys; raise SystemExit(sys.version_info[:2] != (3, 11))'; then
  echo "Replacing the incompatible virtual environment with Python 3.11."
  rm -rf .venv
fi

if [[ ! -d .venv ]]; then
  python3.11 -m venv .venv
fi
source .venv/bin/activate
python -m pip install -r requirements.txt

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env. Add GOOGLE_API_KEY to enable Gemini answer synthesis; basic retrieval and analytics work without it."
fi

if curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then
  echo "An app is already using port 8000. Close it before starting the demo again."
  read
  exit 1
fi

python -m uvicorn api:app --host 127.0.0.1 --port 8000 &
server_pid=$!
cleanup() { kill "$server_pid" 2>/dev/null || true; }
trap cleanup EXIT INT TERM

echo "Starting the agent. First startup downloads the embedding model and may take a few minutes."
for attempt in {1..240}; do
  health=$(curl -fsS http://127.0.0.1:8000/health 2>/dev/null || true)
  if [[ "$health" == *'"status":"ok"'* ]]; then
    open http://127.0.0.1:8000
    wait "$server_pid"
    exit 0
  fi
  if ! kill -0 "$server_pid" 2>/dev/null; then
    echo "The server stopped during startup. Read the error above, then press a key to close."
    read
    exit 1
  fi
  sleep 2
done

echo "The server did not become healthy in time. Check its startup output."
exit 1
