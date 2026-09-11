from flask import Flask, g, request
import os
import time
import logging
from dotenv import load_dotenv

# Ensure openpyxl is installed
try:
    import openpyxl
except ImportError:
    import subprocess
    import sys
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "openpyxl"])
    except Exception as e:
        logging.error(f"Failed to auto-install openpyxl: {str(e)}")

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Set a secret key for secure sessions (login cookies)
app.secret_key = os.getenv('SECRET_KEY', 'dipcr_version_13_secret_key')

# Configure upload settings
app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'uploads', 'evidence')
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10MB limit

# Configure Flask-Mail
from flask_mail import Mail
app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER') or os.getenv('SMTP_HOST') or ''
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT') or os.getenv('SMTP_PORT') or 587)
app.config['MAIL_USE_TLS'] = (os.getenv('MAIL_USE_TLS') or os.getenv('SMTP_USE_TLS') or 'true').lower() in ('1', 'true', 'yes')
app.config['MAIL_USE_SSL'] = (os.getenv('MAIL_USE_SSL') or os.getenv('SMTP_USE_SSL') or 'false').lower() in ('1', 'true', 'yes')
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME') or os.getenv('SMTP_USER') or ''
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD') or os.getenv('SMTP_PASSWORD') or ''
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_DEFAULT_SENDER', 'D-IPCR System <no-reply@cict.edu.ph>')
app.config['MAIL_SUPPRESS_SEND'] = (os.getenv('MAIL_SUPPRESS_SEND') or 'false').lower() in ('1', 'true', 'yes')
# Flask-Mail defaults this to app.debug, which dumps the raw SMTP protocol exchange
# (every "send:"/"data:" line) to the terminal whenever FLASK_DEBUG is on.
app.config['MAIL_DEBUG'] = False

mail = Mail(app)

# Initialize DB connection pool at startup
from app.models.connection import init_db_pool
init_db_pool()

# Request timing middleware
@app.before_request
def start_timer():
    g.start_time = time.time()


@app.after_request
def log_request_time(response):
    if hasattr(g, 'start_time'):
        elapsed = time.time() - g.start_time
        if elapsed > 1.0:
            logger.warning(f"SLOW REQUEST: {request.method} {request.path} — took {elapsed:.2f}s")
        else:
            logger.info(f"REQUEST: {request.method} {request.path} — {elapsed:.2f}s")
    return response


@app.teardown_request
def close_db_connection(exc):
    """Safety net: return any pooled DB connection on EVERY request, even on errors.

    Prevents 'Too many connections' / pool exhaustion if a route raises before its
    manual conn.close() runs. get_db_connection() registers the connection on `g`,
    so this returns it to the pool no matter what happened in the route.
    """
    conn = getattr(g, '_db_conn', None)
    if conn is not None:
        try:
            cnx = getattr(conn, '_cnx', None)
            if cnx is not None and cnx.is_connected():
                conn.close()
        except Exception:
            logger.exception("Failed to close DB connection during teardown")

# Register route blueprints
from app.routes import register_blueprints
register_blueprints(app)


@app.template_filter('ipcr_preview')
def ipcr_preview_filter(indicator_description):
    """
    Renders a placeholder-tagged master indicator ({qty:1}, {duration:6:months}, ...) using
    its tokens' embedded default values, so the Admin's indicator list shows a normal-looking
    sentence instead of raw brace syntax. Display only — see ipcr_description.py.
    """
    from app.models.ipcr_description import render_indicator_preview
    return render_indicator_preview(indicator_description)


@app.template_filter('ipcr_generate')
def ipcr_generate_filter(indicator_description, quantity, duration_value=None, duration_unit=None):
    """
    Substitutes the *real* quantity/duration into a master indicator's description — for a
    template rendering a menu/pool row where a genuine assigned/configured value is already
    known (e.g. a rank's configured RET quantity, or a faculty member's own actual selection),
    as opposed to `ipcr_preview`'s cosmetic use of a placeholder's own embedded example value.
    """
    from app.models.ipcr_description import format_ipcr_target_description
    return format_ipcr_target_description(indicator_description, quantity, duration_value, duration_unit)


@app.context_processor
def inject_own_ipcr_flag():
    # Exposes has_own_ipcr and home_nav to every template
    from flask import session, has_request_context
    from app.models.criteria import is_designated
    from app.navigation import home_nav_for
    if not has_request_context():
        return {'has_own_ipcr': False, 'home_nav': None}
    return {
        'has_own_ipcr': is_designated(session.get('designation')),
        'home_nav': home_nav_for(session.get('role')),
    }


@app.route('/evidence_uploads/<int:evidence_id>')
def serve_evidence(evidence_id):
    from flask import session, redirect, url_for, send_from_directory, abort
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    from app.models.connection import get_db_connection
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT er.file_path, ct.emp_id
            FROM tbl_evidence_repo er
            JOIN tbl_committed_targets ct ON er.target_id = ct.target_id
            WHERE er.evidence_id = %s
        """, (evidence_id,))
        row = cursor.fetchone()
    finally:
        cursor.close()
        conn.close()
    if not row:
        abort(404)
    file_path, owner_emp_id = row
    current_user_id = session['user_id']
    current_role = session.get('role')
    if current_role == 'FACULTY' and current_user_id != owner_emp_id:
        abort(403)
    import os
    return send_from_directory(app.config['UPLOAD_FOLDER'], os.path.basename(file_path))


@app.route('/healthz')
def healthz():
    """
    Reports "healthy" only when the app can actually reach the database, so a broken
    DB connection marks the container unhealthy rather than letting it serve
    error pages.
    """
    from app.models.connection import get_db_connection
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT 1")
            cursor.fetchall()
        finally:
            cursor.close()
        return {"status": "ok"}, 200
    except Exception:
        return {"status": "unavailable"}, 503
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


@app.after_request
def add_header(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '-1'
    return response