"""
Ynov'iT Presales Pipeline — Générateur Diagrammes

Sauvegarde les diagrammes de flux en fichiers Mermaid (.mmd)
et génère un fichier HTML de visualisation.
"""

import logging
from pathlib import Path

logger = logging.getLogger("presales.generators.diagram")


def generate_diagrams(flux_data: dict, output_dir: Path):
    """
    Génère les fichiers de diagrammes.

    Produit :
    - Un fichier .mmd par flux (syntaxe Mermaid)
    - Un fichier HTML pour visualiser tous les flux

    Args:
        flux_data: Sortie de l'agent Flux
        output_dir: Répertoire du projet
    """
    flux_list = flux_data.get("flux", [])

    if not flux_list:
        logger.warning("Aucun flux à générer")
        return

    # ── Fichiers Mermaid individuels ───────────────────────
    for i, flux in enumerate(flux_list, 1):
        nom = flux.get("nom", f"flux_{i}")
        slug = "".join(c if c.isalnum() else "_" for c in nom).lower()
        mmd_path = output_dir / f"flux_{slug}.mmd"

        mermaid_code = flux.get("mermaid", "graph LR\n    A[Pas de diagramme]")
        mmd_path.write_text(mermaid_code, encoding="utf-8")

    # ── Fichier HTML de visualisation ──────────────────────
    html_path = output_dir / "flux_visualisation.html"
    html = _build_viewer_html(flux_list)
    html_path.write_text(html, encoding="utf-8")

    logger.info(
        f"Diagrammes générés : {len(flux_list)} flux → "
        f"{len(flux_list)} fichiers .mmd + 1 viewer HTML"
    )


def _build_viewer_html(flux_list: list) -> str:
    """Construit une page HTML qui affiche tous les diagrammes Mermaid."""

    diagrams_html = ""
    for flux in flux_list:
        nom = flux.get("nom", "")
        desc = flux.get("description", "")
        mermaid = flux.get("mermaid", "")
        modules = ", ".join(flux.get("modules_impliques", []))

        diagrams_html += f"""
    <div class="flux-card">
      <h2>{_esc(nom)}</h2>
      <p class="desc">{_esc(desc)}</p>
      <p class="modules">Modules : {_esc(modules)}</p>
      <div class="mermaid">
{mermaid}
      </div>
    </div>
"""

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <title>Flux métier — Avant-vente Odoo</title>
  <script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
  <style>
    body {{ font-family: Arial, sans-serif; background: #f0f2f5; margin: 0; padding: 20px; }}
    h1 {{ color: #1A2B4A; text-align: center; margin-bottom: 30px; }}
    .flux-card {{
      background: white; border-radius: 10px; padding: 24px; margin: 0 auto 24px;
      max-width: 800px; box-shadow: 0 2px 8px rgba(0,0,0,0.08);
    }}
    .flux-card h2 {{ color: #1A2B4A; margin-top: 0; }}
    .desc {{ color: #4a5c7a; }}
    .modules {{ color: #8496b0; font-size: 13px; font-style: italic; margin-bottom: 16px; }}
    .mermaid {{ text-align: center; }}
  </style>
</head>
<body>
  <h1>Flux métier — Projet Odoo 19</h1>
{diagrams_html}
  <script>mermaid.initialize({{ startOnLoad: true, theme: 'default' }});</script>
</body>
</html>"""


def _esc(text: str) -> str:
    """Échappe les caractères HTML."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
