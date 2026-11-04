# Host Monitor

Local demo. The dashboard shows this machine. A saved remote host is read over SSH with a fixed check.

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

Add a server by name. Leave the host blank, or enter this machine (`127.0.0.1`, `localhost`, `::1`, or the hostname), and the file stores `127.0.0.1` with no SSH password. A hostname or IP is stored as entered, with its port (22 when blank), SSH username, and SSH password. The password stays in `data/servers.json` so the monitor can reconnect. It is not shown again on the page. Removing an entry only edits that file.

The home page keeps showing this machine. Open a server to read that host. A remote host is contacted with SSH and a fixed read-only script. The form has no command field, and a posted command is ignored.

`admin` is the built-in account from `ADMIN_PASSWORD_HASH`. Extra sign-in accounts, if present in `data/users.json`, are a username and a password hash.

## What you can and cannot do

You can sign in, sign out, read this machine's metrics, and add or remove a local or remote server.

You cannot change files, services, processes, or network settings through this app. Remote reads use the username and password you saved and a fixed script. A command typed into a request is not run. Pages after sign-in are view-only except sign-in, sign-out, and the server list add/remove actions. Metric data requests check the session again and send anonymous users to the login page.
