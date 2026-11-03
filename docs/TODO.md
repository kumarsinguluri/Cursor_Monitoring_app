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

- [ ] Add a login page (username and password).
- [ ] Accept only username `admin`.
- [ ] Read `ADMIN_PASSWORD_HASH` and `SECRET_KEY` from the environment.
- [ ] Compare the password to the hash and start a session on success.
- [ ] Set the session cookie `HttpOnly` and `SameSite=Lax`.
- [ ] Add logout. Send anonymous users to the login page.
- [ ] Leave the home page view-only.
- [ ] **Security:** do not log the password, store it in plaintext, or commit `.env`.
- [ ] **Tests:** success login, failed login, and home page blocked when logged out.
- [ ] **Docs:** document the env vars and one command to generate the password hash.

## 3. GitHub Actions

- [ ] Add `.github/workflows/ci.yml` to install dependencies and run unit tests on push and pull request.
- [ ] Supply a dummy hash and `SECRET_KEY` only inside the workflow.
- [ ] **Security:** keep real passwords out of the workflow file and the repo.
- [ ] **Docs:** link the workflow from `README.md`. Local start stays `flask run` on this machine.

## 4. Host identity

- [ ] Read hostname, uptime, and load average from this machine.
- [ ] Show them on the home page after login.
- [ ] **Security:** read local data only. Take no shell command from the request.
- [ ] **Tests:** cover the reader with fixed sample input.
- [ ] **Docs:** note these three fields in `README.md`.

## 5. CPU and memory

- [ ] Read current CPU percent and memory used / total.
- [ ] Show both on the home page.
- [ ] **Security:** read local data only. Show an error string if a read fails; do not leak paths or env values.
- [ ] **Tests:** cover the reader with fixed sample input.
- [ ] **Docs:** note the two fields in `README.md`.

## 6. Short history

- [ ] Keep CPU and memory samples in memory for 60 minutes (one sample every few seconds).
- [ ] Draw one simple chart for each series.
- [ ] Drop the buffer when the process stops.
- [ ] **Security:** cap the buffer size. Do not write samples to disk.
- [ ] **Tests:** cover append, cap, and expiry.
- [ ] **Docs:** state that history is in-memory and lasts at most 60 minutes.

## 7. Network

- [ ] Read bytes sent and received since boot, and the rate since the previous sample.
- [ ] Add the rate to the 60-minute history and a small chart.
- [ ] **Security:** read interface counters only. Do not capture packet contents.
- [ ] **Tests:** cover the rate math with fixed counters.
- [ ] **Docs:** note network throughput in `README.md`.

## 8. Disk

- [ ] Read used and total space for local mounts.
- [ ] Show one row per mount.
- [ ] **Security:** skip mounts that cannot be read. Do not follow user-supplied paths.
- [ ] **Tests:** cover the reader with fixed sample mounts.
- [ ] **Docs:** note disk rows in `README.md`.

## 9. Ports and connections

- [ ] List listening TCP ports and active TCP connections (local address, remote address, state).
- [ ] If the process lacks permission, show a short message instead of a stack trace.
- [ ] **Security:** display addresses and states only. Do not connect out or send traffic.
- [ ] **Tests:** cover formatting with fixed sample rows, including the permission-denied case.
- [ ] **Docs:** note that some port details may be hidden without extra privileges.

## 10. Top processes

- [ ] Show the top processes by CPU and by memory (pid, name, cpu, memory).
- [ ] Limit the list (10 rows).
- [ ] **Security:** do not expose full command lines or environment variables.
- [ ] **Tests:** cover sorting and the row limit with fixed sample processes.
- [ ] **Docs:** note the process table in `README.md`.

## 11. Server list

- [ ] Add a page to add a server by display name. Store name plus `127.0.0.1` in a local JSON file under the project.
- [ ] Reject any address other than this machine.
- [ ] Add remove for an entry. Removing an entry only edits the JSON file.
- [ ] Show the list on the home page and link each entry to the same local metrics.
- [ ] **Security:** ignore host, port, username, and command fields. Do not open SSH. Do not run shell commands.
- [ ] **Tests:** cover add, reject non-local address, and remove.
- [ ] **Docs:** state that the demo monitors this machine only.

## 12. Read-only pass

- [ ] Confirm every page after login is view-only except login, logout, and the server list add/remove actions.
- [ ] Refresh metrics on a short timer without a full-page form post.
- [ ] **Security:** re-check the session on every data request.
- [ ] **Tests:** anonymous data requests redirect to login.
- [ ] **Docs:** add a short “what you can and cannot do” note to `README.md`.
