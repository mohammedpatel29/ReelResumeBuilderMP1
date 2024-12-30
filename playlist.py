import logging
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_file
from flask_login import login_required, current_user
from models import db, Playlist, PlaylistVideo, Video, Tag, VideoTag, PlaylistTag
from sqlalchemy import desc
import qrcode
import io
from openai import OpenAI
from .forms import PlaylistForm, AddVideoForm
import json

# Enhanced logging setup
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

playlist = Blueprint('playlist', __name__)

@playlist.route('/<int:playlist_id>/suggest-tags', methods=['POST'])
@login_required
def suggest_tags(playlist_id):
    """Get AI-powered tag suggestions for a playlist"""
    try:
        logger.debug(f"Starting tag suggestion for playlist {playlist_id}")
        logger.debug(f"Request headers: {dict(request.headers)}")

        playlist = Playlist.query.get_or_404(playlist_id)

        if playlist.user_id != current_user.id:
            logger.warning(f"Unauthorized tag suggestion attempt for playlist {playlist_id}")
            return jsonify({'status': 'error', 'message': 'Unauthorized'}), 403

        # Get video content from the playlist
        videos = Video.query.join(PlaylistVideo).filter(
            PlaylistVideo.playlist_id == playlist_id
        ).all()

        if not videos:
            logger.warning(f"No videos found in playlist {playlist_id}")
            return jsonify({'status': 'error', 'message': 'No videos in playlist'}), 400

        content = "\n".join([
            f"Title: {video.title}\nDescription: {video.description or ''}"
            for video in videos
        ])

        try:
            client = OpenAI()
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "Generate 5-7 relevant tags as a JSON array of strings"},
                    {"role": "user", "content": f"Generate relevant tags for these videos:\n{content}"}
                ],
                temperature=0.7,
                max_tokens=200
            )

            suggested_tags = json.loads(response.choices[0].message.content)
            logger.debug(f"Generated tags: {suggested_tags}")

            # Add new tags to the playlist
            added_tags = []
            for tag_name in suggested_tags:
                # Create or get existing tag
                tag = Tag.query.filter_by(name=tag_name.lower()).first()
                if not tag:
                    tag = Tag(name=tag_name.lower(), type='suggested')
                    db.session.add(tag)
                    db.session.flush()

                # Check if tag is already added to playlist
                existing_tag = PlaylistTag.query.filter_by(
                    playlist_id=playlist_id,
                    tag_id=tag.id
                ).first()

                if not existing_tag:
                    playlist_tag = PlaylistTag(playlist_id=playlist_id, tag_id=tag.id)
                    db.session.add(playlist_tag)
                    added_tags.append(tag_name)

            if added_tags:
                db.session.commit()
                logger.info(f"Added {len(added_tags)} suggested tags to playlist {playlist_id}")
                return jsonify({
                    'status': 'success',
                    'suggested_tags': added_tags
                })
            else:
                return jsonify({
                    'status': 'success',
                    'message': 'No new tags to suggest'
                })

        except Exception as e:
            logger.error(f"OpenAI API error: {str(e)}")
            return jsonify({'status': 'error', 'message': 'Failed to generate suggestions'}), 500

    except Exception as e:
        logger.error(f"Error suggesting tags: {str(e)}")
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500

@playlist.route('/<int:playlist_id>/tags', methods=['POST'])
@login_required
def add_tag(playlist_id):
    """Add a tag to a playlist"""
    try:
        logger.debug(f"Adding tag to playlist {playlist_id}")
        logger.debug(f"Request headers: {dict(request.headers)}")
        logger.debug(f"Form data: {request.form}")

        playlist = Playlist.query.get_or_404(playlist_id)

        if playlist.user_id != current_user.id:
            logger.warning(f"Unauthorized tag addition attempt for playlist {playlist_id}")
            return jsonify({'status': 'error', 'message': 'Unauthorized'}), 403

        tag_name = request.form.get('tag_name')
        if not tag_name:
            logger.warning("Tag name not provided in request")
            return jsonify({'status': 'error', 'message': 'Tag name is required'}), 400

        # Normalize tag name - trim whitespace and convert to lowercase
        tag_name = tag_name.strip().lower()
        if not tag_name:
            return jsonify({'status': 'error', 'message': 'Tag name cannot be empty'}), 400

        # Create or get existing tag
        tag = Tag.query.filter_by(name=tag_name).first()
        if not tag:
            tag = Tag(name=tag_name, type='user')
            db.session.add(tag)
            db.session.flush()

        # Check if tag is already added to playlist
        existing_tag = PlaylistTag.query.filter_by(
            playlist_id=playlist_id,
            tag_id=tag.id
        ).first()

        if existing_tag:
            logger.warning(f"Tag {tag_name} already exists in playlist {playlist_id}")
            return jsonify({'status': 'error', 'message': 'Tag already exists in playlist'}), 400

        # Add tag to playlist
        playlist_tag = PlaylistTag(playlist_id=playlist_id, tag_id=tag.id)
        db.session.add(playlist_tag)
        db.session.commit()
        logger.info(f"Successfully added tag {tag_name} to playlist {playlist_id}")

        return jsonify({
            'status': 'success',
            'tag': {
                'id': tag.id,
                'name': tag.name,
                'type': tag.type
            }
        })

    except Exception as e:
        logger.error(f"Error adding tag: {str(e)}")
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500

@playlist.route('/playlists/<int:playlist_id>/tags/<int:tag_id>', methods=['DELETE'])
@login_required
def remove_tag(playlist_id, tag_id):
    """Remove a tag from a playlist"""
    try:
        playlist = Playlist.query.get_or_404(playlist_id)

        if playlist.user_id != current_user.id:
            return jsonify({'status': 'error', 'message': 'Unauthorized'}), 403

        playlist_tag = PlaylistTag.query.filter_by(
            playlist_id=playlist_id,
            tag_id=tag_id
        ).first_or_404()

        db.session.delete(playlist_tag)
        db.session.commit()

        return jsonify({'status': 'success'})

    except Exception as e:
        logger.error(f"Error removing tag: {str(e)}")
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500

@playlist.route('/playlists')
@login_required
def list_playlists():
    """Show all playlists for the current user"""
    if current_user.user_type != 'jobseeker':
        flash('Only job seekers can manage playlists')
        return redirect(url_for('dashboard'))

    playlists = Playlist.query.filter_by(user_id=current_user.id).order_by(desc(Playlist.created_at)).all()
    return render_template('playlist/list.html', playlists=playlists)

@playlist.route('/playlists/create', methods=['GET', 'POST'])
@login_required
def create_playlist():
    """Create a new playlist"""
    if current_user.user_type != 'jobseeker':
        flash('Only job seekers can create playlists')
        return redirect(url_for('dashboard'))

    form = PlaylistForm()

    if request.method == 'POST' and form.validate_on_submit():
        try:
            playlist = Playlist(
                title=form.title.data,
                description=form.description.data,
                user_id=current_user.id,
                is_public=form.is_public.data
            )

            # Generate share token if playlist is public
            if form.is_public.data:
                playlist.generate_share_token()

            db.session.add(playlist)
            db.session.commit()
            logger.info(f"Created new playlist: {playlist.id} by user: {current_user.id}")

            flash('Playlist created successfully!', 'success')
            return redirect(url_for('playlist.view_playlist', playlist_id=playlist.id))
        except Exception as e:
            logger.error(f"Error creating playlist: {str(e)}")
            db.session.rollback()
            flash('Error creating playlist. Please try again.', 'error')
            return redirect(url_for('playlist.create_playlist'))

    return render_template('playlist/create.html', form=form)

@playlist.route('/playlists/<int:playlist_id>')
@login_required
def view_playlist(playlist_id):
    """View a specific playlist and its videos"""
    playlist = Playlist.query.get_or_404(playlist_id)

    # Check access permissions
    if not playlist.is_public and playlist.user_id != current_user.id:
        flash('You do not have permission to view this playlist')
        return redirect(url_for('dashboard'))

    # Set up forms
    playlist_form = PlaylistForm()
    add_video_form = AddVideoForm()

    # Populate video choices
    add_video_form.video_id.choices = [
        (v.id, v.title) for v in current_user.videos
    ]

    # Increment view count for public playlists
    if playlist.is_public and (not current_user.is_authenticated or playlist.user_id != current_user.id):
        playlist.view_count += 1
        db.session.commit()

    # Get playlist videos with order
    playlist_videos = db.session.query(
        Video, PlaylistVideo.order
    ).join(
        PlaylistVideo, Video.id == PlaylistVideo.video_id
    ).filter(
        PlaylistVideo.playlist_id == playlist_id
    ).order_by(
        PlaylistVideo.order
    ).all()

    # Get tags for the playlist
    tags = Tag.query.join(PlaylistTag).filter(PlaylistTag.playlist_id == playlist_id).all()

    return render_template('playlist/view.html', 
                         playlist=playlist, 
                         playlist_videos=playlist_videos,
                         tags=tags,
                         form=playlist_form,
                         add_video_form=add_video_form)

@playlist.route('/playlists/<int:playlist_id>/add-video', methods=['POST'])
@login_required
def add_video(playlist_id):
    """Add a video to playlist"""
    playlist = Playlist.query.get_or_404(playlist_id)

    if playlist.user_id != current_user.id:
        flash('You do not have permission to modify this playlist')
        return redirect(url_for('dashboard'))

    add_video_form = AddVideoForm()
    add_video_form.video_id.choices = [(v.id, v.title) for v in current_user.videos]

    if not add_video_form.validate_on_submit():
        logger.error(f"Form validation failed: {add_video_form.errors}")
        flash('Invalid form submission. Please try again.')
        return redirect(url_for('playlist.view_playlist', playlist_id=playlist_id))

    try:
        video_id = add_video_form.video_id.data

        # Check if video exists and belongs to user
        video = Video.query.get_or_404(video_id)
        if video.user_id != current_user.id:
            flash('You can only add your own videos to playlists')
            return redirect(url_for('playlist.view_playlist', playlist_id=playlist_id))

        # Check if video is already in playlist
        existing = PlaylistVideo.query.filter_by(
            playlist_id=playlist_id,
            video_id=video_id
        ).first()

        if existing:
            flash('Video is already in playlist')
            return redirect(url_for('playlist.view_playlist', playlist_id=playlist_id))

        # Get max order
        max_order = db.session.query(db.func.max(PlaylistVideo.order)).filter(
            PlaylistVideo.playlist_id == playlist_id
        ).scalar() or 0

        # Add video to playlist
        playlist_video = PlaylistVideo(
            playlist_id=playlist_id,
            video_id=video_id,
            order=max_order + 1
        )

        db.session.add(playlist_video)
        db.session.commit()
        logger.info(f"Added video {video_id} to playlist {playlist_id}")

        flash('Video added to playlist successfully!')
    except Exception as e:
        logger.error(f"Error adding video to playlist: {str(e)}")
        db.session.rollback()
        flash('Error adding video to playlist. Please try again.')

    return redirect(url_for('playlist.view_playlist', playlist_id=playlist_id))

@playlist.route('/playlists/<int:playlist_id>/qr')
def get_playlist_qr(playlist_id):
    """Generate QR code for playlist sharing"""
    try:
        playlist = Playlist.query.get_or_404(playlist_id)

        if not playlist.is_public:
            flash('Only public playlists can be shared via QR code')
            return redirect(url_for('playlist.view_playlist', playlist_id=playlist_id))

        # Generate the share URL
        share_url = url_for('playlist.view_shared_playlist', 
                        share_token=playlist.share_token,
                        _external=True)

        # Create QR code using proper initialization
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=5
        )
        qr.add_data(share_url)
        qr.make(fit=True)

        # Create image and save to bytes
        img = qr.make_image(fill_color="black", back_color="white")
        img_bytes = io.BytesIO()
        img.save(img_bytes, 'PNG')
        img_bytes.seek(0)

        logger.info(f"Generated QR code for playlist {playlist_id}")
        return send_file(img_bytes, mimetype='image/png')
    except Exception as e:
        logger.error(f"Error generating QR code for playlist {playlist_id}: {str(e)}")
        flash('Error generating QR code')
        return redirect(url_for('playlist.view_playlist', playlist_id=playlist_id))

@playlist.route('/playlists/shared/<share_token>')
def view_shared_playlist(share_token):
    """View a shared playlist using its share token"""
    playlist = Playlist.query.filter_by(share_token=share_token, is_public=True).first_or_404()

    # Increment view count
    playlist.view_count += 1
    db.session.commit()

    # Get playlist videos with order
    playlist_videos = db.session.query(
        Video, PlaylistVideo.order
    ).join(
        PlaylistVideo, Video.id == PlaylistVideo.video_id
    ).filter(
        PlaylistVideo.playlist_id == playlist.id
    ).order_by(
        PlaylistVideo.order
    ).all()

    return render_template('playlist/shared.html', 
                         playlist=playlist, 
                         playlist_videos=playlist_videos)

@playlist.route('/playlists/<int:playlist_id>/toggle-public', methods=['POST'])
@login_required
def toggle_public(playlist_id):
    """Toggle playlist's public status"""
    playlist = Playlist.query.get_or_404(playlist_id)

    if playlist.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403

    playlist.is_public = not playlist.is_public
    if playlist.is_public and not playlist.share_token:
        playlist.generate_share_token()

    db.session.commit()
    return jsonify({
        'status': 'success',
        'is_public': playlist.is_public,
        'share_token': playlist.share_token if playlist.is_public else None
    })


@playlist.route('/playlists/<int:playlist_id>/remove-video/<int:video_id>', methods=['POST'])
@login_required
def remove_video(playlist_id, video_id):
    """Remove a video from playlist"""
    playlist = Playlist.query.get_or_404(playlist_id)
    
    if playlist.user_id != current_user.id:
        flash('You do not have permission to modify this playlist')
        return redirect(url_for('dashboard'))
        
    playlist_video = PlaylistVideo.query.filter_by(
        playlist_id=playlist_id,
        video_id=video_id
    ).first_or_404()
    
    db.session.delete(playlist_video)
    db.session.commit()
    
    flash('Video removed from playlist successfully!')
    return redirect(url_for('playlist.view_playlist', playlist_id=playlist_id))

@playlist.route('/playlists/<int:playlist_id>/reorder', methods=['POST'])
@login_required
def reorder_videos(playlist_id):
    """Reorder videos in playlist"""
    playlist = Playlist.query.get_or_404(playlist_id)
    
    if playlist.user_id != current_user.id:
        flash('You do not have permission to modify this playlist')
        return redirect(url_for('dashboard'))
        
    video_order = request.get_json()
    
    for video_id, order in video_order.items():
        playlist_video = PlaylistTag.query.filter_by(
            playlist_id=playlist_id,
            video_id=video_id
        ).first()
        
        if playlist_video:
            playlist_video.order = order
            
    db.session.commit()
    return {'status': 'success'}
@playlist.route('/playlists/<int:playlist_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_playlist(playlist_id):
    """Edit playlist details"""
    playlist = Playlist.query.get_or_404(playlist_id)
    
    if playlist.user_id != current_user.id:
        flash('You do not have permission to edit this playlist')
        return redirect(url_for('dashboard'))
        
    form = PlaylistForm(obj=playlist) # Use form to pre-populate data
    
    if request.method == 'POST' and form.validate_on_submit():
        try:
            playlist.title = form.title.data
            playlist.description = form.description.data
            playlist.is_public = form.is_public.data
            if playlist.is_public and not playlist.share_token:
                playlist.generate_share_token()
            db.session.commit()
            flash('Playlist updated successfully!')
            return redirect(url_for('playlist.view_playlist', playlist_id=playlist_id))
        except Exception as e:
            logger.error(f"Error updating playlist {playlist_id}: {str(e)}")
            flash('Error updating playlist. Please try again.')
            return redirect(url_for('playlist.edit_playlist', playlist_id=playlist_id))
        
    return render_template('playlist/edit.html', playlist=playlist, form=form)