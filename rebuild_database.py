"""Database rebuild script with enhanced error handling and logging"""
from app import create_app
from extensions import db
from sqlalchemy import text
from models import Achievement
import logging
from datetime import datetime

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def create_initial_achievements():
    """Create the initial set of achievements"""
    try:
        logger.info("Creating initial achievements...")
        achievements = [
            {
                'name': 'Getting Started',
                'description': 'Created your first video resume',
                'badge_icon': 'bi-camera-video',
                'requirement_type': 'video_count',
                'requirement_value': 1
            },
            {
                'name': 'Video Pro',
                'description': 'Created 5 video resumes',
                'badge_icon': 'bi-camera-video-fill',
                'requirement_type': 'video_count',
                'requirement_value': 5
            },
            {
                'name': 'Profile Master',
                'description': 'Completed your profile with all information',
                'badge_icon': 'bi-person-check-fill',
                'requirement_type': 'profile_complete',
                'requirement_value': 1
            },
            {
                'name': 'Rising Star',
                'description': 'Reached 100 video views',
                'badge_icon': 'bi-star-fill',
                'requirement_type': 'views_reached',
                'requirement_value': 100
            }
        ]

        for achievement_data in achievements:
            # Check if achievement already exists
            existing = Achievement.query.filter_by(
                name=achievement_data['name']
            ).first()
            if not existing:
                achievement = Achievement(**achievement_data)
                db.session.add(achievement)
                logger.info(f"Added achievement: {achievement_data['name']}")

        db.session.commit()
        logger.info("Initial achievements created successfully")

    except Exception as e:
        logger.error(f"Error creating initial achievements: {str(e)}")
        db.session.rollback()
        raise

def rebuild_database():
    """Rebuild the database schema with proper error handling and logging"""
    try:
        app = create_app()
        with app.app_context():
            logger.info("Starting database rebuild process...")

            # Close any existing connections
            try:
                db.session.remove()
                db.engine.dispose()
                logger.info("Cleaned up existing database connections")
            except Exception as e:
                logger.warning(f"Error cleaning up connections: {str(e)}")

            # Create tables in correct order
            logger.info("Creating tables with new schema...")
            db.create_all()

            # Add indexes for core tables
            logger.info("Adding performance indexes for user table...")
            db.session.execute(text('''
                CREATE INDEX IF NOT EXISTS idx_user_email ON "user" (email);
                CREATE INDEX IF NOT EXISTS idx_user_type ON "user" (user_type);
                CREATE INDEX IF NOT EXISTS idx_user_last_login ON "user" (last_login);
                CREATE INDEX IF NOT EXISTS idx_user_last_active ON "user" (last_active);
                CREATE INDEX IF NOT EXISTS idx_user_created_at ON "user" (created_at);
                CREATE INDEX IF NOT EXISTS idx_user_is_deleted ON "user" (is_deleted);
            '''))

            logger.info("Adding performance indexes for video table...")
            db.session.execute(text('''
                CREATE INDEX IF NOT EXISTS idx_video_user ON video (user_id);
                CREATE INDEX IF NOT EXISTS idx_video_created ON video (created_at);
                CREATE INDEX IF NOT EXISTS idx_video_views ON video (views);
                CREATE INDEX IF NOT EXISTS idx_video_likes ON video (likes);
            '''))

            logger.info("Adding performance indexes for video script tables...")
            db.session.execute(text('''
                CREATE INDEX IF NOT EXISTS idx_video_script_user ON video_script (user_id);
                CREATE INDEX IF NOT EXISTS idx_script_section_script ON script_section (script_id);
                CREATE INDEX IF NOT EXISTS idx_resume_analysis_user ON resume_analysis (user_id);
            '''))

            logger.info("Adding performance indexes for interaction tables...")
            db.session.execute(text('''
                CREATE INDEX IF NOT EXISTS idx_message_sender ON message (sender_id);
                CREATE INDEX IF NOT EXISTS idx_message_receiver ON message (receiver_id);
                CREATE INDEX IF NOT EXISTS idx_message_created ON message (created_at);
                CREATE INDEX IF NOT EXISTS idx_message_read ON message (read);
                CREATE INDEX IF NOT EXISTS idx_bookmark_employer ON bookmark_candidate (employer_id);
                CREATE INDEX IF NOT EXISTS idx_bookmark_jobseeker ON bookmark_candidate (jobseeker_id);
            '''))

            # Create initial achievements
            create_initial_achievements()

            # Commit all changes
            db.session.commit()
            logger.info("Database rebuild completed successfully!")
            return True

    except Exception as e:
        logger.error(f"Error rebuilding database: {str(e)}")
        if 'db' in locals():
            db.session.rollback()
        return False
    finally:
        if 'db' in locals() and hasattr(db, 'engine'):
            db.engine.dispose()

if __name__ == "__main__":
    rebuild_database()