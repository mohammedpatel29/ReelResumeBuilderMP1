
from flask import Flask
from extensions import db
from sqlalchemy import text
import logging
import os

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ['DATABASE_URL']
db.init_app(app)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def add_title_column():
    try:
        with app.app_context():
            db.session.execute(text('''
                ALTER TABLE "user" 
                ADD COLUMN IF NOT EXISTS title VARCHAR(100);
            '''))
            db.session.commit()
            logger.info("Successfully added title column to user table")
            return True
    except Exception as e:
        logger.error(f"Error adding title column: {str(e)}")
        db.session.rollback()
        return False

if __name__ == "__main__":
    add_title_column()
