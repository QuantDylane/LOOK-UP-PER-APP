"""
Script de génération de données sample pour tester l'application de reporting.

Paramètres de génération (facilitent la vérification manuelle des formules) :
  - 10 clients
  - 20 lignes de transaction par client (200 lignes au total)
  - 60% souscriptions (12) / 40% rachats (8) par client
  - Quantités et coûts moyens pondérés en chiffres ronds
  - Valeurs liquidatives à progression linéaire douce
"""

import os
import random
from datetime import datetime, timedelta

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'per_pee_reporting.settings')

import django
django.setup()

import pandas as pd


# ------------------------------------------------------------
# Référentiel minimal (facile à suivre à la main)
# ------------------------------------------------------------

NOMS_FCP = [
    'CGF ACTIONS',
    'CGF OBLIGATAIRE',
    'CGF EQUILIBRE',
    'CGF DYNAMIQUE',
    'CGF SÉRÉNITÉ',
]

DEPOSITAIRE = 'SGBS - Société Générale de Banques au Sénégal'

# 10 clients, données rondes et mémorisables
CLIENTS = [
    {'numero_compte': 'CPT001', 'nom_prenom': 'Diallo Mamadou',   'matricule': 'MAT-0001', 'email': 'mamadou.diallo@cgf.sn',   'plan': 'PLAN EPARGNE ALPHA'},
    {'numero_compte': 'CPT002', 'nom_prenom': 'Ndiaye Fatou',     'matricule': 'MAT-0002', 'email': 'fatou.ndiaye@cgf.sn',      'plan': 'PLAN EPARGNE ALPHA'},
    {'numero_compte': 'CPT003', 'nom_prenom': 'Sow Ibrahima',     'matricule': 'MAT-0003', 'email': 'ibrahima.sow@cgf.sn',      'plan': 'PLAN EPARGNE BETA'},
    {'numero_compte': 'CPT004', 'nom_prenom': 'Ba Aminata',       'matricule': 'MAT-0004', 'email': 'aminata.ba@cgf.sn',        'plan': 'PLAN EPARGNE BETA'},
    {'numero_compte': 'CPT005', 'nom_prenom': 'Fall Oumar',       'matricule': 'MAT-0005', 'email': 'oumar.fall@cgf.sn',        'plan': 'PLAN EPARGNE GAMMA'},
    {'numero_compte': 'CPT006', 'nom_prenom': 'Sy Awa',           'matricule': 'MAT-0006', 'email': 'awa.sy@cgf.sn',            'plan': 'PLAN EPARGNE GAMMA'},
    {'numero_compte': 'CPT007', 'nom_prenom': 'Gueye Cheikh',     'matricule': 'MAT-0007', 'email': 'cheikh.gueye@cgf.sn',      'plan': 'PLAN EPARGNE DELTA'},
    {'numero_compte': 'CPT008', 'nom_prenom': 'Faye Khady',       'matricule': 'MAT-0008', 'email': 'khady.faye@cgf.sn',        'plan': 'PLAN EPARGNE DELTA'},
    {'numero_compte': 'CPT009', 'nom_prenom': 'Sarr Boubacar',    'matricule': 'MAT-0009', 'email': 'boubacar.sarr@cgf.sn',     'plan': 'PLAN EPARGNE OMEGA'},
    {'numero_compte': 'CPT010', 'nom_prenom': 'Cissé Mariama',    'matricule': 'MAT-0010', 'email': 'mariama.cisse@cgf.sn',     'plan': 'PLAN EPARGNE OMEGA'},
]


# ------------------------------------------------------------
# Transactions SICAV : 10 clients × 20 lignes (12 sub / 8 rach)
# ------------------------------------------------------------

def generate_sicav_transactions():
    transactions = []

    start_date = datetime(2025, 1, 6)
    rng = random.Random(42)  # seed pour reproductibilité

    for idx, client in enumerate(CLIENTS):
        # 20 lignes = 12 souscriptions + 8 rachats
        types = ['souscription'] * 12 + ['rachat'] * 8
        rng.shuffle(types)

        for i, sens in enumerate(types):
            # Espacement régulier : une ligne toutes les 2 semaines
            date_tx = start_date + timedelta(days=14 * i + idx)

            # FCP choisi cyclique : facile à suivre
            nom_fcp = NOMS_FCP[(idx + i) % len(NOMS_FCP)]

            # Quantités rondes : 10, 20, 30, 40, 50
            quantite = 10 * (1 + (i % 5))

            # CMP rond : 10 000 pour souscription, 11 000 pour rachat
            # Ces valeurs rondes permettent de recalculer facilement les montants
            cout_moyen = 10000 if sens == 'souscription' else 11000

            transactions.append({
                'Date de transaction': date_tx.date(),
                'Numéro de compte': client['numero_compte'],
                'Type Plan': 'PLAN',
                'Nom du PER/PEE': client['plan'],
                'Matricule type': client['matricule'],
                'Nom & Prénom': client['nom_prenom'],
                'Email': client['email'],
                'Sens': sens,
                'Nom du FCP': nom_fcp,
                'Quantité': quantite,
                'Coût moyen pondéré': cout_moyen,
            })

    return pd.DataFrame(transactions)


# ------------------------------------------------------------
# Valeurs liquidatives : progression linéaire douce et prévisible
# ------------------------------------------------------------

FCP_METADATA = {
    'CGF ACTIONS': {
        'est_fcp_islamique': False, 'echelle_risque': 5,
        'categorie_fond': 'Dynamique', 'type_fond': 'Actions',
        'horizon_investissement': 5,
        'benchmark_obligataire': None, 'benchmark_brvmc': 'BRVM 10',
        'date_creation': datetime(2015, 3, 15).date(),
        'frais_gestion_ttc': '1.5%', 'frais_entree_ttc': '2%', 'frais_sortie_ttc': 'Néant',
        'vl_initiale': 10000, 'progression_par_semaine': 40,  # +40 FCFA / semaine
    },
    'CGF OBLIGATAIRE': {
        'est_fcp_islamique': False, 'echelle_risque': 2,
        'categorie_fond': 'Prudent', 'type_fond': 'Obligataire',
        'horizon_investissement': 2,
        'benchmark_obligataire': 'MBI UMOA', 'benchmark_brvmc': None,
        'date_creation': datetime(2016, 6, 20).date(),
        'frais_gestion_ttc': '0.8%', 'frais_entree_ttc': '0.5%', 'frais_sortie_ttc': 'Néant',
        'vl_initiale': 10000, 'progression_par_semaine': 15,
    },
    'CGF EQUILIBRE': {
        'est_fcp_islamique': False, 'echelle_risque': 4,
        'categorie_fond': 'Équilibré', 'type_fond': 'Diversifié',
        'horizon_investissement': 3,
        'benchmark_obligataire': 'MBI UMOA', 'benchmark_brvmc': 'BRVM Composite',
        'date_creation': datetime(2017, 1, 10).date(),
        'frais_gestion_ttc': '1.2%', 'frais_entree_ttc': '1.5%', 'frais_sortie_ttc': '0.5%',
        'vl_initiale': 10000, 'progression_par_semaine': 25,
    },
    'CGF DYNAMIQUE': {
        'est_fcp_islamique': False, 'echelle_risque': 6,
        'categorie_fond': 'Dynamique', 'type_fond': 'Actions',
        'horizon_investissement': 7,
        'benchmark_obligataire': None, 'benchmark_brvmc': 'BRVM 10',
        'date_creation': datetime(2018, 4, 5).date(),
        'frais_gestion_ttc': '1.8%', 'frais_entree_ttc': '2.5%', 'frais_sortie_ttc': 'Néant',
        'vl_initiale': 10000, 'progression_par_semaine': 50,
    },
    'CGF SÉRÉNITÉ': {
        'est_fcp_islamique': False, 'echelle_risque': 2,
        'categorie_fond': 'Prudent', 'type_fond': 'Obligataire',
        'horizon_investissement': 2,
        'benchmark_obligataire': 'MBI UMOA', 'benchmark_brvmc': None,
        'date_creation': datetime(2019, 7, 22).date(),
        'frais_gestion_ttc': '0.7%', 'frais_entree_ttc': '0.3%', 'frais_sortie_ttc': 'Néant',
        'vl_initiale': 10000, 'progression_par_semaine': 10,
    },
}


def generate_valeurs_liquidatives():
    """Génère des VL hebdomadaires, linéaires, faciles à vérifier à la main."""
    valeurs = []

    start_date = datetime(2025, 1, 1)
    end_date = datetime(2026, 4, 30)

    for fcp_name, meta in FCP_METADATA.items():
        vl = meta['vl_initiale']
        step = meta['progression_par_semaine']
        current_date = start_date

        while current_date <= end_date:
            valeurs.append({
                'Date': current_date.date(),
                'Nom du FCP': fcp_name,
                'Valeur liquidative': vl,
                'Est FCP islamique': 'Oui' if meta['est_fcp_islamique'] else 'Non',
                'Échelle de risque': meta['echelle_risque'],
                'Catégorie de fond': meta['categorie_fond'],
                'Type de fond': meta['type_fond'],
                "Horizon d'investissement (années)": meta['horizon_investissement'],
                'Benchmark Obligataire': meta['benchmark_obligataire'],
                'Benchmark BRVMC': meta['benchmark_brvmc'],
                'Date de création': meta['date_creation'],
                'Dépositaire': DEPOSITAIRE,
                "Frais de gestion (TTC de l'actif net / an)": meta['frais_gestion_ttc'],
                "Frais d'entrée TTC": meta['frais_entree_ttc'],
                'Frais de sortie TTC': meta['frais_sortie_ttc'],
            })
            vl += step  # progression linéaire, rigoureusement prévisible
            current_date += timedelta(days=7)

    return pd.DataFrame(valeurs)


def generate_fcp_metadata():
    rows = []
    for nom_fcp, meta in FCP_METADATA.items():
        rows.append({
            'Fond Commun de Placement\n(FCP)': nom_fcp,
            'FCP islamique': 'Oui' if meta['est_fcp_islamique'] else 'Non',
            'Echelle de risque': meta['echelle_risque'],
            'Catégorie de fond': meta['categorie_fond'],
            'Type de fond': meta['type_fond'],
            "Horizon d'investisement\n(en années)": meta['horizon_investissement'],
            'Benchmark_Obligataire': meta['benchmark_obligataire'],
            'Benchmark_BRVMC': meta['benchmark_brvmc'],
            'Date de création': meta['date_creation'],
            'Dépositaire': DEPOSITAIRE,
            "Frais de gestion\n(TTC de l'actif net / an)": meta['frais_gestion_ttc'],
            "Frais d'entrée TTC": meta['frais_entree_ttc'],
            'Frais de sortie TTC': meta['frais_sortie_ttc'],
        })
    return pd.DataFrame(rows)


def main():
    print("=" * 60)
    print("GÉNÉRATION DES FICHIERS SAMPLE")
    print("  - 10 clients")
    print("  - 20 lignes par client (12 souscriptions, 8 rachats)")
    print("  - Chiffres ronds pour vérification manuelle")
    print("=" * 60)

    output_dir = 'sample_data'
    os.makedirs(output_dir, exist_ok=True)

    print("\n1. Transactions SICAV...")
    df_sicav = generate_sicav_transactions()
    sicav_file = os.path.join(output_dir, 'Transactions_SICAV_Sample.xlsx')
    df_sicav.to_excel(sicav_file, index=False)
    print(f"   OK - {len(df_sicav)} transactions -> {sicav_file}")

    print("\n2. Valeurs liquidatives...")
    df_vl = generate_valeurs_liquidatives()
    vl_file = os.path.join(output_dir, 'Valeurs_Liquidatives_Sample.xlsx')
    df_vl.to_excel(vl_file, index=False)
    print(f"   OK - {len(df_vl)} lignes VL -> {vl_file}")

    print("\n3. Fiche signaletique des FCP...")
    df_meta = generate_fcp_metadata()
    meta_file = os.path.join(output_dir, 'Fiche signalétique des FCP.xlsx')
    df_meta.to_excel(meta_file, index=False)
    print(f"   OK - {len(df_meta)} FCP -> {meta_file}")

    print("\nTermine.")


if __name__ == '__main__':
    main()
