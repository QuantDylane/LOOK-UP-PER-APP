"""Vues liees au compte utilisateur (profil, sessions, mots de passe)."""
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.sessions.models import Session
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .forms import ProfileForm


def _user_sessions(user):
    """Retourne les sessions Django actives de ``user``."""
    out = []
    now = timezone.now()
    for s in Session.objects.filter(expire_date__gt=now):
        try:
            data = s.get_decoded()
        except Exception:
            continue
        uid = data.get("_auth_user_id")
        if not uid or str(uid) != str(user.pk):
            continue
        out.append({
            "session_key": s.session_key,
            "expire_date": s.expire_date,
            "ip_address": data.get("ip_address"),
        })
    out.sort(key=lambda x: x["expire_date"], reverse=True)
    return out


@login_required(login_url="login")
def mon_compte(request):
    """Page profil : infos utilisateur + sessions actives + actions rapides."""
    password_form = PasswordChangeForm(user=request.user)
    profile_form = ProfileForm(instance=request.user)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "update_profile":
            profile_form = ProfileForm(data=request.POST, instance=request.user)
            if profile_form.is_valid():
                profile_form.save()
                messages.success(request, "Profil mis a jour avec succes.")
                return HttpResponseRedirect(reverse("mon_compte"))
            messages.error(request, "Le formulaire de profil contient des erreurs.")
        elif action == "change_password":
            password_form = PasswordChangeForm(user=request.user, data=request.POST)
            if password_form.is_valid():
                password_form.save()
                update_session_auth_hash(request, password_form.user)
                messages.success(request, "Mot de passe mis a jour avec succes.")
                return HttpResponseRedirect(reverse("mon_compte"))
            messages.error(request, "Le formulaire de mot de passe contient des erreurs.")
        else:
            messages.error(request, "Action invalide.")

    sessions = _user_sessions(request.user)
    current_key = request.session.session_key
    for s in sessions:
        s["is_current"] = s["session_key"] == current_key

    role = "Administrateur" if request.user.is_superuser else (
        ", ".join(request.user.groups.values_list("name", flat=True)) or "Consultation"
    )

    context = {
        "password_form": password_form,
        "profile_form": profile_form,
        "sessions": sessions,
        "current_session_key": current_key,
        "role_display": role,
    }
    return render(request, "registration/mon_compte.html", context)


@login_required(login_url="login")
@require_POST
def revoke_other_sessions(request):
    """Supprime toutes les sessions de l'utilisateur courant sauf la session active."""
    current_key = request.session.session_key
    now = timezone.now()
    revoked = 0
    for s in Session.objects.filter(expire_date__gt=now):
        if s.session_key == current_key:
            continue
        try:
            data = s.get_decoded()
        except Exception:
            continue
        if str(data.get("_auth_user_id", "")) == str(request.user.pk):
            s.delete()
            revoked += 1
    if revoked:
        messages.success(request, f"{revoked} autre(s) session(s) deconnectee(s).")
    else:
        messages.info(request, "Aucune autre session active a deconnecter.")
    return HttpResponseRedirect(reverse("mon_compte"))


@login_required(login_url="login")
@require_GET
def session_ping(request):
    """Renouvelle la session courante et renvoie le delai d'expiration restant.

    Avec ``SESSION_SAVE_EVERY_REQUEST = True``, chaque appel rafraichit
    automatiquement le cookie de session.
    """
    return JsonResponse({
        "ok": True,
        "expires_in": int(getattr(settings, "SESSION_COOKIE_AGE", 0)),
    })
