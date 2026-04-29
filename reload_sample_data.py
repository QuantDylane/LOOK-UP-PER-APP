"""
Réinitialise la base de données avec les données sample fraichement générées.
À exécuter après generate_sample_data.py.
"""

import os
from decimal import Decimal
from datetime import timedelta

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'per_pee_reporting.settings')

import django
django.setup()

import pandas as pd
from reporting.models import Sicav, ValeurLiquidative


def main():
    print("Purge des donnees existantes...")
    Sicav.objects.all().delete()
    ValeurLiquidative.objects.all().delete()

    print("Import transactions SICAV...")
    df_sicav = pd.read_excel('sample_data/Transactions_SICAV_Sample.xlsx')
    sicav_rows = []
    for _, row in df_sicav.iterrows():
        sicav_rows.append(Sicav(
            date_transaction=row['Date de transaction'].date() if hasattr(row['Date de transaction'], 'date') else row['Date de transaction'],
            numero_compte=row['Numéro de compte'],
            type_plan='PLAN',
            nom_per_pee=row['Nom du PER/PEE'],
            matricule_type=row['Matricule type'],
            nom_prenom=row['Nom & Prénom'],
            email=row['Email'],
            sens=row['Sens'],
            nom_fcp=row['Nom du FCP'],
            quantite=Decimal(str(row['Quantité'])),
            cout_moyen_pondere=Decimal(str(row['Coût moyen pondéré'])),
        ))
    Sicav.objects.bulk_create(sicav_rows)
    print(f"  {len(sicav_rows)} transactions importees")

    print("Import valeurs liquidatives (hebdomadaires)...")
    df_vl = pd.read_excel('sample_data/Valeurs_Liquidatives_Sample.xlsx')
    vl_rows = []
    for _, row in df_vl.iterrows():
        vl_rows.append(ValeurLiquidative(
            date=row['Date'].date() if hasattr(row['Date'], 'date') else row['Date'],
            nom_fcp=row['Nom du FCP'],
            valeur_liquidative=Decimal(str(row['Valeur liquidative'])),
            est_fcp_islamique=(row['Est FCP islamique'] == 'Oui'),
            echelle_risque=int(row['Échelle de risque']) if pd.notna(row['Échelle de risque']) else None,
            categorie_fond=str(row['Catégorie de fond']).lower() if pd.notna(row['Catégorie de fond']) else None,
            type_fond=str(row['Type de fond']).lower() if pd.notna(row['Type de fond']) else None,
            horizon_investissement=int(row["Horizon d'investissement (années)"]) if pd.notna(row["Horizon d'investissement (années)"]) else None,
            benchmark_obligataire=str(row['Benchmark Obligataire']) if pd.notna(row['Benchmark Obligataire']) else None,
            benchmark_brvmc=str(row['Benchmark BRVMC']) if pd.notna(row['Benchmark BRVMC']) else None,
            date_creation=row['Date de création'].date() if pd.notna(row['Date de création']) and hasattr(row['Date de création'], 'date') else row['Date de création'] if pd.notna(row['Date de création']) else None,
            depositaire=str(row['Dépositaire']) if pd.notna(row['Dépositaire']) else None,
            frais_gestion_ttc=str(row["Frais de gestion (TTC de l'actif net / an)"]) if pd.notna(row["Frais de gestion (TTC de l'actif net / an)"]) else None,
            frais_entree_ttc=str(row["Frais d'entrée TTC"]) if pd.notna(row["Frais d'entrée TTC"]) else None,
            frais_sortie_ttc=str(row['Frais de sortie TTC']) if pd.notna(row['Frais de sortie TTC']) else None,
        ))
    ValeurLiquidative.objects.bulk_create(vl_rows)
    print(f"  {len(vl_rows)} VL importees")

    print("Completion des jours manquants (VL quotidiennes par report)...")
    fcps = ValeurLiquidative.objects.values_list('nom_fcp', flat=True).distinct()
    total_filled = 0
    for fcp_name in fcps:
        if not fcp_name:
            continue
        vl_list = list(ValeurLiquidative.objects.filter(nom_fcp=fcp_name).order_by('date').values(
            'date', 'valeur_liquidative', 'est_fcp_islamique', 'echelle_risque',
            'categorie_fond', 'type_fond', 'horizon_investissement',
            'benchmark_obligataire', 'benchmark_brvmc', 'date_creation',
            'depositaire', 'frais_gestion_ttc', 'frais_entree_ttc', 'frais_sortie_ttc'
        ))
        if len(vl_list) < 2:
            continue
        existing_dates = {vl['date'] for vl in vl_list}
        min_date = min(existing_dates)
        max_date = max(existing_dates)
        current = min_date
        last = None
        fill_rows = []
        while current <= max_date:
            if current in existing_dates:
                for vl in vl_list:
                    if vl['date'] == current:
                        last = vl
                        break
            elif last:
                fill_rows.append(ValeurLiquidative(
                    date=current,
                    nom_fcp=fcp_name,
                    valeur_liquidative=last['valeur_liquidative'],
                    est_fcp_islamique=last['est_fcp_islamique'],
                    echelle_risque=last['echelle_risque'],
                    categorie_fond=last['categorie_fond'],
                    type_fond=last['type_fond'],
                    horizon_investissement=last['horizon_investissement'],
                    benchmark_obligataire=last['benchmark_obligataire'],
                    benchmark_brvmc=last['benchmark_brvmc'],
                    date_creation=last['date_creation'],
                    depositaire=last['depositaire'],
                    frais_gestion_ttc=last['frais_gestion_ttc'],
                    frais_entree_ttc=last['frais_entree_ttc'],
                    frais_sortie_ttc=last['frais_sortie_ttc'],
                ))
            current += timedelta(days=1)
        if fill_rows:
            ValeurLiquidative.objects.bulk_create(fill_rows)
            total_filled += len(fill_rows)
    print(f"  {total_filled} jours manquants completes")

    print(f"\nTotal en base:")
    print(f"  - Transactions SICAV : {Sicav.objects.count()}")
    print(f"  - Valeurs liquidatives: {ValeurLiquidative.objects.count()}")
    print(f"  - Clients uniques    : {Sicav.objects.values('numero_compte').distinct().count()}")
    print(f"  - Plans uniques      : {Sicav.objects.values('nom_per_pee').distinct().count()}")
    print(f"  - FCP uniques        : {ValeurLiquidative.objects.values('nom_fcp').distinct().count()}")


if __name__ == '__main__':
    main()
