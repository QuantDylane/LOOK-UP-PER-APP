---
version: alpha
name: CGF PER/PEE Reporting
description: >-
  Sober "executive" financial reporting UI for CGF Gestion. Anchored on the
  official CGF logo blue and slate gray. Cambria serif typography evokes
  printed asset-management reports; saturated colors are forbidden except for
  ± performance percentages.
colors:
  # Identity
  primary: "#004C90"           # Bleu CGF officiel
  primary-dark: "#003366"      # Bleu CGF foncé (sidebar / hover)
  on-primary: "#FFFFFF"
  neutral: "#FFFFFF"           # Background canvas
  surface: "#FAFBFB"           # Subtle off-white surface

  # Blue scale (derived from primary #004C90)
  blue-800: "#003D73"
  blue-700: "#004C90"
  blue-600: "#165FA3"
  blue-500: "#3A7AB8"
  blue-400: "#6795C9"
  blue-300: "#99B6DB"
  blue-200: "#C9D8EC"
  blue-100: "#E5EFF8"
  blue-050: "#F2F7FB"

  # Gray scale (derived from gris CGF #495B5B)
  gray-900: "#2B3636"
  gray-800: "#384747"
  gray-700: "#495B5B"
  gray-600: "#5D6E6E"
  gray-500: "#7E8C8C"
  gray-400: "#9BA7A7"
  gray-300: "#C7CECE"
  gray-200: "#E2E6E6"
  gray-100: "#F3F5F5"
  gray-050: "#FAFBFB"

  # Semantic text
  text-primary: "#2B3636"
  text-muted: "#5D6E6E"        # AA-compliant on white (4.94:1)

  # Performance signs (TEXT-ONLY exception, used solely for "+x.xx %" / "-x.xx %"
  # numeric values; never as fill, border, button, or standalone icon).
  perf-positive: "#198754"
  perf-negative: "#DC3545"
  perf-neutral: "#5D6E6E"

typography:
  display:
    fontFamily: Cambria, Georgia, "Times New Roman", serif
    fontSize: 2.25rem
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: -0.01em
  h1:
    fontFamily: Cambria, Georgia, "Times New Roman", serif
    fontSize: 1.75rem
    fontWeight: 700
    lineHeight: 1.25
  h2:
    fontFamily: Cambria, Georgia, "Times New Roman", serif
    fontSize: 1.5rem
    fontWeight: 700
    lineHeight: 1.3
  h3:
    fontFamily: Cambria, Georgia, "Times New Roman", serif
    fontSize: 1.1rem
    fontWeight: 600
    lineHeight: 1.35
  body-md:
    fontFamily: Cambria, Georgia, "Times New Roman", serif
    fontSize: 1rem
    fontWeight: 400
    lineHeight: 1.55
  body-sm:
    fontFamily: Cambria, Georgia, "Times New Roman", serif
    fontSize: 0.875rem
    fontWeight: 400
    lineHeight: 1.5
  label-caps:
    fontFamily: Cambria, Georgia, "Times New Roman", serif
    fontSize: 0.75rem
    fontWeight: 600
    lineHeight: 1.4
    letterSpacing: 0.06em
  kpi-value:
    fontFamily: Cambria, Georgia, "Times New Roman", serif
    fontSize: 1.5rem
    fontWeight: 700
    lineHeight: 1.2
  table-cell:
    fontFamily: Cambria, Georgia, "Times New Roman", serif
    fontSize: 0.9375rem
    fontWeight: 400
    lineHeight: 1.45

rounded:
  none: 0px
  sm: 4px
  md: 8px
  lg: 12px
  pill: 999px

spacing:
  xs: 4px
  sm: 8px
  md: 16px
  lg: 24px
  xl: 32px
  xxl: 48px

components:
  page:
    backgroundColor: "{colors.neutral}"
    textColor: "{colors.text-primary}"
    typography: "{typography.body-md}"
    padding: 32px

  sidebar:
    backgroundColor: "{colors.primary-dark}"
    textColor: "{colors.on-primary}"
    typography: "{typography.body-sm}"
    width: 280px
    padding: 16px

  sidebar-collapsed:
    backgroundColor: "{colors.primary-dark}"
    textColor: "{colors.on-primary}"
    width: 80px
    padding: 8px

  topbar:
    backgroundColor: "{colors.neutral}"
    textColor: "{colors.text-primary}"
    typography: "{typography.body-sm}"
    height: 65px
    padding: 16px

  card:
    backgroundColor: "{colors.neutral}"
    textColor: "{colors.text-primary}"
    typography: "{typography.body-md}"
    rounded: "{rounded.lg}"
    padding: 24px

  card-header:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.primary}"
    typography: "{typography.h3}"
    rounded: "{rounded.lg}"
    padding: 16px

  kpi-tile:
    backgroundColor: "{colors.neutral}"
    textColor: "{colors.primary}"
    typography: "{typography.kpi-value}"
    rounded: "{rounded.lg}"
    padding: 16px

  kpi-label:
    backgroundColor: "{colors.neutral}"
    textColor: "{colors.text-muted}"
    typography: "{typography.label-caps}"
    padding: 4px

  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    typography: "{typography.body-sm}"
    rounded: "{rounded.md}"
    padding: 12px

  button-primary-hover:
    backgroundColor: "{colors.primary-dark}"
    textColor: "{colors.on-primary}"
    rounded: "{rounded.md}"
    padding: 12px

  button-outline:
    backgroundColor: "{colors.neutral}"
    textColor: "{colors.primary}"
    typography: "{typography.body-sm}"
    rounded: "{rounded.md}"
    padding: 12px

  button-secondary:
    backgroundColor: "{colors.gray-100}"
    textColor: "{colors.text-primary}"
    typography: "{typography.body-sm}"
    rounded: "{rounded.md}"
    padding: 12px

  input:
    backgroundColor: "{colors.neutral}"
    textColor: "{colors.text-primary}"
    typography: "{typography.body-md}"
    rounded: "{rounded.md}"
    padding: 10px

  table-header:
    backgroundColor: "{colors.gray-100}"
    textColor: "{colors.text-primary}"
    typography: "{typography.label-caps}"
    padding: 12px

  table-row:
    backgroundColor: "{colors.neutral}"
    textColor: "{colors.text-primary}"
    typography: "{typography.table-cell}"
    padding: 12px

  table-row-alt:
    backgroundColor: "{colors.gray-050}"
    textColor: "{colors.text-primary}"
    typography: "{typography.table-cell}"
    padding: 12px

  alert-info:
    backgroundColor: "{colors.blue-100}"
    textColor: "{colors.primary-dark}"
    typography: "{typography.body-sm}"
    rounded: "{rounded.md}"
    padding: 16px

  alert-success:
    backgroundColor: "{colors.blue-100}"
    textColor: "{colors.primary-dark}"
    typography: "{typography.body-sm}"
    rounded: "{rounded.md}"
    padding: 16px

  alert-warning:
    backgroundColor: "{colors.gray-100}"
    textColor: "{colors.gray-800}"
    typography: "{typography.body-sm}"
    rounded: "{rounded.md}"
    padding: 16px

  alert-danger:
    backgroundColor: "{colors.gray-200}"
    textColor: "{colors.gray-900}"
    typography: "{typography.body-sm}"
    rounded: "{rounded.md}"
    padding: 16px

  badge-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    typography: "{typography.label-caps}"
    rounded: "{rounded.pill}"
    padding: 4px

  badge-muted:
    backgroundColor: "{colors.gray-100}"
    textColor: "{colors.gray-700}"
    typography: "{typography.label-caps}"
    rounded: "{rounded.pill}"
    padding: 4px

  # Chart.js series — ordered palette for line / bar / pie series.
  # Series 1 is the primary CGF blue; the ladder fades to neutral grays.
  # textColor is intentionally omitted: data labels render outside the
  # series fill, so series tokens carry only a backgroundColor.
  chart-series-1:
    backgroundColor: "{colors.blue-700}"
  chart-series-2:
    backgroundColor: "{colors.primary-dark}"
  chart-series-3:
    backgroundColor: "{colors.blue-600}"
  chart-series-4:
    backgroundColor: "{colors.blue-500}"
  chart-series-5:
    backgroundColor: "{colors.blue-400}"
  chart-series-6:
    backgroundColor: "{colors.blue-300}"
  chart-series-7:
    backgroundColor: "{colors.gray-700}"
  chart-series-8:
    backgroundColor: "{colors.gray-500}"
  chart-series-9:
    backgroundColor: "{colors.gray-400}"
  chart-series-10:
    backgroundColor: "{colors.gray-300}"

  # Performance heatmap ladder (six steps blue → gray, never red/green).
  # Each cell's background is picked from the value range; text contrast
  # flips to white on the deeper shades.
  heatmap-strong-positive:
    backgroundColor: "{colors.primary-dark}"
    textColor: "{colors.on-primary}"
  heatmap-positive:
    backgroundColor: "{colors.blue-800}"
    textColor: "{colors.on-primary}"
  heatmap-weak-positive:
    backgroundColor: "{colors.blue-200}"
    textColor: "{colors.text-primary}"
  heatmap-weak-negative:
    backgroundColor: "{colors.gray-200}"
    textColor: "{colors.text-primary}"
  heatmap-negative:
    backgroundColor: "{colors.gray-600}"
    textColor: "{colors.on-primary}"
  heatmap-strong-negative:
    backgroundColor: "{colors.gray-800}"
    textColor: "{colors.on-primary}"
  heatmap-null:
    backgroundColor: "{colors.blue-050}"
    textColor: "{colors.text-muted}"

  # Borders (used on cards, table rows, dividers — text never sits on these
  # tints, they are decorative only).
  divider:
    backgroundColor: "{colors.gray-300}"
    textColor: "{colors.text-primary}"

  # Performance text utilities (kept in the schema so agents discover them,
  # even though they apply to inline percentage spans, not real components).
  text-perf-positive:
    backgroundColor: "{colors.neutral}"
    textColor: "{colors.perf-positive}"
    typography: "{typography.table-cell}"
  text-perf-negative:
    backgroundColor: "{colors.neutral}"
    textColor: "{colors.perf-negative}"
    typography: "{typography.table-cell}"
  text-perf-neutral:
    backgroundColor: "{colors.neutral}"
    textColor: "{colors.perf-neutral}"
    typography: "{typography.table-cell}"
---

## Overview

The CGF PER/PEE Reporting application is an internal Django dashboard used by
CGF Gestion advisors to consult contracts, performance, fund factsheets and
regulatory metadata for the firm's individual (PER) and corporate (PEE)
retirement plans.

The product is **Architectural Minimalism meets Asset-Management Gravitas**.
It must read like an executive PDF report printed on premium paper: a calm
white canvas, a single deep blue identity color, slate-gray typography, and
absolutely no decorative chrome. Density is favored over whitespace
flourishes — advisors scan tables of figures, not marketing tiles.

Five non-negotiable principles drive every screen:

1. **Sobriety** — no vivid colors, no gradients beyond the sidebar, no shadows
   beyond the codified elevation tokens.
2. **Legibility first** — strong contrast, serif typography, predictable line
   heights.
3. **Total consistency** — same palette, same font, same components on every
   page; nothing redefined locally.
4. **Identity discipline** — every blue traces back to `{colors.primary}`
   (`#004C90`), every gray to `{colors.gray-700}` (`#495B5B`).
5. **Numbers speak** — performance signs (positive / negative percentages) are
   the only place where green and red are tolerated, and only on text.

## Colors

The palette is rooted in two CGF logo colors and their tonal scales. White is
the canvas; deep blue is the only accent.

- **Primary `{colors.primary}` (`#004C90`)** — the official CGF blue.
  Buttons, links, headings, KPI values, the single chart accent.
- **Primary dark `{colors.primary-dark}` (`#003366`)** — sidebar background,
  primary button hover, deep gradients.
- **Gris CGF `{colors.gray-700}` (`#495B5B`)** — the official CGF gray.
  Secondary text, neutral metadata.
- **Neutral `{colors.neutral}` (`#FFFFFF`)** — the page canvas. Reports look
  like paper.
- **Surface `{colors.surface}` (`#FAFBFB`)** — subtle off-white for card
  headers and zebra-striping in tables.

The blue scale (`blue-050` … `blue-900`) and the gray scale (`gray-050` …
`gray-900`) are the only allowed sources for any tint, border, divider or
chart series. Status colors are remapped onto these scales so that
`alert-success`, `alert-warning` and `alert-danger` cannot smuggle in vivid
Bootstrap defaults.

### Performance percentages — the single exception

Numeric values expressed as a percentage of performance (returns, variations,
period-over-period deltas) are the **only** place where chromatic green and
red appear:

- `{colors.perf-positive}` (`#198754`) — `.text-perf-positive` for `+x.xx %`
- `{colors.perf-negative}` (`#DC3545`) — `.text-perf-negative` for `-x.xx %`
- `{colors.perf-neutral}` — `.text-perf-neutral` for null / N/A

These tokens are **text-only**. Never use them as a fill, a border, a button
color, or a standalone icon color.

## Typography

A single family — **Cambria** (fallback: `Georgia`, `"Times New Roman"`,
`serif`) — is used throughout the application. No sans-serif, no Google
Fonts, no display face. The serif treatment intentionally evokes a
fund-management report.

Hierarchy:

- `{typography.h1}` — page titles, in `{colors.primary}`.
- `{typography.h2}` — section titles.
- `{typography.h3}` — card titles, KPI group titles.
- `{typography.body-md}` — paragraphs, table cells outside dense tables.
- `{typography.body-sm}` — buttons, form controls, dense table cells, alerts.
- `{typography.label-caps}` — small uppercase metadata labels above KPI
  values, in `{colors.text-muted}`.
- `{typography.kpi-value}` — large numeric KPI readouts, in
  `{colors.primary}` and weight 700.
- `{typography.table-cell}` — the dedicated size used in dense data grids.

## Layout

- **Sidebar** — fixed-position, 280 px wide expanded / 80 px collapsed,
  uses `{components.sidebar}` token (deep-blue gradient background, white
  text). Single source of navigation.
- **Top navbar** — sticky, 65 px tall, white background with a 1 px bottom
  border in `{colors.gray-200}`. Holds breadcrumb + user menu only.
- **Main content** — white canvas, padded with `{spacing.xl}` (`32px`).
- **Grid** — Bootstrap 12 columns with default gutters. Cards and KPI tiles
  align to the grid; nothing is positioned by hand.
- **Spacing scale** — only the tokens in `spacing` (`xs` … `xxl`). Never use
  raw pixel values inside templates.

## Elevation & Depth

Three soft shadow levels, all tinted with the primary blue at very low
opacity to keep the executive feel.

- Level 0 — flat surfaces (page background, sidebar). No shadow.
- Level 1 — `0 1px 2px rgba(0, 76, 144, 0.06)` — resting cards, table panels,
  alerts. Default for `{components.card}`.
- Level 2 — `0 4px 12px rgba(0, 76, 144, 0.08)` — hovered cards, dropdown
  menus, modals at rest.
- Level 3 — `0 8px 24px rgba(0, 76, 144, 0.14)` — active modals, the focused
  rapport-PDF preview.

Never use pure-black box shadows; they make the UI look heavy and break the
"premium paper" aesthetic.

## Shapes

Rounded corners come exclusively from the `rounded` scale.

- `{rounded.sm}` (`4px`) — chips, sparkline frames, small inline tags.
- `{rounded.md}` (`8px`) — buttons, inputs, alerts, modals.
- `{rounded.lg}` (`12px`) — cards, KPI tiles, the rapport-PDF page frame.
- `{rounded.pill}` (`999px`) — status badges only.

No element should be perfectly square except the global table grid.

## Components

The token block above is the source of truth. Notable component rules:

- **`{components.card}`** is the universal container. White fill, 12 px
  radius, level-1 shadow at rest, level-2 on hover. Card headers use
  `{components.card-header}` with the surface tint and a primary-colored
  `h3`.
- **`{components.kpi-tile}`** pairs a `{components.kpi-label}` (small caps,
  muted) with a `{typography.kpi-value}` readout in primary blue. KPIs that
  are percentages may receive a `.text-perf-*` class on the numeric span only.
- **`{components.button-primary}`** is solid CGF blue with white text;
  `{components.button-primary-hover}` darkens to `{colors.primary-dark}`.
  `{components.button-outline}` and `{components.button-secondary}` cover the
  rare secondary actions; all three share `{rounded.md}`.
- **Alerts** — `alert-info`, `alert-success`, `alert-warning`, `alert-danger`
  have been remapped: success and info live on the blue scale, warning and
  danger on the gray scale. They never use vivid Bootstrap defaults.
- **Tables** — header row uses `{components.table-header}` (gray-100
  background, label-caps typography); body rows alternate between
  `{components.table-row}` and `{components.table-row-alt}`.
- **Performance heatmap** — a monochrome blue→gray ladder is used (no
  red/green), see the legacy `CHARTE_GRAPHIQUE.md` for the exact six-step
  ladder. The heatmap itself is not a token-level component because each
  cell's color is computed from the underlying value.
- **Icons** — only Bootstrap Icons (`bi bi-*`); they inherit `currentColor`
  from their parent.
- **Charts (Chart.js)** — series colors come from the ordered palette
  `[primary, primary-dark, blue-600, blue-500, blue-400, blue-300, secondary,
  gray-500, gray-400, gray-300]`. Positive / negative bar coloring is blue
  vs. gray, never red/green.

## Do's and Don'ts

**Do**

- Reference colors and dimensions only through token references such as
  `{colors.primary}`, `{rounded.lg}`, `{spacing.md}`. The application's
  `static/css/style.css` exposes them as CSS custom properties (`--blue-700`,
  `--border-radius-lg`, …) — templates must read them with `var(--token)`.
- Treat every page as a printable executive report: white paper, deep-blue
  ink, slate captions.
- Use `.text-perf-positive` / `.text-perf-negative` on percentage values in
  KPI cards and tables to surface direction at a glance.
- Reuse the existing components — card, KPI tile, alert, table — instead of
  creating new ones.

**Don't**

- Don't introduce hex colors that aren't already in the palette. Forbidden
  literals to grep for include `#198754` (outside `.text-perf-positive`),
  `#dc3545` (outside `.text-perf-negative`), `#ffc107`, `#20c997`, `#0dcaf0`,
  `#6610f2`, `#d63384`, `#fd7e14`, `#17a2b8`.
- Don't use any font family other than Cambria and its serif fallbacks. No
  Inter, Roboto, Open Sans, sans-serif, or Font Awesome.
- Don't override the rewritten Bootstrap status classes (`bg-success`,
  `text-danger`, `btn-warning`, …) with vivid colors at the page level.
- Don't apply `perf-positive` / `perf-negative` to fills, borders, buttons or
  bare icons — they are reserved for percentage **text**.
- Don't introduce gold, orange, violet, pink, teal or yellow accents under
  any circumstance.
- Don't use raw black box shadows; always go through the elevation tokens.
