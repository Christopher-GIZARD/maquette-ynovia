"""
Ynov'iT Presales Pipeline — Orchestrateur

Enchaîne les agents dans le bon ordre, propage le contexte,
et génère les livrables finaux.

Séparé du serveur pour pouvoir être utilisé :
- Via l'API (server.py)
- En ligne de commande
- Dans des tests
"""

import json
import logging
from pathlib import Path
from typing import Callable

from services.client_factory import get_claude_client
from services.uo_calculator import UOCalculator
from services.project_history import ProjectHistory
from agents.cdc import CDCAgent
from agents.chiffrage import ChiffrageAgent
from agents.flux import FluxAgent
from agents.config_odoo import ConfigOdooAgent
from agents.licence import LicenceAgent
from agents.proposition import PropositionAgent
from generators.docx_gen import generate_cdc_docx
from generators.xlsx_gen import generate_chiffrage_xlsx
from generators.odoo_module_gen import generate_odoo_module
from generators.diagram_gen import generate_diagrams
from generators.pdf_gen import generate_proposition_html

logger = logging.getLogger("presales.orchestrator")

# Import RAG conditionnel (fonctionne sans si pas indexé)
try:
    from services.rag.retriever import Retriever
    _RAG_AVAILABLE = True
except ImportError:
    _RAG_AVAILABLE = False


class Pipeline:
    """
    Orchestrateur du pipeline avant-vente.

    Responsabilités :
    - Instancie les services et les agents
    - Exécute les agents dans l'ordre
    - Propage le contexte entre les agents
    - Génère les livrables dans les bons formats
    - Notifie la progression via un callback
    """

    def __init__(self):
        # Services
        self.claude = get_claude_client()
        self.uo_calculator = UOCalculator()
        self.project_history = ProjectHistory()

        # RAG (optionnel — fonctionne sans si pas indexé)
        self.retriever = None
        if _RAG_AVAILABLE:
            try:
                retriever = Retriever()
                if retriever.store.collection_count(retriever.collection) > 0:
                    self.retriever = retriever
                    logger.info(f"RAG activé : {retriever.store.collection_count(retriever.collection)} chunks disponibles")
                else:
                    logger.info("RAG : collection vide — lancez l'ingestion PDF pour activer")
            except Exception as e:
                logger.info(f"RAG non disponible : {e}")
        else:
            logger.info("RAG non disponible (dépendances manquantes)")

        # Agents
        self.agents = {
            "cdc": CDCAgent(claude=self.claude, retriever=self.retriever),
            "chiffrage": ChiffrageAgent(
                claude=self.claude,
                uo_calculator=self.uo_calculator,
                project_history=self.project_history,
            ),
            "flux": FluxAgent(claude=self.claude),
            "config_odoo": ConfigOdooAgent(claude=self.claude),
            "licence": LicenceAgent(claude=self.claude),
            "proposition": PropositionAgent(claude=self.claude),
        }

        logger.info(
            f"Pipeline initialisé — Claude: {self.claude.__class__.__name__}, "
            f"Agents: {list(self.agents.keys())}, "
            f"Historique: {self.project_history.count} projets"
        )


    def run(
        self,
        data: dict,
        output_dir: Path,
        on_progress: Callable[[str, int], None] | None = None,
    ) -> dict:
        """
        Exécute le pipeline complet.

        Args:
            data: Données du formulaire (clés: reponses, societe)
            output_dir: Répertoire où écrire les livrables
            on_progress: Callback(message, progress_pct) pour le suivi

        Returns:
            Contexte complet avec les résultats de tous les agents
        """
        progress = on_progress or (lambda msg, pct: None)

        reponses = data["reponses"]
        societe = data["societe"]

        context = {
            "reponses": reponses,
            "societe": societe,
            "entreprise": societe,
            "_project_dir": output_dir
        }

        # ── Étape 1 : Agent CDC ────────────────────────────
        progress("Agent CDC — Rédaction du cahier des charges…", 15)
        context["cdc"] = self.agents["cdc"].run(context)

        # ── Étape 2 : Agent Chiffrage ──────────────────────
        progress("Agent Chiffrage — Calcul et ajustement des UO…", 30)
        context["chiffrage"] = self.agents["chiffrage"].run(context)

        # ── Étape 3 : Agent Flux ───────────────────────────
        progress("Agent Flux — Génération des schémas de flux…", 48)
        context["flux"] = self.agents["flux"].run(context)

        # ── Étape 4 : Agent Config Odoo ────────────────────
        progress("Agent Config — Création du module Odoo…", 62)
        context["config"] = self.agents["config_odoo"].run(context)

        # ── Étape 5 : Agent Licences ───────────────────────
        progress("Agent Licences — Recommandation du plan de licences…", 74)
        context["licences"] = self.agents["licence"].run(context)

        # ── Étape 6 : Agent Proposition ────────────────────
        progress("Agent Proposition — Compilation de la propale…", 86)
        context["propale"] = self.agents["proposition"].run(context)

        # ── Étape 7 : Génération des livrables ─────────────
        progress("Génération des fichiers livrables…", 93)
        self._generate_deliverables(output_dir, context)

        return context

    def _generate_deliverables(self, output_dir: Path, context: dict):
        """Génère tous les livrables dans les formats finaux."""
        societe = context.get("societe", {})
        context_to_save = {k: v for k, v in context.items() if not k.startswith("_")}
        self._save_json(output_dir / "all_results.json", context_to_save)

        # CDC → Word
        if "cdc" in context:
            try:
                generate_cdc_docx(
                    context["cdc"],
                    output_dir / "cahier_des_charges.docx",
                    societe=societe,
                )
            except Exception as e:
                logger.error(f"Erreur génération CDC docx : {e}")
            self._save_json(output_dir / "cahier_des_charges.json", context["cdc"])

        # Chiffrage → Excel + JSON
        if "chiffrage" in context:
            try:
                generate_chiffrage_xlsx(
                    context["chiffrage"],
                    output_dir / "chiffrage.xlsx",
                    societe=societe,
                )
            except Exception as e:
                logger.error(f"Erreur génération chiffrage xlsx : {e}")
            # Toujours garder le JSON brut
            self._save_json(output_dir / "chiffrage.json", context["chiffrage"])

        # Flux → Mermaid + HTML
        if "flux" in context:
            try:
                generate_diagrams(context["flux"], output_dir)
            except Exception as e:
                logger.error(f"Erreur génération diagrammes : {e}")
            self._save_json(output_dir / "flux_metier.json", context["flux"])

        # Config → Module Odoo ZIP
        if "config" in context:
            try:
                generate_odoo_module(
                    context["config"],
                    output_dir / "module_odoo_config.zip",
                    societe=societe,
                )
            except Exception as e:
                logger.error(f"Erreur génération module Odoo : {e}")
            self._save_json(output_dir / "config_odoo.json", context["config"])

        # Licences → JSON
        if "licences" in context:
            self._save_json(output_dir / "licences.json", context["licences"])

        # Proposition → HTML
        if "propale" in context:
            try:
                generate_proposition_html(
                    context["propale"],
                    output_dir / "proposition.html",
                    societe=societe,
                )
            except Exception as e:
                logger.error(f"Erreur génération proposition : {e}")
            self._save_json(output_dir / "proposition.json", context["propale"])

    @staticmethod
    def _save_json(path: Path, data: dict):
        """Sauvegarde un dictionnaire en JSON formaté."""
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )