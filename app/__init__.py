import logging
import secrets

from dotenv import load_dotenv
from flask import Flask, abort, request, session
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from .config import Config
from .extensions import db, limiter, migrate
from .models import Season, Team
from .routes import auth, main


def create_app(config_class=Config):
    load_dotenv()

    log_level = getattr(logging, config_class.LOG_LEVEL, logging.INFO)
    formatter = logging.Formatter(
        "[%(asctime)s +0000] [%(process)d] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    root_logger = logging.getLogger()
    if not root_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)
    root_logger.setLevel(log_level)

    app = Flask(__name__)
    app.config.from_object(config_class)

    if not app.config.get("SECRET_KEY"):
        if app.debug or app.testing:
            app.logger.warning("SECRET_KEY is not set; running in insecure development mode.")
        else:
            raise RuntimeError("SECRET_KEY must be set in production.")

    db.init_app(app)
    migrate.init_app(app, db)
    limiter.init_app(app)

    app.register_blueprint(main.bp)
    app.register_blueprint(auth.bp)

    def generate_csrf_token():
        token = session.get("_csrf_token")
        if not token:
            token = secrets.token_urlsafe(32)
            session["_csrf_token"] = token
        return token

    @app.context_processor
    def inject_csrf_token():
        return {"csrf_token": generate_csrf_token()}

    @app.context_processor
    def inject_platform_links():
        auth_base_url = app.config.get("AUTH_BASE_URL", "http://localhost:8085").rstrip("/")
        return {
            "auth_base_url": auth_base_url,
            "auth_dashboard_url": f"{auth_base_url}/",
        }

    @app.before_request
    def csrf_protect():
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            token = session.get("_csrf_token")
            if request.is_json:
                payload = request.get_json(silent=True) or {}
                request_token = request.headers.get("X-CSRFToken") or payload.get("csrf_token")
            else:
                request_token = request.form.get("csrf_token")
            if not token or not request_token or token != request_token:
                abort(400)

    def seed_defaults():
        changed = False

        season = Season.query.filter_by(label="2026").first()
        if not season:
            db.session.add(Season(label="2026", year=2026, active=True))
            changed = True

        if changed:
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                app.logger.info("Default analytics seed raced with another worker; continuing.")

    def apply_schema_shims():
        inspector = inspect(db.engine)
        tables = set(inspector.get_table_names())

        if "game" in tables:
            columns = {column["name"] for column in inspector.get_columns("game")}
            if "analysis_mode" in columns:
                # Keep legacy column in place but stop depending on it in the app.
                pass

    with app.app_context():
        if app.config.get("AUTO_CREATE_DB"):
            db.create_all()
            apply_schema_shims()
            seed_defaults()

    return app
