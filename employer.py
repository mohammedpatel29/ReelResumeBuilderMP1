
from flask import Blueprint, render_template
from flask_login import login_required

employer = Blueprint('employer', __name__)

@employer.route('/dashboard')
@login_required
def dashboard():
    return render_template('employer/dashboard.html')
