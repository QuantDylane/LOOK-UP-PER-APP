from django.db import models


class Sicav(models.Model):
    """Table des transactions SICAV (Plan d'Épargne unifié)"""

    TYPE_CHOICES = [
        ('PLAN', "Plan d'Épargne"),
    ]

    SENS_CHOICES = [
        ('souscription', 'Souscription'),
        ('rachat', 'Rachat'),
    ]

    date_transaction = models.DateField(verbose_name="Date de transaction", null=True, blank=True)
    numero_compte = models.CharField(max_length=50, verbose_name="Numéro de compte", null=True, blank=True)
    type_plan = models.CharField(max_length=10, choices=TYPE_CHOICES, default='PLAN', verbose_name="Type de plan", null=True, blank=True)
    nom_per_pee = models.CharField(max_length=200, verbose_name="Nom du plan", null=True, blank=True)
    matricule_type = models.CharField(max_length=50, verbose_name="Matricule type", null=True, blank=True)
    nom_prenom = models.CharField(max_length=200, verbose_name="Nom & Prénom", null=True, blank=True)
    email = models.EmailField(verbose_name="Email", null=True, blank=True)
    sens = models.CharField(max_length=20, choices=SENS_CHOICES, verbose_name="Sens", null=True, blank=True)
    nom_fcp = models.CharField(max_length=200, verbose_name="Nom du FCP", null=True, blank=True)
    quantite = models.DecimalField(max_digits=18, decimal_places=4, verbose_name="Quantité", null=True, blank=True)
    cout_moyen_pondere = models.DecimalField(max_digits=18, decimal_places=4, verbose_name="Coût moyen pondéré", null=True, blank=True)

    class Meta:
        db_table = 'sicav'
        verbose_name = "Transaction SICAV"
        verbose_name_plural = "Transactions SICAV"
        ordering = ['-date_transaction']

    def __str__(self):
        return f"{self.nom_prenom} - {self.nom_fcp} ({self.date_transaction})"


class ValeurLiquidative(models.Model):
    """Table des valeurs liquidatives des FCP"""

    CATEGORIE_CHOICES = [
        ('prudent', 'Prudent'),
        ('equilibré', 'Équilibré'),
        ('dynamique', 'Dynamique'),
        ('diversifie', 'Diversifié'),
    ]

    TYPE_FOND_CHOICES = [
        ('actions', 'Actions'),
        ('obligataire', 'Obligataire'),
        ('diversifié', 'Diversifié'),
    ]

    date = models.DateField(verbose_name="Date", null=True, blank=True)
    nom_fcp = models.CharField(max_length=200, verbose_name="Nom du FCP", null=True, blank=True)
    valeur_liquidative = models.DecimalField(max_digits=18, decimal_places=4, verbose_name="Valeur liquidative", null=True, blank=True)
    est_fcp_islamique = models.BooleanField(default=False, verbose_name="Est FCP islamique")
    echelle_risque = models.IntegerField(verbose_name="Échelle de risque (1-7)", null=True, blank=True)
    categorie_fond = models.CharField(max_length=50, choices=CATEGORIE_CHOICES, verbose_name="Catégorie de fond", null=True, blank=True)
    type_fond = models.CharField(max_length=20, choices=TYPE_FOND_CHOICES, verbose_name="Type de fond", null=True, blank=True)
    horizon_investissement = models.IntegerField(verbose_name="Horizon d'investissement (années)", null=True, blank=True)
    benchmark_obligataire = models.CharField(max_length=200, verbose_name="Benchmark Obligataire", null=True, blank=True)
    benchmark_brvmc = models.CharField(max_length=200, verbose_name="Benchmark BRVMC", null=True, blank=True)
    date_creation = models.DateField(verbose_name="Date de création", null=True, blank=True)
    depositaire = models.CharField(max_length=200, verbose_name="Dépositaire", null=True, blank=True)
    frais_gestion_ttc = models.CharField(max_length=100, verbose_name="Frais de gestion (TTC de l'actif net / an)", null=True, blank=True)
    frais_entree_ttc = models.CharField(max_length=100, verbose_name="Frais d'entrée TTC", null=True, blank=True)
    frais_sortie_ttc = models.CharField(max_length=100, verbose_name="Frais de sortie TTC", null=True, blank=True)

    class Meta:
        db_table = 'valeurs_liquidatives'
        verbose_name = "Valeur liquidative"
        verbose_name_plural = "Valeurs liquidatives"
        ordering = ['-date']

    def __str__(self):
        return f"{self.nom_fcp} - {self.valeur_liquidative} ({self.date})"
