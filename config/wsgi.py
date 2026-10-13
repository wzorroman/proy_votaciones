"""
WSGI config for config project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.0/howto/deployment/wsgi/
"""
import os

from django.conf import settings  # noqa: E402
from django.core.wsgi import get_wsgi_application
from whitenoise import WhiteNoise

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

django_app = get_wsgi_application()

# WhiteNoise sirve los archivos estaticos (collectstatic -> STATIC_ROOT)
# y los archivos media subidos por los usuarios (MEDIA_ROOT) directamente
# desde Gunicorn, sin necesidad de nginx.
# Para despliegues de alto trafico se recomienda aun colocar nginx delante.
application = WhiteNoise(django_app)
if getattr(settings, "STATIC_ROOT", None):
    application.add_files(settings.STATIC_ROOT, prefix=settings.STATIC_URL)
if getattr(settings, "MEDIA_ROOT", None):
    application.add_files(settings.MEDIA_ROOT, prefix=settings.MEDIA_URL)