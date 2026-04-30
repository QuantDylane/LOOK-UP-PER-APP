"""
Génère et insère des données fictives de transactions SICAV (souscriptions/rachats)
dans la table `sicav`, en s'appuyant sur les FCP et dates réellement présents dans
la table `valeurs_liquidatives` afin que les coûts moyens pondérés soient cohérents
avec l'historique des VL.

Exécution :
    python scripts/seed_sicav_transactions.py [--clients N] [--reset]

Options :
    --clients N   Nombre de clients fictifs (défaut: 40)
    --reset       Supprime toutes les transactions SICAV existantes avant insertion
"""

from __future__ import annotations

import argparse
import os
import random
import sys
from decimal import Decimal, ROUND_HALF_UP

import django

# Configuration Django
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "per_pee_reporting.settings")
django.setup()

from reporting.models import Sicav, ValeurLiquidative  # noqa: E402


# ---------------------------------------------------------------------------
# Données fictives (UEMOA / Afrique de l'Ouest)
# ---------------------------------------------------------------------------

PRENOMS = [
    "Aminata", "Fatou", "Awa", "Mariama", "Aïssatou", "Khady", "Ndeye", "Bineta",
    "Moussa", "Ibrahima", "Modou", "Cheikh", "Ousmane", "Abdoulaye", "Mamadou",
    "Boubacar", "Pape", "Souleymane", "Aliou", "Babacar", "Seydou", "Lamine",
    "Adama", "Salif", "Diery", "Sokhna", "Coumba", "Rokhaya", "Penda", "Yacine",
    "Marieme", "Astou", "Maguette", "Idrissa", "Demba", "Tidiane",
]

NOMS = [
    "Diop", "Ndiaye", "Sow", "Fall", "Sarr", "Ba", "Diallo", "Cissé", "Sy",
    "Gueye", "Faye", "Mbaye", "Sène", "Diagne", "Kane", "Niang", "Touré",
    "Camara", "Sangaré", "Konaté", "Traoré", "Coulibaly", "Keita", "Diakhité",
    "Thiam", "Wade", "Bâ", "Seck", "Lo", "Dieng",
]

DOMAINES = ["gmail.com", "yahoo.fr", "outlook.com", "orange.sn", "live.fr"]

# Plans / produits commercialisés (matricule_type + nom_per_pee)
PLANS = [
    ("PER_INDIV", "PER Individuel CGF"),
    ("PER_RETRAITE", "PER Retraite Plus"),
    ("PER_DIASPORA", "PER Diaspora Sénégal"),
    ("PEE_CGF", "PEE Collaborateurs CGF"),
    ("PEE_SONATEL", "PEE Sonatel"),
    ("PEE_DPWORLD", "PEE DP World"),
    ("PEE_BNDE", "PEE BNDE Valeurs"),
    ("PEE_TRANSVIE", "PEE Transvie"),
]


def _slug(s: str) -> str:
    repl = (
        ("é", "e"), ("è", "e"), ("ê", "e"), ("ë", "e"),
        ("à", "a"), ("â", "a"), ("ä", "a"),
        ("ï", "i"), ("î", "i"),
        ("ô", "o"), ("ö", "o"),
        ("ù", "u"), ("û", "u"), ("ü", "u"),
        ("ç", "c"), ("ñ", "n"), ("’", ""), ("'", ""),
    )
    out = s.lower()
    for a, b in repl:
        out = out.replace(a, b)
    return out.replace(" ", ".")


def build_clients(n: int, rng: random.Random) -> list[dict]:
    """Construit n clients fictifs avec attributs stables."""
    clients = []
    used_emails: set[str] = set()
    for i in range(n):
        prenom = rng.choice(PRENOMS)
        nom = rng.choice(NOMS)
        nom_prenom = f"{prenom} {nom}"

        base_email = f"{_slug(prenom)}.{_slug(nom)}"
        email = f"{base_email}@{rng.choice(DOMAINES)}"
        suffix = 1
        while email in used_emails:
            suffix += 1
            email = f"{base_email}{suffix}@{rng.choice(DOMAINES)}"
        used_emails.add(email)

        matricule, nom_plan = rng.choice(PLANS)
        # Numéro de compte: 10 chiffres déterministe par client
        numero_compte = f"SN{rng.randint(10_000_000, 99_999_999):08d}"

        clients.append({
            "numero_compte": numero_compte,
            "nom_prenom": nom_prenom,
            "email": email,
            "matricule_type": matricule,
            "nom_per_pee": nom_plan,
        })
    return clients


def quantize4(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def generate_transactions(clients: list[dict], rng: random.Random) -> list[Sicav]:
    """Génère des transactions cohérentes avec les VL disponibles."""
    # Cache: pour chaque FCP, liste de (date, valeur_liquidative)
    fcp_history: dict[str, list[tuple]] = {}
    qs = (
        ValeurLiquidative.objects
        .exclude(nom_fcp__isnull=True)
        .exclude(valeur_liquidative__isnull=True)
        .values_list("nom_fcp", "date", "valeur_liquidative")
        .order_by("nom_fcp", "date")
    )
    for nom_fcp, date, vl in qs:
        fcp_history.setdefault(nom_fcp, []).append((date, vl))

    available_fcps = [f for f, h in fcp_history.items() if len(h) >= 5]
    if not available_fcps:
        raise RuntimeError("Aucun FCP exploitable dans valeurs_liquidatives.")

    transactions: list[Sicav] = []

    for client in clients:
        # Chaque client investit dans 1 à 4 FCP
        n_fcp = rng.randint(1, 4)
        client_fcps = rng.sample(available_fcps, k=min(n_fcp, len(available_fcps)))

        for nom_fcp in client_fcps:
            history = fcp_history[nom_fcp]
            # Souscription initiale: date aléatoire dans la 1ère moitié de l'historique
            n_total_tx = rng.randint(2, 6)
            indices = sorted(rng.sample(range(len(history)), k=min(n_total_tx, len(history))))

            current_qty = Decimal("0")
            for idx, hist_idx in enumerate(indices):
                date_tx, vl = history[hist_idx]

                # 80% souscription pour la 1ère, ensuite mix
                if idx == 0 or current_qty <= 0:
                    sens = "souscription"
                else:
                    sens = rng.choices(
                        ["souscription", "rachat"], weights=[0.7, 0.3], k=1
                    )[0]

                if sens == "souscription":
                    # Souscription en montant: 250k à 5M FCFA -> quantite = montant / vl
                    montant = Decimal(rng.randint(250_000, 5_000_000))
                    quantite = quantize4(montant / vl)
                    current_qty += quantite
                else:
                    # Rachat partiel: 20% à 80% du portefeuille courant
                    pct = Decimal(str(rng.uniform(0.2, 0.8)))
                    quantite = quantize4(current_qty * pct)
                    if quantite <= 0:
                        continue
                    current_qty -= quantite

                # Coût moyen pondéré ≈ VL avec léger bruit (+/- 0.5%)
                noise = Decimal(str(1 + rng.uniform(-0.005, 0.005)))
                cmp_val = quantize4(vl * noise)

                transactions.append(Sicav(
                    date_transaction=date_tx,
                    numero_compte=client["numero_compte"],
                    type_plan="PLAN",
                    nom_per_pee=client["nom_per_pee"],
                    matricule_type=client["matricule_type"],
                    nom_prenom=client["nom_prenom"],
                    email=client["email"],
                    sens=sens,
                    nom_fcp=nom_fcp,
                    quantite=quantite,
                    cout_moyen_pondere=cmp_val,
                ))

    return transactions


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clients", type=int, default=40, help="Nombre de clients fictifs")
    parser.add_argument("--reset", action="store_true", help="Vider la table SICAV avant insertion")
    parser.add_argument("--seed", type=int, default=42, help="Seed aléatoire")
    # parse_known_args pour rester compatible avec un lancement Jupyter
    args, _unknown = parser.parse_known_args()

    rng = random.Random(args.seed)

    if args.reset:
        deleted, _ = Sicav.objects.all().delete()
        print(f"[reset] {deleted} transactions supprimées.")

    if ValeurLiquidative.objects.count() == 0:
        print("ERREUR: la table valeurs_liquidatives est vide. Importez d'abord les VL.")
        return 1

    print(f"Génération de {args.clients} clients fictifs...")
    clients = build_clients(args.clients, rng)

    print("Génération des transactions...")
    transactions = generate_transactions(clients, rng)

    print(f"Insertion de {len(transactions)} transactions en base...")
    Sicav.objects.bulk_create(transactions, batch_size=500)

    total = Sicav.objects.count()
    print(f"OK. Total transactions SICAV en base: {total}")
    print(
        "Répartition: "
        f"souscriptions={Sicav.objects.filter(sens='souscription').count()}, "
        f"rachats={Sicav.objects.filter(sens='rachat').count()}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
