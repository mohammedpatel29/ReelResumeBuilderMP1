from flask import Blueprint, jsonify, send_from_directory
from flask_login import login_required, current_user
from extensions import db
import os

tutorial = Blueprint('tutorial', __name__)

TUTORIAL_VIDEOS_DIR = 'static/videos/tutorials'

@tutorial.route('/tutorial/complete', methods=['POST'])
@login_required
def complete_tutorial():
    """Mark the tutorial as completed for the current user"""
    current_user.has_seen_tutorial = True
    db.session.commit()
    return jsonify({'status': 'success'})

@tutorial.route('/tutorial/skip', methods=['POST'])
@login_required
def skip_tutorial():
    """Mark the tutorial as skipped for the current user"""
    current_user.has_seen_tutorial = True
    db.session.commit()
    return jsonify({'status': 'success'})

@tutorial.route('/tutorial/video/<path:filename>')
@login_required
def serve_tutorial_video(filename):
    """Serve tutorial video files"""
    try:
        return send_from_directory(TUTORIAL_VIDEOS_DIR, filename)
    except:
        return jsonify({'error': 'Video not found'}), 404
