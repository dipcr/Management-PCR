from .auth import auth_bp
from .admin import admin_bp
from .faculty import faculty_bp
from .dean import dean_bp
from .prog_chair import prog_chair_bp
from .ret_chair import ret_chair_bp
from .designated import designated_bp
from .help import help_bp


def register_blueprints(app):
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(faculty_bp)
    app.register_blueprint(dean_bp)
    app.register_blueprint(prog_chair_bp)
    app.register_blueprint(ret_chair_bp)
    app.register_blueprint(designated_bp)
    app.register_blueprint(help_bp)
