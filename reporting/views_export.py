"""Vues dédiées à la page « Exportation » — onglet PDF (rapport HTML A4)."""

import base64
from datetime import date, datetime, timedelta
from io import BytesIO

from django.contrib.auth.decorators import login_required
from django.contrib.staticfiles import finders
from django.db.models import Count
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.template.loader import render_to_string
from django.utils.text import slugify
from xhtml2pdf import pisa

import matplotlib
matplotlib.use('Agg')  # Backend sans GUI (sécuritaire en serveur web)
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from .models import Sicav, ValeurLiquidative
from . import views as v


# ---------------------------------------------------------------------------
# Helpers : courbe de performance en base 100 (méthode TWR par sous-périodes)
# ---------------------------------------------------------------------------

def _build_perf_series(transactions, date_debut, date_fin, n_points=24):
    """Calcule la série temporelle de performance en base 100 sur la période.

    Méthode TWR (time-weighted return) par chaînage des rendements Dietz simple
    entre deux dates d'échantillonnage successives. Les flux nets observés
    entre deux points sont neutralisés. Indice rebasé à 100 dès qu'une valeur
    de portefeuille strictement positive apparaît (utile pour les clients qui
    investissent en cours de période).
    """
    days = (date_fin - date_debut).days
    if days <= 0:
        return []

    # Construire la grille de dates (points d'échantillonnage)
    step = max(1, days // (n_points - 1))
    dates = []
    d = date_debut
    while d < date_fin:
        dates.append(d)
        d = d + timedelta(days=step)
    if not dates or dates[-1] != date_fin:
        dates.append(date_fin)

    series = []
    prev_value = None
    index = 100.0

    for i, d in enumerate(dates):
        positions = v.calculer_positions_a_date(transactions, d)
        valeur = v.calculer_valeur_portefeuille(positions, d) or 0.0

        if prev_value is None or prev_value <= 0:
            # Phase d'amorçage : on attend une première valeur > 0
            if valeur > 0:
                prev_value = valeur
                index = 100.0
            series.append({'date': d, 'index': round(index, 2)})
        else:
            # Flux nets sur le sous-période ]dates[i-1], d]
            d_prev = dates[i - 1]
            flux_sub = sum(
                m for date_f, m in v.calculer_flux_periode(transactions, d_prev, d)
                if d_prev < date_f <= d
            )
            denom = prev_value + 0.5 * flux_sub
            if denom > 0:
                r = (valeur - prev_value - flux_sub) / denom
                index *= (1.0 + r)
            series.append({'date': d, 'index': round(index, 2)})
            prev_value = valeur if valeur > 0 else prev_value

    return series


def _render_perf_chart_png(series, width_px=520, height_px=200):
    """Rend la courbe base 100 en PNG (data URI base64) ; renvoie '' si vide."""
    if not series or len(series) < 2:
        return ''

    dates = [p['date'] for p in series]
    values = [p['index'] for p in series]

    dpi = 100
    fig, ax = plt.subplots(figsize=(width_px / dpi, height_px / dpi), dpi=dpi)
    fig.patch.set_facecolor('#FFFFFF')

    # Ligne principale (charte CGF : bleu #004C90)
    ax.plot(dates, values, color='#004C90', linewidth=1.6, marker='', zorder=3)

    # Aire dégradée légère sous la courbe
    ax.fill_between(dates, values, min(values) - 1, color='#004C90', alpha=0.07, zorder=2)

    # Référence base 100
    ax.axhline(y=100, color='#7E8C8C', linewidth=0.7, linestyle='--', zorder=1)

    # Mise en forme axes
    ax.set_facecolor('#FFFFFF')
    for spine in ('top', 'right'):
        ax.spines[spine].set_visible(False)
    for spine in ('left', 'bottom'):
        ax.spines[spine].set_color('#C7CECE')
        ax.spines[spine].set_linewidth(0.6)

    ax.tick_params(axis='both', which='both', length=2, colors='#5D6E6E', labelsize=7)
    ax.grid(True, axis='y', color='#E2E6E6', linewidth=0.5, zorder=0)

    # Format X : dates compactes
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=3, maxticks=6))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%d/%m/%y'))

    # Marges Y propres autour de la courbe (au moins 100 inclus)
    y_min = min(min(values), 100) - 1
    y_max = max(max(values), 100) + 1
    ax.set_ylim(y_min, y_max)

    fig.tight_layout(pad=0.5)

    buf = BytesIO()
    fig.savefig(buf, format='png', dpi=dpi, bbox_inches='tight', facecolor='#FFFFFF')
    plt.close(fig)
    buf.seek(0)
    encoded = base64.b64encode(buf.read()).decode('ascii')
    return f'data:image/png;base64,{encoded}'


def _link_callback(uri, rel):
    """Résout les ressources statiques pour xhtml2pdf."""
    if uri.startswith('/static/'):
        path = uri.replace('/static/', '', 1)
        absolute = finders.find(path)
        if absolute:
            return absolute
    return uri


def _render_pdf_attachment(context, filename):
    """Convertit le template HTML en PDF et le renvoie en téléchargement."""
    html = render_to_string('reporting/rapport_pdf.html', {
        **context,
        'pdf_mode': True,
        'auto_print': False,
    })

    output = BytesIO()
    result = pisa.CreatePDF(
        src=html,
        dest=output,
        encoding='utf-8',
        link_callback=_link_callback,
    )

    if result.err:
        return HttpResponse("Erreur lors de la génération du PDF.", status=500)

    response = HttpResponse(output.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


# ---------------------------------------------------------------------------
# Helpers de construction des rapports
# ---------------------------------------------------------------------------

def _parse_periode(request):
    """Parse les dates ?date_debut=&date_fin= ; valeurs par défaut = YTD."""
    date_debut_str = request.GET.get('date_debut') or request.POST.get('date_debut')
    date_fin_str = request.GET.get('date_fin') or request.POST.get('date_fin')
    try:
        if date_debut_str:
            date_debut = datetime.strptime(date_debut_str, '%Y-%m-%d').date()
        else:
            date_debut = date(date.today().year, 1, 1)
        if date_fin_str:
            date_fin = datetime.strptime(date_fin_str, '%Y-%m-%d').date()
        else:
            derniere_vl = ValeurLiquidative.objects.order_by('-date').first()
            date_fin = derniere_vl.date if derniere_vl else date.today()
    except ValueError:
        date_debut = date(date.today().year, 1, 1)
        date_fin = date.today()
    return date_debut, date_fin


def _build_rapport_plan(nom_per_pee, date_debut, date_fin):
    """Calcule les données d'un rapport pour un plan donné. None si aucun
    enregistrement."""
    transactions = list(
        Sicav.objects.filter(nom_per_pee=nom_per_pee).order_by('date_transaction')
    )
    if not transactions:
        return None

    first = transactions[0]
    type_plan = first.type_plan

    positions = v.calculer_positions_a_date(transactions, date_fin)
    etats_cmp, _ = v.calculer_etat_portefeuille(transactions, date_fin)
    etats_par_fcp = {e['nom_fcp']: e for e in etats_cmp}

    fcp_details = []
    valeur_totale = 0.0
    cout_total = 0.0
    for nom_fcp, quantite in positions.items():
        vl = v.get_vl_at_date(nom_fcp, date_fin)
        valeur = quantite * vl if vl else 0.0
        etat = etats_par_fcp.get(nom_fcp)
        cout_fcp = etat['total_investi'] if etat else 0.0
        cmp_fcp = etat['cmp'] if etat else 0.0
        plus_value_fcp = valeur - cout_fcp if cout_fcp > 0 else 0.0
        fcp_details.append({
            'nom_fcp': nom_fcp,
            'quantite': quantite,
            'vl_actuelle': vl or 0.0,
            'valeur': valeur,
            'cout_acquisition': cout_fcp,
            'cmp': cmp_fcp,
            'plus_value': plus_value_fcp,
            'plus_value_realisee': etat['plus_value_realisee'] if etat else 0.0,
            'perf_pct': (plus_value_fcp / cout_fcp * 100) if cout_fcp > 0 else 0.0,
        })
        valeur_totale += valeur
        cout_total += cout_fcp

    # % portefeuille
    for f in fcp_details:
        f['pct_portefeuille'] = (f['valeur'] / valeur_totale * 100) if valeur_totale > 0 else 0.0
    fcp_details.sort(key=lambda x: x['valeur'], reverse=True)

    # Performance globale du plan
    positions_debut = v.calculer_positions_a_date(transactions, date_debut)
    v_initial = v.calculer_valeur_portefeuille(positions_debut, date_debut)
    flux = v.calculer_flux_periode(transactions, date_debut, date_fin)
    flux_nets_total = sum(m for _, m in flux)
    perf_simple = v.performance_dietz_simple(v_initial, valeur_totale, flux_nets_total)
    perf_modifiee = v.performance_dietz_modifiee(v_initial, valeur_totale, flux,
                                                 date_debut, date_fin)

    # Clients du plan (agrégat)
    clients = {}
    for t in transactions:
        if not t.numero_compte:
            continue
        c = clients.setdefault(t.numero_compte, {
            'numero_compte': t.numero_compte,
            'nom_prenom': t.nom_prenom or '',
            'email': t.email or '',
            'transactions': [],
        })
        c['transactions'].append(t)

    clients_list = []
    for c in clients.values():
        c_trans = c['transactions']
        # valeur finale du client
        c_pos_fin = v.calculer_positions_a_date(c_trans, date_fin)
        v_final_c = v.calculer_valeur_portefeuille(c_pos_fin, date_fin)
        c_pos_debut = v.calculer_positions_a_date(c_trans, date_debut)
        v_initial_c = v.calculer_valeur_portefeuille(c_pos_debut, date_debut)
        c_flux = v.calculer_flux_periode(c_trans, date_debut, date_fin)
        c_flux_nets = sum(m for _, m in c_flux)
        c_perf_simple = v.performance_dietz_simple(v_initial_c, v_final_c, c_flux_nets)
        c_perf_modifiee = v.performance_dietz_modifiee(v_initial_c, v_final_c, c_flux,
                                                       date_debut, date_fin)
        clients_list.append({
            'numero_compte': c['numero_compte'],
            'nom_prenom': c['nom_prenom'],
            'email': c['email'],
            'valeur': v_final_c,
            'perf_simple': c_perf_simple,
            'perf_modifiee': c_perf_modifiee,
        })
    clients_list.sort(key=lambda x: x['nom_prenom'] or x['numero_compte'])

    # Date d'ouverture du plan = première transaction enregistrée
    date_ouverture = transactions[0].date_transaction if transactions else None

    # Courbe base 100 sur la période
    perf_series = _build_perf_series(transactions, date_debut, date_fin)
    perf_chart_png = _render_perf_chart_png(perf_series)

    return {
        'kind': 'plan',
        'titre': nom_per_pee,
        'sous_titre': type_plan or '',
        'identifiant': nom_per_pee,
        'date_debut': date_debut,
        'date_fin': date_fin,
        'valeur_totale': valeur_totale,
        'cout_total': cout_total,
        'plus_value': valeur_totale - cout_total,
        'perf_pct_globale': ((valeur_totale - cout_total) / cout_total * 100) if cout_total > 0 else 0.0,
        'perf_simple': perf_simple,
        'perf_modifiee': perf_modifiee,
        'nb_clients': len(clients_list),
        'fcp_details': fcp_details,
        'clients': clients_list,
        'date_ouverture': date_ouverture,
        'perf_chart_png': perf_chart_png,
    }


def _build_rapport_client(numero_compte, date_debut, date_fin):
    """Calcule les données d'un rapport pour un client donné."""
    transactions = list(
        Sicav.objects.filter(numero_compte=numero_compte).order_by('date_transaction')
    )
    if not transactions:
        return None

    first = transactions[0]
    # Date d'adhésion = date de la première transaction du client
    date_adhesion = next((t.date_transaction for t in transactions if t.date_transaction), None)
    client_info = {
        'numero_compte': numero_compte,
        'nom_prenom': first.nom_prenom or '',
        'email': first.email or '',
        'type_plan': first.type_plan or '',
        'nom_per_pee': first.nom_per_pee or '',
        'date_adhesion': date_adhesion,
    }

    positions = v.calculer_positions_a_date(transactions, date_fin)
    etats_cmp, _ = v.calculer_etat_portefeuille(transactions, date_fin)
    etats_par_fcp = {e['nom_fcp']: e for e in etats_cmp}

    fcp_details = []
    valeur_totale = 0.0
    cout_total = 0.0
    for nom_fcp, quantite in positions.items():
        vl = v.get_vl_at_date(nom_fcp, date_fin)
        valeur = quantite * vl if vl else 0.0
        etat = etats_par_fcp.get(nom_fcp)
        cout_fcp = etat['total_investi'] if etat else 0.0
        cmp_fcp = etat['cmp'] if etat else 0.0
        plus_value_fcp = valeur - cout_fcp if cout_fcp > 0 else 0.0
        fcp_details.append({
            'nom_fcp': nom_fcp,
            'quantite': quantite,
            'vl_actuelle': vl or 0.0,
            'valeur': valeur,
            'cout_acquisition': cout_fcp,
            'cmp': cmp_fcp,
            'plus_value': plus_value_fcp,
            'plus_value_realisee': etat['plus_value_realisee'] if etat else 0.0,
            'perf_pct': (plus_value_fcp / cout_fcp * 100) if cout_fcp > 0 else 0.0,
        })
        valeur_totale += valeur
        cout_total += cout_fcp

    for f in fcp_details:
        f['pct_portefeuille'] = (f['valeur'] / valeur_totale * 100) if valeur_totale > 0 else 0.0
    fcp_details.sort(key=lambda x: x['valeur'], reverse=True)

    positions_debut = v.calculer_positions_a_date(transactions, date_debut)
    v_initial = v.calculer_valeur_portefeuille(positions_debut, date_debut)
    flux = v.calculer_flux_periode(transactions, date_debut, date_fin)
    flux_nets_total = sum(m for _, m in flux)
    perf_simple = v.performance_dietz_simple(v_initial, valeur_totale, flux_nets_total)
    perf_modifiee = v.performance_dietz_modifiee(v_initial, valeur_totale, flux,
                                                 date_debut, date_fin)

    # Mouvements de la période (tableau dans le rapport)
    mouvements = []
    for t in transactions:
        if not (t.date_transaction and date_debut <= t.date_transaction <= date_fin):
            continue
        vl_t = v.get_vl_at_date(t.nom_fcp, t.date_transaction) if t.nom_fcp else None
        qte = float(t.quantite) if t.quantite else 0.0
        montant = qte * vl_t if vl_t else 0.0
        mouvements.append({
            'date': t.date_transaction,
            'nom_fcp': t.nom_fcp or '',
            'sens': t.sens or '',
            'quantite': qte,
            'vl': vl_t or 0.0,
            'montant': montant,
        })
    mouvements.sort(key=lambda x: x['date'], reverse=True)

    # Courbe base 100 sur la période
    perf_series = _build_perf_series(transactions, date_debut, date_fin)
    perf_chart_png = _render_perf_chart_png(perf_series)

    return {
        'kind': 'client',
        'titre': client_info['nom_prenom'] or client_info['numero_compte'],
        'sous_titre': f"{client_info['numero_compte']} — {client_info['nom_per_pee']}",
        'identifiant': numero_compte,
        'client': client_info,
        'date_debut': date_debut,
        'date_fin': date_fin,
        'valeur_totale': valeur_totale,
        'cout_total': cout_total,
        'plus_value': valeur_totale - cout_total,
        'perf_pct_globale': ((valeur_totale - cout_total) / cout_total * 100) if cout_total > 0 else 0.0,
        'perf_simple': perf_simple,
        'perf_modifiee': perf_modifiee,
        'fcp_details': fcp_details,
        'mouvements': mouvements,
        'perf_chart_png': perf_chart_png,
    }


# ---------------------------------------------------------------------------
# Vues
# ---------------------------------------------------------------------------

@login_required
def export_page(request):
    """Page principale d'exportation (onglet PDF)."""
    plans = (
        Sicav.objects
        .exclude(nom_per_pee__isnull=True).exclude(nom_per_pee='')
        .values('nom_per_pee')
        .annotate(nb_clients=Count('numero_compte', distinct=True))
        .order_by('nom_per_pee')
    )

    clients_qs = (
        Sicav.objects
        .exclude(numero_compte__isnull=True).exclude(numero_compte='')
        .values('numero_compte', 'nom_prenom', 'nom_per_pee')
        .order_by('nom_prenom', 'numero_compte')
    )
    seen = set()
    clients = []
    for c in clients_qs:
        if c['numero_compte'] in seen:
            continue
        seen.add(c['numero_compte'])
        clients.append(c)

    annee = date.today().year
    derniere_vl = ValeurLiquidative.objects.order_by('-date').first()
    date_fin_defaut = derniere_vl.date if derniere_vl else date.today()

    context = {
        'plans': list(plans),
        'clients': clients,
        'date_debut_defaut': date(annee, 1, 1).strftime('%Y-%m-%d'),
        'date_fin_defaut': date_fin_defaut.strftime('%Y-%m-%d'),
    }
    return render(request, 'reporting/export.html', context)


@login_required
def export_rapport_plans(request):
    """Génère le rapport HTML A4 pour un ou plusieurs plans."""
    raw = request.GET.getlist('plans')
    # Support aussi ?plans=A,B,C
    selection = []
    for item in raw:
        selection.extend([s for s in item.split(',') if s.strip()])
    if not selection:
        raise Http404("Aucun plan sélectionné.")

    date_debut, date_fin = _parse_periode(request)
    v.charger_cache_vl()

    rapports = []
    for nom in selection:
        r = _build_rapport_plan(nom, date_debut, date_fin)
        if r:
            rapports.append(r)

    if not rapports:
        raise Http404("Aucun plan trouvé pour la sélection.")

    context = {
        'mode': 'plans',
        'mode_label': 'Plan' if len(rapports) == 1 else 'Plans',
        'rapports': rapports,
        'date_debut': date_debut,
        'date_fin': date_fin,
        'date_generation': datetime.now(),
        'auto_print': request.GET.get('print') == '1',
    }
    return render(request, 'reporting/rapport_pdf.html', context)


@login_required
def export_rapport_clients(request):
    """Génère le rapport HTML A4 pour un ou plusieurs clients."""
    raw = request.GET.getlist('comptes')
    selection = []
    for item in raw:
        selection.extend([s for s in item.split(',') if s.strip()])
    if not selection:
        raise Http404("Aucun client sélectionné.")

    date_debut, date_fin = _parse_periode(request)
    v.charger_cache_vl()

    rapports = []
    for nc in selection:
        r = _build_rapport_client(nc, date_debut, date_fin)
        if r:
            rapports.append(r)

    if not rapports:
        raise Http404("Aucun client trouvé pour la sélection.")

    context = {
        'mode': 'clients',
        'mode_label': 'Client' if len(rapports) == 1 else 'Clients',
        'rapports': rapports,
        'date_debut': date_debut,
        'date_fin': date_fin,
        'date_generation': datetime.now(),
        'auto_print': request.GET.get('print') == '1',
    }
    return render(request, 'reporting/rapport_pdf.html', context)


@login_required
def export_rapport_plans_pdf(request):
    """Télécharge un PDF pour un ou plusieurs plans."""
    raw = request.GET.getlist('plans')
    selection = []
    for item in raw:
        selection.extend([s for s in item.split(',') if s.strip()])
    if not selection:
        raise Http404("Aucun plan sélectionné.")

    date_debut, date_fin = _parse_periode(request)
    v.charger_cache_vl()

    rapports = []
    for nom in selection:
        r = _build_rapport_plan(nom, date_debut, date_fin)
        if r:
            rapports.append(r)

    if not rapports:
        raise Http404("Aucun plan trouvé pour la sélection.")

    ident = slugify(rapports[0]['identifiant']) if len(rapports) == 1 else 'multi'
    filename = f"rapport-plans-{ident}-{datetime.now().strftime('%Y%m%d')}.pdf"

    context = {
        'mode': 'plans',
        'mode_label': 'Plan' if len(rapports) == 1 else 'Plans',
        'rapports': rapports,
        'date_debut': date_debut,
        'date_fin': date_fin,
        'date_generation': datetime.now(),
    }
    return _render_pdf_attachment(context, filename)


@login_required
def export_rapport_clients_pdf(request):
    """Télécharge un PDF pour un ou plusieurs clients."""
    raw = request.GET.getlist('comptes')
    selection = []
    for item in raw:
        selection.extend([s for s in item.split(',') if s.strip()])
    if not selection:
        raise Http404("Aucun client sélectionné.")

    date_debut, date_fin = _parse_periode(request)
    v.charger_cache_vl()

    rapports = []
    for nc in selection:
        r = _build_rapport_client(nc, date_debut, date_fin)
        if r:
            rapports.append(r)

    if not rapports:
        raise Http404("Aucun client trouvé pour la sélection.")

    ident = slugify(rapports[0]['identifiant']) if len(rapports) == 1 else 'multi'
    filename = f"rapport-clients-{ident}-{datetime.now().strftime('%Y%m%d')}.pdf"

    context = {
        'mode': 'clients',
        'mode_label': 'Client' if len(rapports) == 1 else 'Clients',
        'rapports': rapports,
        'date_debut': date_debut,
        'date_fin': date_fin,
        'date_generation': datetime.now(),
    }
    return _render_pdf_attachment(context, filename)
