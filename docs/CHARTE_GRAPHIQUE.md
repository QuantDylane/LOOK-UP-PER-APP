# Charte graphique — PER/PEE Reporting

**Version** : 2.0 — alignée sur le logo CGF officiel
**Dernière mise à jour** : 24 avril 2026
**Périmètre** : toutes les pages et composants visuels de l'application.

## Identité CGF — couleurs officielles (extraites du logo `cgf.png`)

| Rôle              | Hex       | RGB             | Usage                                    |
|-------------------|-----------|-----------------|------------------------------------------|
| **Bleu CGF**      | `#004C90` | (0, 76, 144)    | Couleur primaire, accents, boutons       |
| **Gris CGF**      | `#495B5B` | (73, 91, 91)    | Texte secondaire, neutres                |
| **Bleu CGF foncé**| `#003366` | (0, 51, 102)    | Dégradés, hover, fond sidebar            |

Ces deux couleurs (+ leur déclinaison foncée) sont la référence absolue.
Toutes les autres teintes du design system en sont dérivées.

Cette charte fixe les règles visuelles à respecter sur l'ensemble des écrans.
Toute nouvelle page ou modification de page doit s'y conformer.

---

## 1. Principes directeurs

1. **Sobriété financière** — style « executive », inspiré d'un rapport de gestion.
2. **Lisibilité avant tout** — contraste fort, typographie claire, peu de couleurs.
3. **Cohérence totale** — même palette, même typographie, mêmes composants partout.
4. **Pas de couleurs vives** — ni jaune/or/gold, ni orange, ni violet/rose.
   Seule exception : les **valeurs en pourcentage** peuvent utiliser
   vert (positif) / rouge (négatif) — voir section 3.
5. **Blanc comme fond de référence**, bleus pour les accents, gris pour le texte secondaire.

---

## 2. Typographie

### Police unique
**Cambria** (fallback : `Georgia`, `Times New Roman`, `serif`).

Aucune autre famille n'est autorisée (pas de sans-serif ni de Google Fonts).
Règle appliquée automatiquement via `static/css/style.css` à : `body`, titres,
inputs, boutons, tables, navbar, badges, code.

### Hiérarchie

| Élément        | Taille   | Poids | Couleur                |
|----------------|----------|-------|------------------------|
| h1 / page-title| 1.75 rem | 700   | `--primary-color`      |
| h2             | 1.5 rem  | 700   | `--primary-color`      |
| h3 / card h5   | 1.1 rem  | 600   | `--primary-color`      |
| Corps          | 1 rem    | 400   | `--text-primary`       |
| Muted          | 0.875 rem| 400   | `--text-muted`         |
| Label KPI      | 0.75 rem | 600   | `--text-muted` / upper |

---

## 3. Palette de couleurs

**Règle absolue** : toutes les couleurs utilisées doivent provenir des variables CSS
définies dans `static/css/style.css` ( `:root` ). Aucune couleur en dur dans les templates.

### Bleus (identité principale — issus du bleu CGF `#004C90`)

| Token        | Hex       | Usage                                             |
|--------------|-----------|---------------------------------------------------|
| `--blue-900` | `#003366` | Fond sidebar, dégradés foncés                     |
| `--blue-800` | `#003D73` | Dégradés                                          |
| `--blue-700` | `#004C90` | **Bleu CGF officiel** — accent principal          |
| `--blue-600` | `#165FA3` | Info, liens                                       |
| `--blue-500` | `#3A7AB8` | Séries de graphiques                              |
| `--blue-400` | `#6795C9` | Séries de graphiques                              |
| `--blue-300` | `#99B6DB` | Séries, heatmap faible positif                    |
| `--blue-200` | `#C9D8EC` | Bordures, fonds décoratifs                        |
| `--blue-100` | `#E5EFF8` | Fonds d'alertes info/success                      |
| `--blue-050` | `#F2F7FB` | Fond de section très clair                        |

### Gris (texte & neutres — issus du gris CGF `#495B5B`)

| Token        | Hex       | Usage                                           |
|--------------|-----------|-------------------------------------------------|
| `--gray-900` | `#2B3636` | Texte principal (alias `--text-primary`)        |
| `--gray-800` | `#384747` | Texte fort, indicateurs négatifs (heatmap)      |
| `--gray-700` | `#495B5B` | **Gris CGF officiel** — texte secondaire        |
| `--gray-600` | `#5D6E6E` | Texte tertiaire, warning                        |
| `--gray-500` | `#7E8C8C` | Texte muted                                     |
| `--gray-400` | `#9BA7A7` | Icônes discrètes                                |
| `--gray-300` | `#C7CECE` | Bordures de séparation                          |
| `--gray-200` | `#E2E6E6` | Fonds de tableau, heatmap proche zéro           |
| `--gray-100` | `#F3F5F5` | Fond alternance, fond heatmap null              |
| `--gray-050` | `#FAFBFB` | Fond très neutre                                |

### Statuts (dérivés — PAS de vert/rouge/jaune)

| Statut  | Couleur        | Token                               |
|---------|----------------|-------------------------------------|
| Success | Bleu moyen     | `--success-color` = `--blue-700`    |
| Info    | Bleu           | `--info-color` = `--blue-600`       |
| Warning | Gris foncé     | `--warning-color` = `--gray-600`    |
| Danger  | Gris très foncé| `--danger-color` = `--gray-800`     |

Les classes Bootstrap `bg-success`, `bg-danger`, `bg-warning`, `text-success`,
`text-danger`, `text-warning`, `btn-success`, `btn-danger`, `btn-warning`,
`alert-success`, `alert-danger`, `alert-warning` sont **réécrites globalement**
dans `style.css` pour respecter ces tokens. **Aucune page ne doit les redéfinir
en dur avec des couleurs Bootstrap d'origine.**

---

### ⚠️ Exception unique — Valeurs en pourcentage (performance)

**Seuls les chiffres exprimés en pourcentage de performance** (rendements,
évolutions, variations) peuvent déroger à la palette bleus/gris. Dans ce cas
précis — et uniquement celui-là — les couleurs vert et rouge sont autorisées
pour matérialiser immédiatement le signe de la valeur :

| Cas                      | Couleur   | Token CSS               | Classe utilitaire       |
|--------------------------|-----------|-------------------------|-------------------------|
| Performance **positive** | Vert      | `--perf-positive` `#198754` | `.text-perf-positive` |
| Performance **négative** | Rouge     | `--perf-negative` `#DC3545` | `.text-perf-negative` |
| Performance **nulle / N/A** | Gris  | `--perf-neutral` `--gray-600` | `.text-perf-neutral`|

**Portée stricte de l'exception** :
- Uniquement des valeurs numériques suivies du signe `%`.
- Uniquement dans des cellules/éléments de **texte** (KPI, tableaux, badges).
- Jamais pour un fond plein (`background`), jamais pour une bordure, jamais
  pour un bouton, jamais pour une icône indépendante d'une valeur.
- Aucune autre couleur vive n'est autorisée ailleurs (pas de jaune/or, pas
  d'orange, pas de violet).

Exemple conforme :
```html
<td class="text-end text-perf-positive">+4,20 %</td>
<td class="text-end text-perf-negative">-1,85 %</td>
```

---

## 4. Palette graphiques (Chart.js)

Pour toute série dans un graphique, utiliser **uniquement** cette palette ordonnée :

```js
const PALETTE = [
  '#004C90', '#003366', '#165FA3', '#3A7AB8', '#6795C9',
  '#99B6DB', '#495B5B', '#7E8C8C', '#9BA7A7', '#C7CECE'
];
const COLOR_POSITIVE = '#004C90'; // bleu CGF
const COLOR_NEGATIVE = '#7E8C8C'; // gris CGF moyen
const COLOR_PRIMARY  = '#004C90'; // bleu CGF officiel
```

Interdit dans les graphiques : `#198754` (vert), `#dc3545` (rouge), `#ffc107`
(jaune), `#6f42c1` (violet), `#d63384` (rose), `#fd7e14` (orange), etc.

---

## 5. Composants

### Cartes (`.card`)
- Fond : blanc (`--bg-secondary`)
- Bordure : `1px solid rgba(10, 35, 66, 0.08)`
- Rayon : `var(--border-radius-lg)` = 12 px
- Ombre : `var(--shadow-sm)` au repos, `var(--shadow-md)` au survol
- En-tête : dégradé blanc → `#FAFBFC`, titre h5 en `--primary-color`

### Boutons
- **Primary** : fond `--primary-color`, texte blanc
- **Outline-primary** : bordure `--primary-color`, texte `--primary-color`
- **Success / Danger / Warning** : réécrits pour utiliser les statuts bleu/gris
- Rayon : `var(--border-radius)` = 8 px

### Alertes
- Fond très pâle (`--blue-100` ou `--gray-100`)
- Texte foncé (`--primary-color` ou `--gray-800`)
- Bordure gauche 4 px de la couleur du statut

### Badges KPI
- Label : petite majuscule, `--text-muted`
- Valeur : Cambria, 700, `--primary-color`
- Icône : accent `--accent-color` (`--blue-700`)

### Heatmap de performance
Échelle monochrome bleu → gris (jamais vert / rouge) :

| Seuil (`v`)   | Fond         | Texte        |
|---------------|--------------|--------------|
| `v > 5`       | `#0A2342`    | blanc        |
| `2 < v ≤ 5`   | `#1E4C82`    | blanc        |
| `0 < v ≤ 2`   | `#A7BED9`    | `--text-primary` |
| `-2 < v ≤ 0`  | `#E4E7EB`    | `--text-primary` |
| `-5 < v ≤ -2` | `#7B8794`    | blanc        |
| `v ≤ -5`      | `#323F4B`    | blanc        |
| `null`        | `#F5F7FA`    | `--text-muted` |

---

## 6. Layout

- **Sidebar** : fixe, largeur 280 px, collapsible 80 px, dégradé bleu marine.
- **Top navbar** : 65 px, sticky, fond blanc, bordure basse discrète.
- **Main content** : padding 2 rem, fond blanc.
- **Grille** : 12 colonnes Bootstrap, gutter par défaut.

---

## 7. Icônes

Bibliothèque unique : **Bootstrap Icons** (`bi bi-*`).
Pas d'émoji, pas de Font Awesome, pas d'icônes SVG en dur.
Couleur : hérite du parent ou `--accent-color` pour les icônes « actives ».

---

## 8. Règles d'application et contrôle

### Pour chaque page (`templates/reporting/*.html`) :

- ✅ Aucune couleur hexadécimale en dur en dehors des valeurs autorisées ci-dessus
- ✅ Aucune `font-family` autre que Cambria
- ✅ Utilisation exclusive de variables CSS (`var(--...)`)
- ✅ Classes Bootstrap de statut autorisées **uniquement parce qu'elles sont
  réécrites globalement** ; ne jamais surcharger localement en couleur vive

### Outils de vérification

Avant livraison d'une page, rechercher ces motifs interdits :
```
#198754 | #dc3545 | #ffc107 | #20c997 | #0dcaf0 | #6610f2 | #d63384 | #fd7e14 | #17a2b8
font-family:(?!.*Cambria)
```

Voir `static/css/style.css` section *GLOBAL OVERRIDES* pour les neutralisations
des classes Bootstrap de couleur.
