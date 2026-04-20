"""
Ynov'iT Presales Pipeline — Agent Chiffrage

Agent hybride qui combine :
1. Le calcul déterministe des UO (uo_calculator)
2. La recherche de projets similaires (project_history)
3. L'ajustement par Claude (expertise + données historiques)

Produit un chiffrage détaillé par module avec justifications.
"""

import json
import logging

from agents.base import Agent
from services.claude_client import ClaudeClient
from services.uo_calculator import UOCalculator
from services.project_history import ProjectHistory

logger = logging.getLogger("presales.agents.chiffrage")


class ChiffrageAgent(Agent):
    """
    Agent de chiffrage des projets d'intégration Odoo.

    Reçoit les réponses du formulaire, calcule les UO bruts,
    recherche les projets similaires, et demande à Claude
    d'ajuster le chiffrage.
    """

    prompt_name = "chiffrage"

    def __init__(
        self,
        claude: ClaudeClient,
        uo_calculator: UOCalculator,
        project_history: ProjectHistory,
    ):
        super().__init__(claude)
        self.uo_calc = uo_calculator
        self.history = project_history

    def run(self, context: dict) -> dict:
        """
        Exécute l'agent chiffrage.

        Étapes :
        1. Calcul déterministe des UO
        2. Recherche de projets similaires
        3. Appel Claude pour ajustement
        4. Assemblage du résultat final

        Returns:
            Dictionnaire contenant le chiffrage brut, ajusté,
            les justifications et les risques.
        """
        reponses = context["reponses"]
        societe = context.get("societe", {})

        # ── 1. Calcul déterministe ─────────────────────────
        logger.info("Étape 1/3 — Calcul UO déterministe")
        uo_result = self.uo_calc.compute(reponses)

        # ── 2. Recherche de projets similaires ─────────────
        logger.info("Étape 2/3 — Recherche de projets similaires")
        projets_proches = self.history.find_similar(
            reponses=reponses,
            societe=societe,
        )

        # ── 3. Ajustement IA ───────────────────────────────
        logger.info("Étape 3/3 — Ajustement IA du chiffrage")
        ajustement = self._get_adjustment(reponses, societe, uo_result, projets_proches)

        # ── 4. Application du coefficient de catégorie ─────
        categorie = societe.get("categorie", {})
        coeff_cat = categorie.get("coefficient_combine", 1.0)
        total_ajuste = ajustement.get("total_uo_ajuste", uo_result["total_uo"])
        ajustement["total_uo_final"] = round(total_ajuste * coeff_cat, 1)
        for mod in ajustement.get("par_module", {}).values():
            mod["uo_final"] = round(mod.get("uo_ajuste", 0) * coeff_cat, 1)

        # ── Assemblage du résultat ─────────────────────────
        result = {
            "uo_brut": uo_result,
            "ajustement": ajustement,
            "projets_reference": projets_proches,
            "categorie": categorie,
            "meta": {
                "nb_projets_historique": self.history.count,
                "nb_projets_similaires": len(projets_proches),
                "coefficient_categorie": coeff_cat,
            }
        }

        logger.info(
            f"Chiffrage terminé : {uo_result['total_uo']}j brut → "
            f"{total_ajuste}j ajusté → "
            f"{ajustement['total_uo_final']}j final (coeff catégorie {coeff_cat})"
        )

        return result

    def build_user_message(self, context: dict) -> str:
        """
        Construit le message utilisateur pour Claude.

        Note : cette méthode est utilisée par _get_adjustment()
        qui lui passe un contexte enrichi avec les données calculées.
        """
        reponses = context["reponses"]
        societe = context.get("societe", {})
        uo_result = context["uo_result"]
        projets_proches = context.get("projets_proches", [])

        # ── Section réponses prospect ──────────────────────
        # On ne garde que les réponses pertinentes (pas les False isolés)
        reponses_pertinentes = {
            k: v for k, v in reponses.items()
            if v is not None and v != "" and v != [] and v is not False
            or k.startswith("has_")  # Garder tous les has_* même False
        }

        # ── Section projets similaires ─────────────────────
        if projets_proches:
            section_projets = json.dumps(projets_proches, indent=2, ensure_ascii=False)
        else:
            section_projets = (
                "Aucun projet similaire en base (démarrage à froid). "
                "Appuie-toi sur les heuristiques métier."
            )

        return f"""## Données du prospect

### Société
{json.dumps(societe, indent=2, ensure_ascii=False)}

### Réponses au formulaire
{json.dumps(reponses_pertinentes, indent=2, ensure_ascii=False)}

## Chiffrage UO brut (calcul déterministe)

Total : {uo_result['total_uo']} jours consultant

### Par module
{json.dumps(uo_result['par_module'], indent=2, ensure_ascii=False)}

### Détail des lignes
{json.dumps(uo_result['lignes'], indent=2, ensure_ascii=False)}

## Projets similaires
{section_projets}

---

Analyse ces données et produis le chiffrage ajusté au format JSON demandé."""

    def parse_response(self, response: str) -> dict:
        """Parse la réponse JSON de Claude."""
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
            logger.error(f"Réponse Claude non parsable en JSON : {e}")
            logger.debug(f"Réponse brute : {response[:500]}")
            # Retourner un résultat dégradé plutôt que crasher
            return {
                "total_uo_brut": 0,
                "total_uo_ajuste": 0,
                "justification_globale": f"Erreur de parsing : {str(e)}",
                "par_module": {},
                "risques": [],
                "recommandations": ["Erreur lors de l'ajustement IA — vérifier le chiffrage manuellement"],
                "_parse_error": True,
            }

    def _get_adjustment(
        self,
        reponses: dict,
        societe: dict,
        uo_result: dict,
        projets_proches: list,
    ) -> dict:
        """
        Appelle Claude pour obtenir l'ajustement du chiffrage.

        Construit un contexte enrichi et utilise la méthode run
        de la classe de base via build_user_message + parse_response.
        """
        # Construire un contexte enrichi pour build_user_message
        enriched_context = {
            "reponses": reponses,
            "societe": societe,
            "uo_result": uo_result,
            "projets_proches": projets_proches,
        }

        message = self.build_user_message(enriched_context)
        raw_response = self.claude.send(
            system=self.system_prompt,
            message=message,
        )
        return self.parse_response(raw_response)