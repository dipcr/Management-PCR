# D-IPCR — Digital IPCR System

A Flask + SQL based capstone project implementing the Philippines' **Strategic Performance Management System (SPMS) / Individual Performance Commitment and Review (IPCR)** for an academic college environment.

D-IPCR digitizes the faculty performance cycle; from target cascading through multi-role review, evidence submission, scoring, and printable IPCR.

## Contributors

<table>
  <tr>
    <td align="center">
      <a href="https://github.com/oks328">
        <img src="https://github.com/oks328.png" width="100px;" alt="oks328"/><br />
        <sub><b>oks328</b></sub>
      </a>
    </td>
    <td align="center">
      <a href="https://github.com/yaspartame">
        <img src="https://github.com/yaspartame.png" width="100px;" alt="yaspartame"/><br />
        <sub><b>yaspartame</b></sub>
      </a>
    </td>
    <td align="center">
      <a href="https://github.com/kyarin">
        <img src="https://github.com/kyarin.png" width="100px;" alt="kyarin"/><br />
        <sub><b>kyarin</b></sub>
      </a>
    </td>
    <td align="center">
      <a href="https://github.com/Eieindesu">
        <img src="https://github.com/Eieindesu.png" width="100px;" alt="Eieindesu"/><br />
        <sub><b>Eieindesu</b></sub>
      </a>
    </td>
  </tr>
</table>


---

## Table of Contents

- [What It Does](#what-it-does)
  - [Key Features](#key-features)
- [Installation](#installation)
  - [Method A: Docker](#method-a-docker)
  - [Building & Publishing Images (Developer)](#building--publishing-images-developer)
  - [Method B: Local Development](#method-b-local-development)
- [Environment Variables](#environment-variables)
- [Project Structure](#project-structure)
- [License](#license)

## What It Does

The system routes faculty performance targets through a multi-role cascade:

```
Admin → Dean → Program Chair / RET Chair → Faculty → Review → Lock → Evidence → Scoring → Print
```

### Key Features

- **Cascaded target allocation**- quotas flow down through the institutional hierarchy
- **Multi-stage review pipeline**- RET Chair (If faculty has Research related targets) → Program Chair → Dean approval with item-level feedback
- **IPCR locking**- approved drafts commit to final committed targets
- **Evidence uploads**- per-target PDF evidence with supervisor verification
- **SPMS scoring**- Q/E/T (Quantity/Efficiency/Timeliness) rolled into weighted categories with Final Weighted Rating + Adjectival Rating
- **Printable IPCR**- landscape form matching the official SPMS layout
- **Email notifications**- approval/evidence emails (optional, degrades to console logging when SMTP is unconfigured)
  
## Installation

### Method A: Docker

Requires Docker Engine + Docker Compose v2.

**Step 1 necessary directories and files**

```bash
mkdir dipcr && cd dipcr

# Get docker-compose.yml and .env-example from the repo
# (or download the release assets)
cp .env-example .env
```

**Step 2: `.env` and ```docker-compose.yml```**

Set at minimum these values for env:

```bash
nano .env
```

```env
DB_PASSWORD=user_pass
DB_ROOT_PASSWORD=root
SECRET_KEY=long_string
ADMIN_EMAIL=email@email.com
ADMIN_PASSWORD=YourAdminPassword1!   # 8+ chars, upper, lower, digit, special
```

> Leave `SMTP_HOST` empty to log emails to the console instead of sending.

Customising port for web acces:

```bash
nano docker-compose.yml
```

```yaml
  web:
    ports:
      - "5000:5000" # Change value the one on the left, left port is the external port for access. The one on the right is the internal port handled by docker. 
```

**Step 3: Starting**

```bash
docker compose up -d
```

The first start pulls the web + database images, applies the schema automatically, and creates the first admin account from env's `ADMIN_EMAIL`/`ADMIN_PASSWORD`.

**Step 4: Access**

Open `http://localhost:5000` (or `http://<server-ip>:<port>` if you changed the port) and log in with the admin credentials.

**Updating:**

```bash
docker compose pull
docker compose up -d
```

**Resetting everything (wipes all data (such as SQL)):**

```bash
docker compose down -v # -v flag for deleting every data
docker compose up -d
```

#### Building & Publishing Images (Developer)

Images are published to Docker Hub.
But any form of forks or modifying the codebase and building your own image:

```bash
# Build
docker build -t <your_username>/dipcr-web:latest .
docker build -t <your_username>/dipcr-db:latest ./db

# Push (requires a Docker Hub login)
docker login
docker push <your_username>/dipcr-web:latest
docker push <your_username>/dipcr-db:latest
```

> Note: the `db` image bakes in the schema (`db/schema.sql`) — rebuild & push it whenever the schema changes.

### Method B: Local Development

Requires Python 3.10+ and a reachable MySQL 8 instance.

**Step 1: Clone & install**

```bash
git clone https://github.com/dipcr/Management-PCR
cd Management-PCR
python -m venv venv

# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

pip install -r requirements.txt
```

**Step 2: Configure `.env`**

```bash
cp .env-example .env
```

Point `DB_HOST`/`DB_PORT`/`DB_NAME` at your MySQL instance and set `SECRET_KEY`.

**Step 3: Run**

```bash
python run.py
```

Open `http://127.0.0.1:5000`.

**Creating the first Admin (fresh database):**

Registration only *claims* an existing profile, so a brand-new database needs its first account created directly:

```bash
python bootstrap_admin.py
```

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DB_HOST` | ✅ | MySQL host — `db` (Docker) or server IP (local) |
| `DB_PORT` | ✅ | MySQL port — `3306` (Docker internal, do not change) |
| `DB_NAME` | ✅ | Database name |
| `DB_USER` | ✅ | MySQL application user |
| `DB_PASSWORD` | ✅ | MySQL application user password |
| `DB_ROOT_PASSWORD` | ✅ | MySQL root password (Docker only) |
| `SECRET_KEY` | ✅ | Flask session signing key |
| `FLASK_DEBUG` | — | Enable debug mode (`false` in production) |
| `ADMIN_EMAIL` | ✅* | First admin email (auto-bootstrap, only while no Admin exists) |
| `ADMIN_PASSWORD` | ✅* | First admin password (auto-bootstrap, only while no Admin exists) |
| `SMTP_HOST` | — | SMTP server — empty disables sending (emails logged) |
| `SMTP_PORT` | — | SMTP port (default `587`) |
| `SMTP_USER` / `SMTP_PASSWORD` | — | SMTP credentials |
| `SMTP_USE_TLS` / `SMTP_USE_SSL` | — | SMTP security mode |
| `MAIL_DEFAULT_SENDER` | — | From address for emails |
| `MAIL_SUPPRESS_SEND` | — | `true` to log emails instead of sending |
| `APP_BASE_URL` | — | Public URL used in email links |

> *Read on **every** `run.py` / `wsgi.py` startup, not just the first one — and in local
> development too, not only Docker. `app/setup.py:bootstrap_admin()` creates the first Admin only
> when both vars are set, the password passes the registration policy, and no Admin exists yet;
> otherwise it is a no-op. Setting them in a local `.env` can therefore create an Admin you never
> explicitly asked for. See [SETUP.md](SETUP.md) §2.3.

---

## Project Structure

```
app/
├── models/       # database access & business logic
├── routes/       # thin Flask blueprints (one per role)
├── services/     # email & notification services
└── templates/    # Jinja2 templates
db/
├── Dockerfile    # MySQL image with baked-in schema
└── schema.sql    # full schema + stored procedures
```

Key documentation:
- **`SETUP.md`** — full setup, schema, and configuration guide
- **`TEST_SCRIPT.md`** — manual QA checklist for all six roles

---

## License
This project is licensed under the **GNU General Public License v3.0 (GPL-3.0)**.

It is **not** intended for commercialization. The copyleft license guarantees that any
derivative or modified version must also remain open source under GPL-3.0, no one may
close-source this project or wall it off for proprietary use.

See the [LICENSE](LICENSE) file for the full text.


