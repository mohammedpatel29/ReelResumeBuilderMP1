"""Central blueprint registry for the application"""
from flask import Blueprint
from routes.auth import auth
from routes.profile import profile
from routes.employer import employer
from routes.jobseeker import jobseeker
from routes.playlist import playlist
from routes.video import video
from routes.analytics import analytics
from routes.messaging import messaging
from routes.tutorial import tutorial
from routes.static_pages import static_pages
from routes.tags import tags

# Blueprint registry with explicit prefixes
BLUEPRINTS = [
    # Core routes
    (static_pages, '/'),
    (auth, '/auth'),
    (profile, '/profile'),

    # User type specific routes
    (employer, '/employer'),
    (jobseeker, '/jobseeker'),

    # Feature routes
    (playlist, '/playlist'),
    (video, '/video'),
    (analytics, '/analytics'),
    (messaging, '/messaging'),
    (tutorial, '/tutorial'),
    (tags, '/api')  # All tag-related endpoints under /api prefix
]

def register_blueprints(app):
    """Register all blueprints with the application"""
    for blueprint, url_prefix in BLUEPRINTS:
        app.register_blueprint(blueprint, url_prefix=url_prefix)
        # Log registration for debugging
        app.logger.info(f"Registered blueprint: {blueprint.name} at prefix: {url_prefix}")