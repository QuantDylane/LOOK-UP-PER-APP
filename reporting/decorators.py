"""Decorateurs de roles metier pour reporting.

Trois groupes Django sont prevus :
- ``Administrateurs`` : equivalent a ``is_superuser``.
- ``Gestionnaires``   : acces aux pages Metadonnees et Controle.
- ``Consultants``     : lecture seule (Accueil, Analyses, Exportation, A propos).

Tout superuser est implicitement considere comme membre de tous les groupes.
"""
from functools import wraps

from django.contrib.auth.decorators import login_required, user_passes_test


GROUP_ADMINS = "Administrateurs"
GROUP_GESTIONNAIRES = "Gestionnaires"
GROUP_CONSULTANTS = "Consultants"

ALL_GROUPS = (GROUP_ADMINS, GROUP_GESTIONNAIRES, GROUP_CONSULTANTS)


def _user_in_groups(user, groups):
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    user_groups = set(user.groups.values_list("name", flat=True))
    return any(g in user_groups for g in groups)


def group_required(*groups, login_url="login"):
    """Restreint l'acces aux utilisateurs appartenant a l'un des groupes cites.

    Les superusers passent toujours. Sinon, l'utilisateur connecte doit etre
    membre d'au moins un des ``groups`` listes.
    """
    def decorator(view_func):
        @wraps(view_func)
        @login_required(login_url=login_url)
        def _wrapped(request, *args, **kwargs):
            if not _user_in_groups(request.user, groups):
                return user_passes_test(
                    lambda u: False,
                    login_url=login_url,
                )(view_func)(request, *args, **kwargs)
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator


def gestionnaire_required(view_func):
    """Acces reserve aux Gestionnaires et Administrateurs."""
    return group_required(GROUP_ADMINS, GROUP_GESTIONNAIRES)(view_func)


def admin_required(view_func):
    """Acces reserve aux Administrateurs (superuser ou groupe Administrateurs)."""
    return group_required(GROUP_ADMINS)(view_func)
