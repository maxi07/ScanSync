import os
from flask import Flask
import sys
sys.path.append('/app/src')
from shared.logging import logger
from routes.dashboard import dashboard_bp
from routes.sync import sync_bp
from routes.settings import settings_bp
from routes.api import api_bp
from routes.onedrive import onedrive_bp


logger.info("Starting web service...")

app = Flask(__name__)
app.secret_key = os.urandom(24)
app.register_blueprint(dashboard_bp)
app.register_blueprint(sync_bp)
app.register_blueprint(settings_bp)
app.register_blueprint(api_bp)
app.register_blueprint(onedrive_bp)


if __name__ == '__main__':
    app.run(debug=True, port=5001)
