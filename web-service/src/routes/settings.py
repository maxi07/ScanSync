from flask import Blueprint, render_template
from shared.logging import logger

settings_bp = Blueprint('settings', __name__)


@settings_bp.route('/settings')
def settings():
    logger.info("Requested settings site")
    return render_template('settings.html')
