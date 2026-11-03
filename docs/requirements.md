# Demo Monitoring Infrastructure — Product Requirements

## 1. Summary

A small local web app for internal teams to see the health of the Linux machine it runs on, without logging into that machine. The demo is read-only toward the host: it collects metrics and never changes system state.

It runs on the same machine as Cursor. There is no remote SSH, no agent, and no multi-host collection.

## 2. Problem

L1, L2, and L3 teams, plus application developers, currently sign in to servers to check memory, CPU, network, and port usage. This demo replaces that login for the local machine with one browser view.

## 3. Users

| Audience | What they do in the demo |
| --- | --- |
| L1, L2, L3 infrastructure | Sign in, open the local server, read current usage and recent trends |
| Application development | Same view, to check resource pressure and which ports and processes are active |

The demo has one shared account. It does not separate teams or roles.

## 4. Goals

- Show CPU, memory, network, disk, ports, host identity, and top processes for this Linux machine.
- Show live values and a short chart of the recent past.
- Keep the interface simple and view-only toward the operating system.
- Let a signed-in user add or remove the local server in the app inventory.
- Sign in as `admin` with a password checked against a hash.

## 5. Non-goals

- Remote Linux or Windows hosts, SSH, agents, or cloud accounts
- Alerts, paging, tickets, or thresholds
- Historical storage that survives a restart
- User management, password change in the UI, or per-team access
- Shell, file edits, service control, or killing processes
- Packaging beyond running the Flask app locally

## 6. Product rules

- **Local host only.** Metrics come from the machine running the app (`localhost`).
- **Read-only host.** The app may read `/proc`, sysfs, and process tables. It must not run configuration changes, install packages, or send commands to the host.
- **Inventory is the only write path.** Signed-in users may add or remove server records in the app. That does not change the host.
- **One server.** The inventory holds the local machine only. A second record, or any host that is not this machine, is rejected with a short message.
- **History is in memory.** Samples are kept for 30 minutes and discarded when the process stops.

## 7. Features

### 7.1 Read-only, simple UI

After sign-in, the user sees:

1. **Server list** — one card for the local server, or an empty state with a way to add it.
2. **Server detail** — current readings, charts, and tables. No buttons that act on the host.

The layout should be clear on a laptop browser: readable type, grouped sections, and obvious empty states. Pages: sign-in, server list, add server, server detail.

### 7.2 Sign-in

- Username is `admin`.
- The password is not stored in plaintext. The app compares it to a hash supplied in the environment or a local config file that is not committed (for example `ADMIN_PASSWORD_HASH`).
- A successful sign-in sets a session cookie. The session secret also comes from the environment (for example `SECRET_KEY`).
- Unsigned requests to any page except sign-in go to the sign-in page.
- A sign-out control clears the session.

The demo does not include self-service password reset.

### 7.3 Server inventory

The user can add the local Linux server and remove it later.

Add form fields:

| Field | Rule |
| --- | --- |
| Display name | Required. Shown on the card and detail page. |
| Host | Required. Accepted values are this machine’s hostname, `localhost`, or `127.0.0.1`. Anything else is rejected. |

Behavior:

- Saving creates one inventory record and starts showing metrics for this machine.
- If a record already exists, the form stays disabled and explains that this demo monitors one local server.
- Remove deletes the record and returns to the empty list. It does not stop or reconfigure the machine.
- Inventory is stored in a local file under the app directory so it survives a refresh. Metric history does not use that file.

### 7.4 Metrics

The detail page refreshes live values about every 5 seconds. Each refresh appends one sample. The app keeps 30 minutes of samples in memory (about 360 points) and uses them for charts.

| Area | What the page shows |
| --- | --- |
| Host | Hostname, uptime, load average (1, 5, 15 minutes) |
| CPU | Current total percent and a 30-minute chart |
| Memory | Used, total, percent, and a 30-minute chart |
| Network | Current receive and transmit rate (bytes per second) and a 30-minute chart of both |
| Disk | One row per mounted filesystem: mount point, used, total, percent |
| Ports | Listening ports and active connections: protocol, local address, port, state, and owning process when available |
| Processes | Top 10 by CPU and top 10 by memory: pid, name, CPU percent, memory percent |

Rates are computed from counters between samples. The first sample may show rates as unavailable until the next refresh.

If a reading cannot be collected, that section shows a short error and the rest of the page still renders.

## 8. Technical notes

- Python and Flask.
- Server-rendered pages (Flask templates) and local CSS and chart assets. The demo must not depend on a network call to load the UI.
- Metric collection uses a local library (such as `psutil`) or the Linux `/proc` filesystem. No shell commands assembled from user input.
- Password hashing uses a standard adaptive hash (for example Werkzeug or bcrypt). The app only verifies the hash; it does not invent a new scheme.
- Bind the demo to `127.0.0.1` and a single local port.

Suggested environment values:

- `ADMIN_PASSWORD_HASH` — hash of the admin password
- `SECRET_KEY` — Flask session secret

## 9. Main flows

**Sign in.** Open the app, enter `admin` and the password, land on the server list.

**Add the server.** From an empty list, enter a display name and `localhost`, save, and open the new card.

**Read status.** On the detail page, read host facts, current CPU, memory, and network, the 30-minute charts, disk rows, ports, and top processes. Wait for a refresh and confirm the live numbers update.

**Remove the server.** Remove the inventory record and confirm the list is empty and the host is unchanged.

**Sign out.** Sign out and confirm the detail page is no longer reachable until sign-in.

## 10. Acceptance

- Unsigned users cannot open the list or detail pages.
- `admin` signs in only when the password matches the configured hash.
- The UI can add and remove one local server and rejects any other host.
- With the server added, the detail page shows every metric in the table in section 7.4.
- Charts cover roughly the last 30 minutes and clear after a process restart.
- No screen offers a way to change files, services, processes, or network settings on the host.
- The app runs locally with Flask and is usable in the browser on this machine.
