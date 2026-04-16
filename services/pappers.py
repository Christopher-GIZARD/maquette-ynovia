"""
Ynov'iT Presales Pipeline — Client API Pappers

Enrichit les données société à partir du numéro SIREN via
l'API Pappers (https://www.pappers.fr/api/documentation).

Récupère les informations légales, financières et de contact
pour compléter le formulaire et alimenter les agents.
"""

import logging
from typing import Any

import requests

import config

logger = logging.getLogger("presales.pappers")

PAPPERS_BASE_URL = "https://api.pappers.fr/v2"


class PappersClient:
    """
    Client pour l'API Pappers.

    Usage:
        client = PappersClient()
        data = client.enrich("443061841")
        print(data["raison_sociale"], data["effectif"])
    """

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or config.PAPPERS_API_KEY
        if not self.api_key:
            raise ValueError(
                "Clé API Pappers manquante. "
                "Définissez PAPPERS_API_KEY dans le .env."
            )

    def enrich(self, siren: str) -> dict:
        """
        Récupère les informations d'une entreprise à partir de son SIREN.

        Args:
            siren: Numéro SIREN (9 chiffres) ou SIRET (14 chiffres)

        Returns:
            Dictionnaire avec les infos enrichies, prêt à être
            injecté dans le contexte du pipeline.
            Retourne un dict partiel en cas d'erreur (jamais de crash).
        """
        if not siren:
            logger.warning("SIREN vide — enrichissement ignoré")
            return {}

        # Nettoyer le SIREN (espaces, tirets)
        siren_clean = siren.replace(" ", "").replace("-", "").replace(".", "")

        try:
            raw = self._call_api(siren_clean)
            enriched = self._parse_response(raw)
            logger.info(
                f"Enrichissement Pappers OK : {enriched.get('raison_sociale', '?')} "
                f"(SIREN {siren_clean})"
            )
            return enriched

        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response else "?"
            if status == 404:
                logger.warning(f"SIREN {siren_clean} introuvable sur Pappers")
            elif status == 401:
                logger.error("Clé API Pappers invalide ou expirée")
            elif status == 429:
                logger.warning("Rate limit Pappers atteint")
            else:
                logger.error(f"Erreur Pappers HTTP {status} : {e}")
            return {"siren": siren_clean, "_pappers_error": str(e)}

        except requests.exceptions.RequestException as e:
            logger.error(f"Erreur réseau Pappers : {e}")
            return {"siren": siren_clean, "_pappers_error": str(e)}

        except Exception as e:
            logger.error(f"Erreur inattendue Pappers : {e}")
            return {"siren": siren_clean, "_pappers_error": str(e)}

    def _call_api(self, siren: str) -> dict:
        """Appelle l'endpoint entreprise de l'API Pappers."""
        params = {
            "siren": siren
        }
        headers = {
            "api-key": self.api_key
        }

        response = requests.get(
            f"{PAPPERS_BASE_URL}/entreprise",
            params=params,
            headers=headers,
            timeout=10,
        )
        response.raise_for_status()

        return response.json()

    @staticmethod
    def _parse_response(raw: dict) -> dict:
        """
        Extrait les champs pertinents de la réponse Pappers
        et les mappe sur la structure attendue par le pipeline.
        """
        # Siège social
        siege = raw.get("siege", {})

        # Dernier chiffre d'affaires disponible dans les finances
        finances = raw.get("finances", [])
        ca_annuel = None
        resultat_net = None
        if finances:
            derniere_annee = finances[0]  # La plus récente en premier
            ca_annuel = derniere_annee.get("chiffre_affaires")
            resultat_net = derniere_annee.get("resultat")

        # Effectif — Pappers retourne une tranche ou un nombre
        effectif_raw = raw.get("effectif")
        effectif = _parse_effectif(effectif_raw)

        # Dirigeants
        dirigeants = raw.get("representants", [])
        dirigeant_principal = None
        if dirigeants:
            d = dirigeants[0]
            nom = f"{d.get('prenom', '')} {d.get('nom', '')}".strip()
            qualite = d.get("qualite", "")
            dirigeant_principal = f"{nom} ({qualite})" if qualite else nom

        return {
            # Identité
            "siren": raw.get("siren", ""),
            "siret_siege": raw.get("siret_siege", siege.get("siret", "")),
            "raison_sociale": raw.get("nom_entreprise", ""),
            "forme_juridique": raw.get("forme_juridique", ""),
            "date_creation": raw.get("date_creation", ""),

            # Activité
            "code_naf": raw.get("code_naf", ""),
            "libelle_naf": raw.get("libelle_code_naf", ""),
            "secteur_activite": raw.get("domaine_activite", raw.get("libelle_code_naf", "")),
            "objet_social": raw.get("objet_social", ""),

            # Taille
            "effectif": effectif,
            "effectif_tranche": raw.get("tranche_effectif", ""),
            "ca_annuel": _to_k_euros(ca_annuel),
            "resultat_net": _to_k_euros(resultat_net),

            # Localisation
            "adresse": _build_adresse(siege),
            "code_postal": siege.get("code_postal", ""),
            "ville": siege.get("ville", ""),

            # Contact
            "dirigeant_principal": dirigeant_principal,
            "numero_tva": raw.get("numero_tva_intracommunautaire", ""),

            # Statut
            "statut": raw.get("statut_rcs", ""),
            "capital_social": raw.get("capital", None),

            # Méta
            "_source": "pappers",
        }


def _parse_effectif(effectif_raw) -> int | None:
    """Parse l'effectif depuis la réponse Pappers (peut être str ou int)."""
    if effectif_raw is None:
        return None
    if isinstance(effectif_raw, (int, float)):
        return int(effectif_raw)
    # Tranche textuelle : "10 à 19 salariés" → prend le milieu
    if isinstance(effectif_raw, str):
        import re
        numbers = re.findall(r"\d+\s*\d+", effectif_raw)
        if len(numbers) >= 2:
            return (int(numbers[0].replace(" ", "")) + int(numbers[1].replace(" ", ""))) // 2
        if len(numbers) == 1:
            return int(numbers[0].replace(" ", ""))
    return None


def _to_k_euros(value) -> float | None:
    """Convertit un montant en k€ (Pappers retourne en euros)."""
    if value is None:
        return None
    try:
        return round(float(value) / 1000, 1)
    except (ValueError, TypeError):
        return None


def _build_adresse(siege: dict) -> str:
    """Construit une adresse complète depuis l'objet siège."""
    parts = []
    if siege.get("numero_voie"):
        parts.append(str(siege["numero_voie"]))
    if siege.get("type_voie"):
        parts.append(siege["type_voie"])
    if siege.get("libelle_voie"):
        parts.append(siege["libelle_voie"])

    ligne1 = " ".join(parts)
    ligne2 = f"{siege.get('code_postal', '')} {siege.get('ville', '')}".strip()

    return f"{ligne1}, {ligne2}" if ligne1 else ligne2