"""WSGI entry point.

Development:  python -m flask --app web/wsgi.py run --debug
Production:   waitress-serve --listen 0.0.0.0:8080 wsgi:app   (see serve.py)
"""

from tttool_web.app import create_app

app = create_app()
