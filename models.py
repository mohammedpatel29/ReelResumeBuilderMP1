from datetime import datetime, timedelta
from enum import Enum
from flask_login import UserMixin
from extensions import db
import secrets
from sqlalchemy import Index, desc
import logging

logger = logging.getLogger(__name__)

class UserType(str, Enum):
    """User type enum with case-insensitive comparison"""
    EMPLOYER = 'employer'
    JOBSEEKER = 'jobseeker'

    def __str__(self):
        return self.value.lower()

    def __hash__(self):
        return hash(self.value.upper())

    def __eq__(self, other):
        if isinstance(other, str):
            return self.value.upper() == other.upper()
        if isinstance(other, UserType):
            return self.value.upper() == other.value.upper()
        return False

class User(UserMixin, db.Model):
    """User model with enhanced session handling"""
    __tablename__ = 'user'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    user_type = db.Column(db.String(20), nullable=False)
    first_name = db.Column(db.String(50))
    last_name = db.Column(db.String(50))
    profile_picture = db.Column(db.String(255))
    linkedin_url = db.Column(db.String(255))
    reset_token = db.Column(db.String(100), unique=True)
    reset_token_expires = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True)
    is_deleted = db.Column(db.Boolean, default=False)
    last_login = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __init__(self, **kwargs):
        """Initialize user with proper type conversion"""
        super().__init__(**kwargs)
        if 'user_type' in kwargs:
            self.user_type = str(UserType(kwargs['user_type']))

    @property
    def is_authenticated(self):
        """Check if user is authenticated"""
        return True if not self.is_deleted else False

    @property
    def is_active(self):
        """Check if user is active"""
        return True if not self.is_deleted else False

    @property
    def is_anonymous(self):
        """Check if user is anonymous"""
        return False

    def get_id(self):
        """Get user ID as string"""
        return str(self.id)

    def generate_reset_token(self):
        """Generate password reset token"""
        self.reset_token = secrets.token_urlsafe(32)
        self.reset_token_expires = datetime.utcnow() + timedelta(hours=1)
        return self.reset_token

    def clear_reset_token(self):
        """Clear password reset token"""
        self.reset_token = None
        self.reset_token_expires = None

    def __repr__(self):
        return f'<User {self.email}>'


class JobStatus(Enum):
    ACTIVE = 'active'
    FILLED = 'filled'
    EXPIRED = 'expired'

class EmployerProfile(db.Model):
    __tablename__ = 'employer_profile'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False, unique=True)
    company_name = db.Column(db.String(100), nullable=False)
    company_website = db.Column(db.String(255))
    company_description = db.Column(db.Text)
    company_size = db.Column(db.String(20))
    company_industry = db.Column(db.String(50))
    company_location = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', back_populates='employer_profile')
    job_postings = db.relationship('JobPosting', back_populates='employer', lazy='select')

class JobseekerProfile(db.Model):
    __tablename__ = 'jobseeker_profile'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False, unique=True)
    skills = db.Column(db.JSON, default=lambda: [])
    experience = db.Column(db.JSON, default=lambda: [])
    education = db.Column(db.JSON, default=lambda: [])
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', back_populates='jobseeker_profile')

class Video(db.Model):
    __tablename__ = 'video'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    filename = db.Column(db.String(255), nullable=False)
    thumbnail = db.Column(db.String(255))
    views = db.Column(db.Integer, default=0)
    likes = db.Column(db.Integer, default=0)
    script_content = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship('User', back_populates='videos')
    video_tags = db.relationship('VideoTag', back_populates='video', lazy='select', cascade='all, delete-orphan')
    playlist_entries = db.relationship('PlaylistVideo', back_populates='video', lazy='select')

class Message(db.Model):
    __tablename__ = 'message'

    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    subject = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    sender = db.relationship('User', foreign_keys=[sender_id], back_populates='sent_messages')
    receiver = db.relationship('User', foreign_keys=[receiver_id], back_populates='received_messages')

class JobPosting(db.Model):
    __tablename__ = 'job_posting'

    id = db.Column(db.Integer, primary_key=True)
    employer_id = db.Column(db.Integer, db.ForeignKey('employer_profile.id', ondelete='CASCADE'), nullable=False)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    requirements = db.Column(db.Text)
    responsibilities = db.Column(db.Text)
    status = db.Column(db.Enum(JobStatus), default=JobStatus.ACTIVE)
    required_skills = db.Column(db.JSON, default=lambda: [])
    preferred_skills = db.Column(db.JSON, default=lambda: [])
    experience_level = db.Column(db.String(20))
    matching_score_threshold = db.Column(db.Float, default=0.7)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime)

    employer = db.relationship('EmployerProfile', back_populates='job_postings')
    candidate_matches = db.relationship('CandidateMatch', back_populates='job_posting', lazy='select')

class CandidateMatch(db.Model):
    """Model for storing job posting candidate matches"""
    __tablename__ = 'candidate_match'

    id = db.Column(db.Integer, primary_key=True)
    job_posting_id = db.Column(db.Integer, db.ForeignKey('job_posting.id', ondelete='CASCADE'), nullable=False)
    candidate_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    match_score = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, accepted, rejected
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    job_posting = db.relationship('JobPosting', back_populates='candidate_matches')
    candidate = db.relationship('User', backref=db.backref('job_matches', lazy='dynamic'))

    __table_args__ = (
        Index('idx_candidate_match_job', job_posting_id),
        Index('idx_candidate_match_candidate', candidate_id),
        Index('idx_candidate_match_score', desc(match_score)),
        db.UniqueConstraint('job_posting_id', 'candidate_id', name='uq_candidate_match_job_candidate'),
    )

    def __repr__(self):
        return f'<CandidateMatch {self.id}: Job {self.job_posting_id} -> Candidate {self.candidate_id} (Score: {self.match_score})>'

class Playlist(db.Model):
    """Model for storing video playlists"""
    __tablename__ = 'playlist'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    is_public = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = db.relationship('User', back_populates='playlists')
    videos = db.relationship('PlaylistVideo', back_populates='playlist', lazy='select', cascade='all, delete-orphan')
    playlist_tags = db.relationship('PlaylistTag', back_populates='playlist', lazy='select', cascade='all, delete-orphan')

    __table_args__ = (
        Index('idx_playlist_user', user_id),
        Index('idx_playlist_created', desc(created_at)),
    )

    def __repr__(self):
        return f'<Playlist {self.id}: {self.title}>'

class PlaylistVideo(db.Model):
    """Model for storing videos in playlists"""
    __tablename__ = 'playlist_video'

    id = db.Column(db.Integer, primary_key=True)
    playlist_id = db.Column(db.Integer, db.ForeignKey('playlist.id', ondelete='CASCADE'), nullable=False)
    video_id = db.Column(db.Integer, db.ForeignKey('video.id', ondelete='CASCADE'), nullable=False)
    position = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    playlist = db.relationship('Playlist', back_populates='videos')
    video = db.relationship('Video', back_populates='playlist_entries')

    __table_args__ = (
        Index('idx_playlist_video_playlist', playlist_id),
        Index('idx_playlist_video_video', video_id),
        Index('idx_playlist_video_position', position),
    )

    def __repr__(self):
        return f'<PlaylistVideo {self.playlist_id}:{self.video_id} at position {self.position}>'

class Tag(db.Model):
    """Model for storing tags"""
    __tablename__ = 'tag'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False, unique=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    video_tags = db.relationship('VideoTag', back_populates='tag', lazy='select')
    playlist_tags = db.relationship('PlaylistTag', back_populates='tag', lazy='select')

    def __repr__(self):
        return f'<Tag {self.id}: {self.name}>'

class VideoTag(db.Model):
    """Model for storing video-tag associations"""
    __tablename__ = 'video_tag'

    id = db.Column(db.Integer, primary_key=True)
    video_id = db.Column(db.Integer, db.ForeignKey('video.id', ondelete='CASCADE'), nullable=False)
    tag_id = db.Column(db.Integer, db.ForeignKey('tag.id', ondelete='CASCADE'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    video = db.relationship('Video', back_populates='video_tags')
    tag = db.relationship('Tag', back_populates='video_tags')

    __table_args__ = (
        Index('idx_video_tag_video', video_id),
        Index('idx_video_tag_tag', tag_id),
    )

class PlaylistTag(db.Model):
    """Model for storing playlist-tag associations"""
    __tablename__ = 'playlist_tag'

    id = db.Column(db.Integer, primary_key=True)
    playlist_id = db.Column(db.Integer, db.ForeignKey('playlist.id', ondelete='CASCADE'), nullable=False)
    tag_id = db.Column(db.Integer, db.ForeignKey('tag.id', ondelete='CASCADE'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    playlist = db.relationship('Playlist', back_populates='playlist_tags')
    tag = db.relationship('Tag', back_populates='playlist_tags')

    __table_args__ = (
        Index('idx_playlist_tag_playlist', playlist_id),
        Index('idx_playlist_tag_tag', tag_id),
    )

class UserAchievement(db.Model):
    """Model for storing user achievements"""
    __tablename__ = 'user_achievement'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    achievement_type = db.Column(db.String(50), nullable=False)
    achievement_data = db.Column(db.JSON, default=dict)
    awarded_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    user = db.relationship('User', back_populates='achievements')

    __table_args__ = (
        Index('idx_user_achievement_user', user_id),
        Index('idx_user_achievement_type', achievement_type),
        Index('idx_user_achievement_awarded', desc(awarded_at)),
    )

    def __repr__(self):
        return f'<UserAchievement {self.id}: {self.achievement_type} for User {self.user_id}>'

class BookmarkCandidate(db.Model):
    """Model for storing bookmarked candidates"""
    __tablename__ = 'bookmark_candidate'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    jobseeker_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('idx_bookmark_user', user_id),
        Index('idx_bookmark_jobseeker', jobseeker_id),
        Index('idx_bookmark_created', desc(created_at)),
    )

    def __repr__(self):
        return f'<BookmarkCandidate {self.id}: {self.user_id} -> {self.jobseeker_id}>'

class VideoLike(db.Model):
    """Model for storing video likes"""
    __tablename__ = 'video_like'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    video_id = db.Column(db.Integer, db.ForeignKey('video.id', ondelete='CASCADE'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    user = db.relationship('User', backref=db.backref('video_likes', lazy='dynamic'))
    video = db.relationship('Video', backref=db.backref('user_likes', lazy='dynamic'))

    __table_args__ = (
        Index('idx_video_like_user', user_id),
        Index('idx_video_like_video', video_id),
        Index('idx_video_like_created', desc(created_at)),
        db.UniqueConstraint('user_id', 'video_id', name='uq_video_like_user_video'),
    )

    def __repr__(self):
        return f'<VideoLike {self.id}: User {self.user_id} -> Video {self.video_id}>'


#Relationships
    sent_messages = db.relationship('Message', foreign_keys='Message.sender_id', back_populates='sender', lazy='select')
    received_messages = db.relationship('Message', foreign_keys='Message.receiver_id', back_populates='receiver', lazy='select')
    achievements = db.relationship('UserAchievement', back_populates='user', lazy='select')
    playlists = db.relationship('Playlist', back_populates='user', lazy='select')
    employer_profile = db.relationship('EmployerProfile', back_populates='user', uselist=False)
    jobseeker_profile = db.relationship('JobseekerProfile', back_populates='user', uselist=False)
    videos = db.relationship('Video', back_populates='user', lazy='select')