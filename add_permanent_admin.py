from flask import Flask
from extensions import db
import logging
import os

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ['DATABASE_URL']
db.init_app(app)
from sqlalchemy import text
import logging

logger = logging.getLogger(__name__)

def add_permanent_admin_column():
    """Add permanent_admin column to user table"""
    try:
        with app.app_context():
            # Add the permanent_admin column if it doesn't exist
            with db.engine.connect() as conn:
                conn.execute(text("""
                    ALTER TABLE "user" 
                    ADD COLUMN IF NOT EXISTS permanent_admin BOOLEAN DEFAULT FALSE;
                """))
                
                # Set permanent_admin flag for reelresumeapp@gmail.com
                conn.execute(text("""
                    UPDATE "user" 
                    SET permanent_admin = TRUE, is_admin = TRUE 
                    WHERE email = 'reelresumeapp@gmail.com';
                """))
                conn.commit()
                
            logger.info("Successfully added permanent_admin column")
            return True
    except Exception as e:
        logger.error(f"Error adding permanent_admin column: {str(e)}")
        return False

if __name__ == "__main__":
    add_permanent_admin_column()
