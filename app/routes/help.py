from flask import Blueprint, render_template, session, redirect, url_for, abort

from app.help_content import help_for_role

help_bp = Blueprint('help', __name__, url_prefix='/help')


@help_bp.route('/')
def manual():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    content = help_for_role(session.get('role'))
    if not content:
        abort(404)
    return render_template('help_manual.html', manual=content,
                           home_url=url_for(content['home_endpoint']))
