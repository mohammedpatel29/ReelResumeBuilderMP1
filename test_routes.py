"""Test suite for route definitions and conflicts"""
import pytest
from flask import url_for

def test_no_route_conflicts(app):
    """Test that there are no conflicting routes"""
    routes = []
    for rule in app.url_map.iter_rules():
        route = f"{rule.rule}:{','.join(rule.methods)}"
        assert route not in routes, f"Route conflict detected: {route}"
        routes.append(route)

def test_static_pages_routes(client):
    """Test static page routes"""
    response = client.get('/')
    assert response.status_code == 200

def test_auth_routes(client):
    """Test authentication routes"""
    routes = ['/auth/login', '/auth/signup', '/auth/forgot-password']
    for route in routes:
        response = client.get(route)
        assert response.status_code == 200

def test_protected_routes_redirect(client):
    """Test that protected routes redirect to login"""
    protected_routes = [
        '/profile/setup',
        '/employer/dashboard',
        '/jobseeker/dashboard',
        '/analytics/dashboard',
        '/messaging/messages'
    ]
    for route in protected_routes:
        response = client.get(route)
        assert response.status_code == 302
        assert '/auth/login' in response.location

def test_blueprint_registration(app):
    """Test that all blueprints are registered correctly"""
    expected_blueprints = [
        'static_pages',
        'auth',
        'profile',
        'employer',
        'jobseeker',
        'playlist',
        'video',
        'analytics',
        'messaging',
        'tutorial'
    ]
    
    registered_blueprints = [bp.name for bp in app.blueprints.values()]
    for blueprint in expected_blueprints:
        assert blueprint in registered_blueprints
