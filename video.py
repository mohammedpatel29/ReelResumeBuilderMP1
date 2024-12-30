from flask import Blueprint, render_template, redirect, url_for, flash, request, send_file, jsonify, send_from_directory, current_app
from flask_login import login_required, current_user
from flask_wtf.csrf import generate_csrf
from werkzeug.utils import secure_filename
from models import Video, VideoLike, User, Tag, VideoTag
from extensions import db
from sqlalchemy import desc, exc as SQLAlchemyError, func
from openai import OpenAI
import os
import subprocess
import uuid
import ffmpeg
import logging
import shutil
from datetime import datetime
import json
import tempfile

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

video = Blueprint('video', __name__)

VIDEOS_DIR = 'static/uploads/videos'
THUMBNAILS_DIR = 'static/uploads/thumbnails'
ALLOWED_EXTENSIONS = {'mp4', 'mov', 'avi', 'webm', 'mkv'}
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500MB
DEFAULT_THUMBNAIL = 'static/default-thumbnail.jpg'

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def ensure_directory_permissions():
    """Ensure upload directories exist with proper permissions"""
    try:
        for directory in [VIDEOS_DIR, THUMBNAILS_DIR]:
            os.makedirs(directory, exist_ok=True)
            os.chmod(directory, 0o755)
        return True
    except Exception as e:
        logger.error(f"Error setting directory permissions: {str(e)}")
        return False

@video.route('/video/upload')
@login_required
def upload():
    """Display video creation options page"""
    logger.info(f"Accessing video upload options page")

    try:
        # Check user type
        if current_user.user_type != 'jobseeker':
            logger.warning(f"Access denied for user {current_user.id} - not a jobseeker")
            flash('Access denied. This page is only for job seekers.', 'danger')
            return redirect(url_for('jobseeker.dashboard'))

        script_content = request.args.get('script_content', '')
        video_title = request.args.get('title', '')
        video_description = request.args.get('description', '')

        return render_template('video/upload.html',
                            script_content=script_content,
                            video_title=video_title,
                            video_description=video_description)
    except Exception as e:
        logger.error(f"Error accessing video upload page: {str(e)}")
        flash('An error occurred while loading the page.', 'danger')
        return redirect(url_for('jobseeker.dashboard'))

@video.route('/video/record')
@login_required
def record():
    """Handle video recording page"""
    logger.info(f"Accessing video recording page")

    try:
        if current_user.user_type != 'jobseeker':
            flash('Access denied. This page is only for job seekers.', 'danger')
            return redirect(url_for('jobseeker.dashboard'))

        script_content = request.args.get('script_content', '')
        return render_template('video/recording.html', script_content=script_content)
    except Exception as e:
        logger.error(f"Error accessing recording page: {str(e)}")
        flash('An error occurred while loading the recording page.', 'danger')
        return redirect(url_for('jobseeker.dashboard'))

@video.route('/video/upload/existing', methods=['GET', 'POST'])
@login_required
def upload_existing():
    """Handle existing video upload page"""
    logger.info(f"Accessing existing video upload page - Method: {request.method}")

    try:
        if current_user.user_type != 'jobseeker':
            flash('Access denied. This page is only for job seekers.', 'danger')
            return redirect(url_for('jobseeker.dashboard'))

        # Handle POST request for file upload
        if request.method == 'POST':
            video_path = None
            thumbnail_path = None
            try:
                if 'video' not in request.files:
                    return jsonify({
                        'success': False,
                        'message': 'No video file uploaded'
                    }), 400

                file = request.files['video']
                if file.filename == '':
                    return jsonify({
                        'success': False,
                        'message': 'No selected file'
                    }), 400

                if not allowed_file(file.filename):
                    return jsonify({
                        'success': False,
                        'message': f'Invalid file type. Allowed types are: {", ".join(ALLOWED_EXTENSIONS)}'
                    }), 400

                # Get form data
                title = request.form.get('title', '').strip()
                description = request.form.get('description', '').strip()
                script_content = request.form.get('script_content', '').strip()

                if not title:
                    return jsonify({
                        'success': False,
                        'message': 'Title is required'
                    }), 400

                # Generate unique filename and save video
                filename = secure_filename(f"{uuid.uuid4()}_{file.filename}")
                video_path = os.path.join(VIDEOS_DIR, filename)
                thumbnail_filename = f"{filename.split('.')[0]}_thumb.jpg"
                thumbnail_path = os.path.join(THUMBNAILS_DIR, thumbnail_filename)

                # Save video file
                file.save(video_path)
                os.chmod(video_path, 0o644)
                logger.info(f"Video file saved successfully: {video_path}")

                # Generate thumbnail
                success, error = generate_thumbnail(video_path, thumbnail_path)
                if not success:
                    logger.warning(f"Thumbnail generation warning: {error}")

                # Create video record
                try:
                    new_video = Video(
                        title=title,
                        description=description,
                        filename=filename,
                        thumbnail=thumbnail_filename,
                        user_id=current_user.id,
                        script_content=script_content if script_content else None
                    )
                    db.session.add(new_video)
                    db.session.commit()
                    logger.info(f"Video record created successfully: {new_video.id}")

                    return jsonify({
                        'success': True,
                        'message': 'Video uploaded successfully!',
                        'redirect_url': url_for('video.view', video_id=new_video.id)
                    })

                except Exception as e:
                    logger.error(f"Database error: {str(e)}")
                    if video_path and os.path.exists(video_path):
                        os.remove(video_path)
                    if thumbnail_path and os.path.exists(thumbnail_path):
                        os.remove(thumbnail_path)
                    db.session.rollback()
                    return jsonify({
                        'success': False,
                        'message': 'Database error occurred'
                    }), 500

            except Exception as e:
                logger.error(f"Error in video upload: {str(e)}")
                if video_path and os.path.exists(video_path):
                    os.remove(video_path)
                if thumbnail_path and os.path.exists(thumbnail_path):
                    os.remove(thumbnail_path)
                return jsonify({
                    'success': False,
                    'message': 'An error occurred during upload'
                }), 500

        # GET request - render upload form
        script_content = request.args.get('script_content', '')
        video_title = request.args.get('title', '')
        video_description = request.args.get('description', '')

        return render_template('video/upload_existing.html',
                           script_content=script_content,
                           video_title=video_title,
                           video_description=video_description)

    except Exception as e:
        logger.error(f"Unexpected error in upload_existing route: {str(e)}")
        flash('An error occurred while accessing the upload page.', 'danger')
        return redirect(url_for('jobseeker.dashboard'))

@video.route('/video/upload', methods=['POST'])
@login_required
def upload_post():
    """Handle video upload functionality"""
    logger.info(f"Accessing video upload route - Method: {request.method}")

    try:
        # Check user type
        if current_user.user_type != 'jobseeker':
            logger.warning(f"Access denied for user {current_user.id} - not a jobseeker")
            flash('Access denied. This page is only for job seekers.', 'danger')
            return redirect(url_for('jobseeker.dashboard'))

        # Ensure upload directories exist
        if not ensure_directory_permissions():
            logger.error("Failed to set directory permissions")
            flash('Server configuration error. Please try again later.', 'danger')
            return redirect(url_for('jobseeker.dashboard'))

        if request.method == 'POST':
            try:
                if 'video' not in request.files:
                    logger.warning("No video file in request")
                    return jsonify({
                        'success': False,
                        'message': 'No video file uploaded'
                    }), 400

                file = request.files['video']
                if file.filename == '':
                    logger.warning("Empty filename in video upload")
                    return jsonify({
                        'success': False,
                        'message': 'No selected file'
                    }), 400

                if not allowed_file(file.filename):
                    logger.warning(f"Invalid file type: {file.filename}")
                    return jsonify({
                        'success': False,
                        'message': f'Invalid file type. Allowed types are: {", ".join(ALLOWED_EXTENSIONS)}'
                    }), 400

                # Get form data
                title = request.form.get('title', '').strip()
                description = request.form.get('description', '').strip()
                script_content = request.form.get('script_content', '').strip()

                if not title:
                    return jsonify({
                        'success': False,
                        'message': 'Title is required'
                    }), 400

                # Generate unique filename and save video
                filename = secure_filename(f"{uuid.uuid4()}_{file.filename}")
                video_path = os.path.join(VIDEOS_DIR, filename)
                thumbnail_filename = f"{filename.split('.')[0]}_thumb.jpg"
                thumbnail_path = os.path.join(THUMBNAILS_DIR, thumbnail_filename)

                # Save video file
                try:
                    file.save(video_path)
                    os.chmod(video_path, 0o644)
                except Exception as e:
                    logger.error(f"Error saving video file: {str(e)}")
                    return jsonify({
                        'success': False,
                        'message': 'Failed to save video file'
                    }), 500

                # Generate thumbnail
                success, error = generate_thumbnail(video_path, thumbnail_path)
                if not success:
                    logger.warning(f"Thumbnail generation warning: {error}")

                # Create video record
                try:
                    new_video = Video(
                        title=title,
                        description=description,
                        filename=filename,
                        thumbnail=thumbnail_filename,
                        user_id=current_user.id,
                        script_content=script_content if script_content else None
                    )
                    db.session.add(new_video)
                    db.session.commit()

                    return jsonify({
                        'success': True,
                        'message': 'Video uploaded successfully!',
                        'redirect_url': url_for('video.view', video_id=new_video.id)
                    })

                except Exception as e:
                    logger.error(f"Database error: {str(e)}")
                    cleanup_files(video_path, thumbnail_path)
                    db.session.rollback()
                    return jsonify({
                        'success': False,
                        'message': 'Database error occurred'
                    }), 500

            except Exception as e:
                logger.error(f"Error in video upload: {str(e)}")
                if 'video_path' in locals():
                    cleanup_files(video_path, thumbnail_path if 'thumbnail_path' in locals() else None)
                return jsonify({
                    'success': False,
                    'message': 'An error occurred during upload'
                }), 500

    except Exception as e:
        logger.error(f"Unexpected error in upload route: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'An unexpected error occurred'
        }), 500

def validate_video_format(video_path):
    try:
        probe = ffmpeg.probe(video_path)
        video_stream = next((stream for stream in probe['streams'] if stream['codec_type'] == 'video'), None)
        if not video_stream:
            return False, "No video stream found in the file", None

        metadata = {
            'width': int(video_stream['width']),
            'height': int(video_stream['height']),
            'duration': float(video_stream.get('duration', 0)),
            'codec': video_stream.get('codec_name', 'unknown')
        }
        return True, None, metadata
    except Exception as e:
        logger.error(f"Error validating video format: {str(e)}")
        return False, str(e), None

def generate_thumbnail_at_timestamp(video_path, thumbnail_path, timestamp):
    try:
        logger.info(f"Generating thumbnail for {video_path} at timestamp {timestamp}s")
        os.makedirs(os.path.dirname(thumbnail_path), exist_ok=True)
        stream = ffmpeg.input(video_path, ss=timestamp)
        stream = ffmpeg.filter(stream, 'scale', 640, -1)
        stream = ffmpeg.output(stream, thumbnail_path, vframes=1)
        ffmpeg.run(stream, overwrite_output=True, capture_stdout=True, capture_stderr=True)

        if os.path.exists(thumbnail_path) and os.path.getsize(thumbnail_path) > 0:
            os.chmod(thumbnail_path, 0o644)
            return True
        return False
    except Exception as e:
        logger.error(f"Error generating thumbnail: {str(e)}")
        return False

def generate_thumbnail(video_path, thumbnail_path):
    logger.info(f"Generating thumbnail for {video_path}")
    os.makedirs(os.path.dirname(thumbnail_path), exist_ok=True)

    try:
        timestamps = [1, 5, 10]
        for timestamp in timestamps:
            success = generate_thumbnail_at_timestamp(video_path, thumbnail_path, timestamp)
            if success and os.path.exists(thumbnail_path) and os.path.getsize(thumbnail_path) > 0:
                return True, None
        raise Exception("Failed to generate thumbnail at any timestamp")
    except Exception as e:
        logger.error(f"Thumbnail generation failed: {str(e)}")
        try:
            shutil.copy2(DEFAULT_THUMBNAIL, thumbnail_path)
            os.chmod(thumbnail_path, 0o644)
            return False, str(e)
        except Exception as copy_error:
            logger.error(f"Error copying default thumbnail: {str(copy_error)}")
            return False, str(copy_error)

@video.route('/videos')
@video.route('/video/list')
@login_required
def list_videos():
    logger.info(f"Accessing list_videos for user {current_user.id}")
    if current_user.user_type != 'jobseeker':
        flash('Access denied. This page is only for job seekers.')
        return redirect(url_for('jobseeker.dashboard'))

    try:
        videos = Video.query.filter_by(user_id=current_user.id).order_by(desc(Video.created_at)).all()
        logger.info(f"Found {len(videos)} videos for user {current_user.id}")
        return render_template('video/list_videos.html', videos=videos)
    except Exception as e:
        logger.error(f"Error in list_videos: {str(e)}")
        db.session.rollback()
        flash('An error occurred while loading your videos.', 'danger')
        return redirect(url_for('jobseeker.dashboard'))

@video.route('/video/<int:video_id>')
def view(video_id):
    video = Video.query.get_or_404(video_id)
    video.views += 1
    db.session.commit()

    user_like = None
    if current_user.is_authenticated:
        user_like = VideoLike.query.filter_by(
            video_id=video_id,
            user_id=current_user.id
        ).first()

    can_edit = current_user.is_authenticated and video.user_id == current_user.id
    return render_template('video/view.html', video=video, user_like=user_like, can_edit=can_edit)

@video.route('/video/<int:video_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(video_id):
    """Handle video editing with advanced features"""
    logger.info(f"Accessing edit route for video {video_id}")

    try:
        video = Video.query.get_or_404(video_id)

        if video.user_id != current_user.id:
            logger.warning(f"Unauthorized edit attempt for video {video_id} by user {current_user.id}")
            flash('You do not have permission to edit this video.')
            return redirect(url_for('video.view', video_id=video_id))

        if request.method == 'POST':
            logger.info(f"Processing POST request for video {video_id}")
            try:
                # Get form data
                title = request.form.get('title', '').strip()
                description = request.form.get('description', '').strip()
                filters_str = request.form.get('filters', '{}')
                text_overlay_str = request.form.get('text_overlay', '{}')

                logger.info(f"Received data - Title: {title}, Description length: {len(description)}")
                logger.info(f"Filters: {filters_str}")
                logger.info(f"Text overlay: {text_overlay_str}")

                if not title:
                    return jsonify({'success': False, 'message': 'Title is required'}), 400

                # Parse JSON data
                try:
                    filters = json.loads(filters_str)
                    text_overlay = json.loads(text_overlay_str)
                except json.JSONDecodeError as e:
                    logger.error(f"JSON parsing error: {str(e)}")
                    return jsonify({'success': False, 'message': 'Invalid filter or overlay data'}), 400

                # Get trim values with validation
                try:
                    trim_start = float(request.form.get('trim_start', 0))
                    trim_end = float(request.form.get('trim_end', 0))
                    if trim_start < 0 or trim_end < 0:
                        raise ValueError("Trim values cannot be negative")
                except ValueError as e:
                    logger.error(f"Invalid trim values: {str(e)}")
                    return jsonify({'success': False, 'message': 'Invalid trim values'}), 400

                # Create temporary directory for processing
                with tempfile.TemporaryDirectory() as temp_dir:
                    input_path = os.path.join(VIDEOS_DIR, video.filename)
                    if not os.path.exists(input_path):
                        logger.error(f"Source video file not found: {input_path}")
                        return jsonify({'success': False, 'message': 'Source video file not found'}), 404

                    output_filename = f"edited_{video.filename}"
                    output_path = os.path.join(temp_dir, output_filename)
                    final_path = os.path.join(VIDEOS_DIR, output_filename)

                    try:
                        # Build filter complex string
                        filter_complex = []

                        # Apply trimming if specified
                        if trim_start > 0 or trim_end > 0:
                            logger.info(f"Applying trim: start={trim_start}, end={trim_end}")
                            filter_complex.append(f"trim=start={trim_start}:end={trim_end},setpts=PTS-STARTPTS")

                        # Apply filters if specified
                        if filters:
                            logger.info("Applying video filters")
                            if 'brightness' in filters:
                                brightness_value = float(filters['brightness']) / 100
                                filter_complex.append(f"eq=brightness={brightness_value}")
                            if 'contrast' in filters:
                                contrast_value = float(filters['contrast']) / 100
                                filter_complex.append(f"eq=contrast={contrast_value}")
                            if 'saturation' in filters:
                                saturation_value = float(filters['saturation']) / 100
                                filter_complex.append(f"eq=saturation={saturation_value}")

                        # Apply text overlay if specified
                        if text_overlay and text_overlay.get('text'):
                            logger.info("Applying text overlay")
                            text = text_overlay.get('text', '').replace("'", "\\'")  # Escape single quotes
                            color = text_overlay.get('color', 'white')
                            position = text_overlay.get('position', 'center')

                            # Convert position to FFmpeg coordinates
                            position_map = {
                                'top': 'x=(w-text_w)/2:y=h/10',
                                'middle': 'x=(w-text_w)/2:y=(h-text_h)/2',
                                'bottom': 'x=(w-text_w)/2:y=h-h/10'
                            }

                            overlay_position = position_map.get(position, position_map['middle'])
                            filter_complex.append(
                                f"drawtext=text='{text}':fontcolor={color}:fontsize=24:{overlay_position}:fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
                            )

                        # Create FFmpeg command
                        stream = ffmpeg.input(input_path)

                        if filter_complex:
                            filter_str = ','.join(filter_complex)
                            logger.info(f"Applying filter complex: {filter_str}")
                            stream = stream.filter(filter_str)

                        # Save the processed video
                        stream = ffmpeg.output(stream, output_path, acodec='copy')
                        logger.info("Running FFmpeg command")
                        ffmpeg.run(stream, overwrite_output=True, capture_stdout=True, capture_stderr=True)

                        # Verify the output file exists and has content
                        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
                            raise Exception("Failed to generate output video")

                        # Move the processed video to final location
                        logger.info(f"Moving processed video to {final_path}")
                        shutil.move(output_path, final_path)
                        os.chmod(final_path, 0o644)

                        # Update video record
                        old_filename = video.filename
                        video.filename = output_filename
                        video.title = title
                        video.description = description
                        db.session.commit()

                        # Delete old video file if different from new one
                        if old_filename != output_filename:
                            old_path = os.path.join(VIDEOS_DIR, old_filename)
                            if os.path.exists(old_path):
                                os.remove(old_path)
                                logger.info(f"Deleted old video file: {old_path}")

                        logger.info("Video update completed successfully")
                        return jsonify({
                            'success': True,
                            'message': 'Video updated successfully!',
                            'redirect_url': url_for('video.view', video_id=video.id)
                        })

                    except ffmpeg.Error as e:
                        error_message = e.stderr.decode() if hasattr(e, 'stderr') else str(e)
                        logger.error(f"FFmpeg error: {error_message}")
                        return jsonify({
                            'success': False,
                            'message': 'Error processing video. Please try again.'
                        }), 500

            except Exception as e:
                logger.error(f"Error updating video: {str(e)}")
                db.session.rollback()
                return jsonify({
                    'success': False,
                    'message': 'An error occurred while updating the video.'
                }), 500

        # GET request - render edit form
        logger.info("Rendering edit form")
        return render_template('video/edit.html', video=video)

    except Exception as e:
        logger.error(f"Unexpected error in edit route: {str(e)}")
        flash('An error occurred while accessing the video.')
        return redirect(url_for('video.list_videos'))

@video.route('/video/<int:video_id>/delete', methods=['POST'])
@login_required
def delete(video_id):
    """Handle video deletion with improved error handling and file cleanup"""
    logger.info(f"Processing delete request for video {video_id} from user {current_user.id}")

    # Add session lock to prevent race conditions
    session_lock = False
    try:
        video = Video.query.get_or_404(video_id)
        logger.info(f"Found video {video_id} with title: {video.title}")

        # Check ownership
        if video.user_id != current_user.id:
            logger.warning(f"Unauthorized delete attempt for video {video_id} by user {current_user.id}")
            return jsonify({
                'success': False,
                'message': 'You do not have permission to delete this video.'
            }), 403

        # Set session lock
        session_lock = True

        # Delete related records first
        try:
            likes_count = VideoLike.query.filter_by(video_id=video_id).count()
            VideoLike.query.filter_by(video_id=video_id).delete()
            logger.info(f"Deleted {likes_count} likes for video {video_id}")
        except SQLAlchemyError as e:
            logger.error(f"Error deleting video likes: {str(e)}")
            db.session.rollback()
            session_lock = False
            return jsonify({
                'success': False,
                'message': 'Database error occurred while deleting video likes.'
            }), 500

        # Delete video files
        video_path = os.path.join(VIDEOS_DIR, video.filename)
        thumbnail_path = os.path.join(THUMBNAILS_DIR, video.thumbnail) if video.thumbnail else None

        file_deletion_errors = []
        try:
            if os.path.exists(video_path):
                os.remove(video_path)
                logger.info(f"Deleted video file: {video_path}")
            else:
                logger.warning(f"Video file not found: {video_path}")
                file_deletion_errors.append("Video file not found")

            if thumbnail_path and os.path.exists(thumbnail_path):
                os.remove(thumbnail_path)
                logger.info(f"Deleted thumbnail file: {thumbnail_path}")
            elif thumbnail_path:
                logger.warning(f"Thumbnail file not found: {thumbnail_path}")
                file_deletion_errors.append("Thumbnail file not found")

        except OSError as e:
            logger.error(f"Error deleting video files: {str(e)}")
            file_deletion_errors.append(f"File system error: {str(e)}")

        # Delete video record
        try:
            db.session.delete(video)
            db.session.commit()
            session_lock = False
            logger.info(f"Video record {video_id} deleted successfully")

            return jsonify({
                'success': True,
                'message': 'Video deleted successfully.',
                'redirect_url': url_for('video.list_videos'),
                'warnings': file_deletion_errors if file_deletion_errors else None
            })

        except SQLAlchemyError as e:
            error_msg = str(e)
            logger.error(f"Database error while deleting video record: {error_msg}")
            if session_lock:
                db.session.rollback()
                session_lock = False
            return jsonify({
                'success': False,
                'message': f'Database error occurred while deleting the video record: {error_msg}'
            }), 500

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Unexpected error in delete route for video {video_id}: {error_msg}")
        if session_lock:
            db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'An unexpected error occurred: {error_msg}'
        }), 500

    finally:
        # Ensure session is cleaned up
        if session_lock:
            try:
                db.session.rollback()
            except Exception as e:
                logger.error(f"Error in final session cleanup: {str(e)}")

@video.route('/video/<int:video_id>/like', methods=['POST'])
@login_required
def like(video_id):
    try:
        if current_user.user_type != 'jobseeker':
            return jsonify({'error': 'Only job seekers can like videos'}), 403

        video = Video.query.get_or_404(video_id)
        existing_like = VideoLike.query.filter_by(
            user_id=current_user.id,
            video_id=video_id
        ).first()

        if existing_like:
            db.session.delete(existing_like)
            video.likes = VideoLike.query.filter_by(video_id=video_id).count()
            db.session.commit()
            return jsonify({
                'status': 'unliked',
                'likes': video.likes
            })
        else:
            new_like = VideoLike(user_id=current_user.id, video_id=video_id)
            db.session.add(new_like)
            video.likes = VideoLike.query.filter_by(video_id=video_id).count() + 1
            db.session.commit()
            return jsonify({
                'status': 'liked',
                'likes': video.likes
            })

    except Exception as e:
        logger.error(f"Error processing like for video {video_id}: {str(e)}")
        db.session.rollback()
        return jsonify({'error': 'An error occurred while processing your request'}), 500

@video.route('/thumbnail/<path:filename>')
def get_thumbnail(filename):
    """Get video thumbnail image"""
    try:
        if os.path.exists(os.path.join(THUMBNAILS_DIR, filename)) and os.path.getsize(os.path.join(THUMBNAILS_DIR, filename)) > 0:
            return send_from_directory(THUMBNAILS_DIR, filename)

        video_filename = filename.replace('_thumb.jpg', '')
        video_files = [f for f in os.listdir(VIDEOS_DIR) if f.startswith(video_filename.split('_')[0])]

        if video_files:
            video_path = os.path.join(VIDEOS_DIR, video_files[0])
            thumbnail_path = os.path.join(THUMBNAILS_DIR, filename)

            success = generate_thumbnail_at_timestamp(video_path, thumbnail_path, 1)
            if success and os.path.exists(thumbnail_path) and os.path.getsize(thumbnail_path) > 0:
                return send_from_directory(THUMBNAILS_DIR, filename)

        return send_from_directory('static', 'default-thumbnail.jpg')

    except Exception as e:
        logger.error(f"Error serving thumbnail {filename}: {str(e)}")
        return send_from_directory('static', 'default-thumbnail.jpg')

@video.route('/video/preview/new', methods=['POST'])
@login_required
def preview_new_route(): #Renamed to avoid conflict
    """Handle new video preview submission"""
    logger.info("Handling video preview submission")

    try:
        if not ensure_directory_permissions():
            logger.error("Failed to set directory permissions")
            return jsonify({'error': 'Server configuration error'}), 500

        # Validate video file
        if 'video' not in request.files:
            logger.warning("No video file in request")
            return jsonify({'error': 'No video file provided'}), 400

        video_file = request.files['video']
        if not video_file or video_file.filename == '':
            logger.warning("Empty video file or filename")
            return jsonify({'error': 'Empty video file'}), 400

        # Get form data with validation
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        script_content = request.form.get('script_content', '').strip()

        logger.info(f"Processing video with title: {title}, description length: {len(description)}, script length: {len(script_content)}")

        # Generate unique filename and save video
        filename = f"{str(uuid.uuid4())}_recorded_video.webm"
        video_path = os.path.join(VIDEOS_DIR, filename)
        logger.info(f"Saving video to: {video_path}")

        # Ensure upload directory exists with proper permissions
        os.makedirs(os.path.dirname(video_path), exist_ok=True)

        video_file.save(video_path)
        os.chmod(video_path, 0o644)
        logger.info("Video file saved successfully")

        # Generate thumbnail
        thumbnail_filename = f"{filename.split('.')[0]}_thumb.jpg"
        thumbnail_path = os.path.join(THUMBNAILS_DIR, thumbnail_filename)
        logger.info(f"Generating thumbnail at: {thumbnail_path}")

        success, error = generate_thumbnail(video_path, thumbnail_path)
        if not success:
            logger.warning(f"Thumbnail generation warning: {error}")

        # Create video record
        new_video = Video(
            title=title if title else 'Recorded Video',
            description=description if description else '',
            filename=filename,
            thumbnail=thumbnail_filename,
            user_id=current_user.id,
            script_content=script_content if script_content else None
        )

        db.session.add(new_video)
        db.session.commit()
        logger.info(f"Video record created successfully with ID: {new_video.id}")

        return jsonify({
            'success': True,
            'video_id': new_video.id,
            'redirect_url': url_for('video.view', video_id=new_video.id)
        })

    except Exception as e:
        logger.error(f"Error handling video preview: {str(e)}")
        # Clean up files if they exist
        try:
            if 'video_path' in locals() and os.path.exists(video_path):
                os.remove(video_path)
                logger.info(f"Cleaned up video file: {video_path}")
            if 'thumbnail_path' in locals() and os.path.exists(thumbnail_path):
                os.remove(thumbnail_path)
                logger.info(f"Cleaned up thumbnail file: {thumbnail_path}")
        except Exception as cleanup_error:
            logger.error(f"Error cleaning up files: {str(cleanup_error)}")

        return jsonify({
            'error': "Failed to process video. Please try again."
        }), 400

@video.route('/video/upload/new', methods=['POST'])
@login_required
def upload_new():
    """Handle video upload functionality"""
    logger.info("Handling new video upload request")

    try:
        # Check user type
        if current_user.user_type != 'jobseeker':
            logger.warning(f"Access denied for user {current_user.id} - not a jobseeker")
            return jsonify({
                'success': False,
                'error': 'Access denied. This page is only for job seekers.'
            }), 403

        # Ensure upload directories exist
        if not ensure_directory_permissions():
            logger.error("Failed to set directory permissions")
            return jsonify({
                'success': False,
                'error': 'Server configuration error. Pleasetry again later.'
            }), 500

        # Validate video file
        if 'video' not in request.files:
            logger.warning("No video file in request")
            return jsonify({
                'success': False,
                'error': 'No video file provided'
            }), 400

        video_file = request.files['video']
        if not video_file or video_file.filename == '':
            logger.warning("Empty video file or filename")
            return jsonify({
                'success': False,
                'error': 'Empty video file'
            }), 400

        # Get and validate form data
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        script_content = request.form.get('script_content', '').strip()

        if not title or len(title) < 3:
            return jsonify({
                'success': False,
                'error': 'Title is required and must be at least 3 characters'
            }), 400

        if not description or len(description) < 10:
            return jsonify({
                'success': False,
                'error': 'Description is required and must be at least 10 characters'
            }), 400

        try:
            # Generate unique filename and save video
            filename = secure_filename(f"{uuid.uuid4()}_recorded_video.webm")
            video_path = os.path.join(VIDEOS_DIR, filename)

            # Ensure upload directory exists with proper permissions
            os.makedirs(os.path.dirname(video_path), exist_ok=True)

            # Save video file
            video_file.save(video_path)
            os.chmod(video_path, 0o644)
            logger.info(f"Video file saved successfully: {video_path}")

            # Generate thumbnail
            thumbnail_filename = f"{filename.split('.')[0]}_thumb.jpg"
            thumbnail_path = os.path.join(THUMBNAILS_DIR, thumbnail_filename)
            success, error = generate_thumbnail(video_path, thumbnail_path)
            if not success:
                logger.warning(f"Thumbnail generation warning: {error}")

            # Create video record
            new_video = Video(
                title=title,
                description=description,
                filename=filename,
                thumbnail=thumbnail_filename,
                user_id=current_user.id,
                script_content=script_content if script_content else None
            )
            db.session.add(new_video)
            db.session.commit()
            logger.info(f"Video record created successfully: {new_video.id}")

            return jsonify({
                'success': True,
                'message': 'Video uploaded successfully!',
                'redirect_url': url_for('video.view', video_id=new_video.id)
            })

        except Exception as e:
            logger.error(f"Error processing video: {str(e)}")
            # Clean up any files if they exist
            if 'video_path' in locals():
                cleanup_files(video_path, thumbnail_path if 'thumbnail_path' in locals() else None)
            db.session.rollback()
            return jsonify({
                'success': False,
                'error': 'Failed to process video. Please try again.'
            }), 500

    except Exception as e:
        logger.error(f"Unexpected error in upload_new: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'An unexpected error occurred. Please try again.'
        }), 500

def cleanup_files(*file_paths):
    """Helper function to clean up files"""
    for path in file_paths:
        if path and os.path.exists(path):
            try:
                os.remove(path)
                logger.info(f"Cleaned up file: {path}")
            except Exception as e:
                logger.error(f"Error cleaning up file {path}: {str(e)}")

@video.route('/static/uploads/videos/<path:filename>')
def serve_video(filename):
    """Serve video files from the uploads directory"""
    logger.info(f"Serving video file: {filename}")
    try:
        return send_from_directory(VIDEOS_DIR, filename)
    except Exception as e:
        logger.error(f"Error serving video file {filename}: {str(e)}")
        return "Video not found", 404

@video.route('/csrf-token')
def get_csrf_token():
    """Generate and return a new CSRF token"""
    token = generate_csrf()
    return jsonify({'token': token})

# Add the following routes after the existing video routes

@video.route('/video/<int:video_id>/suggest-tags', methods=['POST'])
@login_required
def suggest_video_tags(video_id):
    """Get AI-powered tag suggestions for a video"""
    try:
        logger.info(f"Starting tag suggestion for video {video_id}")
        video = Video.query.get_or_404(video_id)

        if video.user_id != current_user.id:
            logger.warning(f"Unauthorized tag suggestion attempt for video {video_id}")
            return jsonify({'status': 'error', 'message': 'Unauthorized'}), 403

        content = f"Title: {video.title}\nDescription: {video.description or ''}"
        if hasattr(video, 'script_content') and video.script_content:
            content += f"\nScript: {video.script_content}"

        try:
            client = OpenAI()
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "Generate 5-7 relevant tags as a JSON array of objects with 'name' and 'type' fields. Types should be either 'skill', 'industry', or 'role'. Each object should be like {'name': 'tag_name', 'type': 'tag_type'}"},
                    {"role": "user", "content": f"Generate relevant professional tags for this video resume content:\n{content}"}
                ],
                temperature=0.7,
                max_tokens=200
            )

            tags_data = json.loads(response.choices[0].message.content)
            logger.info(f"Generated tags: {tags_data}")

        except Exception as e:
            logger.error(f"OpenAI API error: {str(e)}")
            return jsonify({'status': 'error', 'message': 'Failed to generate suggestions'}), 500

        suggested_tags = []
        existing_tags = {tag.name.lower() for tag in video.tags}

        for tag_data in tags_data:
            if not isinstance(tag_data, dict) or 'name' not in tag_data or 'type' not in tag_data:
                continue

            tag_name = tag_data['name'].lower()
            if tag_name not in existing_tags:
                tag = Tag.query.filter_by(name=tag_name).first()
                if not tag:
                    tag = Tag(name=tag_name, type=tag_data['type'])
                    db.session.add(tag)
                    db.session.flush()

                video_tag = VideoTag(
                    video_id=video.id,
                    tag_id=tag.id,
                    ai_suggested=True
                )
                db.session.add(video_tag)
                suggested_tags.append({
                    'name': tag_name,
                    'type': tag_data['type']
                })

        if suggested_tags:
            db.session.commit()
            logger.info(f"Added {len(suggested_tags)} suggested tags to video {video_id}")
            return jsonify({
                'status': 'success',
                'suggested_tags': suggested_tags
            })

        return jsonify({'status': 'success', 'message': 'No new tags to suggest'})

    except Exception as e:
        logger.error(f"Error suggesting tags: {str(e)}")
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500

@video.route('/video/<int:video_id>/tags', methods=['POST'])
@login_required
def update_video_tags(video_id):
    """Update tags for a specific video"""
    try:
        video = Video.query.get_or_404(video_id)
        if video.user_id != current_user.id:
            return jsonify({'status': 'error', 'message': 'Unauthorized'}), 403

        tag_ids = request.json.get('tag_ids', [])
        logger.info(f"Updating tags for video {video_id} with tags: {tag_ids}")

        # Remove existing tags
        VideoTag.query.filter_by(video_id=video.id).delete()

        # Add new tags
        for tag_id in tag_ids:
            video_tag = VideoTag(
                video_id=video.id,
                tag_id=tag_id,
                ai_suggested=False
            )
            db.session.add(video_tag)

        db.session.commit()
        logger.info(f"Updated tags for video {video_id}")
        return jsonify({'status': 'success', 'message': 'Tags updated successfully'})

    except Exception as e:
        logger.error(f"Error updating video tags: {str(e)}")
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500

@video.route('/video/<int:video_id>/tags', methods=['GET'])
@login_required
def get_video_tags(video_id):
    """Get all tags for a video"""
    try:
        video = Video.query.get_or_404(video_id)
        tags = [{'id': tag.id, 'name': tag.name} for tag in video.tags]
        return jsonify({'tags': tags})
    except Exception as e:
        logger.error(f"Error getting video tags: {str(e)}")
        return jsonify({'error': 'Failed to get tags'}), 500

@video.route('/video/<int:video_id>/tags/<int:tag_id>', methods=['DELETE'])
@login_required
def remove_video_tag(video_id, tag_id):
    """Remove a tag from a video"""
    try:
        video = Video.query.get_or_404(video_id)

        if video.user_id != current_user.id:
            return jsonify({'error': 'Unauthorized'}), 403

        tag = Tag.query.get_or_404(tag_id)
        if tag in video.tags:
            video.tags.remove(tag)
            db.session.commit()
            logger.info(f"Removed tag {tag.name} from video {video_id}")
            return jsonify({'status': 'success'})
        return jsonify({'error': 'Tag not found on video'}), 404

    except Exception as e:
        logger.error(f"Error removing video tag: {str(e)}")
        db.session.rollback()
        return jsonify({'error': 'Failed to remove tag'}), 500

@video.route('/video/tags/add', methods=['POST'])
@login_required
def add_tag():
    """Handle tag creation"""
    try:
        tag_name = request.form.get('tag_name', '').strip().lower()
        tag_type = request.form.get('tag_type', 'skill').strip().lower()

        if not tag_name:
            return jsonify({
                'success': False,
                'message': 'Tag name is required'
            }), 400

        # Check if tag already exists
        existing_tag = Tag.query.filter_by(name=tag_name).first()
        if existing_tag:
            return jsonify({
                'success': False,
                'message': 'Tag already exists'
            }), 400

        # Create new tag
        new_tag = Tag(name=tag_name, type=tag_type)
        db.session.add(new_tag)
        db.session.commit()

        return jsonify({
            'success': True,
            'tag': {
                'id': new_tag.id,
                'name': new_tag.name,
                'type': new_tag.type
            }
        })

    except Exception as e:
        logger.error(f"Error creating tag: {str(e)}")
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': 'An error occurred while creating the tag'
        }), 500

@video.route('/video/tags/search')
@login_required
def search_tags():
    """Search for tags based on query"""
    try:
        query = request.args.get('q', '').lower()
        if not query:
            return jsonify({
                'status': 'success',
                'tags': []
            })

        tags = Tag.query.filter(Tag.name.ilike(f'%{query}%')).all()
        return jsonify({
            'status': 'success',
            'tags': [{
                'id': tag.id,
                'name': tag.name,
                'type': tag.type
            } for tag in tags]
        })

    except Exception as e:
        logger.error(f"Error searching tags: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@video.route('/video/tags')
@login_required
def manage_tags():
    """Handle video tags management page"""
    try:
        # Get user's tags for display
        user_tags = Tag.query.join(VideoTag).join(Video).filter(Video.user_id == current_user.id).distinct().all()
        
        # Get AI suggested tags with usage count
        ai_suggested_tags = db.session.query(Tag, func.count(VideoTag.video_id).label('count'))\
            .join(VideoTag)\
            .filter(VideoTag.ai_suggested == True)\
            .group_by(Tag.id)\
            .order_by(desc('count'))\
            .limit(10)\
            .all()

        return render_template('video/manage_tags.html', 
                             user_tags=user_tags,
                             ai_suggested_tags=ai_suggested_tags)
    except Exception as e:
        logger.error(f"Error accessing tags page: {str(e)}")
        flash('An error occurred while loading tags.', 'danger')
        return redirect(url_for('video.list_videos'))