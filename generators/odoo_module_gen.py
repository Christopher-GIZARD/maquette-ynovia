"""
Ynov'iT Presales Pipeline — Générateur Module Odoo

Génère un module Odoo 19 installable (.zip) contenant :
- __manifest__.py
- __init__.py
- data/config.xml (paramétrage res.config.settings)
"""

import json
import logging
import zipfile
from pathlib import Path
from datetime import date

logger = logging.getLogger("presales.generators.odoo_module")

MODULE_NAME = "ynit_presales_config"


def generate_odoo_module(config_data: dict, output_path: Path, societe: dict = None):
    """
    Génère un module Odoo installable en .zip.

    Args:
        config_data: Sortie de l'agent Config Odoo
        output_path: Chemin du fichier .zip à créer
        societe: Infos société pour le nom du module
    """
    nom = societe.get("raison_sociale", "Prospect") if societe else "Prospect"
    manifest = config_data.get("manifest", {})
    modules = config_data.get("modules_to_install", [])
    settings = config_data.get("settings", {})
    config_xml = config_data.get("config_xml", "")
    notes = config_data.get("notes", [])
    warnings = config_data.get("warnings", [])

    # Construire les fichiers du module
    files = {}

    # __manifest__.py
    manifest_data = manifest or {
        "name": f"Presales Config — {nom}",
        "version": "19.0.1.0.0",
        "category": "Tools",
        "summary": f"Configuration avant-vente pour {nom}",
        "depends": ["base"] + modules,
        "data": ["data/config.xml"],
        "installable": True,
        "auto_install": False,
    }

    manifest_content = (
        f"# -*- coding: utf-8 -*-\n"
        f"# Module généré automatiquement par Ynov'iT Presales Pipeline\n"
        f"# Date : {date.today().strftime('%d/%m/%Y')}\n"
        f"# Prospect : {nom}\n\n"
        f"{{\n"
        f"    'name': {json.dumps(manifest_data.get('name', 'Presales Config'))},\n"
        f"    'version': '{manifest_data.get('version', '19.0.1.0.0')}',\n"
        f"    'category': '{manifest_data.get('category', 'Tools')}',\n"
        f"    'summary': {json.dumps(manifest_data.get('summary', ''))},\n"
        f"    'depends': {json.dumps(manifest_data.get('depends', ['base']))},\n"
        f"    'data': {json.dumps(manifest_data.get('data', ['data/config.xml']))},\n"
        f"    'installable': True,\n"
        f"    'auto_install': False,\n"
        f"}}\n"
    )
    files[f"{MODULE_NAME}/__manifest__.py"] = manifest_content

    # __init__.py
    files[f"{MODULE_NAME}/__init__.py"] = (
        "# -*- coding: utf-8 -*-\n"
        "# Module généré automatiquement\n"
    )

    # data/config.xml
    if config_xml and config_xml.strip():
        xml_content = config_xml
    else:
        xml_content = _generate_config_xml(settings, modules)

    files[f"{MODULE_NAME}/data/config.xml"] = xml_content

    # README.md
    readme_lines = [
        f"# Presales Config — {nom}",
        "",
        f"Module généré automatiquement le {date.today().strftime('%d/%m/%Y')}.",
        "",
        "## Modules installés",
        "",
    ]
    for mod in modules:
        readme_lines.append(f"- `{mod}`")

    if settings:
        readme_lines.extend(["", "## Paramètres activés", ""])
        for key, val in settings.items():
            readme_lines.append(f"- `{key}` = `{val}`")

    if notes:
        readme_lines.extend(["", "## Notes", ""])
        for note in notes:
            readme_lines.append(f"- {note}")

    if warnings:
        readme_lines.extend(["", "## Avertissements", ""])
        for warning in warnings:
            readme_lines.append(f"- ⚠️ {warning}")

    files[f"{MODULE_NAME}/README.md"] = "\n".join(readme_lines) + "\n"

    # Créer le ZIP
    with zipfile.ZipFile(str(output_path), "w", zipfile.ZIP_DEFLATED) as zf:
        for filepath, content in files.items():
            zf.writestr(filepath, content)

    logger.info(
        f"Module Odoo généré : {output_path} "
        f"({len(modules)} modules, {len(settings)} settings)"
    )


def _generate_config_xml(settings: dict, modules: list) -> str:
    """
    Génère le fichier XML de configuration res.config.settings.
    """
    lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<odoo>',
        '  <data noupdate="0">',
        '',
        '    <!-- Paramétrage automatique avant-vente -->',
        '    <record id="presales_config_settings" model="res.config.settings">',
    ]

    if not settings:
        lines.append('      <!-- Aucun paramètre spécifique détecté -->')
    else:
        for key, value in sorted(settings.items()):
            if isinstance(value, bool):
                lines.append(f'      <field name="{key}">{value}</field>')
            elif isinstance(value, (int, float)):
                lines.append(f'      <field name="{key}">{value}</field>')
            else:
                lines.append(f'      <field name="{key}">{value}</field>')

    lines.extend([
        '    </record>',
        '',
        '  </data>',
        '</odoo>',
        '',
    ])

    return "\n".join(lines)
