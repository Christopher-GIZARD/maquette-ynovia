"""
Ynov'iT Presales Pipeline — Agent Proposition commerciale

Dernier agent du pipeline. Compile les résultats de tous les
agents précédents en une proposition commerciale structurée.
"""

import json
import logging
from datetime import date

from agents.base import Agent

logger = logging.getLogger("presales.agents.proposition")


class PropositionAgent(Agent):
    """Agent de compilation de la proposition commerciale."""

    prompt_name = "proposition"

    def build_user_message(self, context: dict) -> str:
        societe = context.get("societe", {})
        reponses = context["reponses"]

        # Résumé du CDC (pas tout le contenu, juste les clés)
        cdc = context.get("cdc", {})
        cdc_resume = {
            "titre": cdc.get("titre", ""),
            "nb_sections": len(cdc.get("sections", [])),
            "sections": [s.get("titre", "") for s in cdc.get("sections", [])],
        }

        # Chiffrage
        chiffrage = context.get("chiffrage", {})
        chiffrage_resume = {
            "total_brut": chiffrage.get("uo_brut", {}).get("total_uo", 0),
            "total_ajuste": chiffrage.get("ajustement", {}).get("total_uo_ajuste", 0),
            "par_module": chiffrage.get("ajustement", {}).get("par_module", {}),
            "risques": chiffrage.get("ajustement", {}).get("risques", []),
            "recommandations": chiffrage.get("ajustement", {}).get("recommandations", []),
        }

        # Flux
        flux = context.get("flux", {})
        flux_resume = [f.get("nom", "") for f in flux.get("flux", [])]

        # Licences
        licences = context.get("licences", {})

        return f"""## Société

{json.dumps(societe, indent=2, ensure_ascii=False)}

## Date du jour

{date.today().strftime("%d/%m/%Y")}

## Résumé du cahier des charges

{json.dumps(cdc_resume, indent=2, ensure_ascii=False)}

## Chiffrage

{json.dumps(chiffrage_resume, indent=2, ensure_ascii=False)}

## Flux métier identifiés

{json.dumps(flux_resume, indent=2, ensure_ascii=False)}

## Recommandation licences

{json.dumps(licences, indent=2, ensure_ascii=False)}

## Modules activés

{json.dumps([q for q, v in reponses.items() if q.startswith("has_") and v is True], indent=2, ensure_ascii=False)}

---

Compile toutes ces informations en une proposition commerciale au format JSON."""

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
            logger.error(f"Réponse Proposition non parsable : {e}")
            return {
                "titre": "Proposition — Erreur de génération",
                "sections": [],
                "_parse_error": True,
            }