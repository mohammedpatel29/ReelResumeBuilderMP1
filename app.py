"""Flask application with enhanced session, CSRF token handling, and route management"""
import os
import logging
import sys
from datetime import timedelta
from flask import Flask, render_template, request, g, session, jsonify
from flask_cors import CORS
from flask_login import current_user
from flask_wtf.csrf import CSRFError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import text
import traceback

from extensions import db, login_manager, csrf, mail
from flask_migrate import Migrate
from models import User
from blueprints import register_blueprints

# Set up logging
if not os.path.exists('logs'):
    os.makedirs('logs')

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('logs/app.log', mode='a')
    ]
)
logger = logging.getLogger(__name__)

def create_app():
    """Application factory with enhanced session management and route conflict detection"""
    try:
        logger.info("Starting application creation process...")
        app = Flask(__name__)

        # Load configuration
        logger.info("Loading configuration...")
        database_url = os.environ.get('DATABASE_URL')
        if not database_url:
            logger.critical("DATABASE_URL environment variable not set")
            raise ValueError("DATABASE_URL must be set")

        secret_key = os.environ.get('SECRET_KEY')
        if not secret_key:
            secret_key = os.urandom(32)
            logger.warning("SECRET_KEY not set, using random value")

        is_production = os.environ.get('FLASK_ENV') == 'production'

        # Configure application with enhanced security settings
        app.config.update(
            SECRET_KEY=secret_key,
            SQLALCHEMY_DATABASE_URI=database_url,
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
            SQLALCHEMY_POOL_SIZE=5,
            SQLALCHEMY_POOL_TIMEOUT=30,
            SQLALCHEMY_POOL_RECYCLE=300,
            SQLALCHEMY_MAX_OVERFLOW=2,
            SQLALCHEMY_ENGINE_OPTIONS={
                'pool_pre_ping': True,
                'echo': True,
                'connect_args': {
                    'connect_timeout': 10,
                    'application_name': 'ReelResume'
                }
            },
            SESSION_TYPE='filesystem',
            SESSION_FILE_DIR='/tmp/flask_session',
            SESSION_FILE_THRESHOLD=500,
            PERMANENT_SESSION_LIFETIME=timedelta(days=1),
            SESSION_COOKIE_SECURE=is_production,
            SESSION_COOKIE_HTTPONLY=True,
            SESSION_COOKIE_SAMESITE='Lax',
            WTF_CSRF_ENABLED=True,
            WTF_CSRF_TIME_LIMIT=3600,
            WTF_CSRF_SSL_STRICT=is_production,
            WTF_CSRF_METHODS=['POST', 'PUT', 'PATCH', 'DELETE']
        )

        # Initialize extensions in correct order
        logger.info("Initializing extensions...")
        with app.app_context():
            # Initialize SQLAlchemy with retry logic
            max_retries = 3
            retry_count = 0
            while retry_count < max_retries:
                try:
                    db.init_app(app)
                    csrf.init_app(app)
                    login_manager.init_app(app)
                    mail.init_app(app)
                    Migrate(app, db)

                    # Verify database connection
                    if not db.check_connection(app):
                        raise Exception("Database connection check failed")

                    logger.info("Extensions initialized successfully")
                    break
                except Exception as e:
                    retry_count += 1
                    logger.error(f"Failed to initialize extensions (attempt {retry_count}/{max_retries}): {str(e)}")
                    if retry_count == max_retries:
                        raise
                    import time
                    time.sleep(2 ** retry_count)  # Exponential backoff

            # Set up user loader with error handling
            @login_manager.user_loader
            def load_user(user_id):
                if not user_id:
                    return None
                try:
                    return User.query.get(int(user_id))
                except Exception as e:
                    logger.error(f"Error loading user {user_id}: {str(e)}")
                    return None

            # Register blueprints with error handling
            logger.info("Registering blueprints...")
            register_blueprints(app)

            # Enhanced error handlers
            @app.errorhandler(404)
            def not_found_error(error):
                logger.warning(f"404 error: {request.url}")
                if request.is_json:
                    return jsonify(error="Not Found"), 404
                return render_template('errors/404.html'), 404

            @app.errorhandler(500)
            def internal_error(error):
                db.session.rollback()
                logger.error(f"Internal Server Error: {str(error)}\n{traceback.format_exc()}")
                if request.is_json:
                    return jsonify(error="Internal Server Error"), 500
                return render_template('errors/500.html'), 500

            @app.errorhandler(SQLAlchemyError)
            def handle_db_error(error):
                db.session.rollback()
                logger.error(f"Database Error: {str(error)}\n{traceback.format_exc()}")
                if request.is_json:
                    return jsonify(error="Database Error"), 500
                return render_template('errors/500.html'), 500

            @app.errorhandler(CSRFError)
            def handle_csrf_error(error):
                logger.error(f"CSRF Error: {str(error)}")
                if request.is_json:
                    return jsonify(error="Invalid CSRF token"), 400
                return render_template('errors/400.html', error_message="Invalid or expired CSRF token. Please refresh and try again."), 400

            @app.before_request
            def before_request():
                # Ensure session is permanent for authenticated users
                if current_user.is_authenticated and request.endpoint and 'static' not in request.endpoint:
                    session.permanent = True

                # Add request tracking
                g.request_id = os.urandom(16).hex()
                logger.info(f"Processing request: {request.method} {request.path} [Request ID: {g.request_id}]")

            @app.after_request
            def after_request(response):
                # Log response status
                logger.info(f"Request completed: {response.status_code} [Request ID: {g.request_id}]")
                return response

            logger.info("Application setup completed successfully")
            return app

    except Exception as e:
        logger.critical(f"Application creation failed: {str(e)}", exc_info=True)
        raise

if __name__ == '__main__':
    try:
        app = create_app()
        logger.info("Starting Flask server...")
        app.run(host='0.0.0.0', port=5000, debug=True)
    except Exception as e:
        logger.critical(f"Failed to start application: {str(e)}")
        raise