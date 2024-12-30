import os
import subprocess
from werkzeug.utils import secure_filename
import uuid

def generate_thumbnail(video_path, output_dir):
    thumbnail_filename = f"{os.path.splitext(os.path.basename(video_path))[0]}.jpg"
    thumbnail_path = os.path.join(output_dir, thumbnail_filename)
    
    command = [
        'ffmpeg', '-i', video_path,
        '-ss', '00:00:01',
        '-vframes', '1',
        '-vf', 'scale=480:-1',
        '-y',
        thumbnail_path
    ]
    
    try:
        subprocess.run(command, check=True, capture_output=True)
        return thumbnail_filename
    except:
        return None

def process_video_upload(file, videos_dir, thumbnails_dir):
    """Process video upload and generate thumbnail"""
    # Generate unique filename
    original_filename = secure_filename(file.filename)
    filename = f"{uuid.uuid4()}_{original_filename}"
    video_path = os.path.join(videos_dir, filename)
    
    # Ensure directories exist
    os.makedirs(videos_dir, exist_ok=True)
    os.makedirs(thumbnails_dir, exist_ok=True)
    
    # Save uploaded video
    file.save(video_path)
    
    # Generate thumbnail
    thumbnail_filename = generate_thumbnail(video_path, thumbnails_dir)
    
    if not thumbnail_filename:
        raise Exception("Failed to generate thumbnail")
    
    return filename, thumbnail_filename
