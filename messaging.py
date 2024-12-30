from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from flask_wtf.csrf import generate_csrf, validate_csrf
from models import Message, User
from extensions import db
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

messaging = Blueprint('messaging', __name__)

@messaging.route('/messages')
@login_required
def inbox():
    received_messages = Message.query.filter_by(receiver_id=current_user.id).order_by(Message.created_at.desc()).all()
    sent_messages = Message.query.filter_by(sender_id=current_user.id).order_by(Message.created_at.desc()).all()
    return render_template('messaging/inbox.html', received_messages=received_messages, sent_messages=sent_messages)

@messaging.route('/messages/new/<int:receiver_id>', methods=['GET', 'POST'])
@login_required
def new_message(receiver_id):
    try:
        receiver = User.query.get_or_404(receiver_id)

        if request.method == 'POST':
            try:
                # Validate CSRF token
                csrf_token = request.form.get('csrf_token')
                if not csrf_token:
                    logger.warning("No CSRF token found in message form submission")
                    flash('Invalid form submission. Please try again.', 'danger')
                    return render_template('messaging/new_message.html', receiver=receiver), 400

                try:
                    validate_csrf(csrf_token)
                    logger.info("CSRF token validation successful for message submission")
                except Exception as e:
                    logger.warning(f"CSRF validation failed for message submission: {str(e)}")
                    flash('Invalid form submission. Please try again.', 'danger')
                    return render_template('messaging/new_message.html', receiver=receiver), 400

                subject = request.form.get('subject', '').strip()
                content = request.form.get('content', '').strip()

                if not subject or not content:
                    flash('Both subject and message content are required.', 'danger')
                    return render_template('messaging/new_message.html', receiver=receiver)

                message = Message(
                    sender_id=current_user.id,
                    receiver_id=receiver_id,
                    subject=subject,
                    content=content,
                    created_at=datetime.utcnow()
                )

                db.session.add(message)
                db.session.commit()
                logger.info(f"Message sent successfully from user {current_user.id} to user {receiver_id}")
                flash('Message sent successfully!', 'success')
                return redirect(url_for('messaging.inbox'))

            except Exception as e:
                logger.error(f"Error sending message: {str(e)}")
                db.session.rollback()
                flash('An error occurred while sending the message.', 'danger')
                return render_template('messaging/new_message.html', receiver=receiver), 500

        return render_template('messaging/new_message.html', receiver=receiver)

    except Exception as e:
        logger.error(f"Error in new_message route: {str(e)}")
        flash('An error occurred. Please try again.', 'danger')
        return redirect(url_for('messaging.inbox'))

@messaging.route('/messages/<int:message_id>')
@login_required
def view_message(message_id):
    message = Message.query.get_or_404(message_id)

    if message.receiver_id != current_user.id and message.sender_id != current_user.id:
        flash('You do not have permission to view this message.', 'danger')
        return redirect(url_for('messaging.inbox'))

    if message.receiver_id == current_user.id and not message.read:
        message.read = True
        db.session.commit()

    return render_template('messaging/view_message.html', message=message)