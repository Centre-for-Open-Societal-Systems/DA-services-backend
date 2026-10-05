# Setup Guide

Local development environment for `da_services`, the OpenAgriNet Ethiopia DA Services
(Part 2) Frappe app.

Frappe is not practical to run natively on Windows, so this project develops inside the
official `frappe_docker` dev container, the same way `oan_grievance_service` does. Every
`bench` command below runs **inside** the container, never on the Windows host.

---

## 1. Tech stack

| Layer             | Component                        | Version used            |
| ----------------- | -------------------------------- | ----------------------- |
| Container runtime | Docker Desktop (WSL 2 backend)   | 29.x                    |
| Dev environment   | `frappe/frappe_docker` container | `frappe/bench:latest`   |
| Bench CLI         | frappe-bench                     | 5.31                    |
| Framework         | Frappe                           | 16.36 (`version-16`)    |
| Language          | Python                           | 3.14 (Frappe 16 requires ≥3.14) |
| Front-end tooling | Node                             | 24                      |
| Database          | MariaDB                          | 11.8                    |
| Cache / queue     | Redis                            | alpine (two instances)  |
| Mail sink (dev)   | Mailpit                          | latest                  |
| App               | `da_services`                    | 0.0.1                   |

---

## 2. How the pieces are laid out

Two folders sit side by side on the host:

```
C:\Users\<you>\
├── DA-services-backend\              this repository = the da_services Frappe app
└── oan_da_services_devcontainer\     shallow clone of frappe/frappe_docker + .devcontainer\
```

Inside the container:

```
/workspace                                    <- bind mount of oan_da_services_devcontainer
/workspace/da_services_repo                   <- bind mount of THIS repository
/workspace/development                        <- Docker named volume "bench-data"
/workspace/development/frappe-bench           <- the bench (frappe clone, env, node_modules, sites)
/workspace/development/frappe-bench/apps/da_services -> /workspace/da_services_repo   (symlink)
```

Why a named volume for the bench: on Docker Desktop a Windows bind mount is far too slow
for the tens of thousands of small files `bench init` and `yarn` write, and `uv`/`pip`
hang on it. The bench therefore lives on the Linux side; only the app repository is
bind-mounted so you edit code with your normal editor and Frappe picks it up live.

Why a symlink instead of mounting straight into `apps/`: Docker would pre-create the
`frappe-bench/` directory before `bench init` runs, and `bench init` refuses a path that
already exists. Mounting the repo at a neutral path and linking it in afterwards keeps
first-time setup to a single `docker compose up`.

Ports are offset from the grievance stack so both can run at once:

| Service          | Host address               |
| ---------------- | -------------------------- |
| Frappe web       | http://127.0.0.1:8200      |
| Frappe socketio  | 127.0.0.1:9200             |
| Mailpit UI       | http://127.0.0.1:8026      |
| Mailpit SMTP     | 127.0.0.1:1026 (container: `mailpit:1025`) |
| MariaDB          | not published (container: `mariadb:3306`, root/`123`) |

---

## 3. Prerequisites (Windows host)

- Docker Desktop with the WSL 2 backend enabled.
- Git. Commands below assume Git Bash.
- VS Code with the *Dev Containers* extension (optional).

You do **not** need Python, Node, MariaDB or Redis on the host.

### Git Bash path translation

Git Bash rewrites arguments that look like Unix paths, which breaks `docker exec -w`.
Prefix such commands with `MSYS_NO_PATHCONV=1`:

```bash
MSYS_NO_PATHCONV=1 docker exec -w /workspace/development/frappe-bench \
  oan_da_services_dev-frappe-1 bench --site da-services.localhost list-apps
```

### Disk space

Docker Desktop stores images, volumes and the bench on `C:`. Keep at least 10 GB free;
installs stall or fail silently when the drive is nearly full.

---

## 4. First-time setup

### 4.1 Clone both repositories

```bash
cd /c/Users/<you>
git clone https://github.com/Centre-for-Open-Societal-Systems/DA-services-backend.git
git clone --depth 1 https://github.com/frappe/frappe_docker.git oan_da_services_devcontainer
```

### 4.2 Add the dev container config

Copy `.devcontainer/docker-compose.yml` and `.devcontainer/devcontainer.json` from this
repository's `docs/devcontainer/` folder into `oan_da_services_devcontainer/.devcontainer/`.
If your repo is not at `../../DA-services-backend` relative to that folder, set
`DA_SERVICES_REPO=<path>` in the environment before running compose.

### 4.3 Start the containers

```bash
cd /c/Users/<you>/oan_da_services_devcontainer/.devcontainer
docker compose -p oan_da_services_dev up -d
docker ps --filter "name=oan_da_services_dev" --format "table {{.Names}}\t{{.Status}}"
```

| Container                            | Role                                |
| ------------------------------------ | ----------------------------------- |
| `oan_da_services_dev-frappe-1`       | bench; every command runs here      |
| `oan_da_services_dev-mariadb-1`      | database                            |
| `oan_da_services_dev-redis-cache-1`  | metadata and session cache          |
| `oan_da_services_dev-redis-queue-1`  | background jobs and scheduler       |
| `oan_da_services_dev-mailpit-1`      | catches outgoing mail               |

The `frappe` container runs `BENCH_DISABLE_UV=1`, so bench uses `pip`.

### 4.4 Give the frappe user the bench volume

```bash
docker exec -u root oan_da_services_dev-frappe-1 chown frappe:frappe /workspace/development
```

### 4.5 Initialise the bench

```bash
MSYS_NO_PATHCONV=1 docker exec -w /workspace/development oan_da_services_dev-frappe-1 \
  bench init --skip-redis-config-generation --frappe-branch version-16 frappe-bench
```

This clones Frappe, builds the virtualenv, installs Node dependencies and builds assets
(a few minutes). Then point the bench at the compose services:

```bash
MSYS_NO_PATHCONV=1 docker exec -w /workspace/development/frappe-bench oan_da_services_dev-frappe-1 bash -lc '
  bench set-config -g db_host mariadb &&
  bench set-config -g db_port 3306 &&
  bench set-config -g redis_cache redis://redis-cache:6379 &&
  bench set-config -g redis_queue redis://redis-queue:6379 &&
  bench set-config -g redis_socketio redis://redis-queue:6379 &&
  bench set-config -g developer_mode 1'
```

### 4.6 Link the app, create the site and install

The repository is mounted at `/workspace/da_services_repo`. Link it into the bench's
`apps/` folder, register it, then create the site and install.

```bash
MSYS_NO_PATHCONV=1 docker exec -w /workspace/development/frappe-bench oan_da_services_dev-frappe-1 bash -lc '
  ln -sfn /workspace/da_services_repo apps/da_services &&
  grep -qx da_services sites/apps.txt || echo da_services >> sites/apps.txt &&
  env/bin/pip install -e apps/da_services &&
  bench new-site da-services.localhost --mariadb-user-host-login-scope=% --db-root-password 123 --admin-password admin &&
  bench use da-services.localhost &&
  bench --site da-services.localhost install-app da_services &&
  bench --site da-services.localhost enable-scheduler &&
  bench --site da-services.localhost set-config mail_server mailpit &&
  bench --site da-services.localhost set-config mail_port 1025 &&
  bench --site da-services.localhost set-config use_ssl 0 &&
  bench --site da-services.localhost set-config allow_tests true &&
  bench build --app da_services'
```

`allow_tests` is dev-only; never set it on a shared or production site.

Dev-only credentials: MariaDB root `123`, site Administrator `admin`.

### 4.7 Run it

```bash
MSYS_NO_PATHCONV=1 docker exec -d -w /workspace/development/frappe-bench oan_da_services_dev-frappe-1 bench start
```

Open http://127.0.0.1:8200 and log in as `Administrator` / `admin`.

---

## 5. Daily workflow

```bash
# shell in the bench
MSYS_NO_PATHCONV=1 docker exec -it -w /workspace/development/frappe-bench oan_da_services_dev-frappe-1 bash

# inside the container
bench start                                            # web, socketio, watch, schedule, worker
bench --site da-services.localhost migrate             # after doctype JSON / patches.txt
bench --site da-services.localhost clear-cache         # after hooks.py / fixtures
bench --site da-services.localhost console             # frappe REPL
bench --site da-services.localhost mariadb             # SQL shell
bench run-tests --app da_services
bench build --app da_services                          # after public/ asset changes
```

Stop / start the stack from the host:

```bash
cd /c/Users/<you>/oan_da_services_devcontainer/.devcontainer
docker compose -p oan_da_services_dev stop
docker compose -p oan_da_services_dev start
```

The bench, virtualenv and site database persist in the `bench-data` and `mariadb-data`
volumes across restarts. `docker compose down -v` deletes them.

---

## 6. Troubleshooting

- **`Cwd must be an absolute path`** — you forgot `MSYS_NO_PATHCONV=1` in Git Bash.
- **`bench` command hangs for many minutes** — check the bench is on the named volume
  (`df -hT /workspace/development` should say `ext4`, not `9p`), and that `C:` has space.
- **`Bench instance already exists`** — `bench init` refuses a pre-existing directory;
  remove the empty `frappe-bench` folder in the volume and re-run. This happens if the
  repo was mounted straight into `apps/` (older compose); use the `docs/devcontainer`
  compose, which mounts it at `/workspace/da_services_repo` instead.
- **`ModuleNotFoundError: da_services` after recreating the container** — the
  `apps/da_services` symlink lives on the volume and survives, but re-run the `ln -sfn`
  from 4.6 if the volume was recreated.
- **Site loads but assets are missing** — `bench build` inside the container.
- **`da_services UNVERSIONED` in `list-apps`** — the repo has no commit on the current
  branch yet; harmless.
