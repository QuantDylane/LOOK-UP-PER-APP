"""
Moteur de suivi du Coût Moyen Pondéré (CMP) pour un portefeuille de parts
(FCP/OPCVM) dans un cadre PER / PEE / Plan d'Épargne.

Règles de gestion implémentées
------------------------------
1. Initialisation
   - Si aucune position : CMP = prix de la première transaction (VL),
     parts = parts achetées, total investi = montant investi.

2. Souscription (achat de parts)
   - parts_achetees        = montant_investi / VL
   - nouveau_total_parts   = parts_existantes + parts_achetees
   - nouveau_total_investi = ancien_total_investi + montant_investi
   - nouveau_CMP           = nouveau_total_investi / nouveau_total_parts

3. Rachat (vente de parts)
   - montant_rachat          = parts_vendues × VL
   - cout_historique         = parts_vendues × CMP
   - plus_value_realisee     = montant_rachat − cout_historique
   - nouveau_total_parts     = parts_existantes − parts_vendues
   - nouveau_total_investi   = ancien_total_investi − cout_historique
   - CMP inchangé

4. Valorisation
   - valeur_marche           = parts × VL
   - plus_value_latente      = valeur_marche − total_investi
   - performance             = (VL − CMP) / CMP

5. Arbitrage = rachat sur le support source + souscription sur le support cible
   (géré naturellement par la séquence des transactions).

6. Frais
   - Frais d'entrée : à déduire en amont du montant investi (hypothèse : la VL
     et la quantité transmises traduisent déjà le net de frais).
   - Frais de gestion : intégrés dans la VL, pas d'ajustement du CMP.

7. Cohérence
   - CMP > 0 ssi parts > 0
   - total_investi ≈ CMP × parts
   - Après rachat total : parts = 0, CMP = 0, total_investi = 0.
"""

from collections import defaultdict
from dataclasses import dataclass


# Tolérance de comparaison pour considérer un solde comme nul
_EPS = 1e-9


@dataclass
class PositionFCP:
    """État courant d'une position sur un FCP."""

    parts: float = 0.0
    cmp: float = 0.0
    total_investi: float = 0.0
    plus_value_realisee: float = 0.0  # Cumul des PV réalisées sur la position

    def valoriser(self, vl):
        """Retourne (valeur_marche, plus_value_latente, performance_pct)."""
        if vl is None or vl <= 0:
            return 0.0, -self.total_investi, None
        valeur = self.parts * vl
        pv_latente = valeur - self.total_investi
        perf = ((vl - self.cmp) / self.cmp * 100.0) if self.cmp > 0 else None
        return valeur, pv_latente, perf


@dataclass
class EvenementCMP:
    """Trace enrichie d'une transaction rejouée par le moteur."""

    date: object
    nom_fcp: str
    sens: str  # 'souscription' | 'rachat'
    quantite: float
    vl: float
    montant: float            # flux cash signé (>0 souscription, <0 rachat)
    cmp_apres: float
    parts_apres: float
    total_investi_apres: float
    plus_value_realisee: float  # non nulle uniquement sur rachat


def appliquer_souscription(pos: PositionFCP, quantite: float, vl: float) -> float:
    """Applique une souscription à une position. Retourne le montant investi."""
    if quantite is None or quantite <= 0 or vl is None or vl <= 0:
        return 0.0
    montant = quantite * vl
    nouveau_total_parts = pos.parts + quantite
    nouveau_total_investi = pos.total_investi + montant
    pos.parts = nouveau_total_parts
    pos.total_investi = nouveau_total_investi
    pos.cmp = nouveau_total_investi / nouveau_total_parts if nouveau_total_parts > 0 else 0.0
    return montant


def appliquer_rachat(pos: PositionFCP, quantite: float, vl: float):
    """Applique un rachat. CMP inchangé. Retourne (montant_rachat, plus_value_realisee)."""
    if quantite is None or quantite <= 0 or pos.parts <= 0:
        return 0.0, 0.0
    # Borne : on ne peut pas racheter plus que ce qui est détenu
    quantite = min(quantite, pos.parts)
    cout_historique = quantite * pos.cmp
    montant = quantite * vl if vl and vl > 0 else 0.0
    pv_realisee = (montant - cout_historique) if montant else 0.0

    pos.parts -= quantite
    pos.total_investi -= cout_historique
    pos.plus_value_realisee += pv_realisee

    # Cohérence : rachat total -> remise à zéro propre
    if pos.parts <= _EPS:
        pos.parts = 0.0
        pos.total_investi = 0.0
        pos.cmp = 0.0

    return montant, pv_realisee


def construire_ledger(transactions, vl_resolver, date_limite=None):
    """
    Rejoue les transactions chronologiquement (par FCP) et retourne:
      - positions : dict[nom_fcp] -> PositionFCP (état à date_limite)
      - evenements: liste d'EvenementCMP (trace enrichie)

    Paramètres
    ----------
    transactions : itérable d'objets avec ``date_transaction``, ``sens``,
                   ``nom_fcp``, ``quantite`` (et éventuellement ``id``).
    vl_resolver  : callable(nom_fcp, date) -> float ou None, renvoyant la VL
                   du FCP à la date considérée (ou la plus récente précédente).
    date_limite  : si fourni, les transactions postérieures sont ignorées.
    """
    txs = [
        t for t in transactions
        if t.nom_fcp and t.date_transaction
        and (date_limite is None or t.date_transaction <= date_limite)
    ]
    txs.sort(key=lambda t: (t.date_transaction, getattr(t, 'id', 0) or 0))

    positions = defaultdict(PositionFCP)
    evenements = []

    for t in txs:
        pos = positions[t.nom_fcp]
        quantite = float(t.quantite) if t.quantite else 0.0
        vl_raw = vl_resolver(t.nom_fcp, t.date_transaction)
        vl = float(vl_raw) if vl_raw else 0.0

        if t.sens == 'souscription':
            montant = appliquer_souscription(pos, quantite, vl)
            pv = 0.0
            flux = montant
        elif t.sens == 'rachat':
            montant, pv = appliquer_rachat(pos, quantite, vl)
            flux = -montant
        else:
            continue

        evenements.append(EvenementCMP(
            date=t.date_transaction,
            nom_fcp=t.nom_fcp,
            sens=t.sens,
            quantite=quantite,
            vl=vl,
            montant=flux,
            cmp_apres=pos.cmp,
            parts_apres=pos.parts,
            total_investi_apres=pos.total_investi,
            plus_value_realisee=pv,
        ))

    return positions, evenements


def etat_portefeuille(transactions, vl_resolver, date_valorisation):
    """
    Construit l'état du portefeuille à ``date_valorisation``.

    Retourne une liste de dicts par FCP contenant :
      nom_fcp, parts, cmp, total_investi, vl_courante, valeur_marche,
      plus_value_latente, plus_value_realisee, performance_pct
    """
    positions, _ = construire_ledger(transactions, vl_resolver, date_valorisation)
    result = []
    for nom_fcp, pos in positions.items():
        # On conserve les positions encore ouvertes OU celles qui ont généré une PV réalisée
        if pos.parts <= 0 and abs(pos.plus_value_realisee) < _EPS:
            continue
        vl_raw = vl_resolver(nom_fcp, date_valorisation)
        vl = float(vl_raw) if vl_raw else None
        valeur, pv_latente, perf = pos.valoriser(vl)
        result.append({
            'nom_fcp': nom_fcp,
            'parts': pos.parts,
            'cmp': pos.cmp,
            'total_investi': pos.total_investi,
            'vl_courante': vl,
            'valeur_marche': valeur,
            'plus_value_latente': pv_latente,
            'plus_value_realisee': pos.plus_value_realisee,
            'performance_pct': perf,
        })
    return result


def agreger_etat(etats):
    """Agrège une liste d'états FCP en totaux portefeuille."""
    total_parts = sum(e['parts'] for e in etats)
    total_investi = sum(e['total_investi'] for e in etats)
    valeur_marche = sum(e['valeur_marche'] for e in etats)
    pv_latente = sum(e['plus_value_latente'] for e in etats)
    pv_realisee = sum(e['plus_value_realisee'] for e in etats)
    return {
        'parts': total_parts,
        'total_investi': total_investi,
        'valeur_marche': valeur_marche,
        'plus_value_latente': pv_latente,
        'plus_value_realisee': pv_realisee,
    }
