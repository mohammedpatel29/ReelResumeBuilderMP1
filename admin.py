from flask import Blueprint, render_template, redirect, url_for, flash, session, jsonify, request
from flask_login import login_required, current_user, logout_user
from werkzeug.security import generate_password_hash
from sqlalchemy import desc, or_, text
from models import User
from extensions import db
import logging
from datetime import datetime

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

admin = Blueprint('admin', __name__)

def is_admin():
    """Enhanced admin check with additional safeguards"""
    try:
        if not current_user.is_authenticated:
            logger.warning("Unauthenticated user attempted to access admin area")
            flash('Please log in to continue.')
            return False

        if not current_user.is_admin:
            logger.warning(f"Non-admin user {current_user.id} attempted to access admin area")
            flash('Access denied. This page requires admin privileges.')
            return False

        # Additional check for permanent admin status
        if current_user.email == 'reelresumeapp@gmail.com':
            # Special protection for permanent admin
            return True

        # Regular admin check passes
        return True

    except Exception as e:
        logger.error(f"Admin check error: {str(e)}")
        flash('An error occurred while checking admin privileges.')
        return False

@admin.route('/admin/users')
@login_required
def list_users():
    """
    Display list of all active registered users with basic information.
    """
    if not is_admin():
        return redirect(url_for('auth.login'))

    try:
        # Get active users ordered by registration date
        users = User.query.filter_by(is_deleted=False).order_by(desc(User.created_at)).all()

        # Log admin access
        logger.info(f"Admin user {current_user.id} accessed user list at {datetime.utcnow()}")

        return render_template(
            'admin/list_users.html',
            users=users,
            show_deleted=False
        )

    except Exception as e:
        logger.error(f"Admin panel error: {str(e)}")
        session.clear()
        if current_user.is_authenticated:
            logout_user()
        flash('An error occurred while accessing the admin panel. Please try logging in again.')
        return redirect(url_for('auth.login'))

@admin.route('/admin/users/deleted')
@login_required
def list_deleted_users():
    """Display list of soft-deleted users."""
    if not is_admin():
        return redirect(url_for('auth.login'))

    try:
        # Get soft-deleted users ordered by deletion date
        users = User.query.filter_by(is_deleted=True).order_by(desc(User.deleted_at)).all()

        logger.info(f"Admin user {current_user.id} accessed deleted users list")

        return render_template(
            'admin/list_users.html',
            users=users,
            show_deleted=True
        )

    except Exception as e:
        logger.error(f"Error accessing deleted users: {str(e)}")
        flash('An error occurred while accessing deleted users.')
        return redirect(url_for('admin.list_users'))

@admin.route('/admin/users/<int:user_id>/soft-delete', methods=['POST'])
@login_required
def soft_delete_user(user_id):
    """Soft delete a user with enhanced protections for admin accounts."""
    if not is_admin():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    try:
        # Set admin context for audit logging
        with db.engine.connect() as connection:
            connection.execute(text("SET LOCAL app.current_admin_id = :admin_id"),
                            {"admin_id": current_user.id})

        user = User.query.get_or_404(user_id)

        # Check for permanent admin status
        if user.permanent_admin or user.email == 'reelresumeapp@gmail.com':
            logger.warning(f"Attempt to delete permanent admin account {user.id} by {current_user.id}")
            return jsonify({
                'success': False,
                'message': 'Cannot delete permanent admin accounts'
            }), 400

        # Prevent self-deletion
        if user.id == current_user.id:
            logger.warning(f"Admin {current_user.id} attempted to delete their own account")
            return jsonify({
                'success': False,
                'message': 'Cannot delete your own admin account'
            }), 400

        # Prevent deletion of other admins
        if user.is_admin and user.id != current_user.id:
            logger.warning(f"Admin {current_user.id} attempted to delete another admin account {user.id}")
            return jsonify({
                'success': False,
                'message': 'Cannot delete other admin accounts'
            }), 400

        # Additional check for permanent admin email
        if user.email == 'reelresumeapp@gmail.com':
            logger.error(f"Attempt to delete permanent admin account by {current_user.id}")
            return jsonify({
                'success': False,
                'message': 'This account cannot be deleted'
            }), 400

        user.soft_delete()
        logger.info(f"User {user.id} soft deleted by admin {current_user.id}")

        return jsonify({
            'success': True,
            'message': f'User {user.email} has been soft deleted'
        })

    except Exception as e:
        logger.error(f"Error soft deleting user {user_id}: {str(e)}")
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': 'An error occurred while deleting the user'
        }), 500

@admin.route('/admin/users/<int:user_id>/restore', methods=['POST'])
@login_required
def restore_user(user_id):
    """Restore a soft-deleted user."""
    if not is_admin():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    try:
        user = User.query.get_or_404(user_id)

        if not user.is_deleted:
            return jsonify({
                'success': False,
                'message': 'User is not deleted'
            }), 400

        user.restore()
        logger.info(f"User {user.id} restored by admin {current_user.id}")

        return jsonify({
            'success': True,
            'message': f'User {user.email} has been restored'
        })

    except Exception as e:
        logger.error(f"Error restoring user {user_id}: {str(e)}")
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': 'An error occurred while restoring the user'
        }), 500

@admin.route('/admin/users/<int:user_id>/reset-password', methods=['POST'])
@login_required
def reset_user_password(user_id):
    """Reset a user's password with enhanced protections."""
    if not is_admin():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    try:
        # Set admin context for audit logging
        with db.engine.connect() as connection:
            connection.execute(text("SET LOCAL app.current_admin_id = :admin_id"),
                            {"admin_id": current_user.id})

        user = User.query.get_or_404(user_id)
        new_password = request.json.get('new_password')

        # Additional checks for permanent admin
        if user.email == 'reelresumeapp@gmail.com' and current_user.email != 'reelresumeapp@gmail.com':
            logger.warning(f"Unauthorized attempt to reset permanent admin password by {current_user.id}")
            return jsonify({
                'success': False,
                'message': 'Only the permanent admin can reset their own password'
            }), 403

        if not new_password or len(new_password) < 8:
            return jsonify({
                'success': False,
                'message': 'Password must be at least 8 characters long'
            }), 400

        # Update the password with standard password hashing
        user.password_hash = generate_password_hash(new_password)
        db.session.commit()

        logger.info(f"Password reset for user {user.id} by admin {current_user.id}")

        return jsonify({
            'success': True,
            'message': f'Password has been reset for user {user.email}'
        })

    except Exception as e:
        logger.error(f"Error resetting password for user {user_id}: {str(e)}")
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': 'An error occurred while resetting the password'
        }), 500