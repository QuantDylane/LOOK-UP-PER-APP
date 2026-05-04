from django.contrib.auth.decorators import login_required, user_passes_test
from django.urls import path

from . import views
from . import views_export
from .decorators import admin_required, gestionnaire_required

app_name = 'reporting'


def _superuser_required(view_func):
    """Compat: ancien helper, conserve pour ne pas casser d'eventuelles refs."""
    return user_passes_test(
        lambda u: u.is_active and u.is_superuser,
        login_url='login',
    )(view_func)


L = login_required          # login requis
S = admin_required          # acces admin (superuser ou groupe Administrateurs)
G = gestionnaire_required   # acces gestion (Administrateurs ou Gestionnaires)


urlpatterns = [
    path('', L(views.accueil), name='accueil'),
    path('analyse-pee-per/', L(views.analyse_pee_per), name='analyse_pee_per'),
    path('analyse-client/', L(views.analyse_client), name='analyse_client'),
    path('metadonnees/', G(views.metadonnees), name='metadonnees'),
    path('controle/', G(views.controle), name='controle'),
    path('controle/sicav/<int:pk>/supprimer/', S(views.controle_supprimer_sicav), name='controle_supprimer_sicav'),
    path('controle/sicav/<int:pk>/vl-proche/', S(views.controle_appliquer_vl_proche), name='controle_appliquer_vl_proche'),
    path('controle/doublons/purger/', S(views.controle_purger_doublons), name='controle_purger_doublons'),
    path('a-propos/', L(views.a_propos), name='a_propos'),

    # Exportation (rapports PDF/HTML)
    path('export/', L(views_export.export_page), name='export'),
    path('export/rapport-plans/', L(views_export.export_rapport_plans), name='export_rapport_plans'),
    path('export/rapport-clients/', L(views_export.export_rapport_clients), name='export_rapport_clients'),
    path('export/rapport-plans/pdf/', L(views_export.export_rapport_plans_pdf), name='export_rapport_plans_pdf'),
    path('export/rapport-clients/pdf/', L(views_export.export_rapport_clients_pdf), name='export_rapport_clients_pdf'),

    # API Top/Flop performances
    path('api/top-flop-performances/', L(views.api_top_flop_performances), name='api_top_flop_performances'),

    # API Dashboard
    path('api/dashboard/encours/', L(views.api_dashboard_encours), name='api_dashboard_encours'),
    path('api/dashboard/vl-evolution/', L(views.api_vl_evolution), name='api_vl_evolution'),
    path('api/dashboard/fcp-calendar-performance/', L(views.api_fcp_calendar_performance), name='api_fcp_calendar_performance'),
    path('api/dashboard/heatmap-mensuel/', L(views.api_heatmap_mensuel), name='api_heatmap_mensuel'),

    # API Analyse portefeuille (plan)
    path('api/portefeuille/<str:nom_per_pee>/', L(views.api_portefeuille_detail), name='api_portefeuille_detail'),
    path('api/portefeuille/<str:nom_per_pee>/evolution/', L(views.api_portefeuille_evolution), name='api_portefeuille_evolution'),
    path('api/performance-globale/', L(views.api_performance_globale), name='api_performance_globale'),

    # API Analyse client
    path('api/client/<str:numero_compte>/', L(views.api_client_detail), name='api_client_detail'),
    path('api/client/<str:numero_compte>/historique/', L(views.api_client_historique), name='api_client_historique'),
    path('api/client/<str:numero_compte>/evolution/', L(views.api_client_evolution), name='api_client_evolution'),

    # Import/Export CSV - FCP (metadonnees : gestionnaires + admins)
    path('metadonnees/exporter-fcp/', G(views.exporter_fcp), name='exporter_fcp'),
    path('metadonnees/exporter-vl/', G(views.exporter_vl), name='exporter_vl'),
    path('metadonnees/importer-fcp/', G(views.importer_fcp), name='importer_fcp'),
    path('metadonnees/importer-vl/', G(views.importer_vl), name='importer_vl'),

    # Import Excel avec preview - FCP
    path('metadonnees/analyser-excel/', G(views.analyser_fichier_excel), name='analyser_excel'),
    path('metadonnees/executer-import-excel/', G(views.executer_import_excel), name='executer_import_excel'),

    # Modification FCP
    path('metadonnees/modifier-fcp/', G(views.modifier_fcp), name='modifier_fcp'),

    # Import/Export - SICAV (PEE/PER)
    path('metadonnees/exporter-sicav/', G(views.exporter_sicav), name='exporter_sicav'),
    path('metadonnees/analyser-sicav-excel/', G(views.analyser_sicav_excel), name='analyser_sicav_excel'),
    path('metadonnees/executer-import-sicav-excel/', G(views.executer_import_sicav_excel), name='executer_import_sicav_excel'),
    path('metadonnees/modele-sicav/', G(views.telecharger_modele_sicav), name='telecharger_modele_sicav'),
]
