"""Context processors disponibles partout dans les templates."""
from django.conf import settings


def session_settings(request):
    """Expose la duree de session a la base template (warning d'expiration)."""
    return {
        "session_cookie_age": getattr(settings, "SESSION_COOKIE_AGE", 1209600),
    }
