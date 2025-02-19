"""
WSGI config for mcq_be_project project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.1/howto/deployment/wsgi/
"""

import os
import subprocess
import sys
from pathlib import Path

# Get the project root directory (two levels up from this file)
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Install dependencies before importing Django
requirements_path = PROJECT_ROOT / 'requirements.txt'
subprocess.check_call(['pip3', 'install', '-r', str(requirements_path), '--user'])

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mcq_be_project.settings')

application = get_wsgi_application()

app = application