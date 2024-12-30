import os
import sys
import logging
from flask import Flask
from sqlalchemy import create_engine, text

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get the project root directory
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

from extensions import db

# Initialize Flask app
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ['DATABASE_URL']
db.init_app(app)

def migrate_playlist_tags():
    """Add tag-related tables and enhance playlist functionality"""
    with app.app_context():
        try:
            # Create tag table
            db.session.execute(text('''
                CREATE TABLE IF NOT EXISTS tag (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(50) NOT NULL,
                    type VARCHAR(20) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_tag_name ON tag(name);
                CREATE INDEX IF NOT EXISTS idx_tag_type ON tag(type);
            '''))

            # Create video_tag table
            db.session.execute(text('''
                CREATE TABLE IF NOT EXISTS video_tag (
                    id SERIAL PRIMARY KEY,
                    video_id INTEGER REFERENCES video(id) ON DELETE CASCADE,
                    tag_id INTEGER REFERENCES tag(id) ON DELETE CASCADE,
                    ai_suggested BOOLEAN DEFAULT FALSE,
                    confidence_score FLOAT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(video_id, tag_id)
                );
                CREATE INDEX IF NOT EXISTS idx_video_tag_video ON video_tag(video_id);
                CREATE INDEX IF NOT EXISTS idx_video_tag_tag ON video_tag(tag_id);
            '''))

            # Create playlist_tag table
            db.session.execute(text('''
                CREATE TABLE IF NOT EXISTS playlist_tag (
                    id SERIAL PRIMARY KEY,
                    playlist_id INTEGER REFERENCES playlist(id) ON DELETE CASCADE,
                    tag_id INTEGER REFERENCES tag(id) ON DELETE CASCADE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(playlist_id, tag_id)
                );
                CREATE INDEX IF NOT EXISTS idx_playlist_tag_playlist ON playlist_tag(playlist_id);
                CREATE INDEX IF NOT EXISTS idx_playlist_tag_tag ON playlist_tag(tag_id);
            '''))

            # Add new columns to playlist table
            db.session.execute(text('''
                ALTER TABLE playlist 
                ADD COLUMN IF NOT EXISTS is_public BOOLEAN DEFAULT FALSE,
                ADD COLUMN IF NOT EXISTS thumbnail VARCHAR(255),
                ADD COLUMN IF NOT EXISTS view_count INTEGER DEFAULT 0,
                ADD COLUMN IF NOT EXISTS share_token VARCHAR(64) UNIQUE,
                ADD COLUMN IF NOT EXISTS last_modified TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
            '''))

            db.session.commit()
            logger.info("Successfully created tag-related tables and enhanced playlist table")
            return True

        except Exception as e:
            logger.error(f"Error during migration: {str(e)}")
            db.session.rollback()
            return False

if __name__ == "__main__":
    migrate_playlist_tags()