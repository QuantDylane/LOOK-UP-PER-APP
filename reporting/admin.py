from django.contrib import admin
from .models import Sicav, ValeurLiquidative


@admin.register(Sicav)
class SicavAdmin(admin.ModelAdmin):
    list_display = ['date_transaction', 'nom_prenom', 'type_plan', 'nom_fcp', 'sens', 'quantite', 'cout_moyen_pondere']
    list_filter = ['type_plan', 'sens', 'nom_fcp', 'date_transaction']
    search_fields = ['nom_prenom', 'email', 'numero_compte', 'nom_fcp']
    date_hierarchy = 'date_transaction'
    ordering = ['-date_transaction']


@admin.register(ValeurLiquidative)
class ValeurLiquidativeAdmin(admin.ModelAdmin):
    list_display = ['date', 'nom_fcp', 'valeur_liquidative', 'est_fcp_islamique', 'categorie_fond', 'type_fond']
    list_filter = ['est_fcp_islamique', 'categorie_fond', 'type_fond', 'depositaire']
    search_fields = ['nom_fcp', 'depositaire']
    date_hierarchy = 'date'
    ordering = ['-date']
