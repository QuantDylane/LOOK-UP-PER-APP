"""
Génère des données fictives de transactions Sicav (Plan d'Épargne).

Règles :
- 10 clients fictifs uniques.
- 20 transactions au total (60% souscriptions, 40% rachats).
- FCP tirés aléatoirement parmi ceux présents dans ValeurLiquidative.
- Dates tirées dans la plage de dates des VL disponibles.
- Quantités réalistes selon le sens (souscription : 5–200 parts ;
  rachat : 1–50 parts, plafonné au cumul déjà souscrit par le client sur le FCP).
- Les rachats ne sont générés que pour les couples (client, FCP) ayant déjà une
  souscription antérieure.

Utilisation :
    python scripts/generate_fake_sicav.py           # ajoute aux transactions existantes
    python scripts/generate_fake_sicav.py --reset   # supprime puis regénère
"""

import argparse
import os
import random
from decimal import Decimal

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "per_pee_reporting.settings")
django.setup()

from django.db import transaction  # noqa: E402
from django.db.models import Max, Min  # noqa: E402

from reporting.models import Sicav, ValeurLiquidative  # noqa: E402

SEED = 42
N_CLIENTS = 10
N_TRANSACTIONS = 20
PCT_SOUSCRIPTION = 0.60

CLIENTS_FICTIFS = [
    ("Aminata DIOP", "aminata.diop@example.com"),
    ("Mamadou SECK", "mamadou.seck@example.com"),
    ("Fatou NDIAYE", "fatou.ndiaye@example.com"),
    ("Ibrahima FALL", "ibrahima.fall@example.com"),
    ("Aïssatou BA", "aissatou.ba@example.com"),
    ("Moussa SARR", "moussa.sarr@example.com"),
    ("Khady GUEYE", "khady.gueye@example.com"),
    ("Ousmane SOW", "ousmane.sow@example.com"),
    ("Mariama CISSÉ", "mariama.cisse@example.com"),
    ("Cheikh DIAGNE", "cheikh.diagne@example.com"),
]

# 5 plans (A à E), deux clients par plan.
PLAN_NAMES = ["Plan A", "Plan B", "Plan C", "Plan D", "Plan E"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Supprime toutes les transactions Sicav existantes avant de régénérer.",
    )
    args, _ = parser.parse_known_args()

    rng = random.Random(SEED)

    fcps = sorted(
        set(
            ValeurLiquidative.objects.exclude(nom_fcp__isnull=True)
            .exclude(nom_fcp="")
            .values_list("nom_fcp", flat=True)
            .distinct()
        )
    )
    if not fcps:
        raise SystemExit("Aucun FCP en base (table ValeurLiquidative vide).")

    agg = ValeurLiquidative.objects.aggregate(mn=Min("date"), mx=Max("date"))
    if not agg["mn"] or not agg["mx"]:
        raise SystemExit("Impossible de déterminer la plage de dates des VL.")

    date_min = agg["mn"]
    date_max = agg["mx"]
    total_days = (date_max - date_min).days
    if total_days <= 0:
        raise SystemExit("Plage de dates VL invalide.")

    # Générer 10 clients avec numéro de compte. Les clients sont regroupés
    # par paires sur 5 plans (Plan A à Plan E), deux clients par plan.
    clients = []
    for i, (nom, email) in enumerate(CLIENTS_FICTIFS[:N_CLIENTS]):
        numero = f"CPT{1000 + i:04d}"
        plan_index = i // 2  # 0,0,1,1,2,2,3,3,4,4
        nom_plan = PLAN_NAMES[plan_index]
        matricule = f"MAT{2000 + i}"
        clients.append(
            {
                "numero_compte": numero,
                "nom_prenom": nom,
                "email": email,
                "nom_per_pee": nom_plan,
                "matricule_type": matricule,
            }
        )

    n_souscriptions = round(N_TRANSACTIONS * PCT_SOUSCRIPTION)
    n_rachats = N_TRANSACTIONS - n_souscriptions

    # Cumul de parts détenues par (numero_compte, nom_fcp) pour plafonner les rachats
    cumul = {}
    # Première date de souscription par (numero_compte, nom_fcp) pour cohérence temporelle
    first_souscription_date = {}
    transactions = []

    def random_date(after=None):
        low = 0 if after is None else max(0, (after - date_min).days + 1)
        high = total_days
        if low > high:
            low = high
        offset = rng.randint(low, high)
        return date_min.fromordinal(date_min.toordinal() + offset)

    # Générer les souscriptions : d'abord une par client pour garantir les 10 clients,
    # puis le reste tiré aléatoirement.
    souscription_clients = list(clients)
    rng.shuffle(souscription_clients)
    remaining = n_souscriptions - len(souscription_clients)
    if remaining > 0:
        souscription_clients += [rng.choice(clients) for _ in range(remaining)]
    else:
        souscription_clients = souscription_clients[:n_souscriptions]

    for client in souscription_clients:
        fcp = rng.choice(fcps)
        date_tx = random_date()
        quantite = Decimal(str(round(rng.uniform(5, 200), 4)))
        key = (client["numero_compte"], fcp)
        cumul[key] = cumul.get(key, Decimal("0")) + quantite
        if key not in first_souscription_date or date_tx < first_souscription_date[key]:
            first_souscription_date[key] = date_tx
        transactions.append(
            {
                **client,
                "date_transaction": date_tx,
                "sens": "souscription",
                "nom_fcp": fcp,
                "quantite": quantite,
            }
        )

    # Générer les rachats uniquement sur des positions déjà souscrites
    rachats_crees = 0
    attempts = 0
    while rachats_crees < n_rachats and attempts < n_rachats * 50:
        attempts += 1
        # Choisir un (client, fcp) avec du stock > 0
        positions_dispo = [
            (k, v) for k, v in cumul.items() if v > Decimal("0.0001")
        ]
        if not positions_dispo:
            break
        (numero_compte, fcp), stock = rng.choice(positions_dispo)
        client = next(c for c in clients if c["numero_compte"] == numero_compte)

        # Rachat après la date de 1ère souscription correspondante
        first_date = first_souscription_date[(numero_compte, fcp)]
        if first_date >= date_max:
            continue
        date_tx = random_date(after=first_date)

        max_q = min(float(stock), 50.0)
        if max_q <= 1:
            continue
        quantite = Decimal(str(round(rng.uniform(1, max_q), 4)))
        cumul[(numero_compte, fcp)] -= quantite
        transactions.append(
            {
                **client,
                "date_transaction": date_tx,
                "sens": "rachat",
                "nom_fcp": fcp,
                "quantite": quantite,
            }
        )
        rachats_crees += 1

    if rachats_crees < n_rachats:
        # Compléter en souscriptions supplémentaires si pas assez de stock pour rachats
        manquants = n_rachats - rachats_crees
        for _ in range(manquants):
            client = rng.choice(clients)
            fcp = rng.choice(fcps)
            date_tx = random_date()
            quantite = Decimal(str(round(rng.uniform(5, 200), 4)))
            transactions.append(
                {
                    **client,
                    "date_transaction": date_tx,
                    "sens": "souscription",
                    "nom_fcp": fcp,
                    "quantite": quantite,
                }
            )
        print(
            f"Avertissement : seulement {rachats_crees}/{n_rachats} rachats possibles, "
            f"complétés par {manquants} souscriptions supplémentaires."
        )

    # Trier par date
    transactions.sort(key=lambda t: t["date_transaction"])

    with transaction.atomic():
        if args.reset:
            deleted, _ = Sicav.objects.all().delete()
            print(f"{deleted} transactions Sicav supprimées.")
        objs = [
            Sicav(
                date_transaction=t["date_transaction"],
                numero_compte=t["numero_compte"],
                type_plan="PLAN",
                nom_per_pee=t["nom_per_pee"],
                matricule_type=t["matricule_type"],
                nom_prenom=t["nom_prenom"],
                email=t["email"],
                sens=t["sens"],
                nom_fcp=t["nom_fcp"],
                quantite=t["quantite"],
                cout_moyen_pondere=Decimal("0"),  # champ legacy - CMP calculé depuis FCP
            )
            for t in transactions
        ]
        Sicav.objects.bulk_create(objs)

    souscriptions = sum(1 for t in transactions if t["sens"] == "souscription")
    rachats = sum(1 for t in transactions if t["sens"] == "rachat")
    print(
        f"\n{len(transactions)} transactions créées "
        f"({souscriptions} souscriptions / {rachats} rachats) "
        f"pour {len({t['numero_compte'] for t in transactions})} clients "
        f"sur {len({t['nom_fcp'] for t in transactions})} FCP."
    )
    print(f"Plage de dates : {transactions[0]['date_transaction']} → {transactions[-1]['date_transaction']}")


if __name__ == "__main__":
    main()
