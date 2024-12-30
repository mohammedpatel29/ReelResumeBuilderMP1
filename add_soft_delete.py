import os
import sys
import logging
from sqlalchemy import text

# Add parent directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from extensions import db
from app import app

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def add_soft_delete_column():
    try:
        with app.app_context():
            # Add columns one at a time with proper error handling
            commands = [
                # Add is_deleted column
                '''ALTER TABLE "user" ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN DEFAULT FALSE''',
                # Add deleted_at column
                '''ALTER TABLE "user" ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP''',
                # Add indexes
                '''CREATE INDEX IF NOT EXISTS idx_user_is_deleted ON "user" (is_deleted)''',
                '''CREATE INDEX IF NOT EXISTS idx_user_deleted_at ON "user" (deleted_at)'''
            ]
            
            for command in commands:
                try:
                    db.session.execute(text(command))
                    logger.info(f"Successfully executed: {command}")
                except Exception as e:
                    logger.error(f"Error executing {command}: {str(e)}")
                    db.session.rollback()
                    raise
            
            # Verify columns were added
            result = db.session.execute(text('''
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = 'user' 
                AND column_name IN ('is_deleted', 'deleted_at');
            '''))
            
            columns = result.fetchall()
            column_names = [col[0] for col in columns]
            
            if 'is_deleted' in column_names and 'deleted_at' in column_names:
                logger.info("Successfully verified both soft delete columns")
                db.session.commit()
                return True
            else:
                missing = []
                if 'is_deleted' not in column_names:
                    missing.append('is_deleted')
                if 'deleted_at' not in column_names:
                    missing.append('deleted_at')
                logger.error(f"Column verification failed. Missing columns: {', '.join(missing)}")
                db.session.rollback()
                return False
                
    except Exception as e:
        logger.error(f"Error adding soft delete columns: {str(e)}")
        db.session.rollback()
        return False

if __name__ == "__main__":
    add_soft_delete_column()
