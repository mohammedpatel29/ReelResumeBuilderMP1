"""Authentication routes with enhanced security and error handling"""
from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models import User
from extensions import db, mail
from datetime import datetime, timedelta
import logging
import secrets
from flask_mail import Message
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SelectField
from wtforms.validators import DataRequired, Email, Length, EqualTo

# Enhanced logging setup with request tracking
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

auth = Blueprint('auth', __name__, url_prefix='/auth')

# Form classes to handle validation
class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember = BooleanField('Remember Me')

class SignupForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[
        DataRequired(),
        Length(min=8, message='Password must be at least 8 characters long')
    ])
    first_name = StringField('First Name', validators=[DataRequired()])
    last_name = StringField('Last Name', validators=[DataRequired()])
    user_type = SelectField('User Type', choices=[
        ('jobseeker', 'Job Seeker'),
        ('employer', 'Employer')
    ], validators=[DataRequired()])

@auth.route('/login', methods=['GET', 'POST'])
def login():
    """Handle user login with enhanced security and logging"""
    request_id = datetime.now().strftime('%Y%m%d%H%M%S')
    form = LoginForm()

    if current_user.is_authenticated:
        logger.info(f"[Request: {request_id}] Already authenticated user accessing login")
        return redirect(url_for('jobseeker.dashboard' if current_user.user_type == 'jobseeker' else 'employer.dashboard'))

    if request.method == 'POST' and form.validate_on_submit():
        try:
            user = User.query.filter_by(email=form.email.data.strip().lower()).first()

            if not user or not check_password_hash(user.password_hash, form.password.data):
                logger.warning(f"[Request: {request_id}] Failed login attempt for email: {form.email.data}")
                flash('Invalid email or password.', 'error')
                return render_template('auth/login.html', form=form)

            # Clear any existing session data
            session.clear()

            # Set up new session
            login_user(user, remember=form.remember.data)
            user.last_login = datetime.utcnow()
            db.session.commit()

            logger.info(f"[Request: {request_id}] Successful login for user: {user.id}")

            next_page = request.args.get('next')
            if next_page and next_page.startswith('/'):
                return redirect(next_page)
            return redirect(url_for('jobseeker.dashboard' if user.user_type == 'jobseeker' else 'employer.dashboard'))

        except Exception as e:
            logger.error(f"[Request: {request_id}] Login error: {str(e)}")
            db.session.rollback()
            flash('An error occurred during login. Please try again.', 'error')

    return render_template('auth/login.html', form=form)

@auth.route('/signup', methods=['GET', 'POST'])
def signup():
    """Handle new user registration with enhanced validation"""
    request_id = datetime.now().strftime('%Y%m%d%H%M%S')
    form = SignupForm()

    if current_user.is_authenticated:
        logger.info(f"[Request: {request_id}] Authenticated user accessing signup")
        return redirect(url_for('jobseeker.dashboard' if current_user.user_type == 'jobseeker' else 'employer.dashboard'))

    if request.method == 'POST' and form.validate_on_submit():
        try:
            if User.query.filter_by(email=form.email.data.strip().lower()).first():
                logger.warning(f"[Request: {request_id}] Signup attempt with existing email: {form.email.data}")
                flash('Email already registered.', 'error')
                return render_template('auth/signup.html', form=form)

            new_user = User(
                email=form.email.data.strip().lower(),
                password_hash=generate_password_hash(form.password.data),
                user_type=form.user_type.data,
                first_name=form.first_name.data.strip(),
                last_name=form.last_name.data.strip(),
                created_at=datetime.utcnow()
            )

            db.session.add(new_user)
            db.session.commit()

            logger.info(f"[Request: {request_id}] New user registered: {new_user.id}")

            # Log in the new user
            login_user(new_user)

            return redirect(url_for('jobseeker.dashboard' if new_user.user_type == 'jobseeker' else 'employer.dashboard'))

        except Exception as e:
            logger.error(f"[Request: {request_id}] Signup error: {str(e)}")
            db.session.rollback()
            flash('An error occurred during registration. Please try again.', 'error')

    return render_template('auth/signup.html', form=form)

@auth.route('/logout')
@login_required
def logout():
    """Handle user logout with proper session cleanup"""
    request_id = datetime.now().strftime('%Y%m%d%H%M%S')
    try:
        user_id = current_user.id
        session.clear()
        logout_user()
        logger.info(f"[Request: {request_id}] User {user_id} logged out successfully")
        flash('Successfully logged out.', 'success')
        return redirect(url_for('auth.login'))
    except Exception as e:
        logger.error(f"[Request: {request_id}] Logout error: {str(e)}")
        return redirect(url_for('auth.login'))

@auth.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """Handle password reset request with improved error handling"""
    request_id = datetime.now().strftime('%Y%m%d%H%M%S')
    try:
        if current_user.is_authenticated:
            return redirect(url_for('jobseeker.dashboard' if current_user.user_type == 'jobseeker' else 'employer.dashboard'))

        if request.method == 'GET':
            return render_template('auth/forgot_password.html')

        if request.method == 'POST':
            email = request.form.get('email', '').strip().lower()
            if not email:
                flash('Please enter your email address.', 'error')
                return render_template('auth/forgot_password.html')

            user = User.query.filter_by(email=email).first()
            if not user:
                # Don't reveal if the email exists
                flash('If your email is registered, you will receive password reset instructions.', 'info')
                return render_template('auth/forgot_password.html')

            # Generate reset token
            token = user.generate_reset_token()

            try:
                db.session.commit()

                # Send reset email
                reset_url = url_for('auth.reset_password', token=token, _external=True)
                msg = Message(
                    'Password Reset Request',
                    sender='noreply@reelresume.com',
                    recipients=[email]
                )
                msg.body = f'''To reset your password, visit the following link:
{reset_url}

If you did not make this request, simply ignore this email and no changes will be made.
'''
                mail.send(msg)
                flash('Password reset instructions have been sent to your email.', 'success')
                return redirect(url_for('auth.login'))

            except Exception as e:
                logger.error(f"[Request: {request_id}] Error sending password reset email: {str(e)}")
                db.session.rollback()
                flash('An error occurred. Please try again later.', 'error')
                return render_template('auth/forgot_password.html')

    except Exception as e:
        logger.error(f"[Request: {request_id}] Unexpected error in forgot_password route: {str(e)}")
        flash('An unexpected error occurred. Please try again later.', 'error')
        return render_template('auth/forgot_password.html')

@auth.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    """Handle password reset with token"""
    request_id = datetime.now().strftime('%Y%m%d%H%M%S')
    try:
        if current_user.is_authenticated:
            return redirect(url_for('jobseeker.dashboard' if current_user.user_type == 'jobseeker' else 'employer.dashboard'))

        user = User.query.filter_by(reset_token=token).first()
        if not user or not user.reset_token_expires or user.reset_token_expires < datetime.utcnow():
            flash('The password reset link is invalid or has expired.', 'error')
            return redirect(url_for('auth.forgot_password'))

        if request.method == 'GET':
            return render_template('auth/reset_password.html', token=token)

        if request.method == 'POST':
            password = request.form.get('password')
            confirm_password = request.form.get('confirm_password')

            if not password or not confirm_password:
                flash('Please fill in all fields.', 'error')
                return render_template('auth/reset_password.html', token=token)

            if password != confirm_password:
                flash('Passwords do not match.', 'error')
                return render_template('auth/reset_password.html', token=token)

            if len(password) < 8:
                flash('Password must be at least 8 characters long.', 'error')
                return render_template('auth/reset_password.html', token=token)

            user.password_hash = generate_password_hash(password)
            user.reset_token = None
            user.reset_token_expires = None

            try:
                db.session.commit()
                logger.info(f"[Request: {request_id}] Password reset successful for user: {user.id}")
                flash('Your password has been reset successfully. Please log in.', 'success')
                return redirect(url_for('auth.login'))

            except Exception as e:
                logger.error(f"[Request: {request_id}] Error resetting password: {str(e)}")
                db.session.rollback()
                flash('An error occurred. Please try again later.', 'error')
                return render_template('auth/reset_password.html', token=token)

    except Exception as e:
        logger.error(f"[Request: {request_id}] Unexpected error in reset_password route: {str(e)}")
        flash('An unexpected error occurred. Please try again later.', 'error')
        return redirect(url_for('auth.forgot_password'))