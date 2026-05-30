"""ASGI config for BFD9000 project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application

_ = os.environ.setdefault("DJANGO_SETTINGS_MODULE", "BFD9000.settings")

application = get_asgi_application()
