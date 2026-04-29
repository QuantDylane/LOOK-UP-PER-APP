"""
Importer les métadonnées FCP depuis 'Fiche signalétique des FCP.xlsx'
vers la table ValeurLiquidative (mise à jour de tous les enregistrements du même FCP).

Utilisation :
    python import_fiche_signaletique.py
    python import_fiche_signaletique.py --fichier "Fiche signalétique des FCP.xlsx"
"""

import argparse
import os
import sys
from pathlib import Path

import django
import pandas as pd

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "per_pee_reporting.settings")
django.setup()

from reporting.models import ValeurLiquidative  # noqa: E402

# Mapping entre les noms dans la fiche signalétique et les noms dans les VL.
NAME_ALIASES = {
    "FCP ACTION PHARMACIE": "FCP ACTIONS PHARMACIE",
    "FCP POSTEFINANCE HORIZON": "FCP POSTFINANCES HORIZON",
    "FCP DP WORLD": "FCPE DP WORLD DAKAR",
    "FCP SINI GNESIGUI": "FCPE SINI GNESIGUI",
    "FCP FORCE PAD": "FCPE FORCE PAD",
}


def parse_boolean(value):
    if value is None or pd.isna(value):
        return False
    return str(value).strip().lower() in {"oui", "yes", "true", "1", "vrai", "o"}


def format_frais(value):
    """Convertit un frais en chaîne lisible.
    - NaN / None / vide -> None
    - 'Néant', '1% HT', ... -> renvoyé tel quel (strippé)
    - Nombre <= 1 -> pourcentage 'X.XX%'
    - Nombre > 1 -> 'NNNN FCFA'
    """
    if value is None:
        return None
    if pd.isna(value):
        return None
    if isinstance(value, str):
        s = value.strip()
        return s or None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return str(value).strip() or None
    if v <= 1:
        return f"{v * 100:.2f}%"
    return f"{v:.0f} FCFA"


def format_benchmark(value):
    """Formate un benchmark. Si numérique, stocke en chaîne décimale
    (compatible avec to_percent() de la vue metadonnees)."""
    if value is None or pd.isna(value):
        return None
    if isinstance(value, str):
        s = value.strip()
        return s or None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return str(value).strip() or None
    return f"{v:.4f}"


def normalize_categorie(value):
    if value is None or pd.isna(value):
        return None
    s = str(value).strip().lower()
    # Normalisation des accents courants
    s = s.replace("é", "e").replace("è", "e")
    mapping = {
        "prudent": "prudent",
        "equilibre": "equilibre",
        "dynamique": "dynamique",
    }
    return mapping.get(s, s)


def normalize_type_fond(value):
    if value is None or pd.isna(value):
        return None
    s = str(value).strip().lower()
    s = s.replace("é", "e").replace("è", "e")
    return s


def to_int(value):
    if value is None or pd.isna(value):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def to_date(value):
    if value is None or pd.isna(value):
        return None
    if hasattr(value, "date"):
        return value.date()
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--fichier",
        default="Fiche signalétique des FCP.xlsx",
        help="Chemin du fichier Excel de la fiche signalétique.",
    )
    args, _unknown = parser.parse_known_args()

    path = Path(args.fichier)
    if not path.exists():
        print(f"Fichier introuvable: {path}", file=sys.stderr)
        sys.exit(1)

    df = pd.read_excel(path)

    col_nom = "Fond Commun de Placement\n(FCP)"
    col_echelle = "Echelle de risque"
    col_islam = "FCP islamique"
    col_cat = "Catégorie de fond"
    col_type = "Type de fond"
    col_horizon = "Horizon d'investisement\n(en années)"
    col_bench_ob = "Benchmark_Obligataire"
    col_bench_brvmc = "Benchmark_BRVMC"
    col_date_creation = "Date de création"
    col_depositaire = "Dépositaire"
    col_frais_gestion = "Frais de gestion\n(TTC de l'actif net / an)"
    col_frais_entree = "Frais d'entrée TTC"
    col_frais_sortie = "Frais de sortie TTC"

    missing_cols = [
        c
        for c in [
            col_nom,
            col_echelle,
            col_islam,
            col_cat,
            col_type,
            col_horizon,
            col_bench_ob,
            col_bench_brvmc,
            col_date_creation,
            col_depositaire,
            col_frais_gestion,
            col_frais_entree,
            col_frais_sortie,
        ]
        if c not in df.columns
    ]
    if missing_cols:
        print("Colonnes manquantes:", missing_cols, file=sys.stderr)
        sys.exit(1)

    fcps_existants = set(
        ValeurLiquidative.objects.values_list("nom_fcp", flat=True).distinct()
    )

    mis_a_jour = 0
    non_trouves = []
    details = []

    for _, row in df.iterrows():
        nom_raw = row[col_nom]
        if pd.isna(nom_raw):
            continue
        nom_fiche = str(nom_raw).strip()
        nom_fcp = NAME_ALIASES.get(nom_fiche, nom_fiche)

        if nom_fcp not in fcps_existants:
            non_trouves.append(nom_fiche)
            continue

        defaults = {
            "echelle_risque": to_int(row[col_echelle]),
            "est_fcp_islamique": parse_boolean(row[col_islam]),
            "categorie_fond": normalize_categorie(row[col_cat]),
            "type_fond": normalize_type_fond(row[col_type]),
            "horizon_investissement": to_int(row[col_horizon]),
            "benchmark_obligataire": format_benchmark(row[col_bench_ob]),
            "benchmark_brvmc": format_benchmark(row[col_bench_brvmc]),
            "date_creation": to_date(row[col_date_creation]),
            "depositaire": (
                str(row[col_depositaire]).strip()
                if not pd.isna(row[col_depositaire])
                else None
            ),
            "frais_gestion_ttc": format_frais(row[col_frais_gestion]),
            "frais_entree_ttc": format_frais(row[col_frais_entree]),
            "frais_sortie_ttc": format_frais(row[col_frais_sortie]),
        }

        n = ValeurLiquidative.objects.filter(nom_fcp=nom_fcp).update(**defaults)
        mis_a_jour += 1
        details.append(f"  {nom_fcp}: {n} lignes VL mises à jour")

    print(f"\n{mis_a_jour}/{len(df)} FCP mis à jour.")
    for d in details:
        print(d)

    if non_trouves:
        print(
            f"\n{len(non_trouves)} FCP de la fiche ne correspondent à aucun FCP en base :"
        )
        for n in non_trouves:
            print(f"  - {n}")

    # FCP en base qui n'ont pas été enrichis
    vl_fcps = set(ValeurLiquidative.objects.values_list("nom_fcp", flat=True).distinct())
    fiche_fcps = {
        NAME_ALIASES.get(str(n).strip(), str(n).strip())
        for n in df[col_nom].dropna().tolist()
    }
    non_enrichis = sorted(vl_fcps - fiche_fcps)
    if non_enrichis:
        print(f"\n{len(non_enrichis)} FCP en base non présents dans la fiche :")
        for n in non_enrichis:
            print(f"  - {n}")


if __name__ == "__main__":
    main()
