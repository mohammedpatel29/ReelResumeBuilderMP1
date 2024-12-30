"""Test configuration and fixtures"""
import pytest
from app import create_app
from extensions import db

@pytest.fixture
def app():
    """Create application for testing"""
    app = create_app()
    app.config.update({
        'TESTING': True,
        'WTF_CSRF_ENABLED': False,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:'
    })

    # Create tables
    with app.app_context():
        db.create_all()

    yield app

    # Clean up
    with app.app_context():
        db.session.remove()
        db.drop_all()

@pytest.fixture
def client(app):
    """Create test client"""
    return app.test_client()

@pytest.fixture
def runner(app):
    """Create test CLI runner"""
    return app.test_cli_runner()
