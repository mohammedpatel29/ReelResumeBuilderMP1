"""Enhanced database connection handling with conservative settings"""
import logging
import sys
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_mail import Mail
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import event, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
import traceback

# Set up logging
logger = logging.getLogger(__name__)
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
))
logger.addHandler(handler)
logger.setLevel(logging.INFO)

class SafeSQLAlchemy(SQLAlchemy):
    """Enhanced SQLAlchemy class with better error handling and connection management"""

    def apply_pool_defaults(self, app):
        """Apply conservative pool defaults to app config"""
        app.config.setdefault('SQLALCHEMY_POOL_SIZE', 5)
        app.config.setdefault('SQLALCHEMY_MAX_OVERFLOW', 2)
        app.config.setdefault('SQLALCHEMY_POOL_TIMEOUT', 30)
        app.config.setdefault('SQLALCHEMY_POOL_RECYCLE', 300)

    def init_app(self, app):
        """Initialize the application with enhanced error handling"""
        try:
            # Apply pool defaults
            self.apply_pool_defaults(app)

            # Initialize SQLAlchemy
            super().init_app(app)

            logger.info("SQLAlchemy initialization completed")

        except Exception as e:
            logger.error(f"Database initialization failed: {str(e)}\n{traceback.format_exc()}")
            raise

    def check_connection(self, app):
        """Verify database connection and schema after initialization"""
        try:
            with app.app_context():
                # Verify database connection
                with self.engine.connect() as conn:
                    result = conn.execute(text('SELECT version();'))
                    version = result.scalar()
                    logger.info(f"Connected to PostgreSQL: {version}")

                    # Basic schema check
                    tables = conn.execute(text(
                        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
                    )).fetchall()
                    logger.info(f"Schema check complete. Found {len(tables)} tables")
                    return True
        except Exception as e:
            logger.error(f"Database connection check failed: {str(e)}\n{traceback.format_exc()}")
            return False

# Initialize extensions
db = SafeSQLAlchemy()

login_manager = LoginManager()
login_manager.session_protection = 'strong'
login_manager.login_view = 'auth.login'
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'info'
login_manager.refresh_view = 'auth.login'
login_manager.needs_refresh_message = 'Please reauthenticate to access this page.'
login_manager.needs_refresh_message_category = 'info'

csrf = CSRFProtect()
mail = Mail()

# Database connection event listeners
@event.listens_for(Engine, "connect")
def on_connect(dbapi_connection, connection_record):
    """Log new database connections"""
    try:
        logger.info(f"New database connection established: Connection ID: {id(dbapi_connection)}")
    except Exception as e:
        logger.error(f"Error logging connection: {str(e)}")

@event.listens_for(Engine, "checkout")
def on_checkout(dbapi_connection, connection_record, connection_proxy):
    """Verify connection is valid on checkout"""
    try:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("SELECT 1")
        except Exception:
            connection_record.invalidate()
            raise
        finally:
            cursor.close()
    except Exception as e:
        logger.error(f"Invalid connection detected during checkout: {str(e)}\n{traceback.format_exc()}")
        connection_record.invalidate()
        raise SQLAlchemyError(f"Invalid connection detected: {str(e)}") from e

@event.listens_for(Engine, "checkin")
def on_checkin(dbapi_connection, connection_record):
    """Log connection returns"""
    try:
        logger.debug(f"Connection returned (ID: {id(dbapi_connection)})")
    except Exception as e:
        logger.error(f"Error during connection checkin: {str(e)}")