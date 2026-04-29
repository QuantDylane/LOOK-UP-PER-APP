from django.db import migrations, models


def unify_type_plan(apps, schema_editor):
    """Remplace tous les PEE/PER existants par la valeur unifiée PLAN."""
    Sicav = apps.get_model('reporting', 'Sicav')
    Sicav.objects.all().update(type_plan='PLAN')


def reverse_noop(apps, schema_editor):
    """Pas de rollback des valeurs — l'information PEE/PER n'est plus distinguée."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('reporting', '0005_sicav_nom_per_pee'),
    ]

    operations = [
        migrations.AlterField(
            model_name='sicav',
            name='type_plan',
            field=models.CharField(
                blank=True,
                choices=[('PLAN', "Plan d'Épargne")],
                default='PLAN',
                max_length=10,
                null=True,
                verbose_name='Type de plan',
            ),
        ),
        migrations.AlterField(
            model_name='sicav',
            name='nom_per_pee',
            field=models.CharField(
                blank=True,
                max_length=200,
                null=True,
                verbose_name='Nom du plan',
            ),
        ),
        migrations.RunPython(unify_type_plan, reverse_noop),
    ]
