import os
from datetime import timedelta

# Base directory
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Secret key (change this in production!)
SECRET_KEY = 'your-secret-key-here-change-in-production'

# Database configuration
MYSQL_HOST = 'localhost'
MYSQL_USER = 'root'
MYSQL_PASSWORD = ''
MYSQL_DB = 'snack_store'
MYSQL_CURSORCLASS = 'Cursor'

# Flask-Login settings
REMEMBER_COOKIE_DURATION = timedelta(days=7)
SESSION_PROTECTION = 'strong'

# File upload settings
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'mp4', 'webm', 'mov'}
MAX_CONTENT_LENGTH = 20 * 1024 * 1024  # 16MB max file size

# Ensure upload directory exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(os.path.join(UPLOAD_FOLDER, 'products'), exist_ok=True)
os.makedirs(os.path.join(UPLOAD_FOLDER, 'banners'), exist_ok=True)
os.makedirs(os.path.join(UPLOAD_FOLDER, 'payment_qr'), exist_ok=True)
os.makedirs(os.path.join(UPLOAD_FOLDER, 'payment_proofs'), exist_ok=True)

# Application settings
DEBUG = True
TESTING = False

# Security settings
CSRF_ENABLED = True
CSRF_SESSION_KEY = 'your-csrf-session-key-here'

# Email settings (for future use)
MAIL_SERVER = 'smtp.gmail.com'
MAIL_PORT = 587
MAIL_USE_TLS = True
MAIL_USE_SSL = False
MAIL_USERNAME = 'jasmirchy@gmail.com'
MAIL_PASSWORD = 'chfy qktf tnuz esgl'
MAIL_DEFAULT_SENDER = 'info.swadgalli@gmail.com'

# Pagination settings
PRODUCTS_PER_PAGE = 12
ORDERS_PER_PAGE = 10

# Currency settings
DEFAULT_CURRENCY = 'NPR'
CURRENCY_SYMBOL = 'रु'