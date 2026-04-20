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
            "siren": siren,
            "champs_supplementaires": "sites_internet",
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

        # Effectif — on conserve la tranche textuelle brute (ex: "10 à 19 salariés")
        effectif = raw.get("effectif") or raw.get("tranche_effectif") or ""
        if effectif and not isinstance(effectif, str):
            effectif = str(effectif)

        # Dirigeants
        dirigeants = raw.get("representants", [])
        dirigeant_principal = None
        if dirigeants:
            d = dirigeants[0]
            nom = f"{d.get('prenom', '')} {d.get('nom', '')}".strip()
            qualite = d.get("qualite", "")
            if nom:
                dirigeant_principal = f"{nom} ({qualite})" if qualite else nom

        # Catégorisation prospect (2 axes)
        effectif_num = _parse_effectif(raw.get("effectif"))
        finance_data = {
            "ca":            ca_annuel,
            "resultat":      resultat_net,
            "fonds_propres": finances[0].get("fonds_propres") if finances else None,
            "marge_nette":   (
                round(resultat_net / ca_annuel * 100, 1)
                if ca_annuel and resultat_net else None
            ),
            "taux_croissance_ca": (
                round(
                    (finances[0]["chiffre_affaires"] / finances[1]["chiffre_affaires"] - 1) * 100, 1
                )
                if len(finances) >= 2 and finances[1].get("chiffre_affaires")
                else None
            ),
        }
        categorie = _categorize_prospect(effectif_num, finance_data)

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
            "activite_principale": raw.get("libelle_code_naf", ""),
            "ca_annuel": _to_k_euros(ca_annuel),
            "resultat_net": _to_k_euros(resultat_net),

            # Localisation
            "adresse": _build_adresse(siege),
            "code_postal": siege.get("code_postal", ""),
            "ville": siege.get("ville", ""),

            # Contact
            "site_web": (raw.get("sites_internet") or [None])[0] or "",
            "dirigeant_principal": dirigeant_principal,
            "numero_tva": raw.get("numero_tva_intracommunautaire", ""),

            # Statut
            "statut": raw.get("statut_rcs", ""),
            "capital_social": raw.get("capital", None),

            # Catégorisation (2 axes)
            "categorie": categorie,

            # Méta
            "_source": "pappers",
        }


def _parse_effectif(effectif_raw) -> int | None:
    """Parse l'effectif depuis la réponse Pappers (peut être str ou int).

    Gère les formats :
    - int/float : 1500
    - str simple : "10 à 19 salariés"
    - str avec milliers : "Entre 1 000 et 1 999 salariés"
    """
    if effectif_raw is None:
        return None
    if isinstance(effectif_raw, (int, float)):
        return int(effectif_raw)
    if isinstance(effectif_raw, str):
        import re
        # Nettoyer : retirer les espaces entre chiffres (séparateurs de milliers FR)
        # "Entre 1 000 et 1 999 salariés" → "Entre 1000 et 1999 salariés"
        cleaned = re.sub(r'(\d)\s+(\d)', r'\1\2', effectif_raw)
        numbers = re.findall(r"\d+", cleaned)
        if len(numbers) >= 2:
            return (int(numbers[0]) + int(numbers[1])) // 2
        if len(numbers) == 1:
            return int(numbers[0])
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


def _categorize_prospect(effectif: int | None, finance_data: dict) -> dict:
    """
    Catégorise le prospect sur 2 axes pour ajuster le chiffrage.

    Axe 1 — Taille : basé sur effectif + CA
        Impact : complexité du projet (droits d'accès, conduite du changement,
        nombre de flux, volume de données)

    Axe 2 — Santé financière : basé sur rentabilité + croissance
        Impact : capacité d'investissement, niveau de service attendu,
        risque de coupes budgétaires

    Chaque axe produit un coefficient multiplicateur.
    Le coefficient combiné s'applique au chiffrage brut.

    Returns:
        {
            "taille": {"label": "PME", "code": "PME", "coefficient": 1.0, "detail": "..."},
            "sante": {"label": "Dynamique", "code": "DYNAMIQUE", "coefficient": 1.05, "detail": "..."},
            "coefficient_combine": 1.05,
            "resume": "PME en croissance — projet standard avec budget confortable"
        }
    """
    taille = _axe_taille(effectif, finance_data.get("ca"))
    sante = _axe_sante_financiere(finance_data)
    coeff_combine = round(taille["coefficient"] * sante["coefficient"], 2)

    # Résumé en langage naturel pour les agents
    resume = f"{taille['label']} {sante['detail']}"

    return {
        "taille": taille,
        "sante": sante,
        "coefficient_combine": coeff_combine,
        "resume": resume,
    }


def _axe_taille(effectif: int | None, ca_euros: float | None) -> dict:
    """
    Axe 1 — Taille de l'entreprise.

    Critères INSEE/UE + impact projet Odoo.

    Seuils :
        Micro   : < 10 salariés  ET  CA < 2 M€     → coeff 0.85
        TPE     : < 50 salariés  OU  CA < 10 M€     → coeff 0.95
        PME     : < 250 salariés ET  CA < 50 M€     → coeff 1.00 (base)
        ETI     : < 5000 salariés ET CA < 1 500 M€  → coeff 1.15
        GE      : >= 5000 salariés OU CA >= 1 500 M€ → coeff 1.25
    """
    eff = effectif or 0
    ca_me = (ca_euros / 1_000_000) if ca_euros else 0

    if eff < 10 and ca_me < 2:
        return {"label": "Micro-entreprise", "code": "MICRO", "coefficient": 0.85,
                "detail": f"{eff} sal., {ca_me:.1f} M€ CA"}
    elif eff < 50 and ca_me < 10:
        return {"label": "TPE", "code": "TPE", "coefficient": 0.95,
                "detail": f"{eff} sal., {ca_me:.1f} M€ CA"}
    elif eff < 250 and ca_me < 50:
        return {"label": "PME", "code": "PME", "coefficient": 1.0,
                "detail": f"{eff} sal., {ca_me:.1f} M€ CA"}
    elif eff < 5000 and ca_me < 1500:
        return {"label": "ETI", "code": "ETI", "coefficient": 1.15,
                "detail": f"{eff} sal., {ca_me:.1f} M€ CA"}
    else:
        return {"label": "Grande entreprise", "code": "GE", "coefficient": 1.25,
                "detail": f"{eff} sal., {ca_me:.1f} M€ CA"}


def _axe_sante_financiere(finance_data: dict) -> dict:
    """
    Axe 2 — Santé financière.

    Basé sur 3 indicateurs :
    - Rentabilité : marge nette (résultat / CA)
    - Croissance : évolution du CA sur la dernière année
    - Solidité : fonds propres positifs ou négatifs

    Catégories :
        Fragile    : résultat négatif OU fonds propres négatifs   → coeff 0.90
        Stable     : résultat positif, croissance faible (< 5%)   → coeff 1.00
        Dynamique  : résultat positif ET croissance > 5%           → coeff 1.05
        Premium    : marge nette > 8% ET croissance > 10%          → coeff 1.10
    """
    resultat = finance_data.get("resultat")
    fonds_propres = finance_data.get("fonds_propres")
    marge_nette = finance_data.get("marge_nette")
    croissance = finance_data.get("taux_croissance_ca")

    # Pas de données financières
    if resultat is None and fonds_propres is None:
        return {"label": "Inconnu", "code": "INCONNU", "coefficient": 1.0,
                "detail": "— données financières non disponibles"}

    # Fragile : résultat négatif ou fonds propres négatifs
    if (resultat is not None and resultat < 0) or \
            (fonds_propres is not None and fonds_propres < 0):
        indicators = []
        if resultat is not None and resultat < 0:
            indicators.append(f"résultat négatif ({resultat / 1_000_000:.1f} M€)")
        if fonds_propres is not None and fonds_propres < 0:
            indicators.append(f"fonds propres négatifs")
        return {"label": "Fragile", "code": "FRAGILE", "coefficient": 0.90,
                "detail": f"— {', '.join(indicators)}"}

    # Premium : très rentable ET forte croissance
    marge = marge_nette if marge_nette is not None else 0
    crois = croissance if croissance is not None else 0

    if marge > 8 and crois > 10:
        return {"label": "Premium", "code": "PREMIUM", "coefficient": 1.10,
                "detail": f"— marge nette {marge}%, croissance {crois}%"}

    # Dynamique : rentable avec croissance
    if resultat is not None and resultat > 0 and crois > 5:
        return {"label": "Dynamique", "code": "DYNAMIQUE", "coefficient": 1.05,
                "detail": f"— croissance {crois}%, résultat positif"}

    # Stable : rentable mais faible croissance
    return {"label": "Stable", "code": "STABLE", "coefficient": 1.0,
            "detail": f"— résultat positif, croissance {crois}%"}