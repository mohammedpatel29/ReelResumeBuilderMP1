from flask import Blueprint, render_template, redirect, url_for, jsonify
from flask_login import login_required, current_user
from models import Video, User, BookmarkCandidate, VideoLike
from sqlalchemy import func, desc, and_
from datetime import datetime, timedelta
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

analytics = Blueprint('analytics', __name__)

@analytics.route('/analytics/dashboard')
@login_required
def dashboard():
    """Analytics dashboard for job seekers"""
    try:
        if current_user.user_type != 'jobseeker':
            return render_template('errors/404.html'), 404
            
        # Get all videos for the current user
        videos = Video.query.filter_by(user_id=current_user.id).all()
        
        try:
            # Calculate total stats with null checks
            total_views = sum(video.views or 0 for video in videos)
            total_likes = sum(video.likes or 0 for video in videos)
            
            # Get employer views with proper error handling
            employer_views = Video.query.filter_by(
                user_id=current_user.id
            ).with_entities(
                func.coalesce(func.sum(Video.views), 0)
            ).scalar()
            
            # Get employer bookmarks with error handling
            employer_bookmarks = BookmarkCandidate.query.filter_by(
                jobseeker_id=current_user.id
            ).count()
        except Exception as e:
            logger.error(f"Error calculating analytics stats: {str(e)}")
            total_views = 0
            total_likes = 0
            employer_views = 0
            employer_bookmarks = 0
        
        # Get view data for last 30 days
        try:
            thirty_days_ago = datetime.utcnow() - timedelta(days=30)
            videos = Video.query.filter(
                Video.user_id == current_user.id,
                Video.created_at >= thirty_days_ago
            ).order_by(Video.created_at).all()
            
            # Aggregate views by date
            daily_views = []
            current_date = datetime.utcnow().date()
            
            # Create a dict to store views per date
            date_views = {}
            for video in videos:
                video_date = video.created_at.date()
                date_str = video_date.strftime('%Y-%m-%d')
                date_views[date_str] = date_views.get(date_str, 0) + video.views
            
            # Fill in the last 30 days, including days with 0 views
            for i in range(30):
                date = current_date - timedelta(days=i)
                date_str = date.strftime('%Y-%m-%d')
                views = date_views.get(date_str, 0)
                daily_views.append({'date': date_str, 'views': views})
                
            # Sort by date ascending
            daily_views.sort(key=lambda x: x['date'])
            
        except Exception as e:
            logger.error(f"Error calculating daily views: {str(e)}")
            daily_views = [{'date': datetime.utcnow().strftime('%Y-%m-%d'), 'views': 0}]
        
        # Get top performing videos
        top_videos = Video.query.filter_by(
            user_id=current_user.id
        ).order_by(
            desc(Video.views)
        ).limit(5).all()
        
        # Process daily_views for chart data
        view_dates = [entry['date'] for entry in daily_views]
        view_counts = [entry['views'] for entry in daily_views]

        return render_template(
            'analytics/dashboard.html',
            total_views=total_views,
            total_likes=total_likes,
            employer_views=employer_views,
            employer_bookmarks=employer_bookmarks,
            daily_views=daily_views,
            top_videos=top_videos,
            view_dates=view_dates,
            view_counts=view_counts
        )
        
    except Exception as e:
        logger.error(f"Analytics dashboard error: {str(e)}")
        return render_template('errors/500.html'), 500
