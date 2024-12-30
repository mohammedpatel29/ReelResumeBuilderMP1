"""Add employer features migration

This migration adds new tables for enhanced employer features including:
- Job postings
- Candidate matching
- Company profiles
- Employer onboarding
"""

import os
import sys
import logging
from flask import Flask
from sqlalchemy import text

# Get the project root directory
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

from extensions import db

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def upgrade():
    """
    Executes the migrations.
    """
    try:
        # Create tables if they don't exist
        app = Flask(__name__)
        app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
        db.init_app(app)

        with app.app_context():
            # Create new tables
            tables_to_create = [
                """
                CREATE TABLE IF NOT EXISTS job_posting (
                    id SERIAL PRIMARY KEY,
                    employer_id INTEGER NOT NULL REFERENCES "user" (id) ON DELETE CASCADE,
                    title VARCHAR(100) NOT NULL,
                    description TEXT NOT NULL,
                    requirements TEXT,
                    responsibilities TEXT,
                    status VARCHAR(20) DEFAULT 'active',
                    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP WITHOUT TIME ZONE,
                    required_skills JSON DEFAULT '[]',
                    preferred_skills JSON DEFAULT '[]',
                    experience_level VARCHAR(20),
                    matching_score_threshold FLOAT DEFAULT 0.7,
                    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS candidate_match (
                    id SERIAL PRIMARY KEY,
                    job_posting_id INTEGER NOT NULL REFERENCES job_posting (id) ON DELETE CASCADE,
                    candidate_id INTEGER NOT NULL REFERENCES "user" (id) ON DELETE CASCADE,
                    match_score FLOAT NOT NULL,
                    skill_match_details JSON,
                    personality_match_score FLOAT,
                    cultural_fit_score FLOAT,
                    status VARCHAR(20) DEFAULT 'pending',
                    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(job_posting_id, candidate_id)
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS company_profile (
                    id SERIAL PRIMARY KEY,
                    employer_id INTEGER NOT NULL REFERENCES "user" (id) ON DELETE CASCADE,
                    logo_url VARCHAR(255),
                    cover_image_url VARCHAR(255),
                    culture_video_url VARCHAR(255),
                    mission_statement TEXT,
                    company_values JSON DEFAULT '[]',
                    benefits JSON DEFAULT '[]',
                    office_locations JSON DEFAULT '[]',
                    social_media_links JSON DEFAULT '{}',
                    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT unique_employer_profile UNIQUE (employer_id)
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS employer_onboarding (
                    id SERIAL PRIMARY KEY,
                    employer_id INTEGER NOT NULL REFERENCES "user" (id) ON DELETE CASCADE,
                    current_step VARCHAR(50) DEFAULT 'company_profile',
                    completed_steps JSON DEFAULT '[]',
                    preferences JSON DEFAULT '{}',
                    has_completed_tour BOOLEAN DEFAULT FALSE,
                    needs_support BOOLEAN DEFAULT FALSE,
                    support_requested_at TIMESTAMP WITHOUT TIME ZONE,
                    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT unique_employer_onboarding UNIQUE (employer_id)
                )
                """
            ]

            # Execute each table creation
            for table_sql in tables_to_create:
                db.session.execute(text(table_sql))

            # Create indexes for better query performance
            indexes_to_create = [
                "CREATE INDEX IF NOT EXISTS idx_job_posting_employer ON job_posting(employer_id)",
                "CREATE INDEX IF NOT EXISTS idx_job_posting_status ON job_posting(status)",
                "CREATE INDEX IF NOT EXISTS idx_job_posting_updated ON job_posting(updated_at DESC)",
                "CREATE INDEX IF NOT EXISTS idx_candidate_match_job ON candidate_match(job_posting_id)",
                "CREATE INDEX IF NOT EXISTS idx_candidate_match_candidate ON candidate_match(candidate_id)",
                "CREATE INDEX IF NOT EXISTS idx_candidate_match_score ON candidate_match(match_score DESC)",
                "CREATE INDEX IF NOT EXISTS idx_candidate_match_updated ON candidate_match(updated_at DESC)",
                "CREATE INDEX IF NOT EXISTS idx_company_profile_employer ON company_profile(employer_id)",
                "CREATE INDEX IF NOT EXISTS idx_employer_onboarding_employer ON employer_onboarding(employer_id)"
            ]

            # Execute each index creation
            for index_sql in indexes_to_create:
                db.session.execute(text(index_sql))

            # Commit all changes
            db.session.commit()
            logger.info("Successfully created employer feature tables and indexes")

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error during migration: {str(e)}")
        raise

def downgrade():
    """
    Reverts the migrations.
    """
    try:
        app = Flask(__name__)
        app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
        db.init_app(app)

        with app.app_context():
            # Drop tables in reverse order of dependencies
            tables_to_drop = [
                "employer_onboarding",
                "company_profile",
                "candidate_match",
                "job_posting"
            ]

            for table in tables_to_drop:
                db.session.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE"))

            db.session.commit()
            logger.info("Successfully reverted employer feature tables")

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error during migration rollback: {str(e)}")
        raise

if __name__ == "__main__":
    upgrade()