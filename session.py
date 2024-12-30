from functools import wraps
from flask import session, redirect, url_for, flash, request
from datetime import datetime, timedelta
from models import User
from extensions import db
import logging

logger = logging.getLogger(__name__)

def validate_session():
    """Simplified session validation middleware"""
    if not session.get('user_id'):
        return None
        
    try:
        user = User.query.get(session['user_id'])
        if not user or user.is_deleted:
            session.clear()
            return None
            
        return user
    except Exception as e:
        logger.error(f"Session validation error: {str(e)}")
        session.clear()
        return None

def session_required(f):
    """Decorator for routes that require valid session"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = validate_session()
        if not user:
            flash('Your session has expired. Please login again.', 'warning')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function
