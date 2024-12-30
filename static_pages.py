from flask import Blueprint, render_template
from datetime import datetime

static_pages = Blueprint('static_pages', __name__)

@static_pages.context_processor
def inject_now():
    return {'now': datetime.utcnow()}

@static_pages.route('/')
def index():
    """Render the home page"""
    return render_template('index.html')

@static_pages.route('/employers')
def employers():
    """Render the employers page"""
    return render_template('static/employers.html')

@static_pages.route('/candidates')
def candidates():
    """Render the candidates page"""
    return render_template('static/candidates.html')

@static_pages.route('/pricing')
def pricing():
    """Render the pricing page"""
    return render_template('static/pricing.html')

@static_pages.route('/help-center')
def help_center():
    """Render the help center page"""
    return render_template('static/help_center.html')

@static_pages.route('/contact')
def contact():
    """Render the contact page"""
    return render_template('static/contact.html')

@static_pages.route('/faq')
def faq():
    """Render the FAQ page"""
    return render_template('static/faq.html')

@static_pages.route('/terms')
def terms():
    """Render the terms page"""
    return render_template('static/terms.html')

@static_pages.route('/privacy')
def privacy():
    """Render the privacy policy page"""
    return render_template('static/privacy.html')

@static_pages.route('/cookie-policy')
def cookie_policy():
    """Render the cookie policy page"""
    return render_template('static/cookie.html')