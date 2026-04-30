"""Middlewares applicatifs pour reporting."""


def _get_client_ip(request):
    """Retourne l'IP cliente la plus probable (gère un éventuel proxy)."""
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    if xff:
        # Le premier item de la liste est l'IP d'origine
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


class SessionIPMiddleware:
    """Stocke l'adresse IP du client dans la session Django.

    Permet à la page Contrôle (onglet Sessions) d'afficher l'IP associée à
    chaque session active sans introduire de nouvelle table.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if hasattr(request, 'session'):
            ip = _get_client_ip(request)
            if ip and request.session.get('ip_address') != ip:
                request.session['ip_address'] = ip
        return self.get_response(request)
