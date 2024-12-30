from flask import Blueprint, jsonify, request, current_app
from flask_login import login_required, current_user
from models import Tag, Video, VideoTag, Playlist, PlaylistTag, db
from sqlalchemy import func, desc
import logging
from openai import OpenAI

tags = Blueprint('tags', __name__)
logger = logging.getLogger(__name__)

@tags.route('/api/tags/suggest', methods=['POST'])
@login_required
def suggest_tags():
    """Suggest tags based on video content using AI"""
    try:
        logger.info("Received tag suggestion request")
        data = request.get_json()
        video_id = data.get('video_id')
        content = data.get('content')  # Video title and description

        if not video_id or not content:
            logger.warning("Missing required parameters for tag suggestion")
            return jsonify({
                'success': False,
                'message': 'Missing required parameters'
            }), 400

        client = OpenAI()
        logger.info(f"Making OpenAI API call for video {video_id}")
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{
                "role": "system",
                "content": "You are a professional video tagging assistant. Generate relevant professional tags for the given video content."
            }, {
                "role": "user",
                "content": f"Generate 5 relevant professional tags for this video content: {content}"
            }]
        )

        # Extract tags from AI response
        suggested_tags = []
        if response.choices:
            ai_tags = response.choices[0].message.content.split(',')
            logger.info(f"Generated {len(ai_tags)} tags from AI")
            for tag_name in ai_tags:
                tag_name = tag_name.strip().lower()
                # Create or get existing tag
                tag = Tag.query.filter_by(name=tag_name, type='video').first()
                if not tag:
                    tag = Tag(name=tag_name, type='video')
                    db.session.add(tag)
                    db.session.commit()
                suggested_tags.append({
                    'id': tag.id,
                    'name': tag.name
                })

        return jsonify({
            'success': True,
            'tags': suggested_tags
        })

    except Exception as e:
        logger.error(f"Error suggesting tags: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Failed to generate tag suggestions'
        }), 500

@tags.route('/api/tags/search', methods=['GET'])
def search_tags():
    """Search tags with optional filters"""
    try:
        logger.info("Received tag search request")
        query = request.args.get('q', '').lower()
        tag_type = request.args.get('type', 'all')
        limit = int(request.args.get('limit', 10))

        # Base query
        tag_query = Tag.query

        # Apply filters
        if query:
            tag_query = tag_query.filter(Tag.name.ilike(f'%{query}%'))
        if tag_type != 'all':
            tag_query = tag_query.filter(Tag.type == tag_type)

        # Get most used tags first
        tags = tag_query.join(VideoTag).group_by(Tag.id).order_by(desc(func.count(VideoTag.id))).limit(limit).all()

        logger.info(f"Found {len(tags)} tags matching query: {query}")
        return jsonify({
            'success': True,
            'tags': [{
                'id': tag.id,
                'name': tag.name,
                'type': tag.type
            } for tag in tags]
        })

    except Exception as e:
        logger.error(f"Error searching tags: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Failed to search tags'
        }), 500

@tags.route('/api/video/<int:video_id>/tags', methods=['POST'])
@login_required
def update_video_tags(video_id):
    """Update tags for a video"""
    try:
        logger.info(f"Updating tags for video {video_id}")
        video = Video.query.get_or_404(video_id)
        if video.user_id != current_user.id:
            logger.warning(f"Unauthorized attempt to modify tags for video {video_id}")
            return jsonify({
                'success': False,
                'message': 'Unauthorized to modify tags for this video'
            }), 403

        data = request.get_json()
        tag_ids = data.get('tags', [])

        # Remove existing tags
        VideoTag.query.filter_by(video_id=video_id).delete()

        # Add new tags
        for tag_id in tag_ids:
            video_tag = VideoTag(video_id=video_id, tag_id=tag_id)
            db.session.add(video_tag)

        db.session.commit()
        logger.info(f"Successfully updated tags for video {video_id}")
        return jsonify({
            'success': True,
            'message': 'Tags updated successfully'
        })

    except Exception as e:
        logger.error(f"Error updating video tags: {str(e)}")
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': 'Failed to update tags'
        }), 500

@tags.route('/api/playlist/<int:playlist_id>/tags', methods=['POST'])
@login_required
def update_playlist_tags(playlist_id):
    """Update tags for a playlist"""
    try:
        logger.info(f"Updating tags for playlist {playlist_id}")
        playlist = Playlist.query.get_or_404(playlist_id)
        if playlist.user_id != current_user.id:
            logger.warning(f"Unauthorized attempt to modify tags for playlist {playlist_id}")
            return jsonify({
                'success': False,
                'message': 'Unauthorized to modify tags for this playlist'
            }), 403

        data = request.get_json()
        tag_ids = data.get('tags', [])

        # Remove existing tags
        PlaylistTag.query.filter_by(playlist_id=playlist_id).delete()

        # Add new tags
        for tag_id in tag_ids:
            playlist_tag = PlaylistTag(playlist_id=playlist_id, tag_id=tag_id)
            db.session.add(playlist_tag)

        db.session.commit()
        logger.info(f"Successfully updated tags for playlist {playlist_id}")
        return jsonify({
            'success': True,
            'message': 'Tags updated successfully'
        })

    except Exception as e:
        logger.error(f"Error updating playlist tags: {str(e)}")
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': 'Failed to update tags'
        }), 500