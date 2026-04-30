from django.shortcuts import render
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_POST
from django.db.models import Count, Sum, F, Q
from django.db import transaction
from django.contrib import messages
from django.core.cache import cache
from collections import defaultdict
import csv
import io
import json
from decimal import Decimal, InvalidOperation
from datetime import datetime, timedelta, date
from .models import ValeurLiquidative, Sicav
from .cmp import (
    construire_ledger,
    etat_portefeuille,
    agreger_etat,
)

# Pour le support Excel
try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False


# ========== FONCTIONS DE CALCUL DE PERFORMANCE ==========

# Cache global pour les VL (optimisation des performances)
_vl_cache = None
_vl_cache_dates = None

def charger_cache_vl():
    """Charger toutes les VL en mémoire pour éviter les requêtes répétées"""
    global _vl_cache, _vl_cache_dates
    
    # Utiliser une variable locale pour éviter les race conditions
    local_cache = defaultdict(list)
    local_dates = set()
    
    for vl in ValeurLiquidative.objects.all().values('nom_fcp', 'date', 'valeur_liquidative').order_by('nom_fcp', '-date'):
        if vl and vl.get('nom_fcp') and vl.get('valeur_liquidative'):
            local_cache[vl['nom_fcp']].append((vl['date'], float(vl['valeur_liquidative'])))
            local_dates.add(vl['date'])
    
    # Assigner au global seulement à la fin (atomique)
    _vl_cache = local_cache
    _vl_cache_dates = local_dates
    
    return _vl_cache

def get_vl_at_date(nom_fcp, target_date, use_cache=True):
    """Obtenir la VL d'un FCP à une date donnée (ou la plus proche avant)"""
    global _vl_cache
    
    if use_cache and _vl_cache is not None:
        if nom_fcp in _vl_cache:
            for date_vl, valeur in _vl_cache[nom_fcp]:
                if date_vl <= target_date:
                    return valeur
        return None
    
    # Fallback sans cache (pour les cas isolés)
    vl = ValeurLiquidative.objects.filter(
        nom_fcp=nom_fcp,
        date__lte=target_date
    ).order_by('-date').first()
    return float(vl.valeur_liquidative) if vl and vl.valeur_liquidative else None


def calculer_valeur_portefeuille(positions, date_vl, use_cache=True):
    """
    Calculer la valeur d'un portefeuille à une date donnée
    positions: dict {nom_fcp: quantite}
    """
    valeur_totale = 0
    for nom_fcp, quantite in positions.items():
        vl = get_vl_at_date(nom_fcp, date_vl, use_cache)
        if vl and quantite:
            valeur_totale += float(quantite) * vl
    return valeur_totale


def cmp_from_fcp(t):
    """
    Coût Moyen Pondéré (CMP) d'une transaction calculé à partir des FCP.

    Le prix unitaire d'acquisition retenu pour une transaction est la
    Valeur Liquidative (VL) du FCP à la date de la transaction.
    Retourne 0.0 si la VL est indisponible.
    """
    if not t or not t.nom_fcp or not t.date_transaction:
        return 0.0
    vl = get_vl_at_date(t.nom_fcp, t.date_transaction)
    return float(vl) if vl else 0.0


def _vl_resolver(nom_fcp, date_vl):
    """Résolveur de VL utilisé par le moteur CMP (backed by le cache)."""
    return get_vl_at_date(nom_fcp, date_vl)


def calculer_etat_portefeuille(transactions, date_valorisation):
    """
    Retourne (etats_par_fcp, totaux) à la date donnée en appliquant les règles
    CMP (souscription = recalcul du CMP, rachat = CMP inchangé et PV réalisée).
    """
    etats = etat_portefeuille(transactions, _vl_resolver, date_valorisation)
    return etats, agreger_etat(etats)


def calculer_positions_a_date(transactions, date_limite):
    """
    Calculer les positions (nombre de parts par FCP) à une date donnée
    en cumulant les souscriptions et rachats
    """
    positions = defaultdict(float)
    for t in transactions:
        if t.date_transaction and t.date_transaction <= date_limite:
            quantite = float(t.quantite) if t.quantite else 0
            if t.sens == 'souscription':
                positions[t.nom_fcp] += quantite
            elif t.sens == 'rachat':
                positions[t.nom_fcp] -= quantite
    # Filtrer les positions nulles ou négatives
    return {k: v for k, v in positions.items() if v > 0}


def calculer_flux_periode(transactions, date_debut, date_fin):
    """
    Calculer les flux nets (souscriptions - rachats) sur une période
    Retourne une liste de tuples (date, montant_flux)
    """
    flux = []
    for t in transactions:
        if t.date_transaction and date_debut <= t.date_transaction <= date_fin:
            # Montant = quantité × CMP (CMP calculé à partir des FCP : VL à la date de transaction)
            montant = float(t.quantite or 0) * cmp_from_fcp(t)
            if t.sens == 'souscription':
                flux.append((t.date_transaction, montant))
            elif t.sens == 'rachat':
                flux.append((t.date_transaction, -montant))
    return flux


def performance_dietz_simple(v_initial, v_final, flux_nets_total):
    """
    Calcul de la performance avec la méthode Dietz simple
    R = (V_f - V_i - ΣF) / (V_i + 0.5 × ΣF)
    """
    if v_initial is None or v_final is None:
        return None
    
    denominateur = v_initial + 0.5 * flux_nets_total
    if denominateur <= 0:
        return None
    
    performance = (v_final - v_initial - flux_nets_total) / denominateur
    return performance * 100  # Retourner en pourcentage


def performance_dietz_modifiee(v_initial, v_final, flux_avec_dates, date_debut, date_fin):
    """
    Calcul de la performance avec la méthode Dietz modifiée
    R = (V_f - V_i - ΣF) / (V_i + Σ(w_i × F_i))
    w_i = (T - t_i) / T
    """
    if v_initial is None or v_final is None:
        return None
    
    T = (date_fin - date_debut).days
    if T <= 0:
        return None
    
    flux_ponderes = 0
    flux_nets_total = 0
    
    for date_flux, montant in flux_avec_dates:
        t_i = (date_flux - date_debut).days
        w_i = (T - t_i) / T
        flux_ponderes += w_i * montant
        flux_nets_total += montant
    
    denominateur = v_initial + flux_ponderes
    if denominateur <= 0:
        return None
    
    performance = (v_final - v_initial - flux_nets_total) / denominateur
    return performance * 100  # Retourner en pourcentage


def calculer_performances_portefeuilles_pee_per(date_debut, date_fin, methode='simple'):
    """
    Calculer les performances des portefeuilles PEE/PER
    Regroupement par nom_per_pee
    """
    # Charger le cache VL pour optimiser les requêtes
    charger_cache_vl()
    
    performances = []
    
    # Récupérer tous les noms de plans uniques (déduplication stricte par nom_per_pee)
    # On ne group pas par type_plan pour éviter qu'un même plan apparaisse
    # plusieurs fois si ses lignes portent des valeurs type_plan différentes.
    noms_pee_per_raw = (
        Sicav.objects
        .exclude(nom_per_pee__isnull=True)
        .exclude(nom_per_pee='')
        .values('nom_per_pee', 'type_plan')
        .order_by('nom_per_pee', 'type_plan')
    )
    # Garder uniquement le premier type_plan rencontré pour chaque nom_per_pee
    seen = {}
    for row in noms_pee_per_raw:
        if row['nom_per_pee'] not in seen:
            seen[row['nom_per_pee']] = row['type_plan']
    noms_pee_per = list(seen.items())  # [(nom_per_pee, type_plan), ...]
    
    for nom_per_pee, type_plan in noms_pee_per:
        # Transactions de ce portefeuille
        transactions = Sicav.objects.filter(nom_per_pee=nom_per_pee).order_by('date_transaction')
        
        # Positions au début et à la fin de la période
        positions_debut = calculer_positions_a_date(transactions, date_debut)
        positions_fin = calculer_positions_a_date(transactions, date_fin)
        
        # Si pas de positions, ignorer
        if not positions_fin:
            continue
        
        # Calcul des valeurs
        v_initial = calculer_valeur_portefeuille(positions_debut, date_debut)
        v_final = calculer_valeur_portefeuille(positions_fin, date_fin)

        # Coût d'acquisition courant via le moteur CMP (rachat => CMP inchangé)
        _, totaux = calculer_etat_portefeuille(transactions, date_fin)
        cout_acquisition = totaux['total_investi']

        # Flux de la période
        flux = calculer_flux_periode(transactions, date_debut, date_fin)
        flux_nets_total = sum(montant for _, montant in flux)
        
        # Calcul de performance
        if methode == 'modifiee':
            perf = performance_dietz_modifiee(v_initial, v_final, flux, date_debut, date_fin)
        else:
            perf = performance_dietz_simple(v_initial, v_final, flux_nets_total)
        
        # Plus-value latente = Valeur actuelle - Coût d'acquisition
        plus_value = v_final - cout_acquisition if v_final and cout_acquisition else 0
        
        if perf is not None:
            performances.append({
                'nom': nom_per_pee,
                'type_plan': type_plan or 'N/A',
                'performance': round(perf, 2),
                'valeur_actuelle': round(v_final, 2) if v_final else 0,
                'plus_value': round(plus_value, 2),
            })
    
    return performances


def calculer_performances_clients(date_debut, date_fin, methode='simple'):
    """
    Calculer les performances des portefeuilles clients
    Regroupement par numero_compte (client)
    """
    global _vl_cache
    # Charger le cache VL si pas déjà fait
    if _vl_cache is None:
        charger_cache_vl()
    
    performances = []
    
    # Récupérer tous les clients uniques
    clients = Sicav.objects.exclude(
        numero_compte__isnull=True
    ).exclude(
        numero_compte=''
    ).values('numero_compte', 'nom_prenom', 'nom_per_pee', 'type_plan').distinct()
    
    # Regrouper par client
    clients_data = {}
    for c in clients:
        key = c['numero_compte']
        if key not in clients_data:
            clients_data[key] = {
                'nom_prenom': c['nom_prenom'],
                'nom_per_pee': c['nom_per_pee'],
                'type_plan': c['type_plan']
            }
    
    for numero_compte, data in clients_data.items():
        # Transactions de ce client
        transactions = Sicav.objects.filter(numero_compte=numero_compte).order_by('date_transaction')
        
        # Positions au début et à la fin de la période
        positions_debut = calculer_positions_a_date(transactions, date_debut)
        positions_fin = calculer_positions_a_date(transactions, date_fin)
        
        # Si pas de positions, ignorer
        if not positions_fin:
            continue
        
        # Calcul des valeurs
        v_initial = calculer_valeur_portefeuille(positions_debut, date_debut)
        v_final = calculer_valeur_portefeuille(positions_fin, date_fin)

        # Coût d'acquisition courant via le moteur CMP
        _, totaux = calculer_etat_portefeuille(transactions, date_fin)
        cout_acquisition = totaux['total_investi']

        # Flux de la période
        flux = calculer_flux_periode(transactions, date_debut, date_fin)
        flux_nets_total = sum(montant for _, montant in flux)
        
        # Calcul de performance
        if methode == 'modifiee':
            perf = performance_dietz_modifiee(v_initial, v_final, flux, date_debut, date_fin)
        else:
            perf = performance_dietz_simple(v_initial, v_final, flux_nets_total)
        
        # Plus-value latente
        plus_value = v_final - cout_acquisition if v_final and cout_acquisition else 0
        
        if perf is not None:
            performances.append({
                'numero_compte': numero_compte,
                'nom_prenom': data['nom_prenom'] or numero_compte,
                'nom_per_pee': data['nom_per_pee'] or 'N/A',
                'type_plan': data['type_plan'] or 'N/A',
                'performance': round(perf, 2),
                'valeur_actuelle': round(v_final, 2) if v_final else 0,
                'plus_value': round(plus_value, 2),
            })
    
    return performances


def accueil(request):
    """Page d'accueil avec Top/Flop performances"""
    annee_courante = date.today().year
    date_debut_defaut = date(annee_courante, 1, 1)
    date_fin_defaut = date.today()

    total_plans = Sicav.objects.exclude(
        nom_per_pee__isnull=True
    ).exclude(nom_per_pee='').values('nom_per_pee').distinct().count()
    total_clients = Sicav.objects.exclude(
        numero_compte__isnull=True
    ).exclude(numero_compte='').values('numero_compte').distinct().count()
    total_fcp = ValeurLiquidative.objects.values('nom_fcp').distinct().count()

    context = {
        # Conservé pour compatibilité avec l'ancien template
        'total_pee': total_plans,
        'total_per': 0,
        'total_clients': total_clients,
        'clients_pee': total_clients,
        'clients_per': 0,
        'total_plans': total_plans,
        'total_fcp': total_fcp,
        'date_debut_defaut': date_debut_defaut.strftime('%Y-%m-%d'),
        'date_fin_defaut': date_fin_defaut.strftime('%Y-%m-%d'),
    }

    return render(request, 'reporting/accueil.html', context)


def api_top_flop_performances(request):
    """API pour récupérer les Top/Flop performances avec filtres"""
    global _vl_cache
    
    # Récupérer les paramètres
    date_debut_str = request.GET.get('date_debut')
    date_fin_str = request.GET.get('date_fin')
    methode = request.GET.get('methode', 'simple')  # 'simple' ou 'modifiee'
    type_plan_filter = ''  # PEE/PER n'est plus distingué, laissé vide pour compat
    top_n = int(request.GET.get('top_n', 3))  # Nombre d'éléments dans top/flop
    
    # Parser les dates
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
        return JsonResponse({'error': 'Format de date invalide'}, status=400)
    
    try:
        # Calculer les performances des portefeuilles PEE/PER
        perf_pee_per = calculer_performances_portefeuilles_pee_per(date_debut, date_fin, methode)
        
        # Calculer les performances des clients
        perf_clients = calculer_performances_clients(date_debut, date_fin, methode)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
    
    # Filtrer par type de plan si spécifié
    if type_plan_filter:
        perf_pee_per = [p for p in perf_pee_per if p['type_plan'] == type_plan_filter]
        perf_clients = [p for p in perf_clients if p['type_plan'] == type_plan_filter]
    
    # Trier et extraire Top N et Flop N pour PEE/PER (sans chevauchement :
    # quand le nombre total est < 2 × top_n, on tronque le Flop pour ne pas
    # afficher deux fois les mêmes plans dans Top et Flop).
    perf_pee_per_sorted = sorted(perf_pee_per, key=lambda x: x['performance'], reverse=True)
    top_pee_per = perf_pee_per_sorted[:top_n]
    reste_pee_per = perf_pee_per_sorted[len(top_pee_per):]
    flop_count_pp = min(top_n, len(reste_pee_per))
    flop_pee_per = reste_pee_per[-flop_count_pp:][::-1] if flop_count_pp > 0 else []

    # Trier et extraire Top N et Flop N pour clients (idem : pas de chevauchement)
    perf_clients_sorted = sorted(perf_clients, key=lambda x: x['performance'], reverse=True)
    top_clients = perf_clients_sorted[:top_n]
    reste_clients = perf_clients_sorted[len(top_clients):]
    flop_count_cl = min(top_n, len(reste_clients))
    flop_clients = reste_clients[-flop_count_cl:][::-1] if flop_count_cl > 0 else []
    
    return JsonResponse({
        'top_pee_per': top_pee_per,
        'flop_pee_per': flop_pee_per,
        'top_clients': top_clients,
        'flop_clients': flop_clients,
        'date_debut': date_debut.strftime('%d/%m/%Y'),
        'date_fin': date_fin.strftime('%d/%m/%Y'),
        'methode': methode,
        'type_plan_filter': type_plan_filter,
        'top_n': top_n,
    })


def api_performance_globale(request):
    """API pour récupérer les performances agrégées globales et par type de plan"""
    date_debut_str = request.GET.get('date_debut')
    date_fin_str = request.GET.get('date_fin')
    
    # Parser les dates
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
        return JsonResponse({'error': 'Format de date invalide'}, status=400)
    
    # Charger le cache VL
    charger_cache_vl()
    
    def calculer_stats_type_plan(type_plan_filter=None):
        """Calculer les stats agrégées (le filtre PEE/PER est désormais ignoré)"""
        noms_pee_per = Sicav.objects.exclude(
            nom_per_pee__isnull=True
        ).exclude(nom_per_pee='').values_list('nom_per_pee', flat=True).distinct()
        
        encours_total = 0
        cout_total = 0
        v_initial_total = 0
        v_final_total = 0
        flux_nets_total = 0
        flux_avec_dates = []  # Pour Dietz modifiée
        
        for nom_per_pee in noms_pee_per:
            transactions = Sicav.objects.filter(nom_per_pee=nom_per_pee).order_by('date_transaction')
            
            # Positions à la fin
            positions_fin = calculer_positions_a_date(transactions, date_fin)
            if not positions_fin:
                continue
            
            # Valeur finale
            v_final = calculer_valeur_portefeuille(positions_fin, date_fin)
            encours_total += v_final
            v_final_total += v_final

            # Coût d'acquisition via le moteur CMP (rachat => CMP inchangé)
            _, totaux_p = calculer_etat_portefeuille(transactions, date_fin)
            cout_total += totaux_p['total_investi']
            
            # Positions au début pour performance
            positions_debut = calculer_positions_a_date(transactions, date_debut)
            v_initial = calculer_valeur_portefeuille(positions_debut, date_debut)
            v_initial_total += v_initial
            
            # Flux de la période
            flux = calculer_flux_periode(transactions, date_debut, date_fin)
            flux_nets_total += sum(montant for _, montant in flux)
            flux_avec_dates.extend(flux)
        
        # Performance Dietz simple et modifiée agrégées
        perf_simple = performance_dietz_simple(v_initial_total, v_final_total, flux_nets_total)
        perf_modifiee = performance_dietz_modifiee(v_initial_total, v_final_total, flux_avec_dates, date_debut, date_fin)
        
        plus_value = encours_total - cout_total
        
        return {
            'encours': round(encours_total, 2),
            'cout_acquisition': round(cout_total, 2),
            'plus_value': round(plus_value, 2),
            'perf_simple': round(perf_simple, 2) if perf_simple is not None else None,
            'perf_modifiee': round(perf_modifiee, 2) if perf_modifiee is not None else None
        }
    
    try:
        # Calculer pour global, PEE et PER
        global_stats = calculer_stats_type_plan(None)
        pee_stats = calculer_stats_type_plan('PEE')
        per_stats = calculer_stats_type_plan('PER')
        
        return JsonResponse({
            'global': global_stats,
            'pee': pee_stats,
            'per': per_stats,
            'date_debut': date_debut.strftime('%d/%m/%Y'),
            'date_fin': date_fin.strftime('%d/%m/%Y'),
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def analyse_pee_per(request):
    """Dashboard d'analyse des plans d'épargne"""
    portefeuilles = Sicav.objects.exclude(
        nom_per_pee__isnull=True
    ).exclude(
        nom_per_pee=''
    ).values('nom_per_pee').annotate(
        nb_clients=Count('numero_compte', distinct=True),
        nb_transactions=Count('id')
    ).order_by('nom_per_pee')

    fcps = ValeurLiquidative.objects.exclude(
        nom_fcp__isnull=True
    ).values_list('nom_fcp', flat=True).distinct().order_by('nom_fcp')

    total_portefeuilles = len(portefeuilles)
    total_clients = Sicav.objects.exclude(
        numero_compte__isnull=True
    ).exclude(numero_compte='').values('numero_compte').distinct().count()
    total_fcp = ValeurLiquidative.objects.values('nom_fcp').distinct().count()
    total_transactions = Sicav.objects.count()

    annee_courante = date.today().year
    date_debut_defaut = date(annee_courante, 1, 1)
    derniere_vl = ValeurLiquidative.objects.order_by('-date').first()
    date_fin_defaut = derniere_vl.date if derniere_vl else date.today()

    context = {
        'portefeuilles': list(portefeuilles),
        'fcps': list(fcps),
        'total_portefeuilles': total_portefeuilles,
        'total_clients': total_clients,
        'total_fcp': total_fcp,
        'total_transactions': total_transactions,
        'date_debut_defaut': date_debut_defaut.strftime('%Y-%m-%d'),
        'date_fin_defaut': date_fin_defaut.strftime('%Y-%m-%d'),
    }

    return render(request, 'reporting/analyse_pee_per.html', context)


def api_portefeuille_detail(request, nom_per_pee):
    """API pour récupérer les détails d'un portefeuille PEE/PER"""
    global _vl_cache
    
    date_debut_str = request.GET.get('date_debut')
    date_fin_str = request.GET.get('date_fin')
    methode = request.GET.get('methode', 'simple')
    
    # Parser les dates
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
        return JsonResponse({'error': 'Format de date invalide'}, status=400)
    
    # Charger le cache
    charger_cache_vl()
    
    try:
        # Récupérer les transactions du portefeuille
        transactions = Sicav.objects.filter(nom_per_pee=nom_per_pee).order_by('date_transaction')
        
        if not transactions.exists():
            return JsonResponse({'error': 'Portefeuille non trouvé'}, status=404)
        
        # Infos du portefeuille
        first_trans = transactions.first()
        type_plan = first_trans.type_plan
        
        # Positions actuelles par FCP
        positions = calculer_positions_a_date(transactions, date_fin)

        # État portefeuille via le moteur CMP (rachat => CMP inchangé, PV réalisée)
        etats_cmp, _ = calculer_etat_portefeuille(transactions, date_fin)
        etats_par_fcp = {e['nom_fcp']: e for e in etats_cmp}

        # Première passe : calculer les valeurs par FCP
        fcp_data = []
        valeur_totale = 0
        cout_total = 0

        for nom_fcp, quantite in positions.items():
            vl_actuelle = get_vl_at_date(nom_fcp, date_fin)
            valeur = quantite * vl_actuelle if vl_actuelle else 0

            etat = etats_par_fcp.get(nom_fcp)
            cout_fcp = etat['total_investi'] if etat else 0
            cmp_fcp = etat['cmp'] if etat else 0
            pv_realisee_fcp = etat['plus_value_realisee'] if etat else 0

            plus_value_fcp = valeur - cout_fcp if cout_fcp > 0 else 0

            fcp_data.append({
                'nom_fcp': nom_fcp,
                'quantite': quantite,
                'vl_actuelle': vl_actuelle,
                'valeur': valeur,
                'cout_acquisition': cout_fcp,
                'cmp': cmp_fcp,
                'plus_value': plus_value_fcp,
                'plus_value_realisee': pv_realisee_fcp,
                'perf_pct': (plus_value_fcp / cout_fcp * 100) if cout_fcp > 0 else 0,
            })

            valeur_totale += valeur
            cout_total += cout_fcp

        # Deuxième passe : calculer le % portefeuille
        fcp_details = []
        for fcp in fcp_data:
            pct_portefeuille = (fcp['valeur'] / valeur_totale * 100) if valeur_totale > 0 else 0
            fcp_details.append({
                'nom_fcp': fcp['nom_fcp'],
                'quantite': round(fcp['quantite'], 4),
                'vl_actuelle': round(fcp['vl_actuelle'], 2) if fcp['vl_actuelle'] else 0,
                'valeur': round(fcp['valeur'], 2),
                'cout_acquisition': round(fcp['cout_acquisition'], 2),
                'cmp': round(fcp['cmp'], 4),
                'plus_value': round(fcp['plus_value'], 2),
                'plus_value_realisee': round(fcp['plus_value_realisee'], 2),
                'perf_pct': round(fcp['perf_pct'], 2),
                'pct_portefeuille': round(pct_portefeuille, 2),
            })
        
        # Clients du portefeuille - Agrégation par numero_compte
        clients_dict = {}
        for t in transactions:
            if not t.numero_compte:
                continue
            key = t.numero_compte
            if key not in clients_dict:
                clients_dict[key] = {
                    'numero_compte': t.numero_compte,
                    'nom_prenom': t.nom_prenom,
                    'email': t.email,
                    'transactions': [],
                }
            clients_dict[key]['transactions'].append(t)
        
        # Calculer les parts et performance par client (méthode Dietz)
        clients_list = []
        for key, client_data in clients_dict.items():
            client_trans = client_data['transactions']
            
            # Positions du client au DÉBUT de la période
            client_positions_debut = {}
            for t in client_trans:
                if t.nom_fcp and t.date_transaction and t.date_transaction < date_debut:
                    if t.nom_fcp not in client_positions_debut:
                        client_positions_debut[t.nom_fcp] = 0
                    if t.sens == 'souscription' and t.quantite:
                        client_positions_debut[t.nom_fcp] += float(t.quantite)
                    elif t.sens == 'rachat' and t.quantite:
                        client_positions_debut[t.nom_fcp] -= float(t.quantite)
            
            # Valeur initiale du client (V_i)
            v_initial_client = 0
            for nom_fcp, qty in client_positions_debut.items():
                if qty > 0:
                    vl = get_vl_at_date(nom_fcp, date_debut)
                    v_initial_client += qty * vl if vl else 0
            
            # Positions du client à la FIN de la période
            client_positions_fin = {}
            for t in client_trans:
                if t.nom_fcp and t.date_transaction and t.date_transaction <= date_fin:
                    if t.nom_fcp not in client_positions_fin:
                        client_positions_fin[t.nom_fcp] = 0
                    if t.sens == 'souscription' and t.quantite:
                        client_positions_fin[t.nom_fcp] += float(t.quantite)
                    elif t.sens == 'rachat' and t.quantite:
                        client_positions_fin[t.nom_fcp] -= float(t.quantite)
            
            # Total des parts et valeur finale (V_f)
            total_parts = sum(max(0, qty) for qty in client_positions_fin.values())
            v_final_client = 0
            
            for nom_fcp, qty in client_positions_fin.items():
                if qty > 0:
                    vl = get_vl_at_date(nom_fcp, date_fin)
                    v_final_client += qty * vl if vl else 0
            
            # Flux du client pendant la période (CMP calculé à partir des FCP)
            flux_client = []
            for t in client_trans:
                if t.date_transaction and date_debut <= t.date_transaction <= date_fin and t.quantite:
                    cmp = cmp_from_fcp(t)
                    if t.sens == 'souscription' and cmp:
                        flux_client.append((t.date_transaction, float(t.quantite) * cmp))
                    elif t.sens == 'rachat' and cmp:
                        flux_client.append((t.date_transaction, -float(t.quantite) * cmp))
            
            flux_nets_client = sum(m for _, m in flux_client)
            
            # Performance du client avec les deux méthodes Dietz
            perf_simple = performance_dietz_simple(v_initial_client, v_final_client, flux_nets_client)
            perf_modifiee = performance_dietz_modifiee(v_initial_client, v_final_client, flux_client, date_debut, date_fin)
            
            clients_list.append({
                'numero_compte': client_data['numero_compte'],
                'nom_prenom': client_data['nom_prenom'],
                'email': client_data['email'],
                'valeur': round(v_final_client, 2),
                'perf_simple': round(perf_simple, 2) if perf_simple is not None else None,
                'perf_modifiee': round(perf_modifiee, 2) if perf_modifiee is not None else None,
            })
        
        # Trier par nom
        clients_list.sort(key=lambda x: x['nom_prenom'] or x['numero_compte'] or '')
        
        # Performance globale (les deux méthodes)
        positions_debut = calculer_positions_a_date(transactions, date_debut)
        v_initial = calculer_valeur_portefeuille(positions_debut, date_debut)
        v_final = valeur_totale
        
        flux = calculer_flux_periode(transactions, date_debut, date_fin)
        flux_nets_total = sum(montant for _, montant in flux)
        
        perf_simple = performance_dietz_simple(v_initial, v_final, flux_nets_total)
        perf_modifiee = performance_dietz_modifiee(v_initial, v_final, flux, date_debut, date_fin)
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
    
    return JsonResponse({
        'nom_per_pee': nom_per_pee,
        'type_plan': type_plan,
        'valeur_totale': round(valeur_totale, 2),
        'cout_acquisition': round(cout_total, 2),
        'plus_value': round(valeur_totale - cout_total, 2),
        'perf_simple': round(perf_simple, 2) if perf_simple else None,
        'perf_modifiee': round(perf_modifiee, 2) if perf_modifiee else None,
        'nb_clients': len(clients_list),
        'clients': clients_list,
        'fcp_details': fcp_details,
        'date_debut': date_debut.strftime('%d/%m/%Y'),
        'date_fin': date_fin.strftime('%d/%m/%Y'),
    })


def analyse_client(request):
    """Dashboard d'analyse par client"""
    clients = Sicav.objects.exclude(
        numero_compte__isnull=True
    ).exclude(
        numero_compte=''
    ).values('numero_compte', 'nom_prenom', 'email', 'nom_per_pee').annotate(
        nb_transactions=Count('id')
    ).order_by('nom_prenom')

    clients_dict = {}
    for c in clients:
        key = c['numero_compte']
        if key not in clients_dict:
            clients_dict[key] = {
                'numero_compte': c['numero_compte'],
                'nom_prenom': c['nom_prenom'],
                'email': c['email'],
                'nom_per_pee': c['nom_per_pee'],
                'nb_transactions': c['nb_transactions'],
            }
        else:
            clients_dict[key]['nb_transactions'] += c['nb_transactions']

    clients_list = sorted(clients_dict.values(), key=lambda x: x['nom_prenom'] or '')

    total_clients = len(clients_list)
    total_plans = Sicav.objects.exclude(
        nom_per_pee__isnull=True
    ).exclude(nom_per_pee='').values('nom_per_pee').distinct().count()
    total_transactions = Sicav.objects.count()

    annee_courante = date.today().year
    date_debut_defaut = date(annee_courante, 1, 1)
    derniere_vl = ValeurLiquidative.objects.order_by('-date').first()
    date_fin_defaut = derniere_vl.date if derniere_vl else date.today()

    context = {
        'clients': clients_list,
        'total_clients': total_clients,
        'total_plans': total_plans,
        'total_transactions': total_transactions,
        'date_debut_defaut': date_debut_defaut.strftime('%Y-%m-%d'),
        'date_fin_defaut': date_fin_defaut.strftime('%Y-%m-%d'),
    }

    return render(request, 'reporting/analyse_client.html', context)


def api_client_detail(request, numero_compte):
    """API pour récupérer les détails d'un client"""
    global _vl_cache
    
    date_debut_str = request.GET.get('date_debut')
    date_fin_str = request.GET.get('date_fin')
    methode = request.GET.get('methode', 'simple')
    
    # Parser les dates
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
        return JsonResponse({'error': 'Format de date invalide'}, status=400)
    
    # Charger le cache
    charger_cache_vl()
    
    try:
        # Récupérer les transactions du client
        transactions = Sicav.objects.filter(numero_compte=numero_compte).order_by('date_transaction')
        
        if not transactions.exists():
            return JsonResponse({'error': 'Client non trouvé'}, status=404)
        
        # Infos du client
        first_trans = transactions.first()
        client_info = {
            'numero_compte': numero_compte,
            'nom_prenom': first_trans.nom_prenom,
            'email': first_trans.email,
            'type_plan': first_trans.type_plan,
            'nom_per_pee': first_trans.nom_per_pee,
        }
        
        # Positions actuelles par FCP
        positions = calculer_positions_a_date(transactions, date_fin)

        # État portefeuille via le moteur CMP
        etats_cmp, _ = calculer_etat_portefeuille(transactions, date_fin)
        etats_par_fcp = {e['nom_fcp']: e for e in etats_cmp}

        # Calcul détaillé par FCP
        fcp_details = []
        valeur_totale = 0
        cout_total = 0

        for nom_fcp, quantite in positions.items():
            vl_actuelle = get_vl_at_date(nom_fcp, date_fin)
            valeur = quantite * vl_actuelle if vl_actuelle else 0

            etat = etats_par_fcp.get(nom_fcp)
            cout_fcp = etat['total_investi'] if etat else 0
            cmp_fcp = etat['cmp'] if etat else 0
            pv_realisee_fcp = etat['plus_value_realisee'] if etat else 0

            plus_value_fcp = valeur - cout_fcp if cout_fcp > 0 else 0

            fcp_details.append({
                'nom_fcp': nom_fcp,
                'quantite': round(quantite, 4),
                'vl_actuelle': round(vl_actuelle, 2) if vl_actuelle else 0,
                'valeur': round(valeur, 2),
                'cout_acquisition': round(cout_fcp, 2),
                'cmp': round(cmp_fcp, 4),
                'plus_value': round(plus_value_fcp, 2),
                'plus_value_realisee': round(pv_realisee_fcp, 2),
                'perf_pct': round((plus_value_fcp / cout_fcp * 100), 2) if cout_fcp > 0 else 0,
            })

            valeur_totale += valeur
            cout_total += cout_fcp
        
        # Performance globale (les deux méthodes)
        positions_debut = calculer_positions_a_date(transactions, date_debut)
        v_initial = calculer_valeur_portefeuille(positions_debut, date_debut)
        v_final = valeur_totale
        
        flux = calculer_flux_periode(transactions, date_debut, date_fin)
        flux_nets_total = sum(montant for _, montant in flux)
        
        perf_simple = performance_dietz_simple(v_initial, v_final, flux_nets_total)
        perf_modifiee = performance_dietz_modifiee(v_initial, v_final, flux, date_debut, date_fin)
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
    
    return JsonResponse({
        'client': client_info,
        'valeur_totale': round(valeur_totale, 2),
        'cout_acquisition': round(cout_total, 2),
        'plus_value': round(valeur_totale - cout_total, 2),
        'perf_simple': round(perf_simple, 2) if perf_simple else None,
        'perf_modifiee': round(perf_modifiee, 2) if perf_modifiee else None,
        'fcp_details': fcp_details,
        'date_debut': date_debut.strftime('%d/%m/%Y'),
        'date_fin': date_fin.strftime('%d/%m/%Y'),
    })


def api_client_historique(request, numero_compte):
    """API pour récupérer l'historique des transactions d'un client"""
    global _vl_cache

    # Charger le cache VL
    charger_cache_vl()

    # Filtres optionnels
    date_debut_str = request.GET.get('date_debut')
    date_fin_str = request.GET.get('date_fin')
    sens_filter = request.GET.get('sens', '')
    fcp_filter = request.GET.get('fcp', '')

    # Transactions brutes (toutes, pour rejouer le ledger CMP correctement)
    transactions_all = list(
        Sicav.objects.filter(numero_compte=numero_compte).order_by('date_transaction', 'id')
    )

    if not transactions_all:
        return JsonResponse({'error': 'Client non trouvé'}, status=404)

    # Rejouer le ledger sur l'ensemble des transactions pour obtenir l'état CMP
    # après chaque opération (parts, CMP, total investi, PV réalisée).
    _, evenements = construire_ledger(transactions_all, _vl_resolver)
    # Indexation par (id de transaction) pour un accès O(1). Les évènements sont
    # générés dans le même ordre que les transactions valides.
    txs_valid = [
        t for t in transactions_all
        if t.nom_fcp and t.date_transaction and t.sens in ('souscription', 'rachat')
    ]
    txs_valid.sort(key=lambda t: (t.date_transaction, t.id or 0))
    etat_par_tx_id = {t.id: e for t, e in zip(txs_valid, evenements)}

    # Appliquer les filtres d'affichage (sans invalider le ledger déjà calculé)
    date_debut = None
    date_fin = None
    if date_debut_str:
        try:
            date_debut = datetime.strptime(date_debut_str, '%Y-%m-%d').date()
        except ValueError:
            date_debut = None
    if date_fin_str:
        try:
            date_fin = datetime.strptime(date_fin_str, '%Y-%m-%d').date()
        except ValueError:
            date_fin = None

    def _passe_filtre(t):
        if date_debut and (not t.date_transaction or t.date_transaction < date_debut):
            return False
        if date_fin and (not t.date_transaction or t.date_transaction > date_fin):
            return False
        if sens_filter and t.sens != sens_filter:
            return False
        if fcp_filter and t.nom_fcp != fcp_filter:
            return False
        return True

    transactions_affichees = [t for t in transactions_all if _passe_filtre(t)]
    # Affichage par date décroissante
    transactions_affichees.sort(
        key=lambda t: (t.date_transaction or date.min, t.nom_fcp or ''),
        reverse=True,
    )

    # Construire la structure hiérarchique (par date puis par FCP)
    historique = {}
    for t in transactions_affichees:
        date_key = t.date_transaction.strftime('%Y-%m-%d') if t.date_transaction else 'Sans date'
        if date_key not in historique:
            historique[date_key] = {
                'date': t.date_transaction.strftime('%d/%m/%Y') if t.date_transaction else 'Sans date',
                'transactions': []
            }

        # VL à la date de la transaction = prix unitaire d'exécution
        vl_transaction = get_vl_at_date(t.nom_fcp, t.date_transaction) if t.date_transaction and t.nom_fcp else None
        quantite = float(t.quantite) if t.quantite else 0
        montant = quantite * vl_transaction if vl_transaction else 0

        # État CMP après exécution de la transaction
        evt = etat_par_tx_id.get(t.id)
        cmp_apres = evt.cmp_apres if evt else 0.0
        parts_apres = evt.parts_apres if evt else 0.0
        total_investi_apres = evt.total_investi_apres if evt else 0.0
        pv_realisee = evt.plus_value_realisee if evt else 0.0

        # Écart VL vs CMP après transaction (indicateur de performance instantanée)
        ecart_pct = None
        if vl_transaction and cmp_apres > 0:
            ecart_pct = ((vl_transaction - cmp_apres) / cmp_apres) * 100

        historique[date_key]['transactions'].append({
            'id': t.id,
            'nom_fcp': t.nom_fcp,
            'sens': t.sens,
            'quantite': quantite,
            # Prix unitaire de la transaction (VL) — conservé sous l'ancien nom
            # pour compat avec les templates existants.
            'cout_moyen_pondere': vl_transaction or 0,
            'vl_transaction': round(vl_transaction, 4) if vl_transaction else None,
            'ecart_cmp_vl': round(ecart_pct, 2) if ecart_pct is not None else None,
            'montant': montant,
            # Nouveaux champs : état CMP après application de la transaction
            'cmp_apres': round(cmp_apres, 4),
            'parts_apres': round(parts_apres, 4),
            'total_investi_apres': round(total_investi_apres, 2),
            'plus_value_realisee': round(pv_realisee, 2),
        })

    # Convertir en liste ordonnée
    historique_list = [
        {'date_key': k, **v}
        for k, v in sorted(historique.items(), reverse=True)
    ]

    return JsonResponse({
        'historique': historique_list,
        'total_transactions': sum(len(h['transactions']) for h in historique_list),
    })


def _iter_mois(date_debut, date_fin):
    """Itère les (premier_jour, dernier_jour, label) pour chaque mois entre deux dates."""
    MOIS_FR = ['Jan', 'Fév', 'Mar', 'Avr', 'Mai', 'Juin', 'Juil', 'Aoû', 'Sep', 'Oct', 'Nov', 'Déc']
    current = date_debut.replace(day=1)
    while current <= date_fin:
        if current.month == 12:
            fin_mois = date(current.year + 1, 1, 1) - timedelta(days=1)
            prochain = date(current.year + 1, 1, 1)
        else:
            fin_mois = date(current.year, current.month + 1, 1) - timedelta(days=1)
            prochain = date(current.year, current.month + 1, 1)
        if fin_mois > date_fin:
            fin_mois = date_fin
        label = f"{MOIS_FR[current.month - 1]} {str(current.year)[2:]}"
        yield current, fin_mois, label
        current = prochain


def _parse_api_dates(request):
    """Parse les paramètres date_debut et date_fin d'une requête."""
    date_debut_str = request.GET.get('date_debut')
    date_fin_str = request.GET.get('date_fin')
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
        return None, None, JsonResponse({'error': 'Format de date invalide'}, status=400)
    return date_debut, date_fin, None


def _serie_encours(transactions, date_debut, date_fin):
    """
    Retourne la valeur du portefeuille à la fin de chaque mois entre debut et fin,
    ainsi que les souscriptions et rachats du mois.
    """
    charger_cache_vl()
    series = []
    for debut_mois, fin_mois, label in _iter_mois(date_debut, date_fin):
        positions = calculer_positions_a_date(transactions, fin_mois)
        valeur = calculer_valeur_portefeuille(positions, fin_mois)
        souscriptions = 0
        rachats = 0
        for t in transactions:
            if t.date_transaction and debut_mois <= t.date_transaction <= fin_mois:
                # CMP calculé à partir des FCP
                montant = float(t.quantite or 0) * cmp_from_fcp(t)
                if t.sens == 'souscription':
                    souscriptions += montant
                elif t.sens == 'rachat':
                    rachats += montant
        series.append({
            'label': label,
            'date': fin_mois.strftime('%Y-%m-%d'),
            'valeur': round(valeur, 2),
            'souscriptions': round(souscriptions, 2),
            'rachats': round(rachats, 2),
        })
    return series


def api_portefeuille_evolution(request, nom_per_pee):
    """Évolution mensuelle d'un plan (encours + flux)."""
    date_debut, date_fin, err = _parse_api_dates(request)
    if err:
        return err

    transactions = list(Sicav.objects.filter(nom_per_pee=nom_per_pee).order_by('date_transaction'))
    if not transactions:
        return JsonResponse({'error': 'Portefeuille non trouvé'}, status=404)

    series = _serie_encours(transactions, date_debut, date_fin)
    return JsonResponse({
        'nom_per_pee': nom_per_pee,
        'serie': series,
        'date_debut': date_debut.strftime('%d/%m/%Y'),
        'date_fin': date_fin.strftime('%d/%m/%Y'),
    })


def api_client_evolution(request, numero_compte):
    """Évolution mensuelle du portefeuille d'un client."""
    date_debut, date_fin, err = _parse_api_dates(request)
    if err:
        return err

    transactions = list(Sicav.objects.filter(numero_compte=numero_compte).order_by('date_transaction'))
    if not transactions:
        return JsonResponse({'error': 'Client non trouvé'}, status=404)

    series = _serie_encours(transactions, date_debut, date_fin)
    return JsonResponse({
        'numero_compte': numero_compte,
        'serie': series,
        'date_debut': date_debut.strftime('%d/%m/%Y'),
        'date_fin': date_fin.strftime('%d/%m/%Y'),
    })


def metadonnees(request):
    """Page des métadonnées"""
    # ========== DONNÉES FCP ==========
    # Récupérer les FCP uniques (métadonnées) - un seul enregistrement par FCP
    # Le catalogue FCP change rarement : on met en cache 15 minutes.
    _CACHE_KEY_FCP = "metadonnees_fcps_v1"
    _CACHE_TTL = 60 * 15  # 15 minutes

    cached_fcp = cache.get(_CACHE_KEY_FCP)
    if cached_fcp is not None:
        fcps, seen_fcps = cached_fcp
    else:
        fcps_raw = ValeurLiquidative.objects.exclude(nom_fcp__isnull=True).exclude(nom_fcp='').order_by('nom_fcp', '-date')

        # Fonction pour convertir en pourcentage affiché
        def to_percent(value):
            if value is None:
                return None
            try:
                v = float(value)
                # Si la valeur est déjà > 1, c'est probablement déjà en %, sinon multiplier par 100
                if v <= 1:
                    return round(v * 100, 2)
                return round(v, 2)
            except (ValueError, TypeError):
                return None

        # Dédupliquer par nom de FCP (garder le plus récent)
        seen_fcps = set()
        fcps = []
        for fcp in fcps_raw:
            if fcp.nom_fcp not in seen_fcps:
                seen_fcps.add(fcp.nom_fcp)
                fcps.append({
                    'nom_fcp': fcp.nom_fcp,
                    'categorie_fond': fcp.categorie_fond,
                    'type_fond': fcp.type_fond,
                    'est_fcp_islamique': fcp.est_fcp_islamique,
                    'horizon_investissement': fcp.horizon_investissement,
                    'benchmark_obligataire': fcp.benchmark_obligataire,
                    'benchmark_brvmc': fcp.benchmark_brvmc,
                    'benchmark_obligataire_pct': to_percent(fcp.benchmark_obligataire),
                    'benchmark_brvmc_pct': to_percent(fcp.benchmark_brvmc),
                    'date_creation': fcp.date_creation,
                    'depositaire': fcp.depositaire,
                    'frais_gestion_ttc': fcp.frais_gestion_ttc or '',
                    'frais_entree_ttc': fcp.frais_entree_ttc or '',
                    'frais_sortie_ttc': fcp.frais_sortie_ttc or '',
                    'echelle_risque': fcp.echelle_risque,
                })
        cache.set(_CACHE_KEY_FCP, (fcps, seen_fcps), _CACHE_TTL)
    
    # Statistiques FCP
    total_fcp = len(fcps)
    fcp_islamiques = sum(1 for f in fcps if f['est_fcp_islamique'])
    total_vl = ValeurLiquidative.objects.count()
    
    # Liste des VL récentes (dernière date disponible)
    derniere_date = ValeurLiquidative.objects.order_by('-date').values_list('date', flat=True).first()
    if derniere_date:
        valeurs_liquidatives = ValeurLiquidative.objects.filter(date=derniere_date).order_by('nom_fcp')
    else:
        valeurs_liquidatives = []
    
    # Liste des noms de FCP pour le filtre
    noms_fcp = sorted(seen_fcps)

    # Dictionnaire de métadonnées FCP pour enrichir les VL affichées
    fcp_meta_lookup = {f['nom_fcp']: f for f in fcps}

    # Enrichir les VL de la dernière date avec les métadonnées FCP
    # (les enregistrements VL importés en mode pivot n'ont pas toujours
    #  les champs categorie_fond / type_fond renseignés)
    if valeurs_liquidatives:
        valeurs_liquidatives = list(valeurs_liquidatives)
        for vl in valeurs_liquidatives:
            meta = fcp_meta_lookup.get(vl.nom_fcp, {})
            if not vl.categorie_fond:
                vl.categorie_fond = meta.get('categorie_fond') or ''
            if not vl.type_fond:
                vl.type_fond = meta.get('type_fond') or ''

    # Listes pour les filtres par catégorie et type de fond
    categories = sorted(set(f['categorie_fond'] for f in fcps if f['categorie_fond']))
    types_fonds = sorted(set(f['type_fond'] for f in fcps if f['type_fond']))
    
    # Préparer les données FCP pour JavaScript (édition)
    def _to_float_or_none(value):
        """Convertit en float si possible, sinon retourne None (pour les benchmarks qui peuvent être du texte libre)."""
        if value is None or value == '':
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    fcps_json_data = []
    for fcp in fcps:
        fcps_json_data.append({
            'nom_fcp': fcp['nom_fcp'],
            'categorie_fond': fcp['categorie_fond'] or '',
            'type_fond': fcp['type_fond'] or '',
            'est_fcp_islamique': fcp['est_fcp_islamique'],
            'horizon_investissement': fcp['horizon_investissement'],
            'benchmark_obligataire': fcp['benchmark_obligataire'] or '',
            'benchmark_brvmc': fcp['benchmark_brvmc'] or '',
            'benchmark_obligataire_num': _to_float_or_none(fcp['benchmark_obligataire']),
            'benchmark_brvmc_num': _to_float_or_none(fcp['benchmark_brvmc']),
            'date_creation': fcp['date_creation'].strftime('%Y-%m-%d') if fcp['date_creation'] else '',
            'depositaire': fcp['depositaire'] or '',
            'frais_gestion_ttc': fcp['frais_gestion_ttc'] or '',
            'frais_entree_ttc': fcp['frais_entree_ttc'] or '',
            'frais_sortie_ttc': fcp['frais_sortie_ttc'] or '',
            'echelle_risque': fcp['echelle_risque'],
        })
    
    # ========== DONNÉES SICAV (PEE/PER) ==========
    # Statistiques Sicav
    total_sicav = Sicav.objects.count()
    total_pee = Sicav.objects.filter(type_plan='PEE').count()
    total_per = Sicav.objects.filter(type_plan='PER').count()
    
    # Clients uniques
    clients_uniques = Sicav.objects.values('numero_compte').distinct().count()
    
    # Liste des transactions récentes (20 dernières) enrichies du CMP courant
    # calculé par le moteur CMP (running CMP après application de la transaction,
    # par couple (numéro de compte, FCP) = portefeuille du client sur ce fonds).
    charger_cache_vl()
    from .cmp import PositionFCP, appliquer_souscription, appliquer_rachat

    toutes_tx = list(
        Sicav.objects.all().order_by('date_transaction', 'id')
    )
    positions_cmp = {}
    for t in toutes_tx:
        if not (t.nom_fcp and t.date_transaction and t.sens in ('souscription', 'rachat')):
            t.cmp_calcule = None
            continue
        key = (t.numero_compte or '', t.nom_fcp)
        pos = positions_cmp.setdefault(key, PositionFCP())
        vl_raw = get_vl_at_date(t.nom_fcp, t.date_transaction)
        vl = float(vl_raw) if vl_raw else 0.0
        quantite = float(t.quantite) if t.quantite else 0.0
        if t.sens == 'souscription':
            appliquer_souscription(pos, quantite, vl)
        else:
            appliquer_rachat(pos, quantite, vl)
        # Après rachat total, pos.cmp = 0 : on affiche alors la VL d'exécution
        t.cmp_calcule = pos.cmp if pos.cmp > 0 else (vl if vl > 0 else None)

    # Toutes les transactions (par date décroissante) — pas de troncature :
    # le tableau côté template est filtrable, la pagination visuelle reste compacte.
    toutes_tx.sort(
        key=lambda t: (t.date_transaction or date.min, t.id or 0),
        reverse=True,
    )
    transactions_recentes = toutes_tx

    # Types de plan pour filtre
    types_plan = ['PEE', 'PER']
    
    # Sens de transaction pour filtre
    sens_options = ['souscription', 'rachat']
    
    # FCP disponibles dans Sicav — déduplication Python avec strip() pour
    # éliminer les doublons causés par des espaces parasites en base.
    fcp_sicav = sorted(set(
        v.strip() for v in
        Sicav.objects.values_list('nom_fcp', flat=True)
        .exclude(nom_fcp__isnull=True).exclude(nom_fcp='')
        if v and v.strip()
    ))
    
    context = {
        # Données FCP
        'fcps': fcps,
        'fcps_json': json.dumps(fcps_json_data),
        'total_fcp': total_fcp,
        'fcp_islamiques': fcp_islamiques,
        'total_vl': total_vl,
        'valeurs_liquidatives': valeurs_liquidatives,
        'noms_fcp': noms_fcp,
        'categories': categories,
        'types_fonds': types_fonds,
        'derniere_date': derniere_date,
        # Données Sicav (PEE/PER)
        'total_sicav': total_sicav,
        'total_pee': total_pee,
        'total_per': total_per,
        'clients_uniques': clients_uniques,
        'transactions_recentes': transactions_recentes,
        'types_plan': types_plan,
        'sens_options': sens_options,
        'fcp_sicav': fcp_sicav,
    }
    return render(request, 'reporting/metadonnees.html', context)


def controle(request):
    """Page Contrôle : qualité des données SICAV/VL, activité utilisateurs, sessions."""
    from django.contrib.auth import get_user_model
    from django.contrib.sessions.models import Session
    from django.utils import timezone

    User = get_user_model()
    aujourd_hui = date.today()
    il_y_a_30j = aujourd_hui - timedelta(days=30)
    il_y_a_90j = aujourd_hui - timedelta(days=90)

    # Filtre onglet actif
    vue_active = request.GET.get('vue', 'apercu')

    # =========================================================================
    # 1) APERÇU GLOBAL
    # =========================================================================
    total_transactions = Sicav.objects.count()
    total_souscriptions = Sicav.objects.filter(sens='souscription').count()
    total_rachats = Sicav.objects.filter(sens='rachat').count()
    total_plans = Sicav.objects.exclude(nom_per_pee__isnull=True).exclude(nom_per_pee='') \
        .values('nom_per_pee').distinct().count()
    total_clients = Sicav.objects.exclude(numero_compte__isnull=True).exclude(numero_compte='') \
        .values('numero_compte').distinct().count()
    total_fcp_meta = ValeurLiquidative.objects.exclude(nom_fcp__isnull=True).exclude(nom_fcp='') \
        .values('nom_fcp').distinct().count()
    total_vl = ValeurLiquidative.objects.count()

    premiere_tx = Sicav.objects.exclude(date_transaction__isnull=True) \
        .order_by('date_transaction').values_list('date_transaction', flat=True).first()
    derniere_tx = Sicav.objects.exclude(date_transaction__isnull=True) \
        .order_by('-date_transaction').values_list('date_transaction', flat=True).first()
    derniere_vl_date = ValeurLiquidative.objects.order_by('-date') \
        .values_list('date', flat=True).first()

    # Répartition par sens (avec quantités cumulées)
    repartition_sens = list(
        Sicav.objects.values('sens').annotate(
            nb=Count('id'), qte=Sum('quantite')
        ).order_by('-nb')
    )

    # Top 10 FCP par nombre de transactions
    top_fcp_tx = list(
        Sicav.objects.exclude(nom_fcp__isnull=True).exclude(nom_fcp='')
        .values('nom_fcp').annotate(nb=Count('id')).order_by('-nb')[:10]
    )

    # =========================================================================
    # 2) ALERTES DE COHÉRENCE (qualité des données)
    # =========================================================================
    # --- Transactions SICAV problématiques ---
    tx_date_future = list(
        Sicav.objects.filter(date_transaction__gt=aujourd_hui)
        .order_by('-date_transaction')[:100]
    )
    tx_sans_date = list(Sicav.objects.filter(date_transaction__isnull=True)[:100])
    tx_sans_sens = list(
        Sicav.objects.filter(Q(sens__isnull=True) | Q(sens=''))[:100]
    )
    tx_sans_fcp = list(
        Sicav.objects.filter(Q(nom_fcp__isnull=True) | Q(nom_fcp=''))[:100]
    )
    tx_sans_compte = list(
        Sicav.objects.filter(Q(numero_compte__isnull=True) | Q(numero_compte=''))[:100]
    )
    tx_sans_plan = list(
        Sicav.objects.filter(Q(nom_per_pee__isnull=True) | Q(nom_per_pee=''))[:100]
    )
    tx_quantite_invalide = list(
        Sicav.objects.filter(Q(quantite__isnull=True) | Q(quantite__lte=0))[:100]
    )

    # --- Transactions sur FCP inconnu (absent de ValeurLiquidative) ---
    fcp_connus = set(
        ValeurLiquidative.objects.exclude(nom_fcp__isnull=True).exclude(nom_fcp='')
        .values_list('nom_fcp', flat=True).distinct()
    )
    tx_fcp_inconnu = []
    for tx in Sicav.objects.exclude(nom_fcp__isnull=True).exclude(nom_fcp='').iterator():
        if tx.nom_fcp not in fcp_connus:
            tx_fcp_inconnu.append(tx)
            if len(tx_fcp_inconnu) >= 100:
                break

    # --- Transactions sans VL disponible à leur date ---
    charger_cache_vl()
    tx_sans_vl_a_date = []
    for tx in Sicav.objects.exclude(nom_fcp__isnull=True).exclude(nom_fcp='') \
            .exclude(date_transaction__isnull=True).iterator():
        if tx.nom_fcp in fcp_connus:
            vl = get_vl_at_date(tx.nom_fcp, tx.date_transaction)
            if vl is None:
                # CMP déjà corrigé manuellement → transaction considérée comme traitée
                if tx.cout_moyen_pondere and tx.cout_moyen_pondere > 0:
                    continue
                # Chercher la VL la plus proche avant et après
                vl_avant_obj = (
                    ValeurLiquidative.objects
                    .filter(nom_fcp=tx.nom_fcp, date__lt=tx.date_transaction)
                    .order_by('-date').first()
                )
                vl_apres_obj = (
                    ValeurLiquidative.objects
                    .filter(nom_fcp=tx.nom_fcp, date__gt=tx.date_transaction)
                    .order_by('date').first()
                )
                tx_sans_vl_a_date.append({
                    'tx': tx,
                    'cmp_actuel': float(tx.cout_moyen_pondere) if tx.cout_moyen_pondere else None,
                    'vl_avant': {
                        'pk': vl_avant_obj.pk,
                        'date': vl_avant_obj.date,
                        'valeur': float(vl_avant_obj.valeur_liquidative),
                        'ecart': (tx.date_transaction - vl_avant_obj.date).days,
                    } if vl_avant_obj and vl_avant_obj.valeur_liquidative else None,
                    'vl_apres': {
                        'pk': vl_apres_obj.pk,
                        'date': vl_apres_obj.date,
                        'valeur': float(vl_apres_obj.valeur_liquidative),
                        'ecart': (vl_apres_obj.date - tx.date_transaction).days,
                    } if vl_apres_obj and vl_apres_obj.valeur_liquidative else None,
                })
                if len(tx_sans_vl_a_date) >= 100:
                    break

    # --- FCP sans VL récente (dernière VL > 90 jours) ---
    fcp_vl_obsolete = []
    for nom_fcp in fcp_connus:
        derniere = ValeurLiquidative.objects.filter(nom_fcp=nom_fcp) \
            .order_by('-date').values_list('date', flat=True).first()
        if derniere and derniere < il_y_a_90j:
            fcp_vl_obsolete.append({
                'nom_fcp': nom_fcp,
                'derniere_date': derniere,
                'anciennete': (aujourd_hui - derniere).days,
            })
    fcp_vl_obsolete.sort(key=lambda x: x['derniere_date'])

    # --- Clients avec position négative sur un FCP (rachats > souscriptions) ---
    positions_negatives = []
    # Agrégat SQL: somme souscriptions - somme rachats par (compte, fcp)
    from django.db.models import Case, When, F, DecimalField
    agg = (
        Sicav.objects
        .exclude(numero_compte__isnull=True).exclude(numero_compte='')
        .exclude(nom_fcp__isnull=True).exclude(nom_fcp='')
        .values('numero_compte', 'nom_prenom', 'nom_fcp')
        .annotate(
            solde=Sum(
                Case(
                    When(sens='souscription', then=F('quantite')),
                    When(sens='rachat', then=-F('quantite')),
                    default=0,
                    output_field=DecimalField(max_digits=20, decimal_places=4),
                )
            )
        )
    )
    for row in agg:
        if row['solde'] is not None and row['solde'] < 0:
            positions_negatives.append(row)
    positions_negatives.sort(key=lambda r: r['solde'])
    positions_negatives = positions_negatives[:100]

    # --- Doublons potentiels ---
    doublons_qs = (
        Sicav.objects
        .exclude(date_transaction__isnull=True)
        .exclude(numero_compte__isnull=True).exclude(numero_compte='')
        .exclude(nom_fcp__isnull=True).exclude(nom_fcp='')
        .values('date_transaction', 'numero_compte', 'nom_fcp', 'sens', 'quantite')
        .annotate(nb=Count('id'))
        .filter(nb__gt=1)
        .order_by('-nb')[:100]
    )
    doublons_potentiels = list(doublons_qs)

    # --- Totaux d'alertes ---
    total_alertes = (
        len(tx_date_future) + len(tx_sans_date) + len(tx_sans_sens)
        + len(tx_sans_fcp) + len(tx_sans_compte) + len(tx_sans_plan)
        + len(tx_quantite_invalide) + len(tx_fcp_inconnu)
        + len(tx_sans_vl_a_date) + len(fcp_vl_obsolete)
        + len(positions_negatives) + len(doublons_potentiels)
    )

    # --- Cartes d'alertes structurées (dashboard) ---
    # severity : critical (rouge), warning (orange), info (gris)
    # kind     : type de ligne — sicav_tx, fcp_vl, position, doublon
    cartes_alertes = [
        {
            'id': 'date-future', 'severity': 'critical', 'kind': 'sicav_tx',
            'icon': 'bi-calendar-x',
            'titre': 'Transactions avec date future',
            'description': "Une transaction ne peut pas avoir une date postérieure à aujourd'hui.",
            'action': "Modifier la date ou supprimer la transaction.",
            'rows': tx_date_future,
        },
        {
            'id': 'qte-invalide', 'severity': 'critical', 'kind': 'sicav_tx',
            'icon': 'bi-123',
            'titre': 'Quantités nulles, vides ou négatives',
            'description': "Quantité de parts invalide : empêche le calcul du CMP et du portefeuille.",
            'action': "Corriger la quantité dans l'admin ou supprimer la transaction.",
            'rows': tx_quantite_invalide,
        },
        {
            'id': 'fcp-inconnu', 'severity': 'critical', 'kind': 'sicav_tx',
            'icon': 'bi-question-diamond',
            'titre': 'FCP inconnu (absent des VL)',
            'description': "Le FCP référencé par la transaction n'existe pas dans la table des valeurs liquidatives.",
            'action': "Créer le FCP côté Métadonnées ou corriger le libellé.",
            'rows': tx_fcp_inconnu,
        },
        {
            'id': 'pos-negative', 'severity': 'critical', 'kind': 'position',
            'icon': 'bi-dash-circle',
            'titre': 'Positions négatives',
            'description': "Le cumul des rachats dépasse celui des souscriptions pour ce couple (client, FCP).",
            'action': "Vérifier la chronologie et la quantité des transactions concernées.",
            'rows': positions_negatives,
        },
        {
            'id': 'sans-date', 'severity': 'warning', 'kind': 'sicav_tx',
            'icon': 'bi-calendar-minus',
            'titre': 'Transactions sans date',
            'description': "Date de transaction manquante : exclut la transaction des calculs de performance.",
            'action': "Renseigner la date dans l'admin.",
            'rows': tx_sans_date,
        },
        {
            'id': 'sans-sens', 'severity': 'warning', 'kind': 'sicav_tx',
            'icon': 'bi-arrow-down-up',
            'titre': 'Sens non renseigné',
            'description': "Ni souscription ni rachat : la transaction est ignorée par le moteur CMP.",
            'action': "Choisir le sens dans l'admin.",
            'rows': tx_sans_sens,
        },
        {
            'id': 'sans-fcp', 'severity': 'warning', 'kind': 'sicav_tx',
            'icon': 'bi-building-dash',
            'titre': 'FCP non renseigné',
            'description': "Impossible de valoriser une transaction sans savoir sur quel FCP elle porte.",
            'action': "Renseigner le FCP dans l'admin.",
            'rows': tx_sans_fcp,
        },
        {
            'id': 'sans-compte', 'severity': 'warning', 'kind': 'sicav_tx',
            'icon': 'bi-person-dash',
            'titre': 'Numéro de compte manquant',
            'description': "Transaction non rattachable à un client : exclue des analyses clients.",
            'action': "Renseigner le numéro de compte dans l'admin.",
            'rows': tx_sans_compte,
        },
        {
            'id': 'sans-plan', 'severity': 'warning', 'kind': 'sicav_tx',
            'icon': 'bi-briefcase',
            'titre': 'Plan PER/PEE non renseigné',
            'description': "Transaction orpheline : non prise en compte dans les analyses par plan.",
            'action': "Renseigner le nom du plan dans l'admin.",
            'rows': tx_sans_plan,
        },
        {
            'id': 'sans-vl-date', 'severity': 'warning', 'kind': 'sicav_tx_novl',
            'icon': 'bi-calendar-event',
            'titre': 'VL indisponible à la date de transaction',
            'description': "Aucune VL antérieure ou égale à la date de transaction : CMP calculé à 0.",
            'action': "Choisir la VL disponible la plus proche (avant ou après) pour corriger directement le CMP de la transaction.",
            'rows': tx_sans_vl_a_date,
        },
        {
            'id': 'vl-obsolete', 'severity': 'warning', 'kind': 'fcp_vl',
            'icon': 'bi-clock-history',
            'titre': 'FCP sans VL récente (> 90 j)',
            'description': "La dernière VL connue est trop ancienne : valorisation courante dégradée.",
            'action': "Ajouter la VL la plus récente du FCP.",
            'rows': fcp_vl_obsolete,
        },
        {
            'id': 'doublons', 'severity': 'warning', 'kind': 'doublon',
            'icon': 'bi-files',
            'titre': 'Doublons potentiels',
            'description': "Plusieurs transactions identiques (date, compte, FCP, sens, quantité).",
            'action': "Purger pour ne garder qu'une occurrence par groupe.",
            'rows': doublons_potentiels,
        },
    ]

    nb_critiques = sum(len(c['rows']) for c in cartes_alertes if c['severity'] == 'critical')
    nb_warnings = sum(len(c['rows']) for c in cartes_alertes if c['severity'] == 'warning')
    nb_controles_ok = sum(1 for c in cartes_alertes if not c['rows'])
    nb_controles_total = len(cartes_alertes)

    # =========================================================================
    # 3) UTILISATEURS
    # =========================================================================
    utilisateurs = list(
        User.objects.all().order_by('-last_login', 'username')
    )
    nb_users_total = len(utilisateurs)
    nb_users_actifs = sum(1 for u in utilisateurs if u.is_active)
    nb_superusers = sum(1 for u in utilisateurs if u.is_superuser)
    nb_users_connectes_30j = sum(
        1 for u in utilisateurs
        if u.last_login and u.last_login.date() >= il_y_a_30j
    )
    nb_users_jamais = sum(1 for u in utilisateurs if not u.last_login)

    # =========================================================================
    # 4) SESSIONS ACTIVES
    # =========================================================================
    now = timezone.now()
    sessions_actives_qs = Session.objects.filter(expire_date__gt=now).order_by('-expire_date')
    sessions_actives = []
    user_ids_connectes = set()
    for s in sessions_actives_qs[:200]:
        data = s.get_decoded()
        uid = data.get('_auth_user_id')
        user_obj = None
        if uid:
            try:
                user_obj = User.objects.get(pk=uid)
                user_ids_connectes.add(int(uid))
            except User.DoesNotExist:
                pass
        sessions_actives.append({
            'session_key': s.session_key,
            'expire_date': s.expire_date,
            'user': user_obj,
        })
    nb_sessions_actives = sessions_actives_qs.count()
    nb_users_connectes_maintenant = len(user_ids_connectes)

    context = {
        'vue_active': vue_active,
        # Aperçu
        'total_transactions': total_transactions,
        'total_souscriptions': total_souscriptions,
        'total_rachats': total_rachats,
        'total_plans': total_plans,
        'total_clients': total_clients,
        'total_fcp_meta': total_fcp_meta,
        'total_vl': total_vl,
        'premiere_tx': premiere_tx,
        'derniere_tx': derniere_tx,
        'derniere_vl_date': derniere_vl_date,
        'repartition_sens': repartition_sens,
        'top_fcp_tx': top_fcp_tx,
        # Alertes
        'tx_date_future': tx_date_future,
        'tx_sans_date': tx_sans_date,
        'tx_sans_sens': tx_sans_sens,
        'tx_sans_fcp': tx_sans_fcp,
        'tx_sans_compte': tx_sans_compte,
        'tx_sans_plan': tx_sans_plan,
        'tx_quantite_invalide': tx_quantite_invalide,
        'tx_fcp_inconnu': tx_fcp_inconnu,
        'tx_sans_vl_a_date': tx_sans_vl_a_date,
        'fcp_vl_obsolete': fcp_vl_obsolete,
        'positions_negatives': positions_negatives,
        'doublons_potentiels': doublons_potentiels,
        'total_alertes': total_alertes,
        'cartes_alertes': cartes_alertes,
        'nb_critiques': nb_critiques,
        'nb_warnings': nb_warnings,
        'nb_controles_ok': nb_controles_ok,
        'nb_controles_total': nb_controles_total,
        # Utilisateurs
        'utilisateurs': utilisateurs,
        'nb_users_total': nb_users_total,
        'nb_users_actifs': nb_users_actifs,
        'nb_superusers': nb_superusers,
        'nb_users_connectes_30j': nb_users_connectes_30j,
        'nb_users_jamais': nb_users_jamais,
        # Sessions
        'sessions_actives': sessions_actives,
        'nb_sessions_actives': nb_sessions_actives,
        'nb_users_connectes_maintenant': nb_users_connectes_maintenant,
        'aujourd_hui': aujourd_hui,
    }
    return render(request, 'reporting/controle.html', context)


def a_propos(request):
    """Page à propos"""
    return render(request, 'reporting/a_propos.html')


@require_POST
def controle_appliquer_vl_proche(request, pk):
    """
    Corriger le CMP d'une transaction en utilisant la VL la plus proche disponible
    (avant ou après la date de transaction, selon le choix de l'utilisateur).
    Le champ cout_moyen_pondere est mis à jour directement avec la valeur VL trouvée.
    Aucune VL n'est créée.
    """
    if not (request.user.is_authenticated and request.user.is_superuser):
        return JsonResponse({'success': False, 'message': 'Non autorisé'}, status=403)
    try:
        tx = Sicav.objects.get(pk=pk)
    except Sicav.DoesNotExist:
        messages.error(request, "Transaction introuvable.")
        return _redirect_controle(request)
    if not tx.date_transaction or not tx.nom_fcp:
        messages.error(request, "Transaction incomplète (date ou FCP manquant).")
        return _redirect_controle(request)

    direction = request.POST.get('direction', 'avant')
    if direction == 'avant':
        source_vl = (
            ValeurLiquidative.objects
            .filter(nom_fcp=tx.nom_fcp, date__lt=tx.date_transaction)
            .order_by('-date').first()
        )
        label_direction = "antérieure"
    else:
        source_vl = (
            ValeurLiquidative.objects
            .filter(nom_fcp=tx.nom_fcp, date__gt=tx.date_transaction)
            .order_by('date').first()
        )
        label_direction = "postérieure"

    if not source_vl or not source_vl.valeur_liquidative:
        messages.warning(request, f"Aucune VL {label_direction} disponible pour « {tx.nom_fcp} ».")
        return _redirect_controle(request)

    ancien_cmp = tx.cout_moyen_pondere
    tx.cout_moyen_pondere = source_vl.valeur_liquidative
    tx.save(update_fields=['cout_moyen_pondere'])

    messages.success(
        request,
        f"CMP corrigé pour la transaction SICAV #{pk} ({tx.nom_fcp}, {tx.date_transaction:%d/%m/%Y}) : "
        f"{ancien_cmp or '—'} → {source_vl.valeur_liquidative} "
        f"(VL {label_direction} du {source_vl.date:%d/%m/%Y})."
    )
    return _redirect_controle(request)


@require_POST
def controle_supprimer_sicav(request, pk):
    if not (request.user.is_authenticated and request.user.is_superuser):
        return JsonResponse({'success': False, 'message': 'Non autorisé'}, status=403)
    try:
        tx = Sicav.objects.get(pk=pk)
    except Sicav.DoesNotExist:
        messages.error(request, "Transaction introuvable.")
        return _redirect_controle(request)
    tx.delete()
    messages.success(request, f"Transaction SICAV #{pk} supprimée.")
    return _redirect_controle(request)


@require_POST
def controle_purger_doublons(request):
    """Supprimer les doublons stricts (mêmes date/compte/FCP/sens/quantité) en gardant la première occurrence."""
    if not (request.user.is_authenticated and request.user.is_superuser):
        return JsonResponse({'success': False, 'message': 'Non autorisé'}, status=403)

    doublons = (
        Sicav.objects
        .exclude(date_transaction__isnull=True)
        .exclude(numero_compte__isnull=True).exclude(numero_compte='')
        .exclude(nom_fcp__isnull=True).exclude(nom_fcp='')
        .values('date_transaction', 'numero_compte', 'nom_fcp', 'sens', 'quantite')
        .annotate(nb=Count('id'))
        .filter(nb__gt=1)
    )

    total_supprimes = 0
    with transaction.atomic():
        for d in doublons:
            ids = list(
                Sicav.objects.filter(
                    date_transaction=d['date_transaction'],
                    numero_compte=d['numero_compte'],
                    nom_fcp=d['nom_fcp'],
                    sens=d['sens'],
                    quantite=d['quantite'],
                ).order_by('id').values_list('id', flat=True)
            )
            # Garder le premier, supprimer les autres
            if len(ids) > 1:
                deleted, _ = Sicav.objects.filter(pk__in=ids[1:]).delete()
                total_supprimes += deleted

    if total_supprimes:
        messages.success(request, f"{total_supprimes} doublon{'s' if total_supprimes > 1 else ''} supprimé{'s' if total_supprimes > 1 else ''}.")
    else:
        messages.info(request, "Aucun doublon à supprimer.")
    return _redirect_controle(request)


def _redirect_controle(request):
    """Rediriger vers Contrôle en conservant l'onglet Alertes."""
    from django.shortcuts import redirect
    from django.urls import reverse
    return redirect(f"{reverse('reporting:controle')}?vue=alertes")


@require_POST
def modifier_fcp(request):
    """Modifier les métadonnées d'un FCP"""
    try:
        data = json.loads(request.body)
        nom_fcp_original = data.get('nom_fcp_original')
        nom_fcp = data.get('nom_fcp')
        
        if not nom_fcp_original:
            return JsonResponse({'success': False, 'message': 'Nom du FCP original requis'})
        if not nom_fcp:
            return JsonResponse({'success': False, 'message': 'Nom du FCP requis'})
        
        # Vérifier si le nouveau nom existe déjà (si renommage)
        if nom_fcp != nom_fcp_original:
            if ValeurLiquidative.objects.filter(nom_fcp=nom_fcp).exists():
                return JsonResponse({
                    'success': False, 
                    'message': f'Un FCP avec le nom "{nom_fcp}" existe déjà'
                })
        
        # Valider que la somme des benchmarks = 1 (100%) seulement si les deux sont renseignés
        benchmark_oblig = data.get('benchmark_obligataire')
        benchmark_brvmc = data.get('benchmark_brvmc')
        
        # Validation seulement si au moins un benchmark est défini et non vide
        has_oblig = benchmark_oblig is not None and str(benchmark_oblig).strip() != ''
        has_brvmc = benchmark_brvmc is not None and str(benchmark_brvmc).strip() != ''
        
        if has_oblig or has_brvmc:
            try:
                b_oblig = float(benchmark_oblig) if has_oblig else 0
                b_brvmc = float(benchmark_brvmc) if has_brvmc else 0
                total = b_oblig + b_brvmc
                # Tolérance de 0.02 pour les erreurs d'arrondi (2%)
                if abs(total - 1.0) > 0.02:
                    return JsonResponse({
                        'success': False, 
                        'message': f'La somme des benchmarks doit être égale à 100% (actuellement: {total*100:.1f}%)'
                    })
            except (ValueError, TypeError):
                pass
        
        # Préparer les valeurs à mettre à jour
        update_data = {}
        
        if 'categorie_fond' in data:
            update_data['categorie_fond'] = data['categorie_fond'] or None
        if 'type_fond' in data:
            update_data['type_fond'] = data['type_fond'] or None
        if 'est_fcp_islamique' in data:
            update_data['est_fcp_islamique'] = bool(data['est_fcp_islamique'])
        if 'horizon_investissement' in data:
            try:
                update_data['horizon_investissement'] = int(data['horizon_investissement']) if data['horizon_investissement'] else None
            except (ValueError, TypeError):
                update_data['horizon_investissement'] = None
        if 'benchmark_obligataire' in data:
            update_data['benchmark_obligataire'] = str(data['benchmark_obligataire']) if data['benchmark_obligataire'] else None
        if 'benchmark_brvmc' in data:
            update_data['benchmark_brvmc'] = str(data['benchmark_brvmc']) if data['benchmark_brvmc'] else None
        if 'date_creation' in data:
            if data['date_creation']:
                try:
                    update_data['date_creation'] = datetime.strptime(data['date_creation'], '%Y-%m-%d').date()
                except ValueError:
                    update_data['date_creation'] = None
            else:
                update_data['date_creation'] = None
        if 'depositaire' in data:
            update_data['depositaire'] = data['depositaire'] or None
        if 'frais_gestion_ttc' in data:
            update_data['frais_gestion_ttc'] = str(data['frais_gestion_ttc']) if data['frais_gestion_ttc'] else None
        if 'frais_entree_ttc' in data:
            update_data['frais_entree_ttc'] = str(data['frais_entree_ttc']) if data['frais_entree_ttc'] else None
        if 'frais_sortie_ttc' in data:
            update_data['frais_sortie_ttc'] = str(data['frais_sortie_ttc']) if data['frais_sortie_ttc'] else None
        if 'echelle_risque' in data:
            try:
                update_data['echelle_risque'] = int(data['echelle_risque']) if data['echelle_risque'] else None
            except (ValueError, TypeError):
                update_data['echelle_risque'] = None
        
        # Si le nom a changé, l'ajouter aux données à mettre à jour
        if nom_fcp != nom_fcp_original:
            update_data['nom_fcp'] = nom_fcp
        
        # Mettre à jour tous les enregistrements de ce FCP
        updated = ValeurLiquidative.objects.filter(nom_fcp=nom_fcp_original).update(**update_data)
        
        if updated > 0:
            # Invalider le cache des métadonnées FCP
            cache.delete("metadonnees_fcps_v1")
            if nom_fcp != nom_fcp_original:
                return JsonResponse({
                    'success': True, 
                    'message': f'FCP renommé de "{nom_fcp_original}" en "{nom_fcp}" ({updated} enregistrements mis à jour)'
                })
            else:
                return JsonResponse({
                    'success': True, 
                    'message': f'FCP "{nom_fcp}" mis à jour ({updated} enregistrements)'
                })
        else:
            return JsonResponse({
                'success': False, 
                'message': f'Aucun FCP trouvé avec le nom "{nom_fcp_original}"'
            })
            
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Données JSON invalides'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})


# ========== EXPORT FUNCTIONS ==========

def _format_frais_export(value):
    """Formate une valeur de frais pour l'export CSV."""
    if value is None:
        return ''
    s = str(value).strip()
    if not s:
        return ''
    s_lower = s.lower().replace('é', 'e').replace('è', 'e')
    if s_lower in ('neant', 'néant'):
        return 'Néant'
    for marker in ('%', 'FCFA', 'HT', 'fcfa', 'ht'):
        if marker in s:
            return s
    try:
        v = float(s)
    except (ValueError, TypeError):
        return s or ''
    if v == 0:
        return 'Néant'
    if 0 < v <= 1:
        return f"{v * 100:.2f}%"
    return f"{v:.0f} FCFA"


def _format_benchmark_export(value):
    """Formate un benchmark en % pour l'export (ex : 0.75 -> 75,00%)."""
    if value is None:
        return ''
    s = str(value).strip()
    if not s:
        return ''
    if '%' in s:
        return s
    try:
        v = float(s)
    except (ValueError, TypeError):
        return s
    # Si déjà > 1, c'est probablement déjà en %
    if v > 1:
        return f"{v:.2f}%".replace('.', ',')
    return f"{v * 100:.2f}%".replace('.', ',')


def exporter_fcp(request):
    """Exporter la fiche signélatique des FCP (une ligne par FCP, enregistrement le plus récent)"""
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="fiche_signaletique_fcp.csv"'
    response.write('\ufeff')  # BOM pour Excel

    writer = csv.writer(response, delimiter=';')

    writer.writerow([
        'Nom du FCP', 'Catégorie', 'Type de fond', 'FCP Islamique',
        'Échelle de risque', 'Horizon investissement (ans)',
        'Frais gestion TTC', 'Frais entrée TTC', 'Frais sortie TTC',
        'Date de création', 'Dépositaire',
        'Benchmark Obligataire (%)', 'Benchmark BRVMC (%)'
    ])

    # Une ligne par FCP (enregistrement le plus récent)
    fcps_raw = ValeurLiquidative.objects.exclude(
        nom_fcp__isnull=True
    ).exclude(nom_fcp='').order_by('nom_fcp', '-date')

    seen = set()
    for fcp in fcps_raw:
        if fcp.nom_fcp in seen:
            continue
        seen.add(fcp.nom_fcp)
        writer.writerow([
            fcp.nom_fcp or '',
            (fcp.categorie_fond or '').title(),
            (fcp.type_fond or '').title(),
            'Oui' if fcp.est_fcp_islamique else 'Non',
            fcp.echelle_risque or '',
            fcp.horizon_investissement or '',
            _format_frais_export(fcp.frais_gestion_ttc),
            _format_frais_export(fcp.frais_entree_ttc),
            _format_frais_export(fcp.frais_sortie_ttc),
            fcp.date_creation.strftime('%d/%m/%Y') if fcp.date_creation else '',
            fcp.depositaire or '',
            _format_benchmark_export(fcp.benchmark_obligataire),
            _format_benchmark_export(fcp.benchmark_brvmc),
        ])

    return response


def exporter_vl(request):
    """Exporter l'historique des VL en format pivot : Date en ligne, un FCP par colonne."""
    # Charger toutes les VL en mémoire
    valeurs = ValeurLiquidative.objects.exclude(
        nom_fcp__isnull=True
    ).exclude(nom_fcp='').order_by('date', 'nom_fcp')

    # Construire le pivot : {date: {nom_fcp: valeur}}
    pivot = {}
    fcps_set = set()
    for vl in valeurs:
        if not vl.date:
            continue
        pivot.setdefault(vl.date, {})[vl.nom_fcp] = vl.valeur_liquidative
        fcps_set.add(vl.nom_fcp)

    fcp_columns = sorted(fcps_set)
    dates_sorted = sorted(pivot.keys())

    output = io.StringIO()
    output.write('\ufeff')  # BOM pour Excel
    writer = csv.writer(output, delimiter=';')

    # En-tête
    writer.writerow(['Date'] + fcp_columns)

    # Lignes
    for d in dates_sorted:
        row_data = pivot[d]
        row = [d.strftime('%d/%m/%Y')]
        for fcp in fcp_columns:
            val = row_data.get(fcp)
            row.append(str(val).replace('.', ',') if val is not None else '')
        writer.writerow(row)

    response = HttpResponse(output.getvalue(), content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="historique_valeurs_liquidatives.csv"'
    return response


# ========== IMPORT FUNCTIONS ==========

def parse_decimal(value):
    """Convertir une valeur en Decimal, gérant les virgules françaises"""
    if not value or value.strip() == '':
        return None
    try:
        # Remplacer la virgule par un point
        value = value.strip().replace(',', '.').replace(' ', '')
        return Decimal(value)
    except (InvalidOperation, ValueError):
        return None


def parse_date(value):
    """Convertir une date au format JJ/MM/AAAA ou AAAA-MM-JJ"""
    if not value or value.strip() == '':
        return None
    value = value.strip()
    
    # Essayer différents formats
    formats = ['%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y', '%Y/%m/%d']
    for fmt in formats:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def parse_boolean(value):
    """Convertir une valeur en booléen"""
    if not value:
        return False
    value = value.strip().lower()
    return value in ['oui', 'yes', 'true', '1', 'vrai', 'o']


@require_POST
def importer_fcp(request):
    """Importer les métadonnées des FCP depuis un fichier CSV"""
    if 'fichier_csv' not in request.FILES:
        return JsonResponse({'success': False, 'message': 'Aucun fichier fourni'})
    
    fichier = request.FILES['fichier_csv']
    
    # Vérifier l'extension
    if not fichier.name.endswith('.csv'):
        return JsonResponse({'success': False, 'message': 'Le fichier doit être au format CSV'})
    
    try:
        # Lire le contenu du fichier
        contenu = fichier.read().decode('utf-8-sig')  # utf-8-sig gère le BOM
        reader = csv.DictReader(io.StringIO(contenu), delimiter=';')
        
        lignes_importees = 0
        lignes_modifiees = 0
        erreurs = []
        
        for i, row in enumerate(reader, start=2):  # Ligne 2 car ligne 1 = en-têtes
            try:
                nom_fcp = row.get('Nom du FCP', '').strip()
                
                if not nom_fcp:
                    erreurs.append(f"Ligne {i}: Nom du FCP manquant")
                    continue
                
                # Données à mettre à jour
                defaults = {
                    'categorie_fond': row.get('Catégorie', '').strip().lower() or None,
                    'type_fond': row.get('Type de fond', '').strip().lower() or None,
                    'est_fcp_islamique': parse_boolean(row.get('Est FCP Islamique', '')),
                    'horizon_investissement': int(row.get('Horizon investissement (ans)', '').strip()) if row.get('Horizon investissement (ans)', '').strip().isdigit() else None,
                    'frais_gestion_ttc': parse_decimal(row.get('Frais gestion TTC (%)', '')),
                    'frais_entree_ttc': parse_decimal(row.get('Frais entrée TTC (%)', '')),
                    'frais_sortie_ttc': parse_decimal(row.get('Frais sortie TTC (%)', '')),
                    'date_creation': parse_date(row.get('Date de création', '')),
                    'depositaire': row.get('Dépositaire', '').strip() or None,
                    'benchmark_obligataire': row.get('Benchmark Obligataire', '').strip() or None,
                    'benchmark_brvmc': row.get('Benchmark BRVMC', '').strip() or None,
                }
                
                # Mettre à jour tous les enregistrements avec ce nom de FCP
                updated = ValeurLiquidative.objects.filter(nom_fcp=nom_fcp).update(**defaults)
                
                if updated > 0:
                    lignes_modifiees += 1
                else:
                    # Créer un nouvel enregistrement si le FCP n'existe pas
                    ValeurLiquidative.objects.create(nom_fcp=nom_fcp, **defaults)
                    lignes_importees += 1
                    
            except Exception as e:
                erreurs.append(f"Ligne {i}: {str(e)}")
        
        message = f"{lignes_importees} FCP créés, {lignes_modifiees} FCP mis à jour."
        if erreurs:
            message += f" {len(erreurs)} erreurs."
        
        return JsonResponse({
            'success': True, 
            'message': message,
            'importes': lignes_importees,
            'modifies': lignes_modifiees,
            'erreurs': erreurs[:10]  # Limiter les erreurs affichées
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Erreur lors de la lecture du fichier: {str(e)}'})


@require_POST
def importer_vl(request):
    """Importer les valeurs liquidatives depuis un fichier CSV"""
    if 'fichier_csv' not in request.FILES:
        return JsonResponse({'success': False, 'message': 'Aucun fichier fourni'})
    
    fichier = request.FILES['fichier_csv']
    
    # Vérifier l'extension
    if not fichier.name.endswith('.csv'):
        return JsonResponse({'success': False, 'message': 'Le fichier doit être au format CSV'})
    
    try:
        # Lire le contenu du fichier
        contenu = fichier.read().decode('utf-8-sig')
        reader = csv.DictReader(io.StringIO(contenu), delimiter=';')
        
        lignes_importees = 0
        lignes_modifiees = 0
        erreurs = []
        
        for i, row in enumerate(reader, start=2):
            try:
                date = parse_date(row.get('Date', ''))
                nom_fcp = row.get('Nom du FCP', '').strip()
                valeur_liquidative = parse_decimal(row.get('Valeur Liquidative', ''))
                
                if not nom_fcp:
                    erreurs.append(f"Ligne {i}: Nom du FCP manquant")
                    continue
                
                if not date:
                    erreurs.append(f"Ligne {i}: Date manquante ou invalide")
                    continue
                
                # Données
                defaults = {
                    'valeur_liquidative': valeur_liquidative,
                    'categorie_fond': row.get('Catégorie', '').strip().lower() or None,
                    'type_fond': row.get('Type de fond', '').strip().lower() or None,
                    'est_fcp_islamique': parse_boolean(row.get('Est FCP Islamique', '')),
                    'horizon_investissement': int(row.get('Horizon investissement (ans)', '').strip()) if row.get('Horizon investissement (ans)', '').strip().isdigit() else None,
                    'frais_gestion_ttc': parse_decimal(row.get('Frais gestion TTC (%)', '')),
                    'frais_entree_ttc': parse_decimal(row.get('Frais entrée TTC (%)', '')),
                    'frais_sortie_ttc': parse_decimal(row.get('Frais sortie TTC (%)', '')),
                    'date_creation': parse_date(row.get('Date de création', '')),
                    'depositaire': row.get('Dépositaire', '').strip() or None,
                    'benchmark_obligataire': row.get('Benchmark Obligataire', '').strip() or None,
                    'benchmark_brvmc': row.get('Benchmark BRVMC', '').strip() or None,
                }
                
                # Mise à jour ou création
                obj, created = ValeurLiquidative.objects.update_or_create(
                    date=date,
                    nom_fcp=nom_fcp,
                    defaults=defaults
                )
                
                if created:
                    lignes_importees += 1
                else:
                    lignes_modifiees += 1
                    
            except Exception as e:
                erreurs.append(f"Ligne {i}: {str(e)}")
        
        message = f"{lignes_importees} VL créées, {lignes_modifiees} VL mises à jour."
        if erreurs:
            message += f" {len(erreurs)} erreurs."
        
        return JsonResponse({
            'success': True, 
            'message': message,
            'importes': lignes_importees,
            'modifies': lignes_modifiees,
            'erreurs': erreurs[:10]
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Erreur lors de la lecture du fichier: {str(e)}'})


# ========== IMPORT EXCEL AVEC PREVIEW ==========

def read_excel_file(fichier):
    """Lire un fichier Excel et retourner un DataFrame pandas."""
    if not HAS_PANDAS:
        raise ImportError("pandas et openpyxl sont requis pour lire les fichiers Excel")
    return pd.read_excel(fichier)


@require_POST
def analyser_fichier_excel(request):
    """
    Analyser un fichier Excel et retourner un aperçu des données avec comparaison.
    Retourne les nouvelles entrées, les entrées existantes et les changements.
    """
    if not HAS_PANDAS:
        return JsonResponse({
            'success': False, 
            'message': 'pandas et openpyxl sont requis pour lire les fichiers Excel. Installez-les avec: pip install pandas openpyxl'
        })
    
    if 'fichier' not in request.FILES:
        return JsonResponse({'success': False, 'message': 'Aucun fichier fourni'})
    
    fichier = request.FILES['fichier']
    type_import = request.POST.get('type', 'vl')  # 'vl' ou 'fcp'
    
    # Vérifier l'extension
    if not fichier.name.endswith(('.xlsx', '.xls')):
        return JsonResponse({'success': False, 'message': 'Le fichier doit être au format Excel (.xlsx ou .xls)'})
    
    try:
        df = read_excel_file(fichier)
        
        if type_import == 'fcp':
            return analyser_fcp_excel(df)
        else:
            return analyser_vl_excel(df)
            
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Erreur lors de la lecture du fichier: {str(e)}'})


def analyser_fcp_excel(df):
    """Analyser un fichier Excel de métadonnées FCP."""
    # Détecter le format du fichier
    colonnes = list(df.columns)
    
    # Mapping des colonnes possibles
    col_nom = None
    for c in colonnes:
        if 'fcp' in c.lower() or 'fond' in c.lower():
            col_nom = c
            break
    
    if not col_nom:
        return JsonResponse({
            'success': False, 
            'message': 'Colonne "Nom du FCP" non trouvée dans le fichier'
        })
    
    # Récupérer les FCP existants
    fcps_existants = set(ValeurLiquidative.objects.values_list('nom_fcp', flat=True).distinct())
    
    nouveaux = []
    existants = []
    
    for _, row in df.iterrows():
        nom_fcp = str(row[col_nom]).strip() if pd.notna(row[col_nom]) else None
        if not nom_fcp or nom_fcp == 'nan':
            continue
        
        fcp_data = {
            'nom_fcp': nom_fcp,
            'est_fcp_islamique': False,
            'categorie_fond': None,
            'type_fond': None,
        }
        
        # Extraire les données
        for col in colonnes:
            col_lower = col.lower()
            val = row[col]
            
            if pd.isna(val):
                continue
                
            if 'islamique' in col_lower:
                fcp_data['est_fcp_islamique'] = str(val).lower() in ['oui', 'yes', 'true', '1']
            elif 'catégorie' in col_lower or 'categorie' in col_lower:
                fcp_data['categorie_fond'] = str(val).lower()
            elif 'type' in col_lower and 'fond' in col_lower:
                fcp_data['type_fond'] = str(val).lower()
            elif 'horizon' in col_lower:
                try:
                    fcp_data['horizon_investissement'] = int(val)
                except:
                    pass
            elif 'frais' in col_lower and 'gestion' in col_lower:
                try:
                    fcp_data['frais_gestion_ttc'] = float(val)
                except:
                    pass
            elif 'date' in col_lower and 'création' in col_lower:
                if hasattr(val, 'strftime'):
                    fcp_data['date_creation'] = val.strftime('%Y-%m-%d')
        
        if nom_fcp in fcps_existants:
            existants.append(fcp_data)
        else:
            nouveaux.append(fcp_data)
    
    return JsonResponse({
        'success': True,
        'type': 'fcp',
        'total': len(nouveaux) + len(existants),
        'nouveaux': nouveaux[:100],  # Limiter pour l'affichage
        'existants': existants[:100],
        'count_nouveaux': len(nouveaux),
        'count_existants': len(existants),
        'colonnes': colonnes,
    })


def analyser_vl_excel(df):
    """Analyser un fichier Excel de valeurs liquidatives (format pivot ou liste)."""
    colonnes = list(df.columns)
    
    # Détecter si c'est un format pivot (Date + colonnes FCPs) ou liste
    is_pivot = 'Date' in colonnes and len(colonnes) > 2
    
    if is_pivot:
        return analyser_vl_pivot(df, colonnes)
    else:
        return analyser_vl_liste(df, colonnes)


def analyser_vl_pivot(df, colonnes):
    """Analyser un fichier VL au format pivot (Date en ligne, FCP en colonnes)."""
    fcp_columns = [c for c in colonnes if c != 'Date']
    
    # Récupérer les entrées existantes
    existantes_set = set()
    for vl in ValeurLiquidative.objects.values('date', 'nom_fcp'):
        existantes_set.add((str(vl['date']), vl['nom_fcp']))
    
    nouveaux = []
    existants = []
    
    for _, row in df.iterrows():
        date = row['Date']
        if pd.isna(date):
            continue
        date_str = date.strftime('%Y-%m-%d') if hasattr(date, 'strftime') else str(date)
        
        for fcp_name in fcp_columns:
            vl_value = row[fcp_name]
            if pd.isna(vl_value):
                continue
            
            vl_data = {
                'date': date_str,
                'nom_fcp': fcp_name,
                'valeur_liquidative': float(vl_value),
            }
            
            if (date_str, fcp_name) in existantes_set:
                existants.append(vl_data)
            else:
                nouveaux.append(vl_data)
    
    # Compter les dates uniques
    dates_uniques = df['Date'].dropna().nunique()
    
    return JsonResponse({
        'success': True,
        'type': 'vl',
        'format': 'pivot',
        'total': len(nouveaux) + len(existants),
        'nouveaux': nouveaux[:100],
        'existants': existants[:100],
        'count_nouveaux': len(nouveaux),
        'count_existants': len(existants),
        'fcps': fcp_columns,
        'dates_uniques': dates_uniques,
    })


def analyser_vl_liste(df, colonnes):
    """Analyser un fichier VL au format liste (colonnes: Date, Nom FCP, VL)."""
    # Déterminer les colonnes
    col_date = None
    col_fcp = None
    col_vl = None
    
    for c in colonnes:
        c_lower = c.lower()
        if 'date' in c_lower:
            col_date = c
        elif 'fcp' in c_lower or 'fond' in c_lower:
            col_fcp = c
        elif 'valeur' in c_lower or 'liquidative' in c_lower or 'vl' in c_lower:
            col_vl = c
    
    if not all([col_date, col_fcp, col_vl]):
        return JsonResponse({
            'success': False,
            'message': 'Colonnes requises non trouvées (Date, Nom FCP, Valeur Liquidative)'
        })
    
    # Récupérer les entrées existantes
    existantes_set = set()
    for vl in ValeurLiquidative.objects.values('date', 'nom_fcp'):
        existantes_set.add((str(vl['date']), vl['nom_fcp']))
    
    nouveaux = []
    existants = []
    
    for _, row in df.iterrows():
        date = row[col_date]
        nom_fcp = row[col_fcp]
        vl_value = row[col_vl]
        
        if pd.isna(date) or pd.isna(nom_fcp) or pd.isna(vl_value):
            continue
        
        date_str = date.strftime('%Y-%m-%d') if hasattr(date, 'strftime') else str(date)
        
        vl_data = {
            'date': date_str,
            'nom_fcp': str(nom_fcp).strip(),
            'valeur_liquidative': float(vl_value),
        }
        
        if (date_str, vl_data['nom_fcp']) in existantes_set:
            existants.append(vl_data)
        else:
            nouveaux.append(vl_data)
    
    return JsonResponse({
        'success': True,
        'type': 'vl',
        'format': 'liste',
        'total': len(nouveaux) + len(existants),
        'nouveaux': nouveaux[:100],
        'existants': existants[:100],
        'count_nouveaux': len(nouveaux),
        'count_existants': len(existants),
    })


@require_POST
def executer_import_excel(request):
    """
    Exécuter l'import des données Excel après validation de l'utilisateur.
    Mode: 'nouveaux_seulement' ou 'tout_ecraser'
    """
    if not HAS_PANDAS:
        return JsonResponse({
            'success': False, 
            'message': 'pandas et openpyxl sont requis pour lire les fichiers Excel'
        })
    
    if 'fichier' not in request.FILES:
        return JsonResponse({'success': False, 'message': 'Aucun fichier fourni'})
    
    fichier = request.FILES['fichier']
    type_import = request.POST.get('type', 'vl')
    mode = request.POST.get('mode', 'nouveaux_seulement')  # 'nouveaux_seulement' ou 'tout_ecraser'
    
    try:
        df = read_excel_file(fichier)
        
        if type_import == 'fcp':
            return executer_import_fcp_excel(df, mode)
        else:
            return executer_import_vl_excel(df, mode)
            
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Erreur lors de l\'import: {str(e)}'})


def executer_import_fcp_excel(df, mode):
    """Exécuter l'import des métadonnées FCP depuis Excel."""
    colonnes = list(df.columns)
    
    # Trouver la colonne nom
    col_nom = None
    for c in colonnes:
        if 'fcp' in c.lower() or 'fond' in c.lower():
            col_nom = c
            break
    
    if not col_nom:
        return JsonResponse({'success': False, 'message': 'Colonne nom FCP non trouvée'})
    
    # Mapping des colonnes
    col_mapping = {}
    for c in colonnes:
        c_lower = c.lower()
        if 'islamique' in c_lower:
            col_mapping['est_fcp_islamique'] = c
        elif 'catégorie' in c_lower or 'categorie' in c_lower:
            col_mapping['categorie_fond'] = c
        elif 'type' in c_lower and 'fond' in c_lower:
            col_mapping['type_fond'] = c
        elif 'horizon' in c_lower:
            col_mapping['horizon_investissement'] = c
        elif 'benchmark' in c_lower and 'obligataire' in c_lower:
            col_mapping['benchmark_obligataire'] = c
        elif 'benchmark' in c_lower and 'brvmc' in c_lower:
            col_mapping['benchmark_brvmc'] = c
        elif 'date' in c_lower and 'création' in c_lower:
            col_mapping['date_creation'] = c
        elif 'dépositaire' in c_lower or 'depositaire' in c_lower:
            col_mapping['depositaire'] = c
        elif 'frais' in c_lower and 'gestion' in c_lower:
            col_mapping['frais_gestion_ttc'] = c
        elif 'frais' in c_lower and 'entrée' in c_lower:
            col_mapping['frais_entree_ttc'] = c
        elif 'frais' in c_lower and 'sortie' in c_lower:
            col_mapping['frais_sortie_ttc'] = c
    
    fcps_existants = set(ValeurLiquidative.objects.values_list('nom_fcp', flat=True).distinct())
    
    importes = 0
    modifies = 0
    ignores = 0
    
    for _, row in df.iterrows():
        nom_fcp = str(row[col_nom]).strip() if pd.notna(row[col_nom]) else None
        if not nom_fcp or nom_fcp == 'nan':
            continue
        
        est_nouveau = nom_fcp not in fcps_existants
        
        # Si mode nouveaux seulement et FCP existe déjà, ignorer
        if mode == 'nouveaux_seulement' and not est_nouveau:
            ignores += 1
            continue
        
        # Préparer les données
        defaults = {}
        
        if 'est_fcp_islamique' in col_mapping:
            val = row[col_mapping['est_fcp_islamique']]
            defaults['est_fcp_islamique'] = str(val).lower() in ['oui', 'yes', 'true', '1'] if pd.notna(val) else False
        
        if 'categorie_fond' in col_mapping:
            val = row[col_mapping['categorie_fond']]
            defaults['categorie_fond'] = str(val).lower() if pd.notna(val) else None
        
        if 'type_fond' in col_mapping:
            val = row[col_mapping['type_fond']]
            defaults['type_fond'] = str(val).lower() if pd.notna(val) else None
        
        if 'horizon_investissement' in col_mapping:
            val = row[col_mapping['horizon_investissement']]
            try:
                defaults['horizon_investissement'] = int(val) if pd.notna(val) else None
            except:
                defaults['horizon_investissement'] = None
        
        if 'benchmark_obligataire' in col_mapping:
            val = row[col_mapping['benchmark_obligataire']]
            defaults['benchmark_obligataire'] = str(val) if pd.notna(val) else None
        
        if 'benchmark_brvmc' in col_mapping:
            val = row[col_mapping['benchmark_brvmc']]
            defaults['benchmark_brvmc'] = str(val) if pd.notna(val) else None
        
        if 'date_creation' in col_mapping:
            val = row[col_mapping['date_creation']]
            defaults['date_creation'] = val.date() if hasattr(val, 'date') else None
        
        if 'depositaire' in col_mapping:
            val = row[col_mapping['depositaire']]
            defaults['depositaire'] = str(val) if pd.notna(val) else None
        
        if 'frais_gestion_ttc' in col_mapping:
            val = row[col_mapping['frais_gestion_ttc']]
            try:
                defaults['frais_gestion_ttc'] = Decimal(str(val)) if pd.notna(val) else None
            except:
                defaults['frais_gestion_ttc'] = None
        
        if 'frais_entree_ttc' in col_mapping:
            val = row[col_mapping['frais_entree_ttc']]
            try:
                defaults['frais_entree_ttc'] = Decimal(str(val)) if pd.notna(val) else None
            except:
                defaults['frais_entree_ttc'] = None
        
        if 'frais_sortie_ttc' in col_mapping:
            val = row[col_mapping['frais_sortie_ttc']]
            try:
                defaults['frais_sortie_ttc'] = Decimal(str(val)) if pd.notna(val) else None
            except:
                defaults['frais_sortie_ttc'] = None
        
        # Mettre à jour ou créer
        if est_nouveau:
            ValeurLiquidative.objects.create(nom_fcp=nom_fcp, **defaults)
            importes += 1
        else:
            ValeurLiquidative.objects.filter(nom_fcp=nom_fcp).update(**defaults)
            modifies += 1
    
    # Invalider le cache des métadonnées FCP
    cache.delete("metadonnees_fcps_v1")

    return JsonResponse({
        'success': True,
        'message': f'{importes} FCP importés, {modifies} mis à jour, {ignores} ignorés.',
        'importes': importes,
        'modifies': modifies,
        'ignores': ignores,
    })


def executer_import_vl_excel(df, mode):
    """Exécuter l'import des VL depuis Excel (version optimisée bulk)."""
    colonnes = list(df.columns)

    # Détecter le format
    is_pivot = 'Date' in colonnes and len(colonnes) > 2

    # Récupérer les métadonnées existantes (une ligne par FCP) pour enrichissement
    fcp_metadata = {}
    for vl in ValeurLiquidative.objects.values(
        'nom_fcp', 'est_fcp_islamique', 'categorie_fond',
        'type_fond', 'horizon_investissement', 'frais_gestion_ttc',
        'frais_entree_ttc', 'frais_sortie_ttc',
        'date_creation', 'depositaire', 'benchmark_obligataire',
        'benchmark_brvmc'
    ).distinct():
        if vl['nom_fcp']:
            fcp_metadata[vl['nom_fcp']] = vl

    # Charger les entrées existantes en mémoire: {(date, nom_fcp): ValeurLiquidative}
    existantes = {}
    for vl in ValeurLiquidative.objects.all().only(
        'id', 'date', 'nom_fcp', 'valeur_liquidative',
        'est_fcp_islamique', 'categorie_fond', 'type_fond',
        'horizon_investissement', 'frais_gestion_ttc', 'frais_entree_ttc',
        'frais_sortie_ttc', 'date_creation', 'depositaire',
        'benchmark_obligataire', 'benchmark_brvmc'
    ):
        existantes[(vl.date, vl.nom_fcp)] = vl

    # Construire la liste (date, nom_fcp, valeur) depuis le DataFrame
    rows_iter = []
    if is_pivot:
        fcp_columns = [c for c in colonnes if c != 'Date']
        for _, row in df.iterrows():
            d = row['Date']
            if pd.isna(d):
                continue
            date_val = d.date() if hasattr(d, 'date') else d
            for fcp_name in fcp_columns:
                val = row[fcp_name]
                if pd.isna(val):
                    continue
                rows_iter.append((date_val, fcp_name, val))
    else:
        col_date = col_fcp = col_vl = None
        for c in colonnes:
            c_lower = c.lower()
            if 'date' in c_lower:
                col_date = c
            elif 'fcp' in c_lower or 'fond' in c_lower:
                col_fcp = c
            elif 'valeur' in c_lower or 'liquidative' in c_lower or 'vl' in c_lower:
                col_vl = c
        if not all([col_date, col_fcp, col_vl]):
            return JsonResponse({'success': False, 'message': 'Colonnes requises non trouvées'})
        for _, row in df.iterrows():
            d = row[col_date]
            nom = row[col_fcp]
            val = row[col_vl]
            if pd.isna(d) or pd.isna(nom) or pd.isna(val):
                continue
            date_val = d.date() if hasattr(d, 'date') else d
            rows_iter.append((date_val, str(nom).strip(), val))

    to_create = []
    to_update = []
    ignores = 0
    seen_keys = set()

    for date_val, nom_fcp, vl_value in rows_iter:
        key = (date_val, nom_fcp)
        if key in seen_keys:
            continue
        seen_keys.add(key)

        meta = fcp_metadata.get(nom_fcp, {})
        new_value = Decimal(str(vl_value))
        existing = existantes.get(key)

        if existing is not None:
            if mode == 'nouveaux_seulement':
                ignores += 1
                continue
            # Mettre à jour la valeur si elle a changé
            if existing.valeur_liquidative != new_value:
                existing.valeur_liquidative = new_value
                to_update.append(existing)
        else:
            to_create.append(ValeurLiquidative(
                date=date_val,
                nom_fcp=nom_fcp,
                valeur_liquidative=new_value,
                est_fcp_islamique=meta.get('est_fcp_islamique', False),
                categorie_fond=meta.get('categorie_fond'),
                type_fond=meta.get('type_fond'),
                horizon_investissement=meta.get('horizon_investissement'),
                frais_gestion_ttc=meta.get('frais_gestion_ttc'),
                frais_entree_ttc=meta.get('frais_entree_ttc'),
                frais_sortie_ttc=meta.get('frais_sortie_ttc'),
                date_creation=meta.get('date_creation'),
                depositaire=meta.get('depositaire'),
                benchmark_obligataire=meta.get('benchmark_obligataire'),
                benchmark_brvmc=meta.get('benchmark_brvmc'),
            ))

    with transaction.atomic():
        if to_create:
            ValeurLiquidative.objects.bulk_create(to_create, batch_size=1000)
        if to_update:
            ValeurLiquidative.objects.bulk_update(
                to_update, ['valeur_liquidative'], batch_size=1000
            )

    importes = len(to_create)
    modifies = len(to_update)

    # Compléter les jours manquants après l'import (version bulk)
    fill_count = fill_missing_dates()

    # Invalider le cache des métadonnées FCP
    cache.delete("metadonnees_fcps_v1")

    return JsonResponse({
        'success': True,
        'message': f'{importes} VL importées, {modifies} mises à jour, {ignores} ignorées. {fill_count} jours manquants complétés.',
        'importes': importes,
        'modifies': modifies,
        'ignores': ignores,
        'jours_completes': fill_count,
    })


def fill_missing_dates():
    """
    Complète les jours manquants dans les valeurs liquidatives (version bulk).
    Pour chaque jour manquant, on utilise la dernière valeur connue avant cette date.
    Retourne le nombre de jours complétés.
    """
    # Charger toutes les VL en une seule requête
    all_vl = list(ValeurLiquidative.objects.all().values(
        'date', 'nom_fcp', 'valeur_liquidative', 'est_fcp_islamique',
        'categorie_fond', 'type_fond', 'horizon_investissement',
        'benchmark_obligataire', 'benchmark_brvmc', 'date_creation',
        'depositaire', 'frais_gestion_ttc', 'frais_entree_ttc', 'frais_sortie_ttc'
    ).order_by('nom_fcp', 'date'))

    # Grouper par FCP
    by_fcp = defaultdict(list)
    for vl in all_vl:
        if vl['nom_fcp']:
            by_fcp[vl['nom_fcp']].append(vl)

    to_create = []

    for fcp_name, vl_list in by_fcp.items():
        if len(vl_list) < 2:
            continue

        existing_dates = {vl['date'] for vl in vl_list}
        min_date = vl_list[0]['date']
        max_date = vl_list[-1]['date']

        # Construire un index date -> vl pour accès rapide
        date_to_vl = {vl['date']: vl for vl in vl_list}

        current_date = min_date
        last_known_vl = None

        while current_date <= max_date:
            if current_date in existing_dates:
                last_known_vl = date_to_vl[current_date]
            elif last_known_vl is not None:
                to_create.append(ValeurLiquidative(
                    date=current_date,
                    nom_fcp=fcp_name,
                    valeur_liquidative=last_known_vl['valeur_liquidative'],
                    est_fcp_islamique=last_known_vl['est_fcp_islamique'],
                    categorie_fond=last_known_vl['categorie_fond'],
                    type_fond=last_known_vl['type_fond'],
                    horizon_investissement=last_known_vl['horizon_investissement'],
                    benchmark_obligataire=last_known_vl['benchmark_obligataire'],
                    benchmark_brvmc=last_known_vl['benchmark_brvmc'],
                    date_creation=last_known_vl['date_creation'],
                    depositaire=last_known_vl['depositaire'],
                    frais_gestion_ttc=last_known_vl['frais_gestion_ttc'],
                    frais_entree_ttc=last_known_vl['frais_entree_ttc'],
                    frais_sortie_ttc=last_known_vl['frais_sortie_ttc'],
                ))
            current_date += timedelta(days=1)

    if to_create:
        with transaction.atomic():
            ValeurLiquidative.objects.bulk_create(to_create, batch_size=1000)

    return len(to_create)


# ========== SICAV (PEE/PER) FUNCTIONS ==========

def exporter_sicav(request):
    """Exporter les transactions SICAV (PEE/PER) en CSV"""
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="transactions_sicav.csv"'
    response.write('\ufeff')  # BOM pour Excel
    
    writer = csv.writer(response, delimiter=';')
    
    # En-têtes
    writer.writerow([
        'Date Transaction', 'Numéro Compte', 'Type Plan', 'Nom PER/PEE', 'Matricule Type',
        'Nom & Prénom', 'Email', 'Sens', 'Nom FCP', 'Quantité', 'Coût Moyen Pondéré'
    ])
    
    # Données
    transactions = Sicav.objects.all().order_by('-date_transaction')

    # Charger le cache VL pour calculer le CMP à partir des FCP
    charger_cache_vl()

    for t in transactions:
        cmp = cmp_from_fcp(t)
        writer.writerow([
            t.date_transaction.strftime('%d/%m/%Y') if t.date_transaction else '',
            t.numero_compte or '',
            t.type_plan or '',
            t.nom_per_pee or '',
            t.matricule_type or '',
            t.nom_prenom or '',
            t.email or '',
            t.sens or '',
            t.nom_fcp or '',
            str(t.quantite).replace('.', ',') if t.quantite else '',
            (f"{cmp:.4f}".replace('.', ',')) if cmp else '',
        ])
    
    return response


@require_POST
def analyser_sicav_excel(request):
    """Analyser un fichier Excel de transactions SICAV (PEE/PER)."""
    if not HAS_PANDAS:
        return JsonResponse({
            'success': False, 
            'message': 'pandas et openpyxl sont requis pour lire les fichiers Excel'
        })
    
    if 'fichier' not in request.FILES:
        return JsonResponse({'success': False, 'message': 'Aucun fichier fourni'})
    
    fichier = request.FILES['fichier']
    
    if not fichier.name.endswith(('.xlsx', '.xls')):
        return JsonResponse({'success': False, 'message': 'Le fichier doit être au format Excel (.xlsx ou .xls)'})
    
    try:
        df = read_excel_file(fichier)
        colonnes = list(df.columns)
        
        # Récupérer la liste des FCP existants dans la base
        fcps_existants = set(ValeurLiquidative.objects.exclude(
            nom_fcp__isnull=True
        ).exclude(nom_fcp='').values_list('nom_fcp', flat=True).distinct())
        
        # Mapping des colonnes possibles
        col_mapping = {}
        for c in colonnes:
            c_lower = c.lower()
            if 'date' in c_lower:
                col_mapping['date_transaction'] = c
            elif 'compte' in c_lower or 'numéro' in c_lower or 'numero' in c_lower:
                col_mapping['numero_compte'] = c
            elif 'type' in c_lower and ('plan' in c_lower or 'pee' in c_lower or 'per' in c_lower):
                col_mapping['type_plan'] = c
            elif 'matricule' in c_lower:
                col_mapping['matricule_type'] = c
            # Détecter nom_per_pee AVANT nom_prenom ("Nom du PER/PEE", "Nom PER/PEE")
            elif 'nom' in c_lower and ('per' in c_lower or 'pee' in c_lower) and 'prénom' not in c_lower:
                col_mapping['nom_per_pee'] = c
            elif 'nom' in c_lower and 'prénom' in c_lower:
                col_mapping['nom_prenom'] = c
            elif ('nom' in c_lower and 'fcp' not in c_lower and 'per' not in c_lower and 'pee' not in c_lower) or ('prénom' in c_lower):
                col_mapping['nom_prenom'] = c
            elif 'email' in c_lower or 'mail' in c_lower:
                col_mapping['email'] = c
            elif 'sens' in c_lower:
                col_mapping['sens'] = c
            elif 'fcp' in c_lower or ('nom' in c_lower and 'fond' in c_lower):
                col_mapping['nom_fcp'] = c
            elif 'quantité' in c_lower or 'quantite' in c_lower or 'qte' in c_lower:
                col_mapping['quantite'] = c
            elif 'coût' in c_lower or 'cout' in c_lower or 'cmp' in c_lower or 'moyen' in c_lower:
                col_mapping['cout_moyen_pondere'] = c
        
        # Récupérer les entrées existantes (basé sur date + compte + sens + fcp)
        existantes_set = set()
        for s in Sicav.objects.values('date_transaction', 'numero_compte', 'sens', 'nom_fcp'):
            existantes_set.add((
                str(s['date_transaction']) if s['date_transaction'] else '',
                s['numero_compte'] or '',
                s['sens'] or '',
                s['nom_fcp'] or ''
            ))
        
        def parse_date_analyse(date_val):
            """Parse une date depuis différents formats possibles pour l'analyse"""
            if date_val is None:
                return None
            if pd.isna(date_val):
                return None
            
            # Si c'est déjà un objet date/datetime
            if hasattr(date_val, 'strftime'):
                return date_val.strftime('%Y-%m-%d')
            
            # Convertir en string et nettoyer les espaces insécables
            date_str = str(date_val).strip().replace('\xa0', '').replace('\u00a0', '')
            if not date_str:
                return None
            
            # Essayer différents formats
            formats_a_essayer = [
                ('%d/%m/%Y', '%Y-%m-%d'),  # 05/01/2026 -> 2026-01-05
                ('%Y-%m-%d', '%Y-%m-%d'),  # déjà bon format
                ('%d-%m-%Y', '%Y-%m-%d'),  # 05-01-2026
                ('%d.%m.%Y', '%Y-%m-%d'),  # 05.01.2026
                ('%Y/%m/%d', '%Y-%m-%d'),  # 2026/01/05
            ]
            
            for fmt_in, fmt_out in formats_a_essayer:
                try:
                    parsed = datetime.strptime(date_str, fmt_in)
                    return parsed.strftime(fmt_out)
                except ValueError:
                    continue
            
            return date_str  # Retourner tel quel si aucun format ne marche
        
        nouveaux = []
        existants = []
        fcps_inconnus = set()  # FCP qui ne correspondent pas à ceux de la base
        total_souscriptions = 0
        total_rachats = 0

        # Collecteurs pour les validations additionnelles
        lignes_quantite_invalide = []      # quantité absente, nulle ou négative
        lignes_date_invalide = []          # date absente ou illisible
        lignes_date_future = []            # date > aujourd'hui
        sens_invalides = set()             # valeur non reconnue
        types_plan_invalides = set()       # ≠ PEE/PER
        rachats_orphelins = []             # rachat sans souscription préalable (compte, FCP)

        # Stock cumulé (positions existantes en base + positions du fichier) pour
        # détecter les rachats sans parts détenues.
        from collections import defaultdict as _dd
        stock_positions = _dd(float)
        for s in Sicav.objects.values('numero_compte', 'nom_fcp', 'sens', 'quantite'):
            key = (s['numero_compte'] or '', s['nom_fcp'] or '')
            q = float(s['quantite'] or 0)
            if s['sens'] == 'souscription':
                stock_positions[key] += q
            elif s['sens'] == 'rachat':
                stock_positions[key] -= q

        aujourd_hui = date.today()

        for idx, (_, row) in enumerate(df.iterrows(), start=2):  # ligne 1 = en-tête
            # Extraire les données
            date_val = None
            if 'date_transaction' in col_mapping:
                date_val = parse_date_analyse(row[col_mapping['date_transaction']])
            
            numero_compte = ''
            if 'numero_compte' in col_mapping:
                val = row[col_mapping['numero_compte']]
                numero_compte = str(val).strip() if pd.notna(val) else ''
            
            sens = ''
            if 'sens' in col_mapping:
                val = row[col_mapping['sens']]
                sens = str(val).strip().lower() if pd.notna(val) else ''
            
            nom_fcp = ''
            if 'nom_fcp' in col_mapping:
                val = row[col_mapping['nom_fcp']]
                nom_fcp = str(val).strip() if pd.notna(val) else ''
            
            # Vérifier si le FCP existe dans la base
            fcp_existe = nom_fcp in fcps_existants if nom_fcp else True
            if nom_fcp and not fcp_existe:
                fcps_inconnus.add(nom_fcp)
            
            item = {
                'date_transaction': date_val or '',
                'numero_compte': numero_compte,
                'type_plan': '',
                'nom_per_pee': '',
                'matricule_type': '',
                'nom_prenom': '',
                'email': '',
                'sens': sens,
                'nom_fcp': nom_fcp,
                'quantite': None,
                'cout_moyen_pondere': None,
                'fcp_existe': fcp_existe,  # Indicateur pour l'UI
            }
            
            if 'type_plan' in col_mapping:
                val = row[col_mapping['type_plan']]
                item['type_plan'] = str(val).strip().upper() if pd.notna(val) else ''
            
            if 'nom_per_pee' in col_mapping:
                val = row[col_mapping['nom_per_pee']]
                item['nom_per_pee'] = str(val).strip() if pd.notna(val) else ''
            
            if 'matricule_type' in col_mapping:
                val = row[col_mapping['matricule_type']]
                item['matricule_type'] = str(val).strip() if pd.notna(val) else ''
            
            if 'nom_prenom' in col_mapping:
                val = row[col_mapping['nom_prenom']]
                item['nom_prenom'] = str(val).strip() if pd.notna(val) else ''
            
            if 'email' in col_mapping:
                val = row[col_mapping['email']]
                item['email'] = str(val).strip() if pd.notna(val) else ''
            
            if 'quantite' in col_mapping:
                val = row[col_mapping['quantite']]
                try:
                    item['quantite'] = float(val) if pd.notna(val) else None
                except:
                    item['quantite'] = None
            
            if 'cout_moyen_pondere' in col_mapping:
                val = row[col_mapping['cout_moyen_pondere']]
                try:
                    item['cout_moyen_pondere'] = float(val) if pd.notna(val) else None
                except:
                    item['cout_moyen_pondere'] = None
            
            # CMP calculé à partir des FCP (VL à la date de transaction)
            cmp_fcp = None
            if nom_fcp and date_val:
                try:
                    date_obj = datetime.strptime(date_val, '%Y-%m-%d').date() if isinstance(date_val, str) else date_val
                    vl = get_vl_at_date(nom_fcp, date_obj, use_cache=False)
                    cmp_fcp = float(vl) if vl else None
                except Exception:
                    cmp_fcp = None
            item['cmp_fcp'] = cmp_fcp

            # Comptabiliser souscriptions et rachats en utilisant le CMP issu des FCP en priorité
            cmp_calc = cmp_fcp if cmp_fcp is not None else (item['cout_moyen_pondere'] or 0)
            montant = (item['quantite'] or 0) * cmp_calc
            if sens == 'souscription':
                total_souscriptions += montant
            elif sens == 'rachat':
                total_rachats += montant

            # --- Validations ligne par ligne ---
            # Date
            if not date_val:
                lignes_date_invalide.append(idx)
            else:
                try:
                    d_obj = datetime.strptime(date_val, '%Y-%m-%d').date() if isinstance(date_val, str) else date_val
                    if d_obj and d_obj > aujourd_hui:
                        lignes_date_future.append(idx)
                except Exception:
                    pass

            # Quantité strictement positive
            if item['quantite'] is None or item['quantite'] <= 0:
                lignes_quantite_invalide.append(idx)

            # Sens
            if sens and sens not in ('souscription', 'rachat'):
                sens_invalides.add(sens)

            # Type plan
            tp = (item.get('type_plan') or '').upper()
            if tp and tp not in ('PEE', 'PER'):
                types_plan_invalides.add(tp)

            # Mise à jour stock et détection rachats orphelins
            key_pos = (numero_compte, nom_fcp)
            q = item['quantite'] or 0
            if sens == 'souscription':
                stock_positions[key_pos] += q
            elif sens == 'rachat':
                if stock_positions[key_pos] + 1e-6 < q:
                    rachats_orphelins.append({
                        'ligne': idx,
                        'compte': numero_compte,
                        'fcp': nom_fcp,
                        'quantite_demandee': q,
                        'stock_disponible': round(stock_positions[key_pos], 4),
                    })
                stock_positions[key_pos] -= q
            
            # Vérifier si l'entrée existe déjà
            key = (date_val or '', numero_compte, sens, nom_fcp)
            if key in existantes_set:
                existants.append(item)
            else:
                nouveaux.append(item)
        
        # Préparer les avertissements
        avertissements = []

        # Colonnes obligatoires manquantes
        colonnes_requises = {
            'date_transaction': 'Date Transaction',
            'numero_compte': 'Numéro Compte',
            'type_plan': 'Type Plan',
            'sens': 'Sens',
            'nom_fcp': 'Nom FCP',
            'quantite': 'Quantité',
        }
        manquantes = [lib for code, lib in colonnes_requises.items() if code not in col_mapping]
        if manquantes:
            avertissements.append({
                'type': 'colonnes_manquantes',
                'message': f"{len(manquantes)} colonne(s) obligatoire(s) non détectée(s)",
                'details': manquantes,
                'suggestion': "Vérifiez les intitulés d'en-tête. Téléchargez le modèle Excel pour voir les noms attendus."
            })

        # Avertissement FCP inconnus
        if fcps_inconnus:
            avertissements.append({
                'type': 'fcp_inconnus',
                'message': f"{len(fcps_inconnus)} FCP non trouvé(s) dans la base de données",
                'details': list(fcps_inconnus),
                'suggestion': "Vérifiez que ces FCP existent dans les métadonnées ou corrigez les noms dans votre fichier."
            })

        # Quantités invalides
        if lignes_quantite_invalide:
            avertissements.append({
                'type': 'quantite_invalide',
                'message': f"{len(lignes_quantite_invalide)} ligne(s) avec quantité absente, nulle ou négative",
                'details': lignes_quantite_invalide[:30],
                'suggestion': "Toute transaction doit avoir une quantité strictement positive. Corrigez ces lignes avant l'import."
            })

        # Dates illisibles
        if lignes_date_invalide:
            avertissements.append({
                'type': 'date_invalide',
                'message': f"{len(lignes_date_invalide)} ligne(s) avec date manquante ou illisible",
                'details': lignes_date_invalide[:30],
                'suggestion': "Formats acceptés : JJ/MM/AAAA, AAAA-MM-JJ, JJ-MM-AAAA, JJ.MM.AAAA."
            })

        # Dates futures
        if lignes_date_future:
            avertissements.append({
                'type': 'date_future',
                'message': f"{len(lignes_date_future)} transaction(s) avec une date future",
                'details': lignes_date_future[:30],
                'suggestion': "Les transactions datées dans le futur sont inhabituelles. Vérifiez qu'il ne s'agit pas d'une erreur de saisie."
            })

        # Sens invalides
        if sens_invalides:
            avertissements.append({
                'type': 'sens_invalide',
                'message': f"Valeur(s) de sens non reconnue(s) : {', '.join(sorted(sens_invalides))}",
                'details': sorted(sens_invalides),
                'suggestion': "Seules les valeurs « souscription » et « rachat » sont reconnues."
            })

        # Types plan invalides
        if types_plan_invalides:
            avertissements.append({
                'type': 'type_plan_invalide',
                'message': f"Type de plan non reconnu : {', '.join(sorted(types_plan_invalides))}",
                'details': sorted(types_plan_invalides),
                'suggestion': "Seules les valeurs « PEE » et « PER » sont acceptées."
            })

        # Rachats sans stock suffisant
        if rachats_orphelins:
            avertissements.append({
                'type': 'rachat_orphelin',
                'message': f"{len(rachats_orphelins)} rachat(s) dépassant le stock disponible",
                'details': rachats_orphelins[:20],
                'suggestion': "Un rachat ne peut pas dépasser le nombre de parts détenues. Vérifiez l'antériorité des souscriptions."
            })

        # Avertissement si rachats > souscriptions
        if total_rachats > total_souscriptions:
            avertissements.append({
                'type': 'desequilibre_flux',
                'message': "Le total des rachats dépasse le total des souscriptions",
                'details': {
                    'souscriptions': round(total_souscriptions, 2),
                    'rachats': round(total_rachats, 2),
                    'difference': round(total_rachats - total_souscriptions, 2)
                },
                'suggestion': "Vérifiez que les données sont correctes. Les rachats ne devraient généralement pas excéder les souscriptions."
            })
        
        return JsonResponse({
            'success': True,
            'type': 'sicav',
            'total': len(nouveaux) + len(existants),
            'nouveaux': nouveaux[:100],
            'existants': existants[:100],
            'count_nouveaux': len(nouveaux),
            'count_existants': len(existants),
            'colonnes': colonnes,
            'col_mapping': col_mapping,
            'avertissements': avertissements,
            'fcps_existants': list(fcps_existants)[:20],  # Liste des FCP valides pour référence
            'stats': {
                'total_souscriptions': round(total_souscriptions, 2),
                'total_rachats': round(total_rachats, 2),
                'solde_net': round(total_souscriptions - total_rachats, 2)
            }
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Erreur lors de la lecture du fichier: {str(e)}'})


@require_POST
def executer_import_sicav_excel(request):
    """Exécuter l'import des transactions SICAV depuis Excel."""
    if not HAS_PANDAS:
        return JsonResponse({
            'success': False, 
            'message': 'pandas et openpyxl sont requis pour lire les fichiers Excel'
        })
    
    if 'fichier' not in request.FILES:
        return JsonResponse({'success': False, 'message': 'Aucun fichier fourni'})
    
    fichier = request.FILES['fichier']
    mode = request.POST.get('mode', 'nouveaux_seulement')
    
    try:
        df = read_excel_file(fichier)
        colonnes = list(df.columns)
        
        # Mapping des colonnes
        col_mapping = {}
        for c in colonnes:
            c_lower = c.lower()
            if 'date' in c_lower:
                col_mapping['date_transaction'] = c
            elif 'compte' in c_lower or 'numéro' in c_lower or 'numero' in c_lower:
                col_mapping['numero_compte'] = c
            elif 'type' in c_lower and ('plan' in c_lower or 'pee' in c_lower or 'per' in c_lower):
                col_mapping['type_plan'] = c
            elif 'matricule' in c_lower:
                col_mapping['matricule_type'] = c
            # Détecter nom_per_pee AVANT nom_prenom ("Nom du PER/PEE", "Nom PER/PEE")
            elif 'nom' in c_lower and ('per' in c_lower or 'pee' in c_lower) and 'prénom' not in c_lower:
                col_mapping['nom_per_pee'] = c
            elif 'nom' in c_lower and 'prénom' in c_lower:
                col_mapping['nom_prenom'] = c
            elif ('nom' in c_lower and 'fcp' not in c_lower and 'per' not in c_lower and 'pee' not in c_lower) or ('prénom' in c_lower):
                col_mapping['nom_prenom'] = c
            elif 'email' in c_lower or 'mail' in c_lower:
                col_mapping['email'] = c
            elif 'sens' in c_lower:
                col_mapping['sens'] = c
            elif 'fcp' in c_lower or ('nom' in c_lower and 'fond' in c_lower):
                col_mapping['nom_fcp'] = c
            elif 'quantité' in c_lower or 'quantite' in c_lower or 'qte' in c_lower:
                col_mapping['quantite'] = c
            elif 'coût' in c_lower or 'cout' in c_lower or 'cmp' in c_lower or 'moyen' in c_lower:
                col_mapping['cout_moyen_pondere'] = c
        
        # Récupérer les entrées existantes
        existantes_set = set()
        for s in Sicav.objects.values('date_transaction', 'numero_compte', 'sens', 'nom_fcp'):
            existantes_set.add((
                str(s['date_transaction']) if s['date_transaction'] else '',
                s['numero_compte'] or '',
                s['sens'] or '',
                s['nom_fcp'] or ''
            ))
        
        importes = 0
        modifies = 0
        ignores = 0
        
        def parse_date(date_val):
            """Parse une date depuis différents formats possibles"""
            if date_val is None or (isinstance(date_val, str) and not date_val.strip()):
                return None
            
            # Si c'est déjà un objet date/datetime
            if hasattr(date_val, 'date'):
                return date_val.date()
            if isinstance(date_val, date):
                return date_val
            
            # Convertir en string et nettoyer les espaces insécables
            date_str = str(date_val).strip().replace('\xa0', '').replace('\u00a0', '')
            
            # Essayer différents formats
            formats_a_essayer = [
                '%d/%m/%Y',  # 05/01/2026
                '%Y-%m-%d',  # 2026-01-05
                '%d-%m-%Y',  # 05-01-2026
                '%d.%m.%Y',  # 05.01.2026
                '%Y/%m/%d',  # 2026/01/05
            ]
            
            for fmt in formats_a_essayer:
                try:
                    return datetime.strptime(date_str, fmt).date()
                except ValueError:
                    continue
            
            return None
        
        for _, row in df.iterrows():
            # Extraire les données
            date_val = None
            if 'date_transaction' in col_mapping:
                date_val = parse_date(row[col_mapping['date_transaction']])
            
            numero_compte = ''
            if 'numero_compte' in col_mapping:
                val = row[col_mapping['numero_compte']]
                numero_compte = str(val).strip() if pd.notna(val) else ''
            
            sens = ''
            if 'sens' in col_mapping:
                val = row[col_mapping['sens']]
                sens = str(val).strip().lower() if pd.notna(val) else ''
            
            nom_fcp = ''
            if 'nom_fcp' in col_mapping:
                val = row[col_mapping['nom_fcp']]
                nom_fcp = str(val).strip() if pd.notna(val) else ''
            
            # Données complémentaires
            defaults = {}
            
            if 'type_plan' in col_mapping:
                val = row[col_mapping['type_plan']]
                defaults['type_plan'] = str(val).strip().upper() if pd.notna(val) else None
            
            if 'nom_per_pee' in col_mapping:
                val = row[col_mapping['nom_per_pee']]
                defaults['nom_per_pee'] = str(val).strip() if pd.notna(val) else None
            
            if 'matricule_type' in col_mapping:
                val = row[col_mapping['matricule_type']]
                defaults['matricule_type'] = str(val).strip() if pd.notna(val) else None
            
            if 'nom_prenom' in col_mapping:
                val = row[col_mapping['nom_prenom']]
                defaults['nom_prenom'] = str(val).strip() if pd.notna(val) else None
            
            if 'email' in col_mapping:
                val = row[col_mapping['email']]
                defaults['email'] = str(val).strip() if pd.notna(val) else None
            
            if 'quantite' in col_mapping:
                val = row[col_mapping['quantite']]
                try:
                    defaults['quantite'] = Decimal(str(val)) if pd.notna(val) else None
                except:
                    defaults['quantite'] = None
            
            if 'cout_moyen_pondere' in col_mapping:
                val = row[col_mapping['cout_moyen_pondere']]
                try:
                    defaults['cout_moyen_pondere'] = Decimal(str(val)) if pd.notna(val) else None
                except:
                    defaults['cout_moyen_pondere'] = None
            
            # Vérifier si l'entrée existe déjà
            key = (str(date_val) if date_val else '', numero_compte, sens, nom_fcp)
            est_nouveau = key not in existantes_set
            
            if mode == 'nouveaux_seulement' and not est_nouveau:
                ignores += 1
                continue
            
            if est_nouveau:
                Sicav.objects.create(
                    date_transaction=date_val,
                    numero_compte=numero_compte,
                    sens=sens,
                    nom_fcp=nom_fcp,
                    **defaults
                )
                importes += 1
            else:
                Sicav.objects.filter(
                    date_transaction=date_val,
                    numero_compte=numero_compte,
                    sens=sens,
                    nom_fcp=nom_fcp
                ).update(**defaults)
                modifies += 1
        
        return JsonResponse({
            'success': True,
            'message': f'{importes} transactions importées, {modifies} mises à jour, {ignores} ignorées.',
            'importes': importes,
            'modifies': modifies,
            'ignores': ignores,
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Erreur lors de l\'import: {str(e)}'})


def telecharger_modele_sicav(request):
    """Télécharger un modèle Excel pour l'import des transactions PEE/PER."""
    if not HAS_PANDAS:
        return HttpResponse("pandas et openpyxl sont requis pour générer le fichier Excel", status=500)
    
    # Récupérer les FCP existants dans la base
    fcps_existants = list(ValeurLiquidative.objects.exclude(
        nom_fcp__isnull=True
    ).exclude(nom_fcp='').values_list('nom_fcp', flat=True).distinct().order_by('nom_fcp')[:5])
    
    # Si aucun FCP n'existe, utiliser des exemples
    if not fcps_existants:
        fcps_existants = ['FCP EQUILIBRE', 'FCP DYNAMIQUE', 'FCP PRUDENT', 'FCP CROISSANCE', 'FCP SECURITE']
    
    # Compléter à 5 FCP si nécessaire
    while len(fcps_existants) < 5:
        fcps_existants.append(f'FCP EXEMPLE {len(fcps_existants) + 1}')
    
    # Créer des dates au format datetime pour Excel
    from datetime import date as date_type
    dates_transactions = [
        # Client 1 - Souscriptions PEE
        date_type(2026, 1, 5), date_type(2026, 1, 15), date_type(2026, 2, 1), date_type(2026, 2, 15),
        # Client 1 - Souscription PER
        date_type(2026, 1, 10), date_type(2026, 2, 20),
        # Client 2 - Souscriptions PEE
        date_type(2026, 1, 8), date_type(2026, 1, 22), date_type(2026, 2, 5),
        # Client 2 - Petit rachat PEE
        date_type(2026, 2, 28),
        # Client 3 - Souscriptions PER
        date_type(2026, 1, 12), date_type(2026, 1, 25), date_type(2026, 2, 10), date_type(2026, 2, 25),
        # Client 3 - Petit rachat PER
        date_type(2026, 3, 1),
        # Client 4 - Souscriptions mixtes
        date_type(2026, 1, 3), date_type(2026, 1, 18), date_type(2026, 2, 3),
        # Client 5 - Souscriptions PEE
        date_type(2026, 1, 7), date_type(2026, 1, 21),
    ]
    
    # Créer un DataFrame avec plus de données exemples
    # Plus de souscriptions que de rachats pour avoir des données cohérentes
    data = {
        'Date Transaction': dates_transactions,
        'Numéro Compte': [
            'CPT001', 'CPT001', 'CPT001', 'CPT001',
            'CPT001', 'CPT001',
            'CPT002', 'CPT002', 'CPT002',
            'CPT002',
            'CPT003', 'CPT003', 'CPT003', 'CPT003',
            'CPT003',
            'CPT004', 'CPT004', 'CPT004',
            'CPT005', 'CPT005',
        ],
        'Type Plan': [
            'PEE', 'PEE', 'PEE', 'PEE',
            'PER', 'PER',
            'PEE', 'PEE', 'PEE',
            'PEE',
            'PER', 'PER', 'PER', 'PER',
            'PER',
            'PEE', 'PER', 'PEE',
            'PEE', 'PEE',
        ],
        'Nom PER/PEE': [
            'PEE CGF EPARGNE', 'PEE CGF EPARGNE', 'PEE CGF EPARGNE', 'PEE CGF EPARGNE',
            'PER CGF RETRAITE', 'PER CGF RETRAITE',
            'PEE CGF PERFORMANCE', 'PEE CGF PERFORMANCE', 'PEE CGF PERFORMANCE',
            'PEE CGF PERFORMANCE',
            'PER CGF HORIZON', 'PER CGF HORIZON', 'PER CGF HORIZON', 'PER CGF HORIZON',
            'PER CGF HORIZON',
            'PEE CGF EPARGNE', 'PER CGF RETRAITE', 'PEE CGF EPARGNE',
            'PEE CGF CROISSANCE', 'PEE CGF CROISSANCE',
        ],
        'Matricule Type': [
            'MAT001', 'MAT001', 'MAT001', 'MAT001',
            'MAT001', 'MAT001',
            'MAT002', 'MAT002', 'MAT002',
            'MAT002',
            'MAT003', 'MAT003', 'MAT003', 'MAT003',
            'MAT003',
            'MAT004', 'MAT004', 'MAT004',
            'MAT005', 'MAT005',
        ],
        'Nom & Prénom': [
            'KOUASSI Ama', 'KOUASSI Ama', 'KOUASSI Ama', 'KOUASSI Ama',
            'KOUASSI Ama', 'KOUASSI Ama',
            'DIALLO Mamadou', 'DIALLO Mamadou', 'DIALLO Mamadou',
            'DIALLO Mamadou',
            'TRAORE Fatou', 'TRAORE Fatou', 'TRAORE Fatou', 'TRAORE Fatou',
            'TRAORE Fatou',
            'KONE Ibrahim', 'KONE Ibrahim', 'KONE Ibrahim',
            'BAMBA Aissatou', 'BAMBA Aissatou',
        ],
        'Email': [
            'ama.kouassi@email.ci', 'ama.kouassi@email.ci', 'ama.kouassi@email.ci', 'ama.kouassi@email.ci',
            'ama.kouassi@email.ci', 'ama.kouassi@email.ci',
            'mamadou.diallo@email.ci', 'mamadou.diallo@email.ci', 'mamadou.diallo@email.ci',
            'mamadou.diallo@email.ci',
            'fatou.traore@email.ci', 'fatou.traore@email.ci', 'fatou.traore@email.ci', 'fatou.traore@email.ci',
            'fatou.traore@email.ci',
            'ibrahim.kone@email.ci', 'ibrahim.kone@email.ci', 'ibrahim.kone@email.ci',
            'aissatou.bamba@email.ci', 'aissatou.bamba@email.ci',
        ],
        'Sens': [
            # 17 souscriptions, 3 rachats = ratio positif
            'souscription', 'souscription', 'souscription', 'souscription',
            'souscription', 'souscription',
            'souscription', 'souscription', 'souscription',
            'rachat',
            'souscription', 'souscription', 'souscription', 'souscription',
            'rachat',
            'souscription', 'souscription', 'souscription',
            'souscription', 'rachat',
        ],
        'Nom FCP': [
            fcps_existants[0], fcps_existants[1], fcps_existants[0], fcps_existants[2],
            fcps_existants[1], fcps_existants[3],
            fcps_existants[0], fcps_existants[2], fcps_existants[1],
            fcps_existants[0],
            fcps_existants[3], fcps_existants[4], fcps_existants[3], fcps_existants[4],
            fcps_existants[3],
            fcps_existants[1], fcps_existants[2], fcps_existants[0],
            fcps_existants[2], fcps_existants[2],
        ],
        'Quantité': [
            150.0000, 100.0000, 75.5000, 200.0000,
            120.0000, 80.2500,
            250.0000, 175.5000, 125.0000,
            50.0000,  # rachat partiel
            180.0000, 150.0000, 200.0000, 175.0000,
            40.0000,  # rachat partiel
            300.0000, 100.0000, 150.0000,
            200.0000, 30.0000,  # rachat partiel
        ],
        'VL Transaction': [
            # Prix unitaire (VL) à la date de transaction.
            # Colonne OPTIONNELLE : si vide, calculée automatiquement depuis les VL du FCP.
            10000.00, 11250.00, 10150.00, 11000.00,
            11250.00, 11400.00,
            11000.00, 11000.00, 11200.00,
            11100.00,
            11110.00, 11250.00, 11250.00, 11250.00,
            11300.00,
            11000.00, 11250.00, 11050.00,
            11000.00, 11100.00,
        ],
    }
    
    df = pd.DataFrame(data)
    
    # Créer le fichier Excel en mémoire
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Transactions PEE-PER')
        
        # Accéder au workbook pour formater
        workbook = writer.book
        worksheet = writer.sheets['Transactions PEE-PER']
        
        # Ajuster la largeur des colonnes
        column_widths = {
            'A': 18,  # Date Transaction
            'B': 15,  # Numéro Compte
            'C': 12,  # Type Plan
            'D': 22,  # Nom PER/PEE
            'E': 15,  # Matricule Type
            'F': 25,  # Nom & Prénom
            'G': 30,  # Email
            'H': 15,  # Sens
            'I': 20,  # Nom FCP
            'J': 15,  # Quantité
            'K': 20,  # VL Transaction
        }
        
        for col, width in column_widths.items():
            worksheet.column_dimensions[col].width = width
        
        # Ajouter une feuille d'instructions
        instructions_data = {
            'Colonne': [
                'Date Transaction',
                'Numéro Compte',
                'Type Plan',
                'Nom PER/PEE',
                'Matricule Type',
                'Nom & Prénom',
                'Email',
                'Sens',
                'Nom FCP',
                'Quantité',
                'VL Transaction'
            ],
            'Description': [
                'Date de la transaction (formats acceptés: JJ/MM/AAAA ou AAAA-MM-JJ)',
                'Identifiant unique du compte client',
                'Type de plan : PEE ou PER',
                'Nom du plan PER/PEE (ex: PEE CGF EPARGNE)',
                'Matricule du PEE/PER',
                'Nom complet du client',
                'Adresse email du client',
                "Type d'opération : souscription ou rachat",
                'Nom du FCP concerné - DOIT correspondre aux FCP existants',
                'Nombre de parts (décimal avec 4 décimales max, strictement positif)',
                "Prix unitaire d'exécution en FCFA (VL du FCP à la date). "
                "Si vide, calculé automatiquement depuis les VL importées."
            ],
            'Obligatoire': [
                'OBLIGATOIRE',
                'OBLIGATOIRE',
                'OBLIGATOIRE',
                'Recommandé',
                'Optionnel',
                'Recommandé',
                'Optionnel',
                'OBLIGATOIRE',
                'OBLIGATOIRE',
                'OBLIGATOIRE',
                'Optionnel (calculé)'
            ],
            'Exemple': [
                '15/01/2026',
                'CPT001',
                'PEE',
                'PEE CGF EPARGNE',
                'MAT001',
                'KOUASSI Ama',
                'ama.kouassi@email.ci',
                'souscription',
                fcps_existants[0] if fcps_existants else 'FCP EQUILIBRE',
                '100.5000',
                '11250.00'
            ]
        }
        
        df_instructions = pd.DataFrame(instructions_data)
        df_instructions.to_excel(writer, index=False, sheet_name='Instructions')
        
        # Ajouter une feuille avec la liste des FCP existants
        if fcps_existants:
            fcps_liste = list(ValeurLiquidative.objects.exclude(
                nom_fcp__isnull=True
            ).exclude(nom_fcp='').values_list('nom_fcp', flat=True).distinct().order_by('nom_fcp'))
            
            df_fcps = pd.DataFrame({
                'FCP Disponibles': fcps_liste,
                'Note': ['Utilisez exactement ces noms dans la colonne "Nom FCP"'] * len(fcps_liste)
            })
            df_fcps.to_excel(writer, index=False, sheet_name='FCP Disponibles')
            
            worksheet_fcps = writer.sheets['FCP Disponibles']
            worksheet_fcps.column_dimensions['A'].width = 40
            worksheet_fcps.column_dimensions['B'].width = 50
        
        worksheet_instructions = writer.sheets['Instructions']
        worksheet_instructions.column_dimensions['A'].width = 22
        worksheet_instructions.column_dimensions['B'].width = 50
        worksheet_instructions.column_dimensions['C'].width = 15
        worksheet_instructions.column_dimensions['D'].width = 25
    
    output.seek(0)
    
    response = HttpResponse(
        output.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="modele_import_pee_per.xlsx"'
    
    return response


# ========== API DASHBOARD ==========

def api_dashboard_encours(request):
    """
    API encours du dashboard.

    Le modèle de données ayant unifié les plans (plus de distinction PEE/PER),
    cette API renvoie l'encours **réel** (positions × VL) :
      - réparti par Plan à la date de fin (donut "Répartition Encours par Plan")
      - mensuellement, ventilé par FCP (area chart empilé "Évolution Encours
        Net Mensuel par FCP").
    """
    global _vl_cache

    date_debut_str = request.GET.get('date_debut')
    date_fin_str = request.GET.get('date_fin')

    # Parser les dates
    try:
        if date_debut_str:
            date_debut = datetime.strptime(date_debut_str, '%Y-%m-%d').date()
        else:
            date_debut = date(date.today().year, 1, 1)

        if date_fin_str:
            date_fin = datetime.strptime(date_fin_str, '%Y-%m-%d').date()
        else:
            date_fin = date.today()
    except ValueError:
        return JsonResponse({'error': 'Format de date invalide'}, status=400)

    # Charger le cache VL
    charger_cache_vl()

    try:
        # Toutes les transactions (nécessaire pour reconstituer les positions
        # à n'importe quelle date, y compris antérieure à date_debut)
        all_transactions = list(Sicav.objects.all().order_by('date_transaction'))

        # ---- Encours par FCP à la date de fin ----
        positions_fin = calculer_positions_a_date(all_transactions, date_fin)
        encours_par_fcp_fin = {}
        for nom_fcp, qty in positions_fin.items():
            if qty <= 0:
                continue
            vl = get_vl_at_date(nom_fcp, date_fin)
            if vl:
                encours_par_fcp_fin[nom_fcp] = qty * vl

        # ---- Encours par Plan à la date de fin ----
        # On reconstitue les positions par (plan, fcp) puis on valorise via la VL du FCP
        positions_par_plan_fcp = defaultdict(lambda: defaultdict(float))
        for t in all_transactions:
            if not t.date_transaction or t.date_transaction > date_fin:
                continue
            plan = t.nom_per_pee or 'Non renseigné'
            qty = float(t.quantite) if t.quantite else 0
            if t.sens == 'souscription':
                positions_par_plan_fcp[plan][t.nom_fcp] += qty
            elif t.sens == 'rachat':
                positions_par_plan_fcp[plan][t.nom_fcp] -= qty

        encours_par_plan_fin = {}
        for plan, fcps in positions_par_plan_fcp.items():
            total_plan = 0.0
            for nom_fcp, qty in fcps.items():
                if qty <= 0:
                    continue
                vl = get_vl_at_date(nom_fcp, date_fin)
                if vl:
                    total_plan += qty * vl
            if total_plan > 0:
                encours_par_plan_fin[plan] = total_plan

        # Encours global = somme des encours par plan (cohérent avec la page
        # "Analyse Plans" qui agrège plan par plan, après filtrage des
        # positions ≤ 0 au sein de chaque plan).
        encours_total = sum(encours_par_plan_fin.values())

        donut_items = sorted(
            [
                {'nom_plan': nom, 'encours': round(val, 2)}
                for nom, val in encours_par_plan_fin.items()
            ],
            key=lambda x: x['encours'],
            reverse=True,
        )

        # ---- Évolution mensuelle : encours par FCP à fin de chaque mois ----
        evolution_data = []
        fcps_set = set()
        total_sub = 0.0
        total_rach = 0.0

        for debut_mois, fin_mois, label in _iter_mois(date_debut, date_fin):
            positions_mois = calculer_positions_a_date(all_transactions, fin_mois)
            par_fcp = {}
            for nom_fcp, qty in positions_mois.items():
                if qty <= 0:
                    continue
                vl = get_vl_at_date(nom_fcp, fin_mois)
                if vl:
                    par_fcp[nom_fcp] = round(qty * vl, 2)
                    fcps_set.add(nom_fcp)

            # Flux nets du mois (souscriptions / rachats valorisés au CMP du jour)
            sub_mois = 0.0
            rach_mois = 0.0
            for t in all_transactions:
                if t.date_transaction and debut_mois <= t.date_transaction <= fin_mois:
                    montant = float(t.quantite or 0) * cmp_from_fcp(t)
                    if t.sens == 'souscription':
                        sub_mois += montant
                    elif t.sens == 'rachat':
                        rach_mois += montant

            total_sub += sub_mois
            total_rach += rach_mois

            evolution_data.append({
                'date': debut_mois.strftime('%Y-%m'),
                'label': label,
                'mois': label,
                'encours_total': round(sum(par_fcp.values()), 2),
                'par_fcp': par_fcp,
                'souscriptions': round(sub_mois, 2),
                'rachats': round(rach_mois, 2),
            })

        # Ordre des FCP : trié par encours final décroissant (cohérent avec
        # l'area chart), complété ensuite par les FCP qui n'ont plus de
        # position à date_fin mais qui en avaient pendant la période.
        fcps_ordre = [
            nom for nom, _ in sorted(
                encours_par_fcp_fin.items(), key=lambda kv: kv[1], reverse=True
            )
        ]
        for fcp in sorted(fcps_set):
            if fcp not in fcps_ordre:
                fcps_ordre.append(fcp)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

    return JsonResponse({
        'encours_total': round(encours_total, 2),
        'donut': donut_items,
        'fcps': fcps_ordre,
        'evolution': evolution_data,
        'flux': {
            'souscriptions': round(total_sub, 2),
            'rachats': round(total_rach, 2),
            'net': round(total_sub - total_rach, 2),
        },
        'date_debut': date_debut.strftime('%d/%m/%Y'),
        'date_fin': date_fin.strftime('%d/%m/%Y'),
    })


def api_vl_evolution(request):
    """API pour l'évolution des VL (graphique ligne)"""
    date_debut_str = request.GET.get('date_debut')
    date_fin_str = request.GET.get('date_fin')
    fcps_param = request.GET.get('fcps', '')  # Liste de FCP séparés par virgule
    base_100 = request.GET.get('base_100', 'false') == 'true'
    
    # Parser les dates
    try:
        if date_debut_str:
            date_debut = datetime.strptime(date_debut_str, '%Y-%m-%d').date()
        else:
            date_debut = date(date.today().year, 1, 1)
        
        if date_fin_str:
            date_fin = datetime.strptime(date_fin_str, '%Y-%m-%d').date()
        else:
            date_fin = date.today()
    except ValueError:
        return JsonResponse({'error': 'Format de date invalide'}, status=400)
    
    # Liste des FCP à afficher
    fcp_list = [f.strip() for f in fcps_param.split(',') if f.strip()] if fcps_param else []
    
    # Si aucun FCP spécifié, prendre les 5 premiers
    if not fcp_list:
        fcp_list = list(ValeurLiquidative.objects.values_list('nom_fcp', flat=True).distinct().order_by('nom_fcp')[:5])
    
    # Récupérer les VL pour les FCP sélectionnés
    vl_data = ValeurLiquidative.objects.filter(
        nom_fcp__in=fcp_list,
        date__gte=date_debut,
        date__lte=date_fin
    ).values('date', 'nom_fcp', 'valeur_liquidative').order_by('date')
    
    # Organiser par FCP
    fcp_series = {fcp: [] for fcp in fcp_list}
    fcp_base_values = {}
    
    for vl in vl_data:
        fcp = vl['nom_fcp']
        if fcp in fcp_series:
            value = float(vl['valeur_liquidative']) if vl['valeur_liquidative'] else 0
            
            if base_100:
                # Stocker la première valeur comme base
                if fcp not in fcp_base_values:
                    fcp_base_values[fcp] = value if value > 0 else 1
                # Calculer en base 100
                base_value = fcp_base_values[fcp]
                value = (value / base_value) * 100 if base_value > 0 else 100
            
            fcp_series[fcp].append({
                'date': vl['date'].strftime('%Y-%m-%d'),
                'value': round(value, 4)
            })
    
    # Liste de tous les FCP disponibles
    all_fcps = list(ValeurLiquidative.objects.values_list('nom_fcp', flat=True).distinct().order_by('nom_fcp'))
    
    return JsonResponse({
        'series': fcp_series,
        'fcps_selected': fcp_list,
        'fcps_available': all_fcps,
        'base_100': base_100,
        'date_debut': date_debut.strftime('%d/%m/%Y'),
        'date_fin': date_fin.strftime('%d/%m/%Y'),
    })


def api_fcp_calendar_performance(request):
    """API pour le tableau de performance calendaire des FCP (WTD, MTD, QTD, STD, YTD)"""
    type_fond_filter = request.GET.get('type_fond', '')
    categorie_fond_filter = request.GET.get('categorie_fond', '')
    
    today = date.today()
    
    # Calculer les dates de référence
    # WTD: Week To Date (début de semaine = lundi)
    wtd_start = today - timedelta(days=today.weekday())
    
    # MTD: Month To Date
    mtd_start = today.replace(day=1)
    
    # QTD: Quarter To Date
    quarter = (today.month - 1) // 3
    qtd_start = date(today.year, quarter * 3 + 1, 1)
    
    # STD: Semester To Date
    std_start = date(today.year, 1, 1) if today.month <= 6 else date(today.year, 7, 1)
    
    # YTD: Year To Date
    ytd_start = date(today.year, 1, 1)
    
    # Date minimale nécessaire (YTD start)
    min_date = ytd_start
    
    # Charger toutes les VL en une seule requête (optimisation)
    vl_queryset = ValeurLiquidative.objects.filter(
        date__gte=min_date - timedelta(days=30)  # Marge pour trouver VL avant période
    ).exclude(nom_fcp__isnull=True).exclude(nom_fcp='').order_by('nom_fcp', '-date')
    
    if type_fond_filter:
        vl_queryset = vl_queryset.filter(type_fond=type_fond_filter)
    if categorie_fond_filter:
        vl_queryset = vl_queryset.filter(categorie_fond=categorie_fond_filter)
    
    # Organiser par FCP: {nom_fcp: [(date, vl, meta), ...]}
    fcp_data = defaultdict(list)
    fcp_meta = {}
    
    for vl in vl_queryset.values('nom_fcp', 'date', 'valeur_liquidative', 'type_fond', 'categorie_fond'):
        nom = vl['nom_fcp']
        if nom and vl['valeur_liquidative']:
            fcp_data[nom].append((vl['date'], float(vl['valeur_liquidative'])))
            # Garder les métadonnées du plus récent
            if nom not in fcp_meta:
                fcp_meta[nom] = {
                    'type_fond': vl['type_fond'] or '-',
                    'categorie_fond': vl['categorie_fond'] or '-',
                    'vl_actuelle': float(vl['valeur_liquidative']),
                    'date_vl': vl['date'].strftime('%d/%m/%Y') if vl['date'] else '-'
                }
    
    # Fonction pour trouver VL à une date donnée (ou avant) dans une liste triée
    def get_vl_at_date(vl_list, target_date):
        for d, v in vl_list:
            if d <= target_date:
                return v
        return None
    
    # Fonction pour calculer performance
    def calc_perf(vl_list, start_date, end_date):
        v_start = get_vl_at_date(vl_list, start_date)
        v_end = get_vl_at_date(vl_list, end_date)
        if v_start and v_end and v_start > 0:
            return round((v_end - v_start) / v_start * 100, 2)
        return None
    
    performances = []
    
    for nom_fcp, vl_list in fcp_data.items():
        meta = fcp_meta.get(nom_fcp, {})
        
        perf_data = {
            'nom_fcp': nom_fcp,
            'type_fond': meta.get('type_fond', '-'),
            'categorie_fond': meta.get('categorie_fond', '-'),
            'vl_actuelle': meta.get('vl_actuelle', 0),
            'date_vl': meta.get('date_vl', '-'),
            'wtd': calc_perf(vl_list, wtd_start, today),
            'mtd': calc_perf(vl_list, mtd_start, today),
            'qtd': calc_perf(vl_list, qtd_start, today),
            'std': calc_perf(vl_list, std_start, today),
            'ytd': calc_perf(vl_list, ytd_start, today),
        }
        
        performances.append(perf_data)
    
    # Trier par nom de FCP
    performances.sort(key=lambda x: x['nom_fcp'])
    
    # Listes pour les filtres (utiliser set pour garantir l'unicité)
    types_fond = sorted(set(fcp_meta[nom]['type_fond'] for nom in fcp_meta if fcp_meta[nom]['type_fond'] != '-'))
    categories_fond = sorted(set(fcp_meta[nom]['categorie_fond'] for nom in fcp_meta if fcp_meta[nom]['categorie_fond'] != '-'))
    
    return JsonResponse({
        'performances': performances,
        'types_fond': types_fond,
        'categories_fond': categories_fond,
        'date_reference': today.strftime('%d/%m/%Y'),
        'periodes': {
            'wtd': f"{wtd_start.strftime('%d/%m')} - {today.strftime('%d/%m/%Y')}",
            'mtd': f"{mtd_start.strftime('%d/%m')} - {today.strftime('%d/%m/%Y')}",
            'qtd': f"{qtd_start.strftime('%d/%m')} - {today.strftime('%d/%m/%Y')}",
            'std': f"{std_start.strftime('%d/%m')} - {today.strftime('%d/%m/%Y')}",
            'ytd': f"{ytd_start.strftime('%d/%m')} - {today.strftime('%d/%m/%Y')}",
        }
    })


def api_heatmap_mensuel(request):
    """API pour la heatmap des performances mensuelles par portefeuille"""
    global _vl_cache
    
    date_debut_str = request.GET.get('date_debut')
    date_fin_str = request.GET.get('date_fin')
    methode = request.GET.get('methode', 'simple')
    type_plan_filter = request.GET.get('type_plan', '')
    top_n = int(request.GET.get('top_n', 10))
    
    # Parser les dates
    try:
        if date_debut_str:
            date_debut = datetime.strptime(date_debut_str, '%Y-%m-%d').date()
        else:
            date_debut = date(date.today().year, 1, 1)
        
        if date_fin_str:
            date_fin = datetime.strptime(date_fin_str, '%Y-%m-%d').date()
        else:
            date_fin = date.today()
    except ValueError:
        return JsonResponse({'error': 'Format de date invalide'}, status=400)
    
    # Charger le cache VL
    charger_cache_vl()
    
    try:
        # Récupérer les portefeuilles
        portefeuilles_query = Sicav.objects.exclude(nom_per_pee__isnull=True).exclude(nom_per_pee='')
        
        if type_plan_filter:
            portefeuilles_query = portefeuilles_query.filter(type_plan=type_plan_filter)
        
        noms_pee_per = portefeuilles_query.values_list('nom_per_pee', flat=True).distinct()[:top_n]
        
        # Générer les mois entre date_debut et date_fin
        mois_list = []
        current = date_debut.replace(day=1)
        while current <= date_fin:
            mois_list.append(current)
            if current.month == 12:
                current = date(current.year + 1, 1, 1)
            else:
                current = date(current.year, current.month + 1, 1)
        
        # Calculer les performances mensuelles pour chaque portefeuille
        heatmap_data = []
        
        for nom_per_pee in noms_pee_per:
            transactions = Sicav.objects.filter(nom_per_pee=nom_per_pee).order_by('date_transaction')
            
            # Créer un dictionnaire de performances par mois (format attendu par le front)
            performances_dict = {}
            
            for mois in mois_list:
                # Fin du mois
                if mois.month == 12:
                    fin_mois = date(mois.year + 1, 1, 1) - timedelta(days=1)
                else:
                    fin_mois = date(mois.year, mois.month + 1, 1) - timedelta(days=1)
                
                if fin_mois > date_fin:
                    fin_mois = date_fin
                
                # Positions au début et fin du mois
                positions_debut = calculer_positions_a_date(transactions, mois)
                positions_fin = calculer_positions_a_date(transactions, fin_mois)
                
                mois_label = mois.strftime('%b %y')
                
                if not positions_fin:
                    performances_dict[mois_label] = None
                    continue
                
                v_initial = calculer_valeur_portefeuille(positions_debut, mois)
                v_final = calculer_valeur_portefeuille(positions_fin, fin_mois)
                
                flux = calculer_flux_periode(transactions, mois, fin_mois)
                flux_nets_total = sum(montant for _, montant in flux)
                
                if methode == 'modifiee':
                    perf = performance_dietz_modifiee(v_initial, v_final, flux, mois, fin_mois)
                else:
                    perf = performance_dietz_simple(v_initial, v_final, flux_nets_total)
                
                performances_dict[mois_label] = round(perf, 2) if perf is not None else None
            
            heatmap_data.append({
                'nom': nom_per_pee,
                'portefeuille': nom_per_pee,
                'performances': performances_dict
            })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
    
    # Labels des mois
    mois_labels = [m.strftime('%b %y') for m in mois_list]
    
    return JsonResponse({
        'portefeuilles': heatmap_data,
        'data': heatmap_data,
        'mois': mois_labels,
        'date_debut': date_debut.strftime('%d/%m/%Y'),
        'date_fin': date_fin.strftime('%d/%m/%Y'),
    })


