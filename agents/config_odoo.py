"""
Ynov'iT Presales Pipeline — Agent Config Odoo

Génère la structure d'un module Odoo 19 installable qui
paramètre automatiquement une base de test pour le prospect.

Utilise la référence des champs res.config.settings filtrée
(data/odoo_settings_filtered.json) pour mapper les réponses
du formulaire vers les vrais noms techniques Odoo.
"""

import json
import logging
from pathlib import Path

import config
from agents.base import Agent

logger = logging.getLogger("presales.agents.config_odoo")

SETTINGS_REF_PATH = config.DATA_DIR / "odoo_settings_filtered.json"


class ConfigOdooAgent(Agent):
    """Agent de génération du module de configuration Odoo."""

    prompt_name = "config_odoo"

    def __init__(self, claude):
        super().__init__(claude)
        self._settings_ref = self._load_settings_ref()

    @staticmethod
    def _load_settings_ref() -> str:
        """Charge la référence des settings Odoo filtrée."""
        if not SETTINGS_REF_PATH.exists():
            logger.warning(
                f"Référence settings Odoo introuvable : {SETTINGS_REF_PATH}. "
                f"L'agent fonctionnera sans référence technique."
            )
            return ""

        with open(SETTINGS_REF_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Formater en texte compact pour le prompt
        lines = []
        for module in data:
            mod_name = module["module"]
            lines.append(f"\n### {mod_name}")
            for setting in module["settings"]:
                lines.append(f"  - {setting}")

        ref_text = "\n".join(lines)
        total = sum(len(m["settings"]) for m in data)
        logger.info(f"Référence settings chargée : {total} champs sur {len(data)} modules")
        return ref_text

    def build_user_message(self, context: dict) -> str:
        reponses = context["reponses"]
        societe = context.get("societe", {})

        modules = [
            qid for qid, val in reponses.items()
            if qid.startswith("has_") and val is True
        ]

        params = {
            "variantes": reponses.get("sale_variantes", "Non"),
            "unites_mesure": reponses.get("sale_unites_mesure", False),
            "multi_entrepots": reponses.get("stock_entrepots"),
            "routes": reponses.get("stock_routes", []),
            "nb_societes": reponses.get("nb_societes", 1),
            "interco": reponses.get("multi_company_interco", False),
            "langues": reponses.get("langues", ["Français"]),
            "pays": reponses.get("pays_activite", ["France"]),
            "droits_acces": reponses.get("has_droits_acces_specifiques", False),
            "droits_niveau": reponses.get("droits_acces_niveau"),
        }

        # Section référence technique (conditionnelle)
        ref_section = ""
        if self._settings_ref:
            ref_section = f"""
## Référence technique — Champs res.config.settings Odoo 19

Voici la liste EXHAUSTIVE des champs Boolean et Selection disponibles
dans res.config.settings pour les modules pertinents. Utilise UNIQUEMENT
ces noms techniques dans le XML généré.

{self._settings_ref}

"""

        return f"""## Société

{json.dumps(societe, indent=2, ensure_ascii=False)}

## Modules à activer

{json.dumps(modules, indent=2, ensure_ascii=False)}

## Paramètres de configuration

{json.dumps(params, indent=2, ensure_ascii=False)}
{ref_section}
## Réponses complètes

{json.dumps(reponses, indent=2, ensure_ascii=False)}

---

Génère la structure du module Odoo de configuration en utilisant
les noms techniques exacts de la référence ci-dessus."""

    def parse_response(self, response: str) -> dict:
        cleaned = response.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines)

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.error(f"Réponse Config Odoo non parsable : {e}")
            return {
                "manifest": {},
                "modules_to_install": [],
                "config_xml": "",
                "settings": {},
                "notes": [f"Erreur de parsing : {str(e)}"],
                "_parse_error": True,
            }
