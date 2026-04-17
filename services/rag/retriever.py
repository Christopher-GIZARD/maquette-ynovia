"""
Ynov'iT Presales Pipeline — Retriever

Interface haut niveau utilisée par les agents pour chercher
dans la base de connaissances vectorielle.

Gère le mapping entre les modules du formulaire (has_sale, has_stock)
et les modules de la doc Odoo (sale, stock).
"""

import logging
from services.rag.embedder import get_embedder
from services.rag.vector_store import VectorStore

logger = logging.getLogger("presales.rag.retriever")

# Mapping des questions formulaire vers les modules doc
FORMULAIRE_TO_DOC_MODULE = {
    "has_crm": ["crm"],
    "has_sale": ["sale"],
    "has_purchase": ["purchase"],
    "has_account": ["account"],
    "has_stock": ["stock"],
    "has_project": ["project", "hr_timesheet"],
    "has_manufacturing": ["mrp"],
    "has_hr": ["hr", "hr_attendance", "hr_holidays", "hr_recruitment", "hr_expense"],
    "has_helpdesk": ["helpdesk"],
    "has_field_service": ["field_service"],
    "has_website": ["website", "website_sale"],
    "has_maintenance": ["maintenance"],
    "has_repair": ["repair"],
    "has_rental": ["rental"],
    "has_kits_vente": ["mrp", "sale"],
    "has_edi": ["account"],
}


class Retriever:
    """
    Recherche des passages pertinents dans la base documentaire.

    Usage:
        retriever = Retriever()

        # Recherche libre
        results = retriever.search("comment configurer les variantes produits")

        # Recherche filtrée par modules activés
        results = retriever.search_for_modules(
            query="configuration des routes logistiques",
            active_modules=["has_sale", "has_stock"]
        )

        # Recherche contextuelle pour un agent
        context = retriever.get_context_for_agent(
            agent_name="config_odoo",
            reponses={"has_sale": True, "has_stock": True, ...},
            max_tokens=3000
        )
    """

    def __init__(self, collection: str = "odoo_user_docs"):
        self.collection = collection
        self.store = VectorStore()
        self.embedder = get_embedder()

        count = self.store.collection_count(collection)
        if count == 0:
            logger.warning(
                f"Collection '{collection}' vide. "
                f"Lancez l'ingestion : python -m services.rag.pdf_ingester <pdf>"
            )
        else:
            logger.info(f"Retriever initialisé : {count} chunks dans '{collection}'")

    def search(
        self,
        query: str,
        n_results: int = 5,
        module_filter: str | None = None,
    ) -> list[dict]:
        """
        Recherche sémantique dans la base documentaire.

        Args:
            query: Texte de recherche en langage naturel
            n_results: Nombre de résultats
            module_filter: Filtrer sur un module spécifique

        Returns:
            Liste de résultats avec text, metadata, distance
        """
        query_emb = self.embedder.embed_single(query)

        where = None
        if module_filter:
            where = {"module": module_filter}

        results = self.store.search(
            collection_name=self.collection,
            query_embedding=query_emb,
            n_results=n_results,
            where=where,
        )

        return results

    def search_for_modules(
        self,
        query: str,
        active_modules: list[str],
        n_per_module: int = 3,
    ) -> list[dict]:
        """
        Recherche dans les modules activés du formulaire.

        Pour chaque module activé, récupère les n passages
        les plus pertinents par rapport à la query.

        Args:
            query: Texte de recherche
            active_modules: Liste des has_* activés (ex: ["has_sale", "has_stock"])
            n_per_module: Résultats par module

        Returns:
            Liste de résultats dédupliqués, triés par pertinence
        """
        doc_modules = set()
        for has_mod in active_modules:
            doc_modules.update(FORMULAIRE_TO_DOC_MODULE.get(has_mod, []))

        all_results = []
        seen_ids = set()

        for mod in doc_modules:
            results = self.search(query, n_results=n_per_module, module_filter=mod)
            for r in results:
                if r["id"] not in seen_ids:
                    seen_ids.add(r["id"])
                    all_results.append(r)

        # Trier par distance (plus petit = plus pertinent)
        all_results.sort(key=lambda x: x["distance"])
        return all_results

    def get_context_for_agent(
        self,
        agent_name: str,
        reponses: dict,
        max_chars: int = 8000,
    ) -> str:
        """
        Génère un bloc de contexte prêt à injecter dans le prompt d'un agent.

        Construit des queries pertinentes en fonction de l'agent et des
        réponses du formulaire, récupère les passages, et les formate
        en un texte structuré.

        Args:
            agent_name: Nom de l'agent (cdc, chiffrage, flux, config_odoo, licence, proposition)
            reponses: Réponses du formulaire
            max_chars: Taille max du contexte généré

        Returns:
            Texte formaté prêt à injecter dans le message de l'agent
        """
        # Modules activés
        active_modules = [
            qid for qid, val in reponses.items()
            if qid.startswith("has_") and val is True
        ]

        if not active_modules:
            return ""

        # Construire les queries selon l'agent
        queries = self._build_queries(agent_name, reponses, active_modules)

        # Récupérer les passages
        all_results = []
        seen_ids = set()

        for query in queries:
            results = self.search_for_modules(
                query=query,
                active_modules=active_modules,
                n_per_module=2,
            )
            for r in results:
                if r["id"] not in seen_ids:
                    seen_ids.add(r["id"])
                    all_results.append(r)

        # Trier par pertinence et tronquer
        all_results.sort(key=lambda x: x["distance"])

        context_parts = []
        total_chars = 0

        for r in all_results:
            text = r["text"]
            if total_chars + len(text) > max_chars:
                break
            module = r["metadata"].get("module", "?")
            section = r["metadata"].get("section", "?")
            context_parts.append(f"[{module} — {section}]\n{text}")
            total_chars += len(text)

        if not context_parts:
            return ""

        header = (
            f"## Documentation Odoo 19 (extraits pertinents)\n\n"
            f"Les passages suivants sont extraits de la documentation officielle Odoo 19 "
            f"et concernent les modules activés par le prospect.\n\n"
        )

        return header + "\n\n---\n\n".join(context_parts)

    @staticmethod
    def _build_queries(agent_name: str, reponses: dict, active_modules: list[str]) -> list[str]:
        """Construit des queries de recherche adaptées à chaque agent."""
        queries = []

        # Queries de base par module activé
        module_labels = {
            "has_crm": "CRM gestion prospects opportunités",
            "has_sale": "ventes devis commandes facturation",
            "has_purchase": "achats commandes fournisseurs",
            "has_account": "comptabilité facturation journaux",
            "has_stock": "stock inventaire entrepôt logistique",
            "has_project": "projet tâches feuilles de temps",
            "has_manufacturing": "fabrication production ordre de fabrication nomenclature",
            "has_hr": "ressources humaines employés congés",
            "has_helpdesk": "helpdesk tickets support",
            "has_field_service": "intervention terrain field service",
            "has_website": "site web ecommerce",
            "has_maintenance": "maintenance équipements",
            "has_repair": "réparation",
            "has_rental": "location",
        }

        for mod in active_modules:
            if mod in module_labels:
                queries.append(module_labels[mod])

        # Queries spécifiques selon l'agent
        if agent_name == "config_odoo":
            queries.append("configuration paramétrage activation module")
            if reponses.get("sale_variantes") and reponses["sale_variantes"] != "Non":
                queries.append("variantes produit attributs configuration")
            if reponses.get("stock_routes"):
                queries.append("routes logistiques multi-étapes réception livraison")
            if reponses.get("nb_societes", 1) > 1:
                queries.append("multi-société inter-compagnie configuration")

        elif agent_name == "cdc":
            queries.append("fonctionnalités principales configuration")
            if reponses.get("migration_donnees"):
                queries.append("import données migration reprise")

        elif agent_name == "flux":
            queries.append("flux processus workflow étapes")
            if "has_stock" in active_modules:
                queries.append("réception expédition livraison picking")
            if "has_manufacturing" in active_modules:
                queries.append("ordre fabrication planification production")

        elif agent_name == "chiffrage":
            queries.append("complexité configuration personnalisation")

        return queries[:8]  # Max 8 queries pour ne pas surcharger
