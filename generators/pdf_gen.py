"""
Ynov'iT Presales Pipeline — Générateur Proposition

Génère la proposition commerciale en HTML formaté pour
l'impression PDF (via le navigateur ou WeasyPrint).
"""

import logging
from pathlib import Path
from datetime import date

logger = logging.getLogger("presales.generators.pdf")


def generate_proposition_html(propale_data: dict, output_path: Path, societe: dict = None):
    """
    Génère la proposition commerciale en HTML prêt pour impression PDF.

    Le fichier HTML est conçu avec des styles @media print pour
    produire un PDF professionnel via Ctrl+P dans le navigateur.

    Args:
        propale_data: Sortie de l'agent Proposition
        output_path: Chemin du fichier .html à créer
        societe: Infos société
    """
    nom = societe.get("raison_sociale", "Prospect") if societe else "Prospect"
    titre = propale_data.get("titre", f"Proposition commerciale — {nom}")
    reference = propale_data.get("reference", f"PROP-{date.today().strftime('%Y%m%d')}")
    sections = propale_data.get("sections", [])

    sections_html = ""
    for section in sections:
        sections_html += _render_section(section)

    html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <title>{_esc(titre)}</title>
  <style>
    @page {{ size: A4; margin: 2cm 2.5cm; }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: Arial, Helvetica, sans-serif;
      font-size: 11pt; line-height: 1.6; color: #333;
      max-width: 800px; margin: 0 auto; padding: 40px 20px;
    }}
    .cover {{
      text-align: center; padding: 120px 0 60px;
      page-break-after: always;
    }}
    .cover .logo {{ font-size: 14pt; font-weight: bold; color: #3EC9A7; letter-spacing: 2px; }}
    .cover h1 {{ font-size: 22pt; color: #1A2B4A; margin: 40px 0 16px; }}
    .cover .client {{ font-size: 14pt; color: #4a5c7a; }}
    .cover .meta {{ font-size: 10pt; color: #8496b0; margin-top: 60px; }}
    h2 {{
      font-size: 16pt; color: #1A2B4A; margin: 30px 0 12px;
      padding-bottom: 6px; border-bottom: 2px solid #3EC9A7;
    }}
    h3 {{ font-size: 13pt; color: #1A2B4A; margin: 20px 0 8px; }}
    p {{ margin-bottom: 10px; }}
    .section {{ margin-bottom: 24px; }}
    table {{
      width: 100%; border-collapse: collapse; margin: 16px 0;
      font-size: 10pt;
    }}
    th {{
      background: #1A2B4A; color: white; padding: 8px 12px;
      text-align: left; font-weight: bold;
    }}
    td {{ padding: 8px 12px; border-bottom: 1px solid #E2E6EA; }}
    tr:nth-child(even) {{ background: #F0F2F5; }}
    .total-row {{ background: #3EC9A7 !important; color: white; font-weight: bold; }}
    .footer {{
      margin-top: 60px; padding-top: 16px;
      border-top: 1px solid #E2E6EA;
      font-size: 9pt; color: #8496b0; text-align: center;
    }}
    @media print {{
      body {{ padding: 0; max-width: none; }}
      .section {{ page-break-inside: avoid; }}
    }}
  </style>
</head>
<body>

  <div class="cover">
    <div class="logo">YNOV'IT SERVICES</div>
    <h1>{_esc(titre)}</h1>
    <div class="client">{_esc(nom)}</div>
    <div class="meta">
      Réf. {_esc(reference)}<br>
      {propale_data.get("date", date.today().strftime("%d/%m/%Y"))}<br>
      Document confidentiel
    </div>
  </div>

{sections_html}

  <div class="footer">
    Ynov'iT Services — Intégrateur Odoo<br>
    Ce document est confidentiel et destiné uniquement à son destinataire.
  </div>

</body>
</html>"""

    output_path.write_text(html, encoding="utf-8")
    logger.info(f"Proposition HTML générée : {output_path} ({len(sections)} sections)")


def _render_section(section: dict) -> str:
    """Rend une section en HTML."""
    numero = section.get("numero", "")
    titre = section.get("titre", "")
    contenu = section.get("contenu", "")

    heading = f"{numero}. {titre}" if numero else titre
    html = f'  <div class="section">\n    <h2>{_esc(heading)}</h2>\n'

    if contenu:
        html += f"    <p>{_esc(contenu)}</p>\n"

    # Tableau de chiffrage si présent
    if "tableau_chiffrage" in section:
        html += _render_chiffrage_table(section)

    # Phases de planning si présentes
    if "phases" in section:
        html += _render_phases(section["phases"])

    # Sous-sections
    for sub in section.get("sous_sections", []):
        html += f'    <h3>{_esc(sub.get("titre", ""))}</h3>\n'
        html += f'    <p>{_esc(sub.get("contenu", ""))}</p>\n'

    html += "  </div>\n\n"
    return html


def _render_chiffrage_table(section: dict) -> str:
    """Rend le tableau de chiffrage."""
    rows = section.get("tableau_chiffrage", [])
    total = section.get("total_uo", 0)
    fourchette = section.get("fourchette", {})

    html = "    <table>\n"
    html += "      <tr><th>Poste</th><th>UO (jours)</th><th>Détail</th></tr>\n"

    for row in rows:
        html += (
            f"      <tr>"
            f"<td>{_esc(row.get('poste', ''))}</td>"
            f"<td style='text-align:center'>{row.get('uo', 0)}</td>"
            f"<td>{_esc(row.get('detail', ''))}</td>"
            f"</tr>\n"
        )

    if fourchette:
        basse = fourchette.get("basse", total)
        haute = fourchette.get("haute", total)
        html += (
            f'      <tr class="total-row">'
            f"<td>TOTAL (fourchette)</td>"
            f"<td style='text-align:center'>{basse} — {haute} j</td>"
            f"<td></td></tr>\n"
        )
    else:
        html += (
            f'      <tr class="total-row">'
            f"<td>TOTAL</td>"
            f"<td style='text-align:center'>{total} j</td>"
            f"<td></td></tr>\n"
        )

    html += "    </table>\n"
    return html


def _render_phases(phases: list) -> str:
    """Rend le planning par phases."""
    html = "    <table>\n"
    html += "      <tr><th>Phase</th><th>Durée</th><th>Description</th></tr>\n"

    for phase in phases:
        html += (
            f"      <tr>"
            f"<td>{_esc(phase.get('nom', ''))}</td>"
            f"<td>{_esc(phase.get('duree', ''))}</td>"
            f"<td>{_esc(phase.get('description', ''))}</td>"
            f"</tr>\n"
        )

    html += "    </table>\n"
    return html


def _esc(text) -> str:
    """Échappe les caractères HTML."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
