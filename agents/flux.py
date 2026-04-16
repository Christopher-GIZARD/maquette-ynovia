"""
Ynov'iT Presales Pipeline — Agent Flux

Identifie les flux métier du prospect et génère des diagrammes
Mermaid pour chaque flux. Les flux dépendent des modules activés
et de leur paramétrage.
"""

import json
import logging

from agents.base import Agent

logger = logging.getLogger("presales.agents.flux")


class FluxAgent(Agent):
    """Agent de génération des schémas de flux métier."""

    prompt_name = "flux"

    def build_user_message(self, context: dict) -> str:
        reponses = context["reponses"]
        societe = context.get("societe", {})

        modules = [
            qid for qid, val in reponses.items()
            if qid.startswith("has_") and val is True
        ]

        # Détails logistiques
        logistique = {
            "entrepots": reponses.get("stock_entrepots"),
            "routes": reponses.get("stock_routes", []),
        }

        # Détails fabrication
        fabrication = {
            "type": reponses.get("manufacturing_type"),
            "sous_traitance": reponses.get("manufacturing_sous_traitance"),
        }

        return f"""## Société

{json.dumps(societe, indent=2, ensure_ascii=False)}

## Modules activés

{json.dumps(modules, indent=2, ensure_ascii=False)}

## Configuration logistique

{json.dumps(logistique, indent=2, ensure_ascii=False)}

## Configuration fabrication

{json.dumps(fabrication, indent=2, ensure_ascii=False)}

## Réponses complètes

{json.dumps(reponses, indent=2, ensure_ascii=False)}

---

Identifie les flux métier et génère les diagrammes Mermaid."""

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
            logger.error(f"Réponse Flux non parsable : {e}")
            return {"flux": [], "nb_flux": 0, "_parse_error": True}