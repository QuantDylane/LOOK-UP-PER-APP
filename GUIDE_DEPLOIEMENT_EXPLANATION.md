# 📋 GUIDE COMPLET DE DÉPLOIEMENT - EXPLICATION TECHNIQUE
## Application de Suivi de Collecte CGF Gestion

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
C'est une **application web Django** développée pour CGF Gestion qui permet aux commerciaux de gérer leurs clients, prospects et collectes de manière centralisée. Avant, chacun utilisait des fichiers Excel dispersés.

### Objectif métier
- ✅ Centraliser tous les données clients et prospects
- ✅ Suivre les collectes en temps réel
- ✅ Générer des rapports automatiques (PDF, PowerPoint, Excel)
- ✅ Tracer toutes les modifications (audit trail)
- ✅ Gérer les tickets de support

### Technologie utilisée
- **Framework** : Django 4.2+ (Python)
- **Base de données** : SQLite (développement) ou PostgreSQL (production)
- **Serveur web** : Gunicorn + Nginx/Apache
- **Frontend** : HTML/CSS/JavaScript + Bootstrap 5
- **Fichiers statiques** : Whitenoise pour servir les CSS/JS/images

### Durée d'utilisation
L'application est **en production depuis janvier 2026**.

---

## 2. ARCHITECTURE ET STRUCTURE DU DOSSIER {#architecture}

Voici l'arborescence complète et ce que chaque dossier contient :

```
Application suivi collecte CGF gestion/
│
├── 📄 manage.py
│   └── Fichier de commande principal Django
│       (python manage.py runserver, migrate, etc.)
│
├── 📄 db.sqlite3
│   └── Base de données SQLite (développement)
│       ⚠️ Ne pas copier en production (PostgreSQL à la place)
│
├── 📄 requirements.txt
│   └── Liste EXACTE de toutes les dépendances Python
│       (Django, Pillow, reportlab, etc.)
│       → À utiliser pour : pip install -r requirements.txt
│
├── 📁 collecte_project/ [Configuration du projet]
│   ├── __init__.py
│   ├── settings.py
│   │   ├── Configuration de Django (base de données, apps, middleware)
│   │   ├── Chemins des fichiers statiques et templates
│   │   ├── Paramètres de sécurité (SECRET_KEY, ALLOWED_HOSTS, DEBUG)
│   │   └── ⚠️ À modifier obligatoirement pour la production
│   │
│   ├── urls.py
│   │   └── Routeur principal : redirige vers collecte.urls
│   │
│   ├── wsgi.py
│   │   └── Point d'entrée pour Gunicorn/Apache (production)
│   │
│   └── __pycache__/ [Fichiers compilés Python - ignorer]
│
├── 📁 collecte/ [Application métier - CŒUR DE L'APP]
│   │
│   ├── models.py [TRÈS IMPORTANT]
│   │   └── Définit la structure des données :
│   │       • Commercial (équipe commerciale)
│   │       • Client (données clients/prospects)
│   │       • Collecte (montants collectés)
│   │       • Objectif (objectifs mensuels/institutionnels)
│   │       • ValidationAction (workflow validation)
│   │       • TicketSupport (gestion des tickets)
│   │       • Notification, DemandeModification, etc.
│   │       → À respecter : ces tables sont en base de données
│   │
│   ├── views.py [TRÈS IMPORTANT]
│   │   └── Logique métier : traite les requêtes HTTP
│   │       • Authentification et permissions
│   │       • Affichage des listes (clients, collectes)
│   │       • Création/modification/suppression
│   │       • Génération de rapports (PDF, PowerPoint, Excel)
│   │       • Exports et imports de données
│   │
│   ├── urls.py
│   │   └── Routes spécifiques à l'app "collecte"
│   │       Exemple: /clients/, /collectes/, /rapports/, etc.
│   │
│   ├── forms.py
│   │   └── Formulaires Django (validation, rendu HTML)
│   │       • ClientForm (création/édition clients)
│   │       • CollecteForm (saisie des collectes)
│   │       • etc.
│   │
│   ├── admin.py
│   │   └── Interface Django Admin pour les super-utilisateurs
│   │       (gestion directe des données en base)
│   │
│   ├── apps.py
│   │   └── Configuration de l'app (métadonnées)
│   │
│   ├── context_processors.py
│   │   └── Variables globales disponibles dans TOUS les templates
│   │       (notifications, utilisateur connecté, etc.)
│   │
│   ├── tests.py
│   │   └── Tests unitaires de l'application
│   │
│   ├── 📁 migrations/ [CRITIQUE - Historique de schéma BD]
│   │   ├── __init__.py
│   │   ├── 0001_initial.py
│   │   ├── 0002_historiquemodification.py
│   │   ├── 0003_validation_action.py
│   │   ├── ... (0004 à 0016)
│   │   └── ⚠️ CHAQUE fichier = modification du schéma BD
│   │       Ordre d'exécution : 0001 → 0002 → ... → 0016
│   │       → À lancer avec : python manage.py migrate
│   │
│   ├── 📁 management/
│   │   └── commands/
│   │       └── populate_db.py
│   │           Commande personnalisée pour peupler la BD
│   │           Usage: python manage.py populate_db
│   │
│   ├── 📁 templatetags/
│   │   └── collecte_tags.py
│   │       Filtres/tags Jinja2 custom pour les templates
│   │       (formatage personnalisé, calculs, etc.)
│   │
│   └── __pycache__/ [Fichiers compilés Python - ignorer]
│
├── 📁 templates/ [Interface utilisateur - HTML]
│   ├── base.html
│   │   └── Template parent (header, nav, footer)
│   │       Tous les autres templates hérient de celui-ci
│   │
│   ├── accueil.html
│   │   └── Page d'accueil / dashboard principal
│   │
│   ├── login.html
│   │   └── Page de connexion
│   │
│   ├── suivi_clients.html
│   │   └── Liste des clients/prospects
│   │
│   ├── client_form.html, client_detail.html
│   │   └── Création/édition et détails d'un client
│   │
│   ├── suivi_collectes.html
│   │   └── Historique des collectes
│   │
│   ├── validation_actions.html
│   │   └── Workflow de validation des actions commerciales
│   │
│   ├── controle.html
│   │   └── Module d'administration :
│   │       • Statistiques
│   │       • Historique des modifications
│   │       • Alertes
│   │       • Sauvegardes (backup)
│   │       • Sessions actives
│   │       • Gestion d'activité
│   │
│   ├── gestion_objectifs.html
│   │   └── Suivi des objectifs (mensuels/institutionnels)
│   │
│   ├── gestion_support.html
│   │   └── Gestion des tickets support
│   │
│   ├── exportation.html, importation.html
│   │   └── Export/Import de données (CSV, Excel)
│   │
│   └── [Autres templates : notifications, rapports, etc.]
│
├── 📁 static/ [Ressources côté client]
│   ├── css/
│   │   └── style.css
│   │       Styles personnalisés (en plus de Bootstrap 5)
│   │
│   ├── js/
│   │   └── main.js
│   │       JavaScript pour interactivité (ajax, validation côté client)
│   │
│   └── images/
│       └── Logos, icônes, etc.
│
├── 📁 media/ [Fichiers uploadés à runtime]
│   └── photos_profil/
│       └── Photos de profil des commerciaux
│           ⚠️ Géré par Django ImageField
│
└── 📁 documentation/
    ├── FICHE_PROJET_SUIVI_COLLECTE.md
    │   └── Description métier du projet
    │
    ├── DESCRIPTIF_TECHNIQUE_FONCTIONNEL.md
    │   └── Détails techniques et spécifications fonctionnelles
    │
    ├── GUIDE_UTILISATEUR_COMPLET.md
    │   └── Manuel utilisateur final
    │
    ├── FICHE_PROJET_DEPLOIEMENT.md
    │   └── Notes sur le déploiement
    │
    ├── UTILISATEURS.md
    │   └── Liste des utilisateurs et rôles
    │
    └── RESUME_DEMANDE_IT.md
        └── Résumé technique pour l'IT
```

---

## 3. COMPOSANTS TECHNIQUES {#composants}

### 3.1 Stack technique complète

| Composant | Version | Rôle |
|-----------|---------|------|
| **Python** | 3.11+ | Langage principal |
| **Django** | 4.2+ | Framework web |
| **PostgreSQL** | 13+ | Base de données (production) |
| **SQLite** | Builtin | Base de données (développement) |
| **Gunicorn** | 21.0+ | Serveur WSGI (production) |
| **Whitenoise** | 6.6+ | Serveur de fichiers statiques |
| **Pillow** | 10.0+ | Traitement d'images |
| **reportlab** | 4.0+ | Génération de PDF |
| **python-pptx** | 0.6+ | Génération de PowerPoint |
| **openpyxl** | 3.1+ | Traitement de fichiers Excel |
| **crispy-forms** | 2.1+ | Rendu de formulaires Bootstrap |
| **markdown** | 3.5+ | Conversion Markdown → HTML |
| **python-dotenv** | 1.0+ | Variables d'environnement |

### 3.2 Modèles de données (tables principales)

```
Commercial
├── user (FK User) - Utilisateur Django lié
├── code (CharField) - Code unique (COM_A, COM_B, etc.)
├── telephone
├── photo (ImageField)
└── actif (Boolean)

Client
├── commercial (FK) - Commercial responsable
├── nom, prenom
├── type_client (PEE/PER, Particulier, Institutionnel)
├── produits_souscrits (JSON) - [FCP, Gestion Libre, etc.]
├── email, telephone
├── stade (Prospect, Client)
├── date_dernier_contact
├── date_prochaine_action
├── numero_compte (Unique)
└── compte_valide (Boolean)

Collecte
├── client (FK)
├── montant
├── devise
├── date_collecte
├── montant_verse
├── produit
└── commentaire

Objectif
├── mois, année
├── type_objectif (Mensuel, Institutionnel)
├── commercial (FK optionnel)
├── montant_objectif
└── description

ValidationAction
├── action_commerciale (FK)
├── statut (Proposée, Validée, Rejetée, Exécutée)
├── dates (proposition, validation, execution)
└── dépôt (FK optionnel)

TicketSupport
├── utilisateur (FK User)
├── priorite (Basse, Normale, Haute)
├── statut (Ouvert, En cours, Fermé)
├── titre, description
└── historique des réponses
```

### 3.3 Flux principaux

**Flux 1 : Authentification**
```
Client → Login.html → views.py (login) → BD (User table) → Dashboard
```

**Flux 2 : Gestion des clients**
```
Commercial → suivi_clients.html → views.py (list) → BD (Client table) 
→ Détail → Édition → views.py (update) → BD → Succès
```

**Flux 3 : Enregistrement collecte**
```
Commercial → suivi_collectes.html → Saisir montant → views.py
→ BD (Collecte insert) → Notification auto (context_processors.py)
```

**Flux 4 : Rapports**
```
User → controle_statistiques.html → Demander rapport
→ views.py (generate_report) → python-pptx/reportlab 
→ Fichier PDF/PPT/CSV → Téléchargement
```

---

## 4. PRÉREQUIS DE DÉPLOIEMENT {#prerequis}

### 4.1 Serveur (recommandations)

- **OS** : Linux (Ubuntu 20.04+ ou CentOS 8+) ou Windows Server
- **CPU** : Minimum 2 cores, idéalement 4+ pour production
- **RAM** : Minimum 2 GB, idéalement 4+ GB
- **Disque** : 20 GB minimum (logs, BD, médias uploadés)
- **Accès internet** : Pour pip install et dépendances

### 4.2 Logiciels pré-installés (essentiels)

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install python3.11 python3-pip python3-venv
sudo apt install postgresql postgresql-contrib  # Si PostgreSQL
sudo apt install nginx                           # Si Nginx
sudo apt install git                            # Optionnel, pour les mises à jour

# Windows Server
# Télécharger Python depuis python.org (3.11+)
# Télécharger PostgreSQL depuis postgresql.org (optionnel)
# Télécharger nginx depuis nginx.org (optionnel)
```

### 4.3 Fichiers à préparer

**Avant le déploiement, vous aurez besoin de :**
1. ✅ Le dossier complet du projet (cloner ou copier)
2. ✅ Un fichier `.env` (variables d'environnement)
3. ✅ Les certificats SSL (si HTTPS)
4. ✅ Une base de données PostgreSQL configurée (optionnel, mais recommandé)
5. ✅ Un plan de backup de la base de données

---

## 5. INSTRUCTIONS DE DÉPLOIEMENT {#deploiement}

### ÉTAPE 1 : Préparation du serveur

#### Sur Linux (Ubuntu 20.04+)

```bash
# 1. Créer un utilisateur dédié à l'app
sudo useradd -m -d /home/collecte collecte
sudo usermod -aG sudo collecte
su - collecte

# 2. Cloner ou copier le projet
cd /home/collecte
# Méthode 1 : Git
git clone <url_repo> app
# OU Méthode 2 : Copier le dossier
cp -r /chemin/vers/projet app

# 3. Se placer dans le dossier
cd /home/collecte/app
```

#### Sur Windows Server

```batch
REM 1. Créer un dossier pour l'app
mkdir C:\Applications\collecte
cd C:\Applications\collecte

REM 2. Copier le projet
xcopy "chemin\source" . /E /I

REM 3. Ouvrir PowerShell en tant qu'admin
powershell -ExecutionPolicy Bypass
```

### ÉTAPE 2 : Configuration de l'environnement Python

```bash
# 1. Créer un virtual environment
python3.11 -m venv venv

# 2. L'activer
# Sur Linux/Mac
source venv/bin/activate
# Sur Windows
.\venv\Scripts\activate

# 3. Mettre à jour pip
pip install --upgrade pip

# 4. Installer les dépendances
pip install -r requirements.txt

# 5. Vérifier l'installation
python -c "import django; print(django.VERSION)"
```

### ÉTAPE 3 : Configuration du fichier settings.py

**⚠️ CRITIQUEMENT IMPORTANT ⚠️**

Éditer `collecte_project/settings.py` :

```python
# 1. Sécurité
SECRET_KEY = 'générer une nouvelle clé secrète'
# Générer une clé : python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"

DEBUG = False  # ⚠️ JAMAIS True en production

ALLOWED_HOSTS = ['votre-domaine.com', 'www.votre-domaine.com', 'votre-ip-serveur']

# 2. Base de données
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',  # Pas SQLite !
        'NAME': 'collecte_db',
        'USER': 'postgres',
        'PASSWORD': 'votre_mot_de_passe',
        'HOST': 'localhost',
        'PORT': '5432',
    }
}

# 3. Dossiers statiques (pour Whitenoise)
STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# 4. Fichiers uploadés (photos, etc.)
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# 5. Variables d'environnement
import os
from dotenv import load_dotenv
load_dotenv()
SECRET_KEY = os.getenv('SECRET_KEY')
ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', '').split(',')
```

### ÉTAPE 4 : Configuration de la base de données

#### Avec PostgreSQL

```bash
# 1. Se connecter à PostgreSQL
sudo -u postgres psql

# 2. Créer la base de données et l'utilisateur
CREATE USER collecte_user WITH PASSWORD 'votre_mot_de_passe';
CREATE DATABASE collecte_db OWNER collecte_user;
ALTER ROLE collecte_user SET client_encoding TO 'utf8';
ALTER ROLE collecte_user SET default_transaction_isolation TO 'read committed';
ALTER ROLE collecte_user SET default_transaction_deferrable TO on;
ALTER ROLE collecte_user SET timezone TO 'UTC';
GRANT ALL PRIVILEGES ON DATABASE collecte_db TO collecte_user;
\q

# 3. Retourner dans le projet
cd /home/collecte/app
source venv/bin/activate

# 4. Appliquer les migrations
python manage.py migrate

# 5. Créer un superutilisateur
python manage.py createsuperuser
# Suivre les prompts : username, email, password

# 6. (Optionnel) Peupler la BD avec des données de test
python manage.py populate_db
```

### ÉTAPE 5 : Préparer les fichiers statiques

```bash
# Se placer dans le projet
cd /home/collecte/app
source venv/bin/activate

# Collecter les fichiers statiques (CSS, JS, images)
python manage.py collectstatic --noinput

# Cela crée un dossier "staticfiles/" avec tous les assets
```

### ÉTAPE 6 : Configuration de Gunicorn

Créer un fichier `gunicorn_config.py` :

```python
import multiprocessing

bind = "127.0.0.1:8000"  # Écoute seulement en local
workers = multiprocessing.cpu_count() * 2 + 1  # Nombre de workers
worker_class = "sync"
timeout = 120
access_log_format = '%({X-Forwarded-For}i)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s'
error_logfile = '/home/collecte/app/logs/gunicorn-error.log'
access_logfile = '/home/collecte/app/logs/gunicorn-access.log'
```

### ÉTAPE 7 : Configuration du serveur web (Nginx)

Créer `/etc/nginx/sites-available/collecte` :

```nginx
upstream django {
    server 127.0.0.1:8000;
}

server {
    listen 80;
    server_name votre-domaine.com www.votre-domaine.com;
    charset utf-8;
    client_max_body_size 20M;

    # Logs
    access_log /home/collecte/app/logs/nginx-access.log;
    error_log /home/collecte/app/logs/nginx-error.log;

    # Fichiers statiques
    location /static/ {
        alias /home/collecte/app/staticfiles/;
    }

    # Fichiers uploadés
    location /media/ {
        alias /home/collecte/app/media/;
    }

    # Proxy vers Gunicorn
    location / {
        proxy_pass http://django;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Activer le site :

```bash
sudo ln -s /etc/nginx/sites-available/collecte /etc/nginx/sites-enabled/
sudo nginx -t  # Vérifier la syntaxe
sudo systemctl restart nginx
```

### ÉTAPE 8 : Service Systemd (pour démarrage automatique)

Créer `/etc/systemd/system/collecte.service` :

```ini
[Unit]
Description=Django Collecte Application
After=network.target

[Service]
User=collecte
Group=www-data
WorkingDirectory=/home/collecte/app
ExecStart=/home/collecte/app/venv/bin/gunicorn \
    --config gunicorn_config.py \
    collecte_project.wsgi:application
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Démarrer le service :

```bash
sudo systemctl daemon-reload
sudo systemctl start collecte
sudo systemctl enable collecte
sudo systemctl status collecte
```

### ÉTAPE 9 : SSL/HTTPS (optionnel mais recommandé)

Avec Let's Encrypt et Certbot :

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot certonly -a nginx -d votre-domaine.com -d www.votre-domaine.com

# Mettre à jour nginx.conf avec les chemins des certificats
sudo systemctl restart nginx
```

---

## 6. CONFIGURATION POST-DÉPLOIEMENT {#configuration}

### 6.1 Accéder à l'application

- **URL publique** : https://votre-domaine.com
- **Admin Django** : https://votre-domaine.com/admin
- **Identifiants** : Ceux créés avec `createsuperuser`

### 6.2 Configuration initiale (dans Django Admin)

1. Se connecter en tant que superutilisateur
2. Créer les groupes de permissions :
   - **Admin** (accès complet)
   - **Directeur** (rapports + statistiques)
   - **Commercial** (gestion de ses clients)
   - **Support** (gestion des tickets)

3. Créer les utilisateurs et les assigner aux groupes

4. Créer les Commerciaux (via Admin ou model) :
   ```
   Admin → Commercials → Ajouter
   - User : Sélectionner l'utilisateur
   - Code : COM_A, COM_B, etc.
   - Téléphone, Photo
   ```

### 6.3 Paramètres applicatifs

Dans l'interface Admin Django (`/admin/`) :

- **Notifications** : Configurer les seuils d'alerte
- **Objectifs** : Définir les objectifs mensuels par commercial
- **Produits** : Ajouter/modifier les produits (FCP, Gestion Libre)

### 6.4 Sauvegardes

Créer un script de backup automatique (`backup.sh`) :

```bash
#!/bin/bash

BACKUP_DIR="/home/collecte/backups"
DATE=$(date +%Y%m%d_%H%M%S)

# Backup BD PostgreSQL
pg_dump -U collecte_user collecte_db | gzip > "$BACKUP_DIR/db_$DATE.sql.gz"

# Backup du dossier media
tar -czf "$BACKUP_DIR/media_$DATE.tar.gz" /home/collecte/app/media/

# Garder que les 7 derniers backups
find $BACKUP_DIR -name "db_*.sql.gz" -mtime +7 -delete
find $BACKUP_DIR -name "media_*.tar.gz" -mtime +7 -delete

# Log
echo "Backup $DATE - OK" >> "$BACKUP_DIR/backup.log"
```

L'exécuter via cron (tous les jours à 2h du matin) :

```bash
crontab -e
# Ajouter : 0 2 * * * /home/collecte/backup.sh
```

---

## 7. DÉPANNAGE ET POINTS CRITIQUES {#depannage}

### 7.1 Erreurs courantes et solutions

#### ❌ "ModuleNotFoundError: No module named 'django'"
**Cause** : Virtual environment pas activé ou dépendances non installées
**Solution** :
```bash
source venv/bin/activate
pip install -r requirements.txt
```

#### ❌ "ProgrammingError: relation 'collecte_*' does not exist"
**Cause** : Migrations non appliquées
**Solution** :
```bash
python manage.py migrate
```

#### ❌ "OperationalError: FATAL: Ident authentication failed for user 'postgres'"
**Cause** : Identifiants PostgreSQL incorrects
**Solution** : Vérifier settings.py et les identifiants dans createuser PostgreSQL

#### ❌ "DisallowedHost at / Invalid HTTP_HOST header"
**Cause** : Le domaine accédé n'est pas dans ALLOWED_HOSTS
**Solution** : Éditer settings.py et ajouter le domaine/IP

#### ❌ "StaticFilesNotFoundError: CSS/JS non chargés"
**Cause** : Fichiers statiques non collectés
**Solution** :
```bash
python manage.py collectstatic --noinput
```

#### ❌ "504 Gateway Timeout"
**Cause** : Gunicorn ne répond pas ou trop lent
**Solution** :
```bash
# Vérifier l'état du service
sudo systemctl status collecte
# Vérifier les logs
tail -f /home/collecte/app/logs/gunicorn-error.log
# Redémarrer
sudo systemctl restart collecte
```

### 7.2 Points critiques à surveiller

| Point | Criticité | Action |
|-------|-----------|--------|
| **Sauvegardes BD** | 🔴 Critique | Automatiser quotidiennement |
| **Espace disque** | 🔴 Critique | Monitorer, nettoyer logs anciens |
| **Permissions fichiers** | 🟡 Importante | media/ et staticfiles/ doivent être writeable |
| **SECRET_KEY** | 🔴 Critique | À générer aléatoirement, ne jamais commiter |
| **DEBUG=False** | 🔴 Critique | JAMAIS True en production |
| **ALLOWED_HOSTS** | 🔴 Critique | À compléter avec tous les domaines/IPs valides |
| **Certificats SSL** | 🟡 Importante | Vérifier l'expiration (Let's Encrypt à renouveler) |
| **Logs applicatifs** | 🟡 Importante | Monitorer les erreurs dans gunicorn-error.log |

### 7.3 Commandes essentielles de maintenance

```bash
# Vérifier la santé de l'application
python manage.py check

# Voir les migrations non appliquées
python manage.py showmigrations

# Créer un nouvel utilisateur en ligne de commande
python manage.py shell
>>> from django.contrib.auth import get_user_model
>>> User = get_user_model()
>>> User.objects.create_user('username', 'email@example.com', 'password')

# Dumper la BD (backup manuel)
python manage.py dumpdata > backup.json

# Restaurer depuis un dump
python manage.py loaddata backup.json

# Supprimer tous les objets d'une table (DANGEREUX!)
python manage.py shell
>>> from collecte.models import Client
>>> Client.objects.all().delete()

# Afficher les requêtes SQL exécutées (debug)
python manage.py shell
>>> from django.db import connection
>>> from django.test.utils import CaptureQueriesContext
>>> with CaptureQueriesContext(connection) as context:
>>>     # Votre code
>>>     pass
>>> for query in context.captured_queries:
>>>     print(query['sql'])
```

### 7.4 Monitoring recommandé

Installer des outils pour surveiller :

```bash
# Monitoring système
sudo apt install htop  # CPU/RAM
sudo apt install nethogs  # Réseau
sudo apt install iotop  # Disque

# Logs centralisés
sudo apt install logrotate  # Rotation des logs

# Alertes
# Configuration pour envoyer des emails en cas d'erreur Django
# dans settings.py :
ADMINS = [('Admin', 'admin@example.com')]
MANAGERS = ADMINS
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = 'votre-email@gmail.com'
EMAIL_HOST_PASSWORD = 'votre-mot-de-passe-app'
```

---

## 8. RÉSUMÉ POUR DÉPLOIEMENT RAPIDE

**Si vous êtes pressé, voici les 10 étapes essentielles :**

```bash
# 1. Clone/copie du projet
git clone <url> /home/collecte/app
cd /home/collecte/app

# 2. Virtual environment
python3.11 -m venv venv && source venv/bin/activate

# 3. Dépendances
pip install -r requirements.txt

# 4. Configuration (settings.py)
# ✏️ Éditer : SECRET_KEY, DEBUG=False, ALLOWED_HOSTS, DATABASES

# 5. Base de données
python manage.py migrate
python manage.py createsuperuser

# 6. Fichiers statiques
python manage.py collectstatic --noinput

# 7. Test local
python manage.py runserver 0.0.0.0:8000

# 8. Installation Gunicorn + Nginx
pip install gunicorn
# ✏️ Créer gunicorn_config.py et nginx.conf

# 9. Service systemd
# ✏️ Créer /etc/systemd/system/collecte.service
sudo systemctl start collecte

# 10. Vérification
curl http://localhost/
# Devrait fonctionner ✅
```

---

## 9. SUPPORT ET CONTACTS

- **Développeur** : Dylane NDOUDY
- **Email** : dndoudy@cgfgestion.com
- **Téléphone** : (+225) 01 70 63 09 60
- **Documentation** : Voir dossier `/documentation/`

---

**Document mis à jour : 4 février 2026**
**Version : 1.0**
**Déploiement production : Recommandé pour équipes IT avec expérience Django**
