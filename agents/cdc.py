"""
Ynov'iT Presales Pipeline — Agent Cahier des charges

Génère un cahier des charges structuré à partir des réponses
du formulaire prospect. Le document couvre le contexte, le
périmètre fonctionnel, la reprise de données, les contraintes
et les risques.
"""

import json
import logging
from datetime import date

from agents.base import Agent
from services.claude_client import ClaudeClient

logger = logging.getLogger("presales.agents.cdc")


class CDCAgent(Agent):
    """Agent de rédaction du cahier des charges."""

    prompt_name = "cdc"

    def build_user_message(self, context: dict) -> str:
        reponses = context["reponses"]
        societe = context.get("societe", {})
        entreprise = context.get("entreprise", societe)

        # Identifier les modules activés avec leurs détails
        modules_actifs = self._extract_modules_details(reponses)

        # Extraire les infos de migration
        migration = self._extract_migration(reponses)

        # Extraire les contraintes
        contraintes = self._extract_contraintes(reponses)

        return f"""## Informations société

{json.dumps(entreprise, indent=2, ensure_ascii=False)}

## Date du jour

{date.today().strftime("%d/%m/%Y")}

## Modules activés et détails

{json.dumps(modules_actifs, indent=2, ensure_ascii=False)}

## Reprise de données

{json.dumps(migration, indent=2, ensure_ascii=False)}

## Contraintes et paramètres généraux

{json.dumps(contraintes, indent=2, ensure_ascii=False)}

## Réponses complètes du formulaire

{json.dumps(reponses, indent=2, ensure_ascii=False)}

---

Rédige le cahier des charges complet au format JSON demandé."""

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
            logger.error(f"Réponse CDC non parsable : {e}")
            return {
                "titre": "Cahier des charges — Erreur de génération",
                "sections": [{
                    "numero": "1",
                    "titre": "Erreur",
                    "contenu": f"La réponse de l'IA n'a pas pu être interprétée : {str(e)}",
                    "sous_sections": []
                }],
                "_parse_error": True,
            }

    @staticmethod
    def _extract_modules_details(reponses: dict) -> dict:
        """Extrait les modules activés avec leurs sous-réponses."""
        modules = {}

        # Mapping des préfixes de questions par module
        module_prefixes = {
            "has_crm": "crm_",
            "has_sale": "sale_",
            "has_purchase": "purchase_",
            "has_account": "account_",
            "has_stock": "stock_",
            "has_project": "project_",
            "has_manufacturing": "manufacturing_",
            "has_hr": "hr_",
            "has_helpdesk": "helpdesk_",
            "has_field_service": "field_service_",
            "has_website": "website_",
            "has_maintenance": "maintenance_",
            "has_repair": "repair_",
            "has_rental": "rental_",
            "has_kits_vente": "kits_",
        }

        for has_key, prefix in module_prefixes.items():
            if reponses.get(has_key) is True:
                details = {}
                for qid, val in reponses.items():
                    if qid.startswith(prefix) and val is not None:
                        details[qid] = val
                modules[has_key] = {
                    "actif": True,
                    "details": details,
                }

        return modules

    @staticmethod
    def _extract_migration(reponses: dict) -> dict:
        """Extrait les informations de reprise de données."""
        if not reponses.get("migration_donnees"):
            return {"active": False}

        migration = {
            "active": True,
            "perimetre": reponses.get("migration_perimetre", []),
            "volumes": {},
        }

        # Extraire les volumes par type de données
        volume_keys = {
            "vol_clients": "Clients / contacts",
            "vol_fournisseurs": "Fournisseurs",
            "vol_produits": "Catalogue produits",
            "vol_stocks_empl": "Stocks",
        }

        for key, label in volume_keys.items():
            if key in reponses:
                migration["volumes"][label] = {
                    "volume": reponses[key],
                    "format": reponses.get(f"{key}_format", "Non précisé"),
                }

        return migration

    @staticmethod
    def _extract_contraintes(reponses: dict) -> dict:
        """Extrait les contraintes et paramètres généraux."""
        return {
            "nb_societes": reponses.get("nb_societes", 1),
            "multi_company_interco": reponses.get("multi_company_interco", False),
            "nb_users_internes": reponses.get("nb_users_internes", 0),
            "nb_users_portail": reponses.get("nb_users_portail", 0),
            "langues": reponses.get("langues", ["Français"]),
            "pays_activite": reponses.get("pays_activite", ["France"]),
            "erp_actuel": reponses.get("erp_actuel", []),
            "date_go_live": reponses.get("date_go_live", "Non définie"),
            "budget": reponses.get("budget", "Non défini"),
            "droits_acces": reponses.get("has_droits_acces_specifiques", False),
            "droits_acces_niveau": reponses.get("droits_acces_niveau", None),
        }