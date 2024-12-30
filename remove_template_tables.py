import os
import sys
import logging
from sqlalchemy import text
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create a minimal Flask application
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

def remove_template_tables():
    try:
        with app.app_context():
            # Drop template-related tables
            commands = [
                '''ALTER TABLE video DROP COLUMN IF EXISTS template_id''',
                '''DROP TABLE IF EXISTS template_purchase CASCADE''',
                '''DROP TABLE IF EXISTS video_template CASCADE'''
            ]

            for command in commands:
                try:
                    db.session.execute(text(command))
                    logger.info(f"Successfully executed: {command}")
                except Exception as e:
                    logger.error(f"Error executing {command}: {str(e)}")
                    db.session.rollback()
                    raise

            db.session.commit()
            logger.info("Successfully removed template tables and references")
            return True

    except Exception as e:
        logger.error(f"Error removing template tables: {str(e)}")
        db.session.rollback()
        return False

if __name__ == "__main__":
    remove_template_tables()