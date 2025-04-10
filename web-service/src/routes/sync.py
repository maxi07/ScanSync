from flask import Blueprint, render_template
from shared.logging import logger

sync_bp = Blueprint('sync', __name__)


@sync_bp.route('/sync')
def sync():
    logger.info("Requested sync site")
    return render_template('sync.html')
