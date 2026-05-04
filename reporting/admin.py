from django.contrib import admin
from .models import Sicav, ValeurLiquidative, LoginAudit


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


@admin.register(LoginAudit)
class LoginAuditAdmin(admin.ModelAdmin):
    list_display = ['created_at', 'event', 'username', 'ip_address', 'user_agent']
    list_filter = ['event', 'created_at']
    search_fields = ['username', 'ip_address']
    date_hierarchy = 'created_at'
    ordering = ['-created_at']
    readonly_fields = [f.name for f in LoginAudit._meta.fields]

    def has_add_permission(self, request):
        return False

