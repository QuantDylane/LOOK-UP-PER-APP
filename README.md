# LOOK-UP PER APP

Application Django de reporting pour la gestion et le suivi des plans d'épargne (PEE/PER) et des fonds communs de placement (FCP).

## Fonctionnalités

- Tableau de bord des performances (Top/Flop FCP)
- Analyse par portefeuille PEE/PER
- Analyse par client
- Catalogue des métadonnées FCP (valeurs liquidatives, frais, benchmarks)
- Import/export de données (Excel, CSV)
- Contrôle qualité des données

## Prérequis

- Python 3.10+
- pip

## Installation

```bash
# 1. Cloner le dépôt
git clone <url-du-repo>
cd LOOK-UP-PER-APP

# 2. Créer et activer un environnement virtuel
python -m venv .venv
source .venv/bin/activate      # Linux/macOS
# .venv\Scripts\activate       # Windows

# 3. Installer les dépendances
pip install -r requirements.txt

# 4. Configurer les variables d'environnement
cp .env.example .env
# Éditer .env selon votre environnement

# 5. Appliquer les migrations
python manage.py migrate

# 6. Créer un super-utilisateur (première fois)
python manage.py createsuperuser

# 7. Charger les données de démonstration (optionnel)
python scripts/generate_sample_data.py   # génère les fichiers Excel dans sample_data/
python scripts/reload_sample_data.py     # importe les données en base

# 8. Lancer le serveur de développement
python manage.py runserver
```

L'application est accessible sur [http://127.0.0.1:8000/](http://127.0.0.1:8000/).

## Scripts utilitaires

Tous les scripts se trouvent dans le dossier `scripts/` et s'exécutent depuis la racine du projet :

| Script | Description |
|--------|-------------|
| `scripts/generate_sample_data.py` | Génère des données de démonstration (FCP, VL, transactions) dans `sample_data/` |
| `scripts/reload_sample_data.py` | Purge la base et recharge les données depuis `sample_data/` |
| `scripts/generate_fake_sicav.py` | Génère des transactions SICAV fictives |
| `scripts/import_excel_data.py` | Importe les valeurs liquidatives depuis `data/FCP valeurs liquidatives.xlsx` |
| `scripts/import_fiche_signaletique.py` | Importe les métadonnées FCP depuis `data/Fiche signalétique des FCP.xlsx` |

## Structure du projet

```
LOOK-UP-PER-APP/
├── data/                   # Fichiers Excel de données sources
├── docs/                   # Documentation et ressources visuelles
├── manage.py
├── per_pee_reporting/      # Configuration Django (settings, urls, wsgi)
├── reporting/              # Application principale
│   ├── migrations/
│   ├── models.py
│   ├── views.py
│   └── ...
├── sample_data/            # Données de démonstration générées
├── scripts/                # Scripts utilitaires (import, génération)
├── static/                 # Fichiers statiques (CSS, images)
├── templates/              # Templates HTML
├── .env.example            # Variables d'environnement (modèle)
└── requirements.txt
```

## Variables d'environnement

Voir `.env.example` pour la liste complète. Les principales variables :

| Variable | Défaut | Description |
|----------|--------|-------------|
| `DJANGO_SECRET_KEY` | valeur insecure | Clé secrète Django (**changer en prod**) |
| `DJANGO_DEBUG` | `True` | Mode debug |
| `DJANGO_ALLOWED_HOSTS` | *(vide)* | Hôtes autorisés (séparés par des virgules) |
| `DJANGO_CACHE_BACKEND` | LocMemCache | Backend de cache Django |
| `DJANGO_CACHE_LOCATION` | `unique-snowflake` | Localisation du cache |
