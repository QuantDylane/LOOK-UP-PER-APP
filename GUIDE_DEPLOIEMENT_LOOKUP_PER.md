# 📋 GUIDE COMPLET DE DÉPLOIEMENT - EXPLICATION TECHNIQUE
## Application LOOK-UP PER APP — Reporting PEE/PER & FCP (CGF Gestion)

---

## TABLE DES MATIÈRES
1. [Vue d'ensemble du projet](#vue-densemble)
2. [Architecture et structure du dossier](#architecture)
3. [Composants techniques](#composants)
4. [Prérequis de déploiement](#prerequis)
5. [Instructions de déploiement](#deploiement)
6. [Configuration post-déploiement](#configuration)
7. [Dépannage et points critiques](#depannage)

---

## 1. VUE D'ENSEMBLE DU PROJET {#vue-densemble}

### Qu'est-ce que c'est ?
**LOOK-UP PER APP** est une **application web Django** de reporting destinée à CGF Gestion. Elle permet de **suivre, analyser et restituer** les performances des plans d'épargne (**PEE/PER**) et des **Fonds Communs de Placement (FCP)** gérés par la société, à partir de données importées depuis Excel.

### Objectif métier
- ✅ Centraliser les **valeurs liquidatives (VL)** des FCP et les **transactions SICAV** (souscriptions/rachats)
- ✅ Offrir un **tableau de bord** des performances (Top/Flop FCP, encours, heatmap mensuelle)
- ✅ Fournir une **analyse par portefeuille (plan PEE/PER)** et **par client** (numéro de compte)
- ✅ Maintenir un **catalogue de métadonnées FCP** (frais, benchmark, échelle de risque, dépositaire)
- ✅ **Importer/Exporter** les données via Excel et CSV
- ✅ **Contrôler la qualité** des données (doublons, VL manquantes, rapprochement)
- ✅ Générer des **rapports PDF** (rapports plans / rapports clients)

### Technologie utilisée
- **Framework** : Django 5.2 (Python)
- **Base de données** : SQLite (par défaut) — PostgreSQL recommandé en production
- **Serveur web** : Gunicorn / uWSGI + Nginx (Linux) ou Waitress + IIS (Windows)
- **Frontend** : HTML/CSS/JavaScript + Bootstrap (templates Django)
- **Génération PDF** : `xhtml2pdf`
- **Manipulation de données** : `pandas`, `openpyxl`, `matplotlib`

---

## 2. ARCHITECTURE ET STRUCTURE DU DOSSIER {#architecture}

```
LOOK UP PER APP/
│
├── 📄 manage.py
│   └── Point d'entrée des commandes Django
│
├── 📄 db.sqlite3
│   └── Base SQLite (développement) — NE PAS copier en prod
│
├── 📄 requirements.txt
│   └── Dépendances Python : Django>=5.2, pandas, openpyxl, xhtml2pdf, matplotlib
│
├── 📄 README.md
│   └── Démarrage rapide et description fonctionnelle
│
├── 📄 GUIDE_DEPLOIEMENT_EXPLANATION.md
│   └── Guide générique de déploiement (référence)
│
├── 📁 per_pee_reporting/        [Configuration du projet Django]
│   ├── settings.py              # SECRET_KEY, DEBUG, ALLOWED_HOSTS, BD, cache
│   ├── urls.py                  # Routeur racine (redirige vers reporting.urls)
│   ├── wsgi.py / asgi.py        # Points d'entrée serveur (Gunicorn / ASGI)
│   └── __init__.py
│
├── 📁 reporting/                [Application métier — CŒUR DE L'APP]
│   ├── models.py                # Modèles : Sicav, ValeurLiquidative
│   ├── views.py                 # Vues principales (dashboard, analyses, APIs JSON)
│   ├── views_export.py          # Génération des rapports PDF (xhtml2pdf)
│   ├── urls.py                  # Routes (login_required / superuser_required)
│   ├── admin.py                 # Interface Django Admin
│   ├── apps.py                  # Configuration de l'app
│   ├── cmp.py                   # Calcul du Coût Moyen Pondéré
│   ├── tests.py                 # Tests unitaires
│   ├── migrations/              # Schéma BD (0001 → 0006)
│   │   ├── 0001_initial.py
│   │   ├── 0002_alter_valeurliquidative_frais_entree_ttc_and_more.py
│   │   ├── 0003_alter_valeurliquidative_categorie_fond_and_more.py
│   │   ├── 0004_valeurliquidative_echelle_risque.py
│   │   ├── 0005_sicav_nom_per_pee.py
│   │   └── 0006_unify_type_plan.py
│   └── templatetags/
│       └── reporting_extras.py  # Filtres custom pour templates
│
├── 📁 templates/                [Interface utilisateur — HTML]
│   ├── base.html                # Template parent (header, nav, footer)
│   ├── registration/
│   │   └── login.html           # Page de connexion
│   └── reporting/
│       ├── accueil.html             # Dashboard (Top/Flop, encours, heatmap)
│       ├── analyse_pee_per.html     # Analyse par plan PEE/PER
│       ├── analyse_client.html      # Analyse par client
│       ├── metadonnees.html         # Catalogue FCP / VL / SICAV (superuser)
│       ├── controle.html            # Contrôle qualité (superuser)
│       ├── _controle_tx_table.html  # Partial : table des transactions
│       ├── export.html              # Page d'export
│       ├── rapport_pdf.html         # Template du rapport PDF
│       └── a_propos.html            # À propos
│
├── 📁 scripts/                  [Scripts utilitaires]
│   ├── import_excel_data.py     # Import des VL depuis Excel
│   └── import_fiche_signaletique.py  # Import des fiches signalétiques FCP
│
├── 📁 static/                   [Ressources statiques]
│   ├── css/style.css
│   └── images/
│
└── 📁 docs/                     [Documentation]
    ├── CHARTE_GRAPHIQUE.md
    └── DESIGN.md
```

---

## 3. COMPOSANTS TECHNIQUES {#composants}

### 3.1 Stack technique

| Composant | Version | Rôle |
|-----------|---------|------|
| **Python** | 3.10+ | Langage principal |
| **Django** | 5.2+ | Framework web |
| **pandas** | 2.0+ | Manipulation de données / imports Excel |
| **openpyxl** | 3.1+ | Lecture/écriture des fichiers `.xlsx` |
| **xhtml2pdf** | 0.2.11+ | Génération des rapports PDF |
| **matplotlib** | 3.7+ | Graphiques côté serveur |
| **SQLite** | builtin | BD de développement |
| **PostgreSQL** | 13+ | BD recommandée en production |
| **Gunicorn** | 21.0+ | Serveur WSGI (Linux) |
| **Waitress** | 3.0+ | Serveur WSGI (Windows) |
| **Nginx / IIS** | — | Reverse proxy & fichiers statiques |

### 3.2 Modèles de données (tables principales)

```
Sicav  (db_table = 'sicav')
├── date_transaction (Date)
├── numero_compte (Char 50)              -- Identifiant client
├── type_plan (Char 10)                  -- 'PLAN'
├── nom_per_pee (Char 200)               -- Nom du plan PEE/PER
├── matricule_type (Char 50)
├── nom_prenom (Char 200)
├── email (Email)
├── sens (Char 20)                       -- 'souscription' / 'rachat'
├── nom_fcp (Char 200)
├── quantite (Decimal 18,4)
└── cout_moyen_pondere (Decimal 18,4)

ValeurLiquidative  (db_table = 'valeurs_liquidatives')
├── date (Date)
├── nom_fcp (Char 200)
├── valeur_liquidative (Decimal 18,4)
├── est_fcp_islamique (Boolean)
├── echelle_risque (Int 1–7)
├── categorie_fond (Char)                -- Prudent/Équilibré/Dynamique/Diversifié
├── type_fond (Char)                     -- Actions/Obligataire/Diversifié
├── horizon_investissement (Int années)
├── benchmark_obligataire (Char 200)
├── benchmark_brvmc (Char 200)
├── date_creation (Date)
├── depositaire (Char 200)
├── frais_gestion_ttc (Char 100)
├── frais_entree_ttc (Char 100)
└── frais_sortie_ttc (Char 100)
```

### 3.3 Routes principales (extrait `reporting/urls.py`)

| URL | Vue | Accès |
|-----|-----|-------|
| `/` | Dashboard accueil | Connecté |
| `/analyse-pee-per/` | Analyse par plan | Connecté |
| `/analyse-client/` | Analyse par client | Connecté |
| `/metadonnees/` | Catalogue FCP / VL / SICAV | **Superuser** |
| `/controle/` | Contrôle qualité données | **Superuser** |
| `/export/` | Page d'export rapports | Connecté |
| `/export/rapport-plans/pdf/` | Rapport PDF par plan | Connecté |
| `/export/rapport-clients/pdf/` | Rapport PDF client | Connecté |
| `/api/dashboard/...` | APIs JSON dashboard | Connecté |
| `/admin/` | Django Admin | Superuser |

### 3.4 Flux principaux

**Flux 1 — Import des données métier**
```
Admin (superuser) → /metadonnees/ → Upload Excel (FCP / VL / SICAV)
→ analyser_excel (preview pandas) → executer_import_excel
→ INSERT dans valeurs_liquidatives / sicav
```

**Flux 2 — Consultation dashboard**
```
Utilisateur → / (accueil) → APIs /api/dashboard/* (JSON)
→ ValeurLiquidative + Sicav → Calcul performances → Charts JS
```

**Flux 3 — Génération PDF**
```
Utilisateur → /export/ → /export/rapport-plans/pdf/
→ views_export.py → Template rapport_pdf.html
→ xhtml2pdf → Téléchargement PDF
```

**Flux 4 — Contrôle qualité**
```
Superuser → /controle/ → Détection doublons / VL manquantes
→ Actions : supprimer SICAV, appliquer VL proche, purger doublons
```

---

## 4. PRÉREQUIS DE DÉPLOIEMENT {#prerequis}

### 4.1 Serveur recommandé

- **OS** : Linux (Ubuntu 22.04+) ou Windows Server 2019+
- **CPU** : 2 cores minimum, 4+ recommandé
- **RAM** : 2 GB minimum, 4+ GB recommandé (pandas peut être gourmand)
- **Disque** : 10 GB minimum (BD + fichiers Excel sources + logs)
- **Accès Internet** : pour `pip install`

### 4.2 Logiciels pré-installés

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install -y python3.11 python3-pip python3-venv \
    postgresql postgresql-contrib nginx git \
    libpq-dev build-essential
```

```powershell
# Windows Server
# - Python 3.11+ (python.org)
# - PostgreSQL (optionnel)
# - IIS + URL Rewrite + HttpPlatformHandler (optionnel)
```

### 4.3 Fichiers à préparer

1. ✅ Code source du projet (clone Git ou copie)
2. ✅ Fichier `.env` avec `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=False`, `DJANGO_ALLOWED_HOSTS`
3. ✅ Fichiers Excel sources (VL et fiches signalétiques)
4. ✅ (Optionnel) BD PostgreSQL provisionnée
5. ✅ Plan de sauvegarde

---

## 5. INSTRUCTIONS DE DÉPLOIEMENT {#deploiement}

### ÉTAPE 1 — Récupérer le projet

```bash
# Linux
sudo useradd -m -d /home/lookup lookup
su - lookup
git clone <url_repo> /home/lookup/app
cd /home/lookup/app
```

```powershell
# Windows
mkdir C:\Applications\lookup-per
cd C:\Applications\lookup-per
git clone <url_repo> .
```

### ÉTAPE 2 — Environnement Python

```bash
python3.11 -m venv .venv
source .venv/bin/activate          # Linux
# .\.venv\Scripts\Activate.ps1     # Windows
pip install --upgrade pip
pip install -r requirements.txt
```

### ÉTAPE 3 — Variables d'environnement

Créer un fichier `.env` (chargé via votre process manager ou `django-environ`) ou exporter directement :

```bash
export DJANGO_SECRET_KEY="$(python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())')"
export DJANGO_DEBUG=False
export DJANGO_ALLOWED_HOSTS="lookup.cgfgestion.com,votre-ip"
# Cache (recommandé en prod)
export DJANGO_CACHE_BACKEND="django.core.cache.backends.redis.RedisCache"
export DJANGO_CACHE_LOCATION="redis://127.0.0.1:6379/1"
```

> ⚠️ Le projet lit déjà ces variables dans [per_pee_reporting/settings.py](per_pee_reporting/settings.py). Aucun patch du fichier n'est nécessaire si elles sont définies dans l'environnement.

### ÉTAPE 4 — Base de données

#### Option A — SQLite (simple, mono-utilisateur)
Aucune configuration. Le fichier `db.sqlite3` est créé à la première migration.

#### Option B — PostgreSQL (recommandé)

```bash
sudo -u postgres psql <<SQL
CREATE USER lookup_user WITH PASSWORD 'votre_mot_de_passe';
CREATE DATABASE lookup_db OWNER lookup_user;
ALTER ROLE lookup_user SET client_encoding TO 'utf8';
ALTER ROLE lookup_user SET timezone TO 'Africa/Abidjan';
GRANT ALL PRIVILEGES ON DATABASE lookup_db TO lookup_user;
SQL
```

Puis ajouter le driver et adapter `settings.py` (ou via `dj-database-url`) :

```bash
pip install psycopg[binary]
```

```python
# per_pee_reporting/settings.py
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ["DB_NAME"],
        "USER": os.environ["DB_USER"],
        "PASSWORD": os.environ["DB_PASSWORD"],
        "HOST": os.environ.get("DB_HOST", "localhost"),
        "PORT": os.environ.get("DB_PORT", "5432"),
    }
}
```

### ÉTAPE 5 — Migrations & superuser

```bash
python manage.py migrate
python manage.py createsuperuser
```

> ⚠️ Les routes `/metadonnees/` et `/controle/` sont **réservées aux superusers**. Créer au moins un superuser pour pouvoir importer les données.

### ÉTAPE 6 — Import des données initiales

```bash
# VL des FCP (depuis data/FCP valeurs liquidatives.xlsx)
python scripts/import_excel_data.py

# Fiches signalétiques FCP (depuis data/Fiche signalétique des FCP.xlsx)
python scripts/import_fiche_signaletique.py
```

Alternative : se connecter à `/metadonnees/` en tant que superuser et utiliser l'interface d'import Excel.

### ÉTAPE 7 — Fichiers statiques

```bash
python manage.py collectstatic --noinput
# → génère le dossier ./staticfiles/
```

### ÉTAPE 8 — Test local

```bash
python manage.py runserver 0.0.0.0:8000
# → http://localhost:8000/
```

### ÉTAPE 9 — Serveur applicatif (production)

#### Linux — Gunicorn

```bash
pip install gunicorn
```

`/home/lookup/app/gunicorn_config.py` :

```python
import multiprocessing
bind = "127.0.0.1:8001"
workers = multiprocessing.cpu_count() * 2 + 1
timeout = 120
errorlog = "/home/lookup/app/logs/gunicorn-error.log"
accesslog = "/home/lookup/app/logs/gunicorn-access.log"
```

`/etc/systemd/system/lookup.service` :

```ini
[Unit]
Description=LOOK-UP PER APP (Django)
After=network.target

[Service]
User=lookup
Group=www-data
WorkingDirectory=/home/lookup/app
EnvironmentFile=/home/lookup/app/.env
ExecStart=/home/lookup/app/.venv/bin/gunicorn \
    --config gunicorn_config.py \
    per_pee_reporting.wsgi:application
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now lookup
sudo systemctl status lookup
```

#### Windows — Waitress

```powershell
pip install waitress
waitress-serve --listen=127.0.0.1:8001 per_pee_reporting.wsgi:application
```

(Encapsuler dans un service via `nssm` ou IIS HttpPlatformHandler.)

### ÉTAPE 10 — Reverse proxy Nginx

`/etc/nginx/sites-available/lookup` :

```nginx
server {
    listen 80;
    server_name lookup.cgfgestion.com;
    client_max_body_size 50M;     # Imports Excel volumineux

    location /static/ {
        alias /home/lookup/app/staticfiles/;
    }

    location / {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/lookup /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

### ÉTAPE 11 — HTTPS (Let's Encrypt)

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d lookup.cgfgestion.com
```

---

## 6. CONFIGURATION POST-DÉPLOIEMENT {#configuration}

### 6.1 Accès

- **Application** : `https://lookup.cgfgestion.com/`
- **Login** : `https://lookup.cgfgestion.com/accounts/login/` (ou `/login/`)
- **Admin Django** : `https://lookup.cgfgestion.com/admin/`

### 6.2 Création des utilisateurs

Depuis `/admin/` :
1. Créer les utilisateurs (commerciaux / analystes / direction).
2. Pour les utilisateurs ayant besoin d'accéder à `/metadonnees/` ou `/controle/`, cocher **`is_superuser`** (ou définir des permissions Django personnalisées si une granularité plus fine est ajoutée plus tard).

### 6.3 Imports périodiques des données

Mettre en place un cron pour rafraîchir les VL/fiches FCP :

```cron
# Tous les jours à 06h00
0 6 * * * cd /home/lookup/app && /home/lookup/app/.venv/bin/python scripts/import_excel_data.py >> logs/import.log 2>&1
```

### 6.4 Sauvegardes

```bash
#!/bin/bash
# /home/lookup/backup.sh
BACKUP_DIR=/home/lookup/backups
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p "$BACKUP_DIR"

# PostgreSQL
pg_dump -U lookup_user lookup_db | gzip > "$BACKUP_DIR/db_$DATE.sql.gz"
# OU SQLite
# cp /home/lookup/app/db.sqlite3 "$BACKUP_DIR/db_$DATE.sqlite3"

# Rétention 14 jours
find "$BACKUP_DIR" -mtime +14 -delete
```

```cron
0 2 * * * /home/lookup/backup.sh
```

---

## 7. DÉPANNAGE ET POINTS CRITIQUES {#depannage}

### 7.1 Erreurs courantes

| Erreur | Cause probable | Solution |
|--------|---------------|----------|
| `ModuleNotFoundError: No module named 'django'` | venv non activé | `source .venv/bin/activate` |
| `DisallowedHost ... Invalid HTTP_HOST header` | Domaine absent de `DJANGO_ALLOWED_HOSTS` | Ajouter le domaine dans la variable d'env |
| `OperationalError: no such table: sicav` | Migrations non appliquées | `python manage.py migrate` |
| Page `/metadonnees/` renvoie login | L'utilisateur n'est pas superuser | Cocher `is_superuser` dans l'admin |
| PDF vide ou cassé | Polices/CSS manquants côté `xhtml2pdf` | Vérifier `static/` et `STATIC_ROOT`, relancer `collectstatic` |
| Import Excel échoue | Colonnes / format différents | Comparer avec le **modèle SICAV** téléchargeable depuis `/metadonnees/` |
| `413 Request Entity Too Large` | Nginx refuse l'upload Excel | Augmenter `client_max_body_size` |
| Cache incohérent après import | Cache local `LocMemCache` | Passer à Redis (`DJANGO_CACHE_BACKEND`) ou redémarrer Gunicorn |

### 7.2 Points critiques à surveiller

| Point | Criticité | Action |
|-------|-----------|--------|
| `DJANGO_DEBUG=False` en prod | 🔴 Critique | Vérifier après chaque déploiement |
| `DJANGO_SECRET_KEY` aléatoire | 🔴 Critique | Ne jamais committer la clé |
| `DJANGO_ALLOWED_HOSTS` complet | 🔴 Critique | Inclure tous les domaines/IP exposés |
| Sauvegarde BD quotidienne | 🔴 Critique | Cron + rétention |
| Permissions superuser | 🟡 Importante | Limiter aux administrateurs métier |
| Cache Redis en multi-worker | 🟡 Importante | Sinon caches désynchronisés entre workers Gunicorn |
| Timezone `Africa/Abidjan` | 🟢 Vérifier | Doit correspondre aux dates des Excel |
| Espace disque (logs + Excel) | 🟡 Importante | `logrotate`, purge des Excel anciens |

### 7.3 Commandes de maintenance

```bash
# État des migrations
python manage.py showmigrations

# Diagnostic Django
python manage.py check --deploy

# Shell Django (créer un superuser via script)
python manage.py shell -c "from django.contrib.auth import get_user_model; \
U=get_user_model(); U.objects.create_superuser('admin','admin@cgfgestion.com','MotDePasseFort')"

# Dump JSON (BD)
python manage.py dumpdata reporting > backup_reporting.json
python manage.py loaddata backup_reporting.json

# Recharger un import VL
python scripts/import_excel_data.py

# Vider le cache Django
python manage.py shell -c "from django.core.cache import cache; cache.clear()"
```

### 7.4 Logs à surveiller

- `logs/gunicorn-error.log` — erreurs applicatives
- `logs/gunicorn-access.log` — trafic HTTP
- `/var/log/nginx/error.log` — erreurs proxy
- `logs/import.log` — succès/échecs des imports cron

---

## 8. RÉSUMÉ — DÉPLOIEMENT EXPRESS

```bash
# 1. Cloner
git clone <url> /home/lookup/app && cd /home/lookup/app

# 2. venv + dépendances
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 3. Variables d'env (prod)
export DJANGO_SECRET_KEY="$(python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())')"
export DJANGO_DEBUG=False
export DJANGO_ALLOWED_HOSTS="lookup.cgfgestion.com"

# 4. BD + admin
python manage.py migrate
python manage.py createsuperuser

# 5. Données
python scripts/import_excel_data.py
python scripts/import_fiche_signaletique.py

# 6. Static
python manage.py collectstatic --noinput

# 7. Service
pip install gunicorn
sudo systemctl enable --now lookup

# 8. Nginx + HTTPS
sudo certbot --nginx -d lookup.cgfgestion.com
```

---

## 9. CONTACTS

- **Développeur** : Dylane NDOUDY
- **Email** : dndoudy@cgfgestion.com
- **Téléphone** : (+225) 01 70 63 09 60
- **Documentation projet** : [README.md](README.md), [docs/DESIGN.md](docs/DESIGN.md), [docs/CHARTE_GRAPHIQUE.md](docs/CHARTE_GRAPHIQUE.md)

---

**Document : Guide de déploiement — LOOK-UP PER APP**
**Version : 1.0**
**Dernière mise à jour : 29 avril 2026**
