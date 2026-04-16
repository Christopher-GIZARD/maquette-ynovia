"""
Ynov'iT Presales Pipeline — Mock Client Claude

Simule les réponses de l'API Claude pour permettre le développement
et les tests sans clé API.

Utilise les données reçues dans le message pour construire
des réponses réalistes et structurées.

Usage :
    Dans .env → CLAUDE_MODE=mock
    Le pipeline utilisera automatiquement ce client.
"""

import json
import time
import logging
import re

logger = logging.getLogger("presales.claude.mock")


class MockClaudeClient:
    """
    Client mock qui simule les réponses Claude.

    Même interface que ClaudeClient — les agents n'y voient
    que du feu.
    """

    def __init__(self, **kwargs):
        """Accepte les mêmes paramètres que ClaudeClient (et les ignore)."""
        logger.info("MockClaudeClient initialisé — mode développement")

    def send(
        self,
        system: str,
        message: str,
        max_tokens: int | None = None,
        temperature: float | None = None,
        max_retries: int = 3,
    ) -> str:
        """
        Simule un appel Claude.

        Détecte le type d'agent à partir du prompt système
        et retourne une réponse réaliste.
        """
        logger.info(
            f"[MOCK] Appel simulé — "
            f"system={len(system)} chars, message={len(message)} chars"
        )

        # Petit délai pour simuler la latence réseau
        time.sleep(0.3)

        # Identifier l'agent à partir du contenu du prompt système
        response = self._route_response(system, message)

        logger.info(f"[MOCK] Réponse générée — {len(response)} chars")
        return response

    def send_json(
        self,
        system: str,
        message: str,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> dict:
        """Simule un appel Claude avec réponse JSON."""
        raw = self.send(system, message, max_tokens, temperature)
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines)
        return json.loads(cleaned)

    def _route_response(self, system: str, message: str) -> str:
        """Identifie l'agent et génère la réponse appropriée."""
        system_lower = system.lower()

        if "chiffrage" in system_lower:
            return self._mock_chiffrage(message)
        elif "cahier des charges" in system_lower or "cdc" in system_lower:
            return self._mock_cdc(message)
        elif "flux" in system_lower or "schéma" in system_lower or "diagramme" in system_lower:
            return self._mock_flux(message)
        elif "config" in system_lower and "odoo" in system_lower:
            return self._mock_config_odoo(message)
        elif "licence" in system_lower:
            return self._mock_licences(message)
        elif "proposition" in system_lower or "propale" in system_lower:
            return self._mock_proposition(message)
        else:
            return self._mock_generic(message)

    def _mock_chiffrage(self, message: str) -> str:
        """Génère un chiffrage ajusté mock basé sur les données reçues."""
        # Extraire les infos du message
        modules = self._extract_modules(message)
        total_brut = self._extract_number(message, r"Total\s*:\s*([\d.]+)\s*jours")

        # Construire un ajustement réaliste (+10 à 20%)
        par_module = {}
        total_ajuste = 0

        for mod in modules:
            # Extraire le UO brut du module depuis le message
            mod_uo = self._extract_module_uo(message, mod)
            coeff = 1.15  # +15% par défaut
            ajuste = round(mod_uo * coeff, 1)
            total_ajuste += ajuste

            par_module[mod] = {
                "label": mod.replace("has_", "").replace("_", " ").title(),
                "uo_brut": mod_uo,
                "uo_ajuste": ajuste,
                "coefficient": coeff,
                "justification": f"Ajustement de +15% : marge de sécurité standard en l'absence de données historiques."
            }

        # Ajouter le général si présent
        general_uo = self._extract_module_uo(message, "_general")
        if general_uo > 0:
            coeff_gen = 1.2
            ajuste_gen = round(general_uo * coeff_gen, 1)
            total_ajuste += ajuste_gen
            par_module["_general"] = {
                "label": "Paramètres généraux",
                "uo_brut": general_uo,
                "uo_ajuste": ajuste_gen,
                "coefficient": coeff_gen,
                "justification": "Ajustement de +20% : la reprise de données et la configuration générale sont souvent sous-estimées."
            }

        if total_brut == 0:
            total_brut = total_ajuste / 1.15

        result = {
            "total_uo_brut": round(total_brut, 1),
            "total_uo_ajuste": round(total_ajuste, 1),
            "ecart_global_pct": round((total_ajuste - total_brut) / max(total_brut, 1) * 100, 1),
            "justification_globale": (
                "Ajustement global de +15% à +20% selon les modules. "
                "En l'absence de projets historiques comparables, "
                "les heuristiques métier standard ont été appliquées. "
                "La reprise de données depuis Excel justifie une marge supplémentaire."
            ),
            "par_module": par_module,
            "risques": [
                {
                    "module": "_general",
                    "description": "Qualité des données sources incertaine — la reprise depuis Excel peut révéler des incohérences nécessitant un nettoyage manuel.",
                    "impact_uo": 3,
                    "probabilite": "moyenne"
                },
                {
                    "module": "global",
                    "description": "Aucun projet historique similaire disponible — le chiffrage est basé sur les heuristiques. À affiner après les premiers ateliers.",
                    "impact_uo": 5,
                    "probabilite": "faible"
                }
            ],
            "recommandations": [
                "Prévoir un atelier de cadrage de 0.5j pour valider le périmètre avant de démarrer.",
                "Demander un échantillon des données Excel du client pour évaluer la qualité avant la reprise.",
                "Planifier une marge de 10% pour la conduite du changement si c'est le premier ERP du client."
            ]
        }

        return json.dumps(result, indent=2, ensure_ascii=False)

    def _mock_cdc(self, message: str) -> str:
        """Génère un cahier des charges mock."""
        modules = self._extract_modules(message)
        societe = self._extract_societe(message)

        sections = []

        sections.append({
            "titre": "Contexte du projet",
            "contenu": (
                f"La société {societe} souhaite mettre en place l'ERP Odoo 19 "
                f"pour couvrir les fonctions suivantes : {', '.join(m.replace('has_', '') for m in modules)}. "
                f"Ce projet s'inscrit dans une démarche de digitalisation et de structuration des processus métier."
            )
        })

        sections.append({
            "titre": "Périmètre fonctionnel",
            "contenu": "Le projet couvre les modules suivants :",
            "sous_sections": [
                {
                    "titre": mod.replace("has_", "").replace("_", " ").title(),
                    "contenu": f"Mise en place et paramétrage du module {mod.replace('has_', '')} selon les besoins exprimés dans le questionnaire."
                }
                for mod in modules
            ]
        })

        sections.append({
            "titre": "Hypothèses et prérequis",
            "contenu": (
                "Le projet est mené sur la base des hypothèses suivantes : "
                "disponibilité d'un référent métier côté client, "
                "fourniture des données de reprise en format exploitable (CSV/Excel structuré), "
                "validation des livrables sous 5 jours ouvrés."
            )
        })

        sections.append({
            "titre": "Exclusions",
            "contenu": (
                "Les éléments suivants sont exclus du périmètre : "
                "développements spécifiques non décrits dans ce document, "
                "formation des utilisateurs finaux (à chiffrer séparément), "
                "maintenance et support post-go-live."
            )
        })

        sections.append({
            "titre": "Risques identifiés",
            "contenu": (
                "Les principaux risques identifiés sont : "
                "qualité des données sources pour la reprise, "
                "disponibilité des interlocuteurs côté client, "
                "évolution du périmètre en cours de projet."
            )
        })

        result = {
            "titre": f"Cahier des charges — Projet Odoo 19 — {societe}",
            "sections": sections,
        }

        return json.dumps(result, indent=2, ensure_ascii=False)

    def _mock_flux(self, message: str) -> str:
        """Génère des schémas de flux mock en Mermaid."""
        modules = self._extract_modules(message)
        flux = []

        if "has_sale" in modules:
            flux.append({
                "nom": "Order-to-Cash",
                "description": "Flux de vente complet : du devis à l'encaissement",
                "mermaid": (
                    "graph LR\n"
                    "    A[Opportunité CRM] --> B[Devis]\n"
                    "    B --> C{Validation client}\n"
                    "    C -->|Accepté| D[Bon de commande]\n"
                    "    C -->|Refusé| E[Perdu]\n"
                    "    D --> F[Livraison]\n"
                    "    F --> G[Facturation]\n"
                    "    G --> H[Encaissement]"
                ),
                "modules_impliques": ["crm", "sale", "stock", "account"]
            })

        if "has_purchase" in modules:
            flux.append({
                "nom": "Procure-to-Pay",
                "description": "Flux d'achat complet : de la demande au paiement fournisseur",
                "mermaid": (
                    "graph LR\n"
                    "    A[Besoin] --> B[Demande de prix]\n"
                    "    B --> C[Bon de commande fournisseur]\n"
                    "    C --> D[Réception]\n"
                    "    D --> E[Contrôle facture]\n"
                    "    E --> F[Paiement fournisseur]"
                ),
                "modules_impliques": ["purchase", "stock", "account"]
            })

        if "has_manufacturing" in modules:
            flux.append({
                "nom": "Make-to-Stock",
                "description": "Flux de fabrication sur stock",
                "mermaid": (
                    "graph LR\n"
                    "    A[Prévision / Règle de stock] --> B[Ordre de fabrication]\n"
                    "    B --> C[Consommation matières]\n"
                    "    C --> D[Production]\n"
                    "    D --> E[Contrôle qualité]\n"
                    "    E --> F[Mise en stock produit fini]"
                ),
                "modules_impliques": ["manufacturing", "stock"]
            })

        if "has_stock" in modules and "has_sale" in modules:
            flux.append({
                "nom": "Flux logistique",
                "description": "Processus de gestion des entrepôts et expéditions",
                "mermaid": (
                    "graph TD\n"
                    "    A[Commande confirmée] --> B[Picking]\n"
                    "    B --> C[Colisage]\n"
                    "    C --> D[Expédition]\n"
                    "    D --> E[Mise à jour stock]\n"
                    "    E --> F[Notification client]"
                ),
                "modules_impliques": ["stock", "sale"]
            })

        result = {
            "flux": flux,
            "nb_flux": len(flux),
        }

        return json.dumps(result, indent=2, ensure_ascii=False)

    def _mock_config_odoo(self, message: str) -> str:
        """Génère une configuration de module Odoo mock."""
        modules = self._extract_modules(message)

        # Mapping module → technical module names
        module_map = {
            "has_crm": ["crm"],
            "has_sale": ["sale_management", "sale"],
            "has_purchase": ["purchase"],
            "has_account": ["account_accountant"],
            "has_stock": ["stock"],
            "has_project": ["project", "timesheet_grid"],
            "has_manufacturing": ["mrp"],
            "has_hr": ["hr", "hr_holidays", "hr_contract"],
            "has_helpdesk": ["helpdesk"],
            "has_field_service": ["industry_fsm"],
            "has_website": ["website_sale"],
            "has_maintenance": ["maintenance"],
            "has_repair": ["repair"],
            "has_rental": ["sale_renting"],
            "has_kits_vente": ["mrp"],
        }

        odoo_modules = []
        for mod in modules:
            odoo_modules.extend(module_map.get(mod, []))

        # Déduplication
        odoo_modules = sorted(set(odoo_modules))

        # Settings à activer
        settings = {}
        if "has_sale" in modules:
            settings["group_sale_order_template"] = True
            if "sale_variantes" in message and "Simples" in message:
                settings["group_product_variant"] = True
            if "sale_unites_mesure" in message:
                settings["group_uom"] = True

        if "has_stock" in modules:
            settings["group_stock_multi_locations"] = True
            if "multi-empl" in message.lower() or "multi-entrepôt" in message.lower():
                settings["group_stock_multi_warehouses"] = True

        if "has_purchase" in modules:
            settings["group_purchase_order_template"] = True

        result = {
            "manifest": {
                "name": "Configuration Avant-Vente",
                "version": "19.0.1.0.0",
                "category": "Tools",
                "depends": ["base"] + odoo_modules,
                "data": [
                    "data/res_config_settings.xml",
                ],
                "installable": True,
                "auto_install": False,
            },
            "modules_to_install": odoo_modules,
            "settings": settings,
            "security_groups": [],
            "notes": [
                "Module généré automatiquement par le pipeline avant-vente.",
                "À vérifier et ajuster après les ateliers de cadrage.",
            ]
        }

        return json.dumps(result, indent=2, ensure_ascii=False)

    def _mock_licences(self, message: str) -> str:
        """Génère une recommandation de licences mock."""
        nb_users = self._extract_number(message, r"nb_users_internes[\"']?\s*[:=]\s*(\d+)")
        nb_portail = self._extract_number(message, r"nb_users_portail[\"']?\s*[:=]\s*(\d+)")
        modules = self._extract_modules(message)

        if nb_users == 0:
            nb_users = 10  # Fallback

        result = {
            "recommandation": {
                "plan": "Standard" if len(modules) <= 5 else "Custom",
                "licences_internes": nb_users,
                "licences_portail": nb_portail,
                "cout_mensuel_estime": {
                    "par_utilisateur_interne": 31.10,
                    "par_utilisateur_portail": 0,
                    "total_mensuel": round(nb_users * 31.10 + nb_portail * 0, 2),
                    "total_annuel": round((nb_users * 31.10) * 12, 2),
                },
            },
            "justification": (
                f"Avec {nb_users} utilisateurs internes et {len(modules)} modules activés, "
                f"le plan {'Standard' if len(modules) <= 5 else 'Custom'} est recommandé. "
                f"Les utilisateurs portail ({nb_portail}) sont inclus sans surcoût."
            ),
            "details_par_role": [
                {
                    "role": "Administrateur / Direction",
                    "nb_users": min(2, nb_users),
                    "acces": "Tous les modules",
                    "type_licence": "Interne"
                },
                {
                    "role": "Commercial",
                    "nb_users": max(1, nb_users // 3),
                    "acces": "CRM, Ventes, Facturation",
                    "type_licence": "Interne"
                },
                {
                    "role": "Opérationnel",
                    "nb_users": max(1, nb_users - min(2, nb_users) - max(1, nb_users // 3)),
                    "acces": "Stock, Achats, Projet",
                    "type_licence": "Interne"
                },
            ],
            "notes": [
                "Les tarifs sont indicatifs et basés sur la grille publique Odoo.",
                "Un plan Custom est recommandé à partir de 6 modules pour optimiser les coûts.",
                "Les utilisateurs portail (clients/fournisseurs) sont gratuits.",
            ]
        }

        return json.dumps(result, indent=2, ensure_ascii=False)

    def _mock_proposition(self, message: str) -> str:
        """Génère une proposition commerciale mock."""
        societe = self._extract_societe(message)
        modules = self._extract_modules(message)

        result = {
            "titre": f"Proposition commerciale — Intégration Odoo 19 — {societe}",
            "sections": [
                {
                    "titre": "Synthèse du projet",
                    "contenu": (
                        f"Ynov'iT Services propose à {societe} la mise en place de l'ERP Odoo 19 "
                        f"couvrant {len(modules)} domaines fonctionnels. Le projet inclut le paramétrage, "
                        f"la reprise de données, la formation et l'accompagnement au démarrage."
                    )
                },
                {
                    "titre": "Périmètre",
                    "contenu": f"Modules inclus : {', '.join(m.replace('has_', '').title() for m in modules)}"
                },
                {
                    "titre": "Méthodologie",
                    "contenu": (
                        "Le projet sera mené en 4 phases : "
                        "1) Cadrage et spécifications détaillées, "
                        "2) Paramétrage et développements, "
                        "3) Recette et reprise de données, "
                        "4) Formation et mise en production."
                    )
                },
                {
                    "titre": "Planning prévisionnel",
                    "contenu": "Durée estimée : 8 à 12 semaines selon la disponibilité des équipes."
                },
                {
                    "titre": "Conditions",
                    "contenu": (
                        "Facturation au temps passé sur la base du chiffrage présenté. "
                        "Tout dépassement de périmètre fera l'objet d'un avenant."
                    )
                }
            ]
        }

        return json.dumps(result, indent=2, ensure_ascii=False)

    def _mock_generic(self, message: str) -> str:
        """Réponse générique si l'agent n'est pas identifié."""
        return json.dumps({
            "message": "Réponse mock générique",
            "note": "Agent non identifié — vérifiez le prompt système",
            "_mock": True
        }, indent=2, ensure_ascii=False)

    # ── Helpers d'extraction ───────────────────────────────

    @staticmethod
    def _extract_modules(message: str) -> list[str]:
        """Extrait les modules activés (has_* = true) depuis le message."""
        modules = []
        # Pattern: "has_xxx": true ou has_xxx: True
        for match in re.finditer(r'"?(has_\w+)"?\s*[:=]\s*(true|True)', message):
            modules.append(match.group(1))
        return sorted(set(modules))

    @staticmethod
    def _extract_number(message: str, pattern: str) -> float:
        """Extrait un nombre depuis le message avec une regex."""
        match = re.search(pattern, message)
        if match:
            try:
                return float(match.group(1))
            except (ValueError, IndexError):
                return 0
        return 0

    @staticmethod
    def _extract_societe(message: str) -> str:
        """Extrait la raison sociale depuis le message."""
        match = re.search(r'raison_sociale["\']?\s*[:=]\s*["\']([^"\']+)["\']', message)
        if match:
            return match.group(1)
        return "Prospect"

    @staticmethod
    def _extract_module_uo(message: str, module_id: str) -> float:
        """Extrait le total UO d'un module depuis le message."""
        # Chercher dans le JSON du message: "has_xxx": {"uo": X.X}
        pattern = rf'"{re.escape(module_id)}":\s*\{{[^}}]*"uo":\s*([\d.]+)'
        match = re.search(pattern, message)
        if match:
            return float(match.group(1))
        return 0