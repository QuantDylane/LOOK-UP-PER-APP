from django import template

register = template.Library()


@register.filter(name='format_frais')
def format_frais(value):
    """
    Formate une valeur de frais pour l'affichage :
      - None / vide           → "-"  (pas de données)
      - "Néant" / "neant"    → "Néant"  (frais nuls)
      - Déjà formaté ("2.10%", "500 FCFA", "1% HT") → renvoyé tel quel
      - Fraction numérique ≤ 1  (ex: 0.021)  → "2.10%"
      - Nombre entier > 1   (ex: 500)        → "500 FCFA"
    """
    if value is None:
        return "-"

    s = str(value).strip()

    if not s:
        return "-"

    s_lower = s.lower().replace("é", "e").replace("è", "e")

    # Valeur explicitement nulle
    if s_lower in ("neant", "néant", "0%", "0.00%"):
        return "Néant"

    # Déjà formaté : contient %, FCFA, HT
    for marker in ("%", "FCFA", "HT", "fcfa", "ht"):
        if marker in s:
            return s

    # Essayer une conversion numérique
    try:
        v = float(s)
    except (ValueError, TypeError):
        # Chaîne non numérique inconnue — afficher telle quelle
        return s or "-"

    if v == 0:
        return "Néant"
    if 0 < v <= 1:
        # Fraction décimale → pourcentage
        return f"{v * 100:.2f}%"
    # Montant monétaire (ex : 500, 1500)
    return f"{v:.0f} FCFA"
