"""Profile management routes with enhanced error handling and logging"""
from flask import Blueprint, render_template, redirect, url_for, flash, request, session, jsonify
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from models import User
from extensions import db
import os
import logging
import traceback
from datetime import datetime

# Set up enhanced logging with detailed formatting
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/profile.log', mode='a')
    ]
)
logger = logging.getLogger(__name__)

profile = Blueprint('profile', __name__, url_prefix='/profile')

PROFILE_PICTURES_DIR = 'static/uploads/profile_pictures'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    """Check if uploaded file has allowed extension"""
    try:
        return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
    except Exception as e:
        logger.error(f"Error checking file extension: {str(e)}", exc_info=True)
        return False

def ensure_upload_directory():
    """Ensure upload directory exists with proper permissions"""
    try:
        if not os.path.exists(PROFILE_PICTURES_DIR):
            os.makedirs(PROFILE_PICTURES_DIR, exist_ok=True)
            logger.info(f"Created profile pictures directory: {PROFILE_PICTURES_DIR}")
        return True
    except Exception as e:
        logger.error(f"Failed to create upload directory: {str(e)}", exc_info=True)
        return False

@profile.route('/setup', methods=['GET', 'POST'])
@login_required
def setup():
    """Handle user profile setup with comprehensive error handling and logging"""
    request_id = datetime.now().strftime('%Y%m%d%H%M%S')
    logger.info(f"[Request: {request_id}] Profile setup accessed by user {current_user.id}")

    try:
        if request.method == 'POST':
            logger.debug(f"[Request: {request_id}] Processing POST request for user {current_user.id}")

            # Extract and validate form data
            form_data = {
                'first_name': request.form.get('first_name', '').strip(),
                'last_name': request.form.get('last_name', '').strip(),
                'linkedin_url': request.form.get('linkedin_url', '').strip()
            }

            # Validate required fields
            if not all([form_data['first_name'], form_data['last_name']]):
                logger.warning(f"[Request: {request_id}] Missing required fields for user {current_user.id}")
                flash('Please fill in all required fields.', 'error')
                return render_template('profile/setup.html')

            try:
                # Update user basic info with transaction management
                db.session.begin_nested()

                for key, value in form_data.items():
                    setattr(current_user, key, value)
                    logger.debug(f"[Request: {request_id}] Updated {key} for user {current_user.id}")

                # Handle employer-specific fields
                if current_user.user_type == 'employer':
                    logger.debug(f"[Request: {request_id}] Processing employer-specific fields")
                    employer_fields = {
                        'company_name': request.form.get('company_name', '').strip(),
                        'company_website': request.form.get('company_website', '').strip(),
                        'company_description': request.form.get('company_description', '').strip(),
                        'company_size': request.form.get('company_size', '').strip(),
                        'company_industry': request.form.get('company_industry', '').strip(),
                        'company_location': request.form.get('company_location', '').strip()
                    }

                    for key, value in employer_fields.items():
                        setattr(current_user, key, value)
                        logger.debug(f"[Request: {request_id}] Updated employer field {key}")

                # Handle profile picture upload
                if 'profile_picture' in request.files:
                    file = request.files['profile_picture']
                    if file and file.filename and allowed_file(file.filename):
                        try:
                            if ensure_upload_directory():
                                filename = secure_filename(file.filename)
                                filepath = os.path.join(PROFILE_PICTURES_DIR, filename)
                                file.save(filepath)
                                current_user.profile_picture = filename
                                logger.info(f"[Request: {request_id}] Profile picture saved successfully: {filename}")
                            else:
                                raise Exception("Failed to ensure upload directory exists")
                        except Exception as e:
                            logger.error(f"[Request: {request_id}] Error saving profile picture: {str(e)}", exc_info=True)
                            flash('Error uploading profile picture. Other changes were saved.', 'warning')

                # Commit changes to database
                db.session.commit()
                logger.info(f"[Request: {request_id}] Profile updated successfully for user {current_user.id}")
                flash('Profile updated successfully!', 'success')

                return redirect(url_for(
                    'employer.dashboard' if current_user.user_type == 'employer' else 'jobseeker.dashboard'
                ))

            except Exception as e:
                logger.error(f"[Request: {request_id}] Database error updating profile: {str(e)}\n{traceback.format_exc()}")
                db.session.rollback()
                flash('Error updating profile. Please try again.', 'error')
                return render_template('profile/setup.html')

        # GET request - render form
        logger.debug(f"[Request: {request_id}] Rendering profile setup form for user {current_user.id}")
        return render_template('profile/setup.html')

    except Exception as e:
        logger.error(f"[Request: {request_id}] Unexpected error in profile setup: {str(e)}\n{traceback.format_exc()}")
        db.session.rollback()
        flash('An unexpected error occurred. Please try again.', 'error')
        return redirect(url_for(
            'employer.dashboard' if current_user.user_type == 'employer' else 'jobseeker.dashboard'
        ))

@profile.route('/check-setup')
@login_required
def check_setup():
    """Check if user has completed profile setup"""
    request_id = datetime.now().strftime('%Y%m%d%H%M%S')
    try:
        logger.debug(f"[Request: {request_id}] Checking profile setup status for user {current_user.id}")
        is_complete = bool(
            current_user.first_name and 
            current_user.last_name and 
            (current_user.company_name if current_user.user_type == 'employer' else True)
        )
        logger.info(f"[Request: {request_id}] Profile completion check for user {current_user.id}: {is_complete}")
        return jsonify({'is_complete': is_complete}), 200
    except Exception as e:
        logger.error(f"[Request: {request_id}] Error checking profile setup: {str(e)}\n{traceback.format_exc()}")
        return jsonify({'error': 'Failed to check profile status'}), 500