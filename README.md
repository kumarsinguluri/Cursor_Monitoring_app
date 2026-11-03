# Host Monitor

Local demo. The home page is a read-only dashboard for this machine.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
flask --app app:create_app run --host 127.0.0.1 --port 5000 --no-debug
```

Open http://127.0.0.1:5000

The app listens on localhost only. `--no-debug` keeps the interactive debugger off.
