import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'per_pee_reporting.settings')
django.setup()

import pandas as pd
import re
from decimal import Decimal, InvalidOperation
from datetime import datetime
from reporting.models import ValeurLiquidative


def parse_frais(value):
    """
    Parse une valeur de frais qui peut être sous différents formats:
    - Numérique (0.01, 500)
    - Pourcentage texte ("1% HT", "2,5%")
    - Texte nul ("Néant", "N/A", vide)
    Retourne un Decimal ou None.
    """
    if pd.isna(value):
        return None
    
    # Convertir en string
    value_str = str(value).strip()
    
    # Cas "Néant", "N/A", vide, etc.
    if value_str.lower() in ['néant', 'neant', 'n/a', 'na', '', '-', 'none']:
        return None
    
    # Essayer d'extraire un nombre (avec ou sans %)
    # Remplacer la virgule par un point
    value_str = value_str.replace(',', '.')
    
    # Extraire le premier nombre trouvé
    match = re.search(r'[\d.]+', value_str)
    if match:
        try:
            num = Decimal(match.group())
            # Si c'était un pourcentage (contient %), on garde la valeur telle quelle
            # car les frais sont déjà en format décimal (0.01 = 1%)
            return num
        except (InvalidOperation, ValueError):
            return None
    
    return None


def import_data():
    """Import des données depuis les fichiers Excel."""
    
    # 1. Importer les métadonnées des FCP
    print('=== Import des métadonnées FCP ===')
    df_meta = pd.read_excel('data/Fiche signalétique des FCP.xlsx')
    
    # Créer un dictionnaire des métadonnées par nom de FCP
    fcp_metadata = {}
    for _, row in df_meta.iterrows():
        nom = row['Fond Commun de Placement\n(FCP)']
        fcp_metadata[nom] = {
            'est_fcp_islamique': row['FCP islamique'] == 'Oui',
            'echelle_risque': int(row['Echelle de risque']) if pd.notna(row['Echelle de risque']) else None,
            'categorie_fond': str(row['Catégorie de fond']).lower() if pd.notna(row['Catégorie de fond']) else None,
            'type_fond': str(row['Type de fond']).lower() if pd.notna(row['Type de fond']) else None,
            'horizon_investissement': int(row["Horizon d'investisement\n(en années)"]) if pd.notna(row["Horizon d'investisement\n(en années)"]) else None,
            'benchmark_obligataire': str(row['Benchmark_Obligataire']) if pd.notna(row['Benchmark_Obligataire']) else None,
            'benchmark_brvmc': str(row['Benchmark_BRVMC']) if pd.notna(row['Benchmark_BRVMC']) else None,
            'date_creation': row['Date de création'].date() if pd.notna(row['Date de création']) else None,
            'depositaire': str(row['Dépositaire']) if pd.notna(row['Dépositaire']) else None,
            'frais_gestion_ttc': parse_frais(row["Frais de gestion\n(TTC de l'actif net / an)"]),
            'frais_entree_ttc': parse_frais(row["Frais d'entrée TTC"]),
            'frais_sortie_ttc': parse_frais(row['Frais de sortie TTC']),
        }
    
    print(f'{len(fcp_metadata)} FCP trouvés dans le fichier de métadonnées')
    
    # Créer une fonction de correspondance de noms
    def find_metadata(fcp_name):
        """Trouver les métadonnées pour un FCP donné."""
        # Correspondance exacte
        if fcp_name in fcp_metadata:
            return fcp_metadata[fcp_name]
        
        # Normaliser le nom
        normalized = fcp_name.upper().replace(' ', '').replace('-', '').replace('_', '')
        
        # Mapping spécifique pour les noms différents
        name_mapping = {
            'FCPACTIONSPHARMCIE': 'FCP ACTION PHARMACIE',
            'FCPEPWORLD': 'FCP DP WORLD',
            'FCPEDPWORLDDAKAR': 'FCP DP WORLD',
            'FCPEFORCEPAD': 'FCP FORCE PAD',
            'FCPESINIGNESIGUI': 'FCP SINI GNESIGUI',
        }
        
        for key, value in name_mapping.items():
            if key in normalized:
                return fcp_metadata.get(value, {})
        
        # Recherche approximative
        for key in fcp_metadata.keys():
            key_norm = key.upper().replace(' ', '').replace('-', '').replace('_', '')
            if key_norm in normalized or normalized in key_norm:
                return fcp_metadata[key]
        
        return {}
    
    # 2. Importer les valeurs liquidatives
    print('=== Import des valeurs liquidatives ===')
    df_vl = pd.read_excel('data/FCP valeurs liquidatives.xlsx')
    
    fcp_columns = [col for col in df_vl.columns if col != 'Date']
    print(f'{len(fcp_columns)} FCP trouvés dans le fichier VL')
    print(f'{len(df_vl)} dates à traiter')
    
    created = 0
    updated = 0
    batch = []
    batch_size = 500
    
    total_rows = len(df_vl) * len(fcp_columns)
    processed = 0
    
    for _, row in df_vl.iterrows():
        date = row['Date']
        if pd.isna(date):
            continue
        date = date.date() if hasattr(date, 'date') else date
        
        for fcp_name in fcp_columns:
            vl_value = row[fcp_name]
            if pd.isna(vl_value):
                continue
            
            meta = find_metadata(fcp_name)
            
            defaults = {
                'valeur_liquidative': Decimal(str(vl_value)),
                'est_fcp_islamique': meta.get('est_fcp_islamique', False),
                'echelle_risque': meta.get('echelle_risque'),
                'categorie_fond': meta.get('categorie_fond'),
                'type_fond': meta.get('type_fond'),
                'horizon_investissement': meta.get('horizon_investissement'),
                'benchmark_obligataire': meta.get('benchmark_obligataire'),
                'benchmark_brvmc': meta.get('benchmark_brvmc'),
                'date_creation': meta.get('date_creation'),
                'depositaire': meta.get('depositaire'),
                'frais_gestion_ttc': meta.get('frais_gestion_ttc'),
                'frais_entree_ttc': meta.get('frais_entree_ttc'),
                'frais_sortie_ttc': meta.get('frais_sortie_ttc'),
            }
            
            obj, is_created = ValeurLiquidative.objects.update_or_create(
                date=date,
                nom_fcp=fcp_name,
                defaults=defaults
            )
            
            if is_created:
                created += 1
            else:
                updated += 1
            
            processed += 1
            if processed % 1000 == 0:
                print(f'  Progression: {processed}/{total_rows} ({100*processed/total_rows:.1f}%)')
    
    print(f'\nImport terminé: {created} créés, {updated} mis à jour')
    print(f'Total VL en base: {ValeurLiquidative.objects.count()}')
    
    # Compléter les jours manquants
    print('\n=== Complétion des jours manquants ===')
    fill_missing_dates()


def fill_missing_dates():
    """
    Complète les jours manquants dans les valeurs liquidatives.
    Pour chaque jour manquant, on utilise la dernière valeur connue avant cette date.
    """
    from datetime import timedelta
    
    # Récupérer tous les FCP distincts
    fcps = ValeurLiquidative.objects.values_list('nom_fcp', flat=True).distinct()
    
    total_filled = 0
    
    for fcp_name in fcps:
        if not fcp_name:
            continue
            
        # Récupérer toutes les VL pour ce FCP, triées par date
        vl_queryset = ValeurLiquidative.objects.filter(nom_fcp=fcp_name).order_by('date')
        vl_list = list(vl_queryset.values('date', 'valeur_liquidative', 'est_fcp_islamique', 
                                          'categorie_fond', 'type_fond', 'horizon_investissement',
                                          'benchmark_obligataire', 'benchmark_brvmc', 'date_creation',
                                          'depositaire', 'frais_gestion_ttc', 'frais_entree_ttc', 'frais_sortie_ttc',
                                          'echelle_risque'))
        
        if len(vl_list) < 2:
            continue
        
        # Récupérer les dates existantes
        existing_dates = set(vl['date'] for vl in vl_list)
        
        # Trouver la première et dernière date
        min_date = min(existing_dates)
        max_date = max(existing_dates)
        
        # Parcourir chaque jour entre min et max
        current_date = min_date
        last_known_vl = None
        
        while current_date <= max_date:
            if current_date in existing_dates:
                # Mettre à jour la dernière VL connue
                for vl in vl_list:
                    if vl['date'] == current_date:
                        last_known_vl = vl
                        break
            else:
                # Jour manquant - créer une entrée avec la dernière VL connue
                if last_known_vl:
                    ValeurLiquidative.objects.create(
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
                        echelle_risque=last_known_vl['echelle_risque'],
                    )
                    total_filled += 1
            
            current_date += timedelta(days=1)
    
    print(f'{total_filled} jours manquants complétés')
    print(f'Total VL en base après complétion: {ValeurLiquidative.objects.count()}')


if __name__ == '__main__':
    import_data()
