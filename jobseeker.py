from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required, current_user
from models import Video

jobseeker = Blueprint('jobseeker', __name__)

@jobseeker.route('/dashboard')
@login_required
def dashboard():
    if not current_user.is_authenticated:
        return redirect(url_for('auth.login'))

    # Calculate profile completion percentage and todos
    todos = []
    completed_items = 0
    total_items = 4

    if not current_user.profile_picture:
        todos.append("Add a profile picture")
    else:
        completed_items += 1

    if not current_user.linkedin_url:
        todos.append("Link your LinkedIn profile")
    else:
        completed_items += 1

    videos = Video.query.filter_by(user_id=current_user.id).all()
    if not videos:
        todos.append("Upload your first video resume")
    else:
        completed_items += 1

    if hasattr(current_user, 'title') and not current_user.title:
        todos.append("Add your professional title")
    else:
        completed_items += 1

    completion_percentage = int((completed_items / total_items) * 100)

    # Get video stats
    total_likes = sum(video.likes or 0 for video in videos)
    employer_views = sum(video.views or 0 for video in videos)
    total_messages = len(current_user.received_messages)

    # Calculate visibility score
    visibility_factors = []
    visibility_improvements = []
    visibility_score_value = 0

    if current_user.profile_picture:
        visibility_factors.append("Profile picture uploaded")
        visibility_score_value += 20
    else:
        visibility_improvements.append("Add a profile picture to increase visibility")

    if videos:
        visibility_factors.append("Video resume uploaded")
        visibility_score_value += 30
    else:
        visibility_improvements.append("Create a video resume to showcase your skills")

    if current_user.linkedin_url:
        visibility_factors.append("LinkedIn profile connected")
        visibility_score_value += 20
    else:
        visibility_improvements.append("Link your LinkedIn profile")

    if hasattr(current_user, 'title') and current_user.title:
        visibility_factors.append("Professional title added")
        visibility_score_value += 30
    else:
        visibility_improvements.append("Add your professional title")

    visibility_score = {
        'score': visibility_score_value,
        'factors': visibility_factors,
        'improvements': visibility_improvements
    }

    return render_template('jobseeker/dashboard.html',
                         profile_completion={'percentage': completion_percentage, 'todos': todos},
                         stats={'total_likes': total_likes, 'employer_views': employer_views},
                         videos=videos,
                         playlists=current_user.playlists,
                         visibility_score=visibility_score)