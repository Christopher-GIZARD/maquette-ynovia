"""
Ynov'iT Presales Pipeline — Historique des projets

Stocke et recherche les projets passés pour alimenter
l'agent chiffrage avec des données de comparaison.

Phase 1 (actuelle) : stockage JSON fichier, recherche par score de distance
Phase 2 (futur)    : migration vers base vectorielle (pgvector)

Le score de similarité est calculé sur :
- Modules activés en commun (poids le plus fort)
- Taille de l'entreprise (effectif, CA)
- Complexité (multi-société, variantes, nombre d'entrepôts)
"""

import json
import logging
from pathlib import Path
from datetime import datetime

import config

logger = logging.getLogger("presales.history")

HISTORY_FILE = config.OUTPUTS_DIR / "_project_history.json"


class ProjectHistory:
    """
    Gestionnaire de l'historique des projets.

    Stocke les projets terminés avec leur chiffrage estimé
    et réel, et permet de retrouver les projets les plus
    similaires à un nouveau prospect.
    """

    def __init__(self, history_path: Path | None = None):
        self.path = history_path or HISTORY_FILE
        self._history = self._load()

    def _load(self) -> list[dict]:
        """Charge l'historique depuis le fichier JSON."""
        if not self.path.exists():
            return []
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            logger.warning(f"Historique corrompu ou illisible : {self.path}")
            return []

    def _save(self):
        """Persiste l'historique sur disque."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self._history, f, indent=2, ensure_ascii=False)

    @property
    def count(self) -> int:
        """Nombre de projets en historique."""
        return len(self._history)

    def add_project(
        self,
        project_id: str,
        societe: dict,
        reponses: dict,
        chiffrage_estime: dict,
        chiffrage_reel: dict | None = None,
        notes: str = "",
    ):
        """
        Ajoute un projet à l'historique.

        Args:
            project_id: Identifiant unique du projet
            societe: Infos entreprise (effectif, CA, secteur)
            reponses: Réponses du formulaire
            chiffrage_estime: Résultat du calculateur UO + ajustement IA
            chiffrage_reel: Chiffrage réel constaté (ajouté plus tard)
            notes: Commentaires du chef de projet sur les écarts
        """
        # Extraire les caractéristiques clés pour la recherche
        features = self._extract_features(reponses, societe)

        entry = {
            "project_id": project_id,
            "date": datetime.now().isoformat(),
            "societe": {
                "raison_sociale": societe.get("raison_sociale", ""),
                "secteur_activite": societe.get("secteur_activite", ""),
                "effectif": societe.get("effectif"),
                "ca_annuel": societe.get("ca_annuel"),
            },
            "features": features,
            "chiffrage_estime": chiffrage_estime,
            "chiffrage_reel": chiffrage_reel,
            "notes": notes,
        }

        self._history.append(entry)
        self._save()

        logger.info(
            f"Projet ajouté à l'historique : {project_id} "
            f"({self.count} projets au total)"
        )

    def update_reel(
        self,
        project_id: str,
        chiffrage_reel: dict,
        notes: str = "",
    ):
        """
        Met à jour le chiffrage réel d'un projet terminé.

        C'est cette donnée qui permet la boucle de retour
        et l'amélioration continue du chiffrage.
        """
        for entry in self._history:
            if entry["project_id"] == project_id:
                entry["chiffrage_reel"] = chiffrage_reel
                entry["notes"] = notes
                self._save()
                logger.info(f"Chiffrage réel mis à jour pour {project_id}")
                return True

        logger.warning(f"Projet introuvable pour mise à jour : {project_id}")
        return False

    def find_similar(
        self,
        reponses: dict,
        societe: dict | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        """
        Trouve les projets les plus similaires au nouveau prospect.

        Retourne une liste de projets triés par score de similarité
        décroissant, prêts à être injectés dans le prompt de l'agent.

        Args:
            reponses: Réponses du formulaire du nouveau prospect
            societe: Infos entreprise (optionnel, améliore la recherche)
            limit: Nombre max de résultats

        Returns:
            Liste de dicts avec les infos projet + score de similarité
        """
        if not self._history:
            logger.info("Aucun projet en historique — phase démarrage à froid")
            return []

        limit = limit or config.SIMILAR_PROJECTS_LIMIT
        new_features = self._extract_features(reponses, societe or {})

        scored = []
        for entry in self._history:
            score = self._similarity_score(new_features, entry["features"])
            scored.append((score, entry))

        # Tri par score décroissant
        scored.sort(key=lambda x: x[0], reverse=True)

        results = []
        for score, entry in scored[:limit]:
            # Format simplifié pour injection dans le prompt
            result = {
                "project_id": entry["project_id"],
                "societe": entry["societe"]["raison_sociale"],
                "secteur": entry["societe"].get("secteur_activite", ""),
                "score_similarite": round(score, 2),
                "modules": entry["features"]["modules"],
                "chiffrage_estime": entry.get("chiffrage_estime", {}),
                "chiffrage_reel": entry.get("chiffrage_reel"),
                "ecart_pct": self._compute_ecart(entry),
                "notes": entry.get("notes", ""),
            }
            results.append(result)

        logger.info(
            f"Recherche similarité : {len(results)} projets trouvés "
            f"(meilleur score : {results[0]['score_similarite'] if results else 0})"
        )

        return results

    @staticmethod
    def _extract_features(reponses: dict, societe: dict) -> dict:
        """
        Extrait les caractéristiques clés pour le calcul de similarité.

        Ces features sont stockées avec chaque projet et comparées
        lors de la recherche.
        """
        # Modules activés
        modules = sorted([
            qid for qid, val in reponses.items()
            if qid.startswith("has_") and val is True
        ])

        # Indicateurs de complexité
        nb_societes = reponses.get("nb_societes", 1)
        nb_users = reponses.get("nb_users_internes", 0)
        has_variantes = reponses.get("sale_variantes", "Non") != "Non"
        has_manufacturing = reponses.get("has_manufacturing", False)
        has_migration = reponses.get("migration_donnees", False)
        multi_company = nb_societes > 1

        # Taille entreprise
        effectif = societe.get("effectif", 0) or 0
        ca = societe.get("ca_annuel", 0) or 0

        return {
            "modules": modules,
            "nb_modules": len(modules),
            "nb_societes": nb_societes,
            "nb_users": nb_users,
            "multi_company": multi_company,
            "has_variantes": has_variantes,
            "has_manufacturing": has_manufacturing,
            "has_migration": has_migration,
            "effectif": effectif,
            "ca": ca,
        }

    @staticmethod
    def _similarity_score(new: dict, existing: dict) -> float:
        """
        Calcule un score de similarité entre 0 et 1.

        Pondérations :
        - Modules en commun : 50% (le critère le plus discriminant)
        - Nombre d'utilisateurs : 15%
        - Taille entreprise : 10%
        - Complexité (variantes, fabrication, multi-société) : 25%
        """
        score = 0.0

        # ── Modules en commun (Jaccard) — poids 0.50
        set_new = set(new["modules"])
        set_old = set(existing["modules"])
        if set_new or set_old:
            jaccard = len(set_new & set_old) / len(set_new | set_old)
            score += 0.50 * jaccard

        # ── Nombre d'utilisateurs — poids 0.15
        if new["nb_users"] > 0 and existing["nb_users"] > 0:
            ratio = min(new["nb_users"], existing["nb_users"]) / max(new["nb_users"], existing["nb_users"])
            score += 0.15 * ratio

        # ── Taille entreprise (effectif) — poids 0.10
        if new["effectif"] > 0 and existing["effectif"] > 0:
            ratio = min(new["effectif"], existing["effectif"]) / max(new["effectif"], existing["effectif"])
            score += 0.10 * ratio

        # ── Complexité — poids 0.25
        complexity_matches = 0
        complexity_total = 4
        if new["multi_company"] == existing["multi_company"]:
            complexity_matches += 1
        if new["has_variantes"] == existing["has_variantes"]:
            complexity_matches += 1
        if new["has_manufacturing"] == existing["has_manufacturing"]:
            complexity_matches += 1
        if new["has_migration"] == existing["has_migration"]:
            complexity_matches += 1
        score += 0.25 * (complexity_matches / complexity_total)

        return score

    @staticmethod
    def _compute_ecart(entry: dict) -> float | None:
        """
        Calcule l'écart en % entre estimé et réel.

        Retourne None si le chiffrage réel n'est pas encore disponible.
        Positif = dépassement, Négatif = sous-consommation.
        """
        reel = entry.get("chiffrage_reel")
        estime = entry.get("chiffrage_estime")

        if not reel or not estime:
            return None

        total_estime = estime.get("total_uo", 0)
        total_reel = reel.get("total_uo", 0)

        if total_estime == 0:
            return None

        return round((total_reel - total_estime) / total_estime * 100, 1)