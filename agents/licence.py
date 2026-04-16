"""
Ynov'iT Presales Pipeline — Agent Licences

Recommande un plan de licences Odoo optimal en croisant
le nombre d'utilisateurs, les modules activés et les rôles.
"""

import json
import logging

from agents.base import Agent

logger = logging.getLogger("presales.agents.licence")


class LicenceAgent(Agent):
    """Agent de recommandation de licences Odoo."""

    prompt_name = "licence"

    def build_user_message(self, context: dict) -> str:
        reponses = context["reponses"]
        societe = context.get("societe", {})

        modules = [
            qid.replace("has_", "") for qid, val in reponses.items()
            if qid.startswith("has_") and val is True
        ]

        users = {
            "nb_users_internes": reponses.get("nb_users_internes", 0),
            "nb_users_portail": reponses.get("nb_users_portail", 0),
            "nb_societes": reponses.get("nb_societes", 1),
        }

        # Infos sur les équipes si disponibles
        equipes = {}
        if reponses.get("crm_nb_equipes"):
            equipes["equipes_commerciales"] = reponses["crm_nb_equipes"]
        if reponses.get("helpdesk_nb_equipes"):
            equipes["equipes_support"] = reponses["helpdesk_nb_equipes"]

        return f"""## Société

{json.dumps(societe, indent=2, ensure_ascii=False)}

## Utilisateurs

{json.dumps(users, indent=2, ensure_ascii=False)}

## Modules activés

{json.dumps(modules, indent=2, ensure_ascii=False)}

## Équipes identifiées

{json.dumps(equipes, indent=2, ensure_ascii=False)}

## Droits d'accès

Droits spécifiques : {reponses.get("has_droits_acces_specifiques", False)}
Niveau : {reponses.get("droits_acces_niveau", "Standard")}

---

Recommande le plan de licences optimal."""

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
            logger.error(f"Réponse Licences non parsable : {e}")
            return {
                "recommandation": {},
                "justification": f"Erreur de parsing : {str(e)}",
                "details_par_role": [],
                "_parse_error": True,
            }