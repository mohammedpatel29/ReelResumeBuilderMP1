"""Session management utilities for Flask application"""
import os
import json
import logging
from datetime import datetime, timedelta
from typing import Optional
from functools import wraps
import traceback

logger = logging.getLogger(__name__)

class SessionManager:
    """Handles session storage and request tracking"""

    def __init__(self, session_dir: str = '/tmp/flask_session') -> None:
        self.session_dir = session_dir
        self._ensure_session_directory()
        self._request_id: Optional[str] = None
        self._setup_logging()

    def _setup_logging(self) -> None:
        """Configure logging with proper formatting"""
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - [%(levelname)s] - %(message)s'
        )
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)

        # Remove existing handlers to avoid duplicates
        logger.handlers.clear()
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

    def _ensure_session_directory(self) -> None:
        """Ensure session directory exists with proper permissions"""
        try:
            if not os.path.exists(self.session_dir):
                os.makedirs(self.session_dir, mode=0o700)
                logger.info(f"Created session directory: {self.session_dir}")

            # Verify directory permissions and writability
            test_file = os.path.join(self.session_dir, 'test_write')
            try:
                with open(test_file, 'w') as f:
                    f.write('test')
                os.remove(test_file)
                logger.info(f"Session directory {self.session_dir} is ready")
            except (IOError, OSError) as e:
                logger.error(f"Session directory write test failed: {str(e)}")
                raise
        except Exception as e:
            logger.critical(f"Failed to setup session directory: {str(e)}\n{traceback.format_exc()}")
            raise

    def get_request_id(self) -> str:
        """Get or generate request ID for the current request"""
        if not self._request_id:
            self._request_id = os.urandom(16).hex()
        return self._request_id

    def clear_session(self) -> None:
        """Safely clear the session data"""
        try:
            session.clear()
            logger.info(f"[Request: {self.get_request_id()}] Session cleared successfully")
        except Exception as e:
            logger.error(f"[Request: {self.get_request_id()}] Error clearing session: {str(e)}\n{traceback.format_exc()}")


# Create global session manager instance
session_manager = SessionManager()