"""
D-IPCR Wiki — a tiny Flask wiki that renders the Markdown user manual in `pages/`.

Public, no authentication. Pages live at `pages/<section>/<page>.md` and navigation is
discovered from the directory layout, so dropping in a Markdown file is all it takes to
add a page. Screenshots live under `static/img/`.

Local:     python app.py                     -> http://127.0.0.1:5010
Container: gunicorn --bind 0.0.0.0:5000 app:app
"""
import os
import re

import markdown
from flask import Flask, abort, render_template, request, url_for

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PAGES_DIR = os.path.join(BASE_DIR, 'pages')

app = Flask(__name__)

MD_EXTENSIONS = ['fenced_code', 'tables', 'toc', 'attr_list', 'sane_lists', 'md_in_html']


def _md():
    return markdown.Markdown(
        extensions=MD_EXTENSIONS,
        extension_configs={'toc': {'permalink': False, 'toc_depth': '2-3', 'toc_class': 'md-toc'}},
    )


def _title_from_md(text, fallback):
    for line in text.splitlines():
        if line.startswith('# '):
            return line[2:].strip()
    return fallback


def _humanize(name):
    """'01-overview.md' -> 'Overview'; 'prog-chair' -> 'Prog Chair'."""
    name = re.sub(r'\.md$', '', name)
    name = re.sub(r'^\d+[-_]', '', name)
    return name.replace('-', ' ').replace('_', ' ').strip().title()


def _section_title(dirname):
    meta = os.path.join(PAGES_DIR, dirname, '_section.md')
    if os.path.exists(meta):
        with open(meta, encoding='utf-8') as f:
            return _title_from_md(f.read(), _humanize(dirname))
    return _humanize(dirname)


def build_nav():
    """Ordered sections discovered from pages/<section>/<page>.md."""
    sections = []
    if not os.path.isdir(PAGES_DIR):
        return sections
    for dirname in sorted(os.listdir(PAGES_DIR)):
        section_path = os.path.join(PAGES_DIR, dirname)
        if not os.path.isdir(section_path) or dirname.startswith('.'):
            continue
        pages = []
        for fn in sorted(os.listdir(section_path)):
            if not fn.endswith('.md') or fn.startswith('_'):
                continue
            with open(os.path.join(section_path, fn), encoding='utf-8') as f:
                title = _title_from_md(f.read(), _humanize(fn))
            pages.append({'slug': f'{dirname}/{fn[:-3]}', 'title': title})
        if pages:
            sections.append({'slug': dirname, 'title': _section_title(dirname), 'pages': pages})
    return sections


def read_page(slug):
    """Return (path, markdown_text) for a validated slug, else (None, None)."""
    if not slug or '..' in slug or slug.startswith('/'):
        return None, None
    path = os.path.join(PAGES_DIR, *slug.split('/')) + '.md'
    real = os.path.realpath(path)
    if not real.startswith(os.path.realpath(PAGES_DIR) + os.sep) or not os.path.exists(real):
        return None, None
    with open(real, encoding='utf-8') as f:
        return real, f.read()


def _page_slug(slug):
    """Slug of the page that should be highlighted in the sidebar for `slug`."""
    if slug in ('index', None):
        return None
    return slug


@app.context_processor
def inject_globals():
    return {
        'nav_sections': build_nav(),
        'site_name': 'D-IPCR Wiki',
    }


@app.route('/')
def home():
    _, text = read_page('index')
    body = _md().convert(text) if text else '<p>Welcome to the D-IPCR wiki.</p>'
    return render_template('page.html', title='Home', body=body, toc='', current=None)


@app.route('/p/<path:slug>')
def page(slug):
    path, text = read_page(slug)
    if not path:
        abort(404)
    md = _md()
    body = md.convert(text)
    title = _title_from_md(text, _humanize(slug.split('/')[-1]))
    return render_template('page.html', title=title, body=body,
                           toc=getattr(md, 'toc', ''), current=slug)


@app.route('/search')
def search():
    q = (request.args.get('q') or '').strip()
    results = []
    if q:
        needle = q.lower()
        for section in build_nav():
            for p in section['pages']:
                _, text = read_page(p['slug'])
                if not text:
                    continue
                low = text.lower()
                idx = low.find(needle)
                if idx == -1:
                    continue
                start = max(0, idx - 80)
                snippet = re.sub(r'\s+', ' ', text[start:idx + len(needle) + 140]).strip()
                results.append({
                    'slug': p['slug'],
                    'title': p['title'],
                    'section': section['title'],
                    'snippet': snippet,
                })
    return render_template('search.html', title='Search', q=q, results=results, current=None, toc='')


@app.route('/healthz')
def healthz():
    return {'status': 'ok'}, 200


@app.errorhandler(404)
def not_found(_):
    return render_template('page.html', title='Not found',
                           body='<h1>Page not found</h1><p>That page does not exist. '
                                'Use the sidebar or search to find your way.</p>',
                           toc='', current=None), 404


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5010, debug=True)
