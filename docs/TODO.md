# TODO — Local Linux monitoring demo

Work top to bottom. Finish one checkbox before starting the next.

Demo scope (local machine only):

- Flask UI, read-only toward the host (the app only reads metrics).
- Sign in as `admin`. Password is checked against `ADMIN_PASSWORD_HASH` in `.env`. Session cookie after login.
- Pages can add or remove a server entry. For this demo the entry is always this machine (`127.0.0.1`).
- Metrics: hostname, uptime, load average, CPU, memory, network, disk, listening ports, active connections, top processes.
- Live values plus about 15–60 minutes of history kept in memory (cleared when the app stops).
- Run on this machine. GitHub Actions only runs tests.

---

## 1. Project initialization and basic UI

- [x] Add `app/`, `templates/`, `static/`, `tests/`, and `requirements.txt` with Flask pinned.
- [x] Add `.gitignore` for `.env`, `.venv/`, and `__pycache__/`.
- [x] Serve one home page with a title, navigation, and an empty dashboard area.
- [x] Style the page so it is readable on a laptop screen.
- [x] **Security:** put no secrets, debug backdoor, or default `SECRET_KEY` in source.
- [x] **Docs:** add `README.md` with venv, install, and `flask run` on localhost.

## 2. Sign-in and unit tests

- [x] Add a login page (username and password).
- [x] Accept only username `admin`.
- [x] Read `ADMIN_PASSWORD_HASH` and `SECRET_KEY` from the environment.
- [x] Compare the password to the hash and start a session on success.
- [x] Set the session cookie `HttpOnly` and `SameSite=Lax`.
- [x] Add logout. Send anonymous users to the login page.
- [x] Leave the home page view-only.
- [x] **Security:** do not log the password, store it in plaintext, or commit `.env`.
- [x] **Tests:** success login, failed login, and home page blocked when logged out.
- [x] **Docs:** document the env vars and one command to generate the password hash.

## 3. GitHub Actions

- [x] Add `.github/workflows/ci.yml` to install dependencies and run unit tests on push and pull request.
- [x] Supply a dummy hash and `SECRET_KEY` only inside the workflow.
- [x] **Security:** keep real passwords out of the workflow file and the repo.
- [x] **Docs:** link the workflow from `README.md`. Local start stays `flask run` on this machine.

## 4. Host identity

- [x] Read hostname, uptime, and load average from this machine.
- [x] Show them on the home page after login.
- [x] **Security:** read local data only. Take no shell command from the request.
- [x] **Tests:** cover the reader with fixed sample input.
- [x] **Docs:** note these three fields in `README.md`.

## 5. CPU and memory

- [x] Read current CPU percent and memory used / total.
- [x] Show both on the home page.
- [x] **Security:** read local data only. Show an error string if a read fails; do not leak paths or env values.
- [x] **Tests:** cover the reader with fixed sample input.
- [x] **Docs:** note the two fields in `README.md`.

## 6. Short history

- [x] Keep CPU and memory samples in memory for 60 minutes (one sample every few seconds).
- [x] Draw one simple chart for each series.
- [x] Drop the buffer when the process stops.
- [x] **Security:** cap the buffer size. Do not write samples to disk.
- [x] **Tests:** cover append, cap, and expiry.
- [x] **Docs:** state that history is in-memory and lasts at most 60 minutes.

## 7. Network

- [x] Read bytes sent and received since boot, and the rate since the previous sample.
- [x] Add the rate to the 60-minute history and a small chart.
- [x] **Security:** read interface counters only. Do not capture packet contents.
- [x] **Tests:** cover the rate math with fixed counters.
- [x] **Docs:** note network throughput in `README.md`.

## 8. Disk

- [x] Read used and total space for local mounts.
- [x] Show one row per mount.
- [x] **Security:** skip mounts that cannot be read. Do not follow user-supplied paths.
- [x] **Tests:** cover the reader with fixed sample mounts.
- [x] **Docs:** note disk rows in `README.md`.

## 9. Ports and connections

- [x] List listening TCP ports and active TCP connections (local address, remote address, state).
- [x] If the process lacks permission, show a short message instead of a stack trace.
- [x] **Security:** display addresses and states only. Do not connect out or send traffic.
- [x] **Tests:** cover formatting with fixed sample rows, including the permission-denied case.
- [x] **Docs:** note that some port details may be hidden without extra privileges.

## 10. Top processes

- [x] Show the top processes by CPU and by memory (pid, name, cpu, memory).
- [x] Limit the list (10 rows).
- [x] **Security:** do not expose full command lines or environment variables.
- [x] **Tests:** cover sorting and the row limit with fixed sample processes.
- [x] **Docs:** note the process table in `README.md`.

## 11. Server list

- [x] Add a page to add a server by display name. Store name plus `127.0.0.1` in a local JSON file under the project.
- [x] Reject any address other than this machine.
- [x] Add remove for an entry. Removing an entry only edits the JSON file.
- [x] Show the list on the home page and link each entry to the same local metrics.
- [x] **Security:** ignore host, port, username, and command fields. Do not open SSH. Do not run shell commands.
- [x] **Tests:** cover add, reject non-local address, and remove.
- [x] **Docs:** state that the demo monitors this machine only.

## 12. Read-only pass

- [x] Confirm every page after login is view-only except login, logout, and the server list add/remove actions.
- [x] Refresh metrics on a short timer without a full-page form post.
- [x] **Security:** re-check the session on every data request.
- [x] **Tests:** anonymous data requests redirect to login.
- [x] **Docs:** add a short “what you can and cannot do” note to `README.md`.
