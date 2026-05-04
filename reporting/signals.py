"""Signaux d'audit d'authentification."""
from django.contrib.auth.signals import (
    user_logged_in,
    user_logged_out,
    user_login_failed,
)
from django.dispatch import receiver

from .models import LoginAudit


def _get_client_ip(request):
    if request is None:
        return None
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _get_user_agent(request):
    if request is None:
        return ""
    return (request.META.get("HTTP_USER_AGENT") or "")[:300]


@receiver(user_logged_in)
def _on_login_success(sender, request, user, **kwargs):
    LoginAudit.objects.create(
        event=LoginAudit.EVENT_LOGIN_SUCCESS,
        username=getattr(user, "username", "") or "",
        user=user if getattr(user, "pk", None) else None,
        ip_address=_get_client_ip(request),
        user_agent=_get_user_agent(request),
    )


@receiver(user_logged_out)
def _on_logout(sender, request, user, **kwargs):
    LoginAudit.objects.create(
        event=LoginAudit.EVENT_LOGOUT,
        username=getattr(user, "username", "") or "",
        user=user if user and getattr(user, "pk", None) else None,
        ip_address=_get_client_ip(request),
        user_agent=_get_user_agent(request),
    )


@receiver(user_login_failed)
def _on_login_failed(sender, credentials, request=None, **kwargs):
    LoginAudit.objects.create(
        event=LoginAudit.EVENT_LOGIN_FAILED,
        username=(credentials or {}).get("username", "") or "",
        user=None,
        ip_address=_get_client_ip(request),
        user_agent=_get_user_agent(request),
    )
