# Host Monitor

Local demo. It monitors this machine only and is read-only toward the host.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Environment

The app reads two variables. It has no default secret and it does not log the password.

| Variable | Purpose |
| --- | --- |
| `SECRET_KEY` | Signs the session cookie |
| `ADMIN_PASSWORD_HASH` | Werkzeug hash of the admin password |

Generate a secret and a hash, then put them in a gitignored `.env` file. Single-quote the hash so `$` in the hash is kept as-is:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
python -c "from getpass import getpass; from werkzeug.security import generate_password_hash; print(generate_password_hash(getpass('Password: ')))"
```

```
SECRET_KEY=paste-the-secret-here
ADMIN_PASSWORD_HASH='paste-the-hash-here'
```

Do not commit `.env`. The password is not stored in the repo or in the app.

## Run

```bash
flask --app app:create_app run --host 127.0.0.1 --port 5000 --no-debug
```

Open http://127.0.0.1:5000 and sign in as `admin`.

The app listens on localhost only. `--no-debug` keeps the interactive debugger off. `python-dotenv` loads `.env` when you use `flask run`.

## Tests

```bash
python -m unittest discover -s tests -t . -v
```

## Continuous integration

[`.github/workflows/ci.yml`](.github/workflows/ci.yml) installs dependencies and runs the unit tests on push and pull request. The workflow has a dummy hash and `SECRET_KEY` for that job only. Local start stays `flask run` on this machine.

## What the dashboard shows

After sign-in the home page shows this machine:

- Hostname, uptime, and load average (1, 5, and 15 minutes)
- Current CPU percent, and memory used / total
- Network throughput: bytes received and sent since boot, and the rate since the previous sample, across all interfaces
- One disk row per local mount (mounts that cannot be read are skipped)
- Listening TCP ports and active TCP connections (local address, remote address, state). Some port details may be hidden without extra privileges
- Top processes by CPU and by memory (10 rows: pid, name, CPU, memory). Full command lines and environment variables are not shown

CPU, memory, and network rates are sampled about every 5 seconds. History is kept in memory for at most 60 minutes, is not written to disk, and is dropped when the process stops.

## Server list

The demo monitors this machine only. Add a display name on the Add server page. The address must be this machine (`127.0.0.1`, `localhost`, `::1`, or the hostname). The file stores the name and `127.0.0.1`. Any other address is rejected. Removing an entry only edits `data/servers.json`.

Each entry links to the same local metrics.

The same page lists every user and can add another one. `admin` is the built-in account from `ADMIN_PASSWORD_HASH`. Added accounts are stored in `data/users.json` as a username and a password hash, and they can sign in. The password itself is not stored.

## What you can and cannot do

You can sign in, sign out, read this machine's metrics, add or remove the local server entry, and add or remove extra user accounts.

You cannot change files, services, processes, or network settings on the host. The app does not open SSH, run a shell command from a request, or monitor another machine. Pages after sign-in are view-only except sign-in, sign-out, and the server list add/remove actions. Metric data requests check the session again and send anonymous users to the login page.
