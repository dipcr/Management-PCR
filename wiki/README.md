# D-IPCR Wiki

A tiny Flask wiki that serves the D-IPCR user manual. Pages are plain **Markdown files** on
disk; navigation, breadcrumbs and search are discovered automatically from the folder layout.

## Structure

```
wiki/
├── app.py                 # Flask app: renders Markdown, sidebar, search
├── requirements.txt
├── Dockerfile
├── docker-compose.yml      # standalone service, host port 5010
├── templates/              # base / page / search templates
├── static/
│   ├── css/wiki.css
│   └── img/                # screenshots, grouped by role
│       ├── 00-login.png
│       ├── admin/
│       ├── dean/
│       ├── prog-chair/
│       ├── ret-chair/
│       ├── designated-faculty/
│       ├── faculty/
│       └── getting-started/
└── pages/                  # the manual (Markdown)
    ├── index.md
    ├── getting-started/
    ├── admin/
    ├── dean/
    ├── prog-chair/
    ├── ret-chair/
    ├── designated-faculty/
    └── faculty/
```

## Running locally

```bash
pip install -r requirements.txt
python app.py            # http://127.0.0.1:5010
```

## Running with Docker

```bash
docker compose up -d --build      # http://<host>:5010
```

The compose file maps host **5010 → 5000** and mounts `pages/` and `static/img/`, so you can
edit the manual or drop in new screenshots **without rebuilding** the image.

## Adding a page

1. Create `pages/<section>/<NN>-<name>.md`.
2. Start it with a single `# Title` line — that becomes the sidebar label.
3. Reference screenshots with an absolute path, e.g.
   `![Caption](/static/img/faculty/02-my-ipcr.png)`.
4. Add `pages/<section>/_section.md` (starting with `# Section Title`) to control the sidebar
   heading for that section.

Pages are ordered by filename, so the `NN-` prefix controls the order.

## Adding screenshots

Screenshots are captured from the live app with Playwright and written straight into
`static/img/`. Capture the **login page**, then for each role log in, click through the
sidebar sections and screenshot each one (`page.screenshot({ path, fullPage: true })`).

## Pages' front matter

There is no front matter — the first `# ` heading is the page title, and the folder names form
the sidebar sections.

## Health

`GET /healthz` returns `{"status": "ok"}` and is used by the container healthcheck.
