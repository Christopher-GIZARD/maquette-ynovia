"""
Ynov'iT Presales Pipeline — Calculateur UO déterministe

Parcourt l'arbre de décision (decision_tree.json) et calcule
les Unités d'Œuvre (jours consultant) en fonction des réponses
du formulaire.

Types de champs UO gérés :
- uo_base_module : coût fixe d'activation d'un module (boolean)
- uo             : coût fixe si la question est répondue positivement
- uo_map         : lookup dans un dict {valeur_sélectionnée: UO}
- uo_per_item    : UO × nombre d'items cochés (multi_select)
- uo_per_unit    : UO × valeur numérique saisie (number)

Le calcul est purement déterministe — pas d'IA ici.
Il sert de base au chiffrage que l'agent IA ajustera ensuite.
"""

import json
import logging
from pathlib import Path

import config

logger = logging.getLogger("presales.uo")


class UOLine:
    """Une ligne de chiffrage UO."""

    def __init__(
        self,
        question_id: str,
        label: str,
        uo_type: str,
        uo_value: float,
        module: str | None = None,
        detail: str = "",
    ):
        self.question_id = question_id
        self.label = label
        self.uo_type = uo_type      # base_module | uo | uo_map | uo_per_item | uo_per_unit
        self.uo_value = uo_value
        self.module = module        # ex: "has_sale", "has_stock", None pour les généraux
        self.detail = detail        # ex: "5 items × 0.5", "> 20 000 → 5"

    def to_dict(self) -> dict:
        return {
            "question_id": self.question_id,
            "label": self.label,
            "module": self.module,
            "uo_type": self.uo_type,
            "uo_value": self.uo_value,
            "detail": self.detail,
        }


class UOCalculator:
    """
    Moteur de calcul déterministe des UO.

    Usage:
        calculator = UOCalculator()
        result = calculator.compute(reponses)

        print(result["total_uo"])
        print(result["par_module"])
        for line in result["lignes"]:
            print(line)
    """

    def __init__(self, tree_path: Path | None = None):
        path = tree_path or config.DECISION_TREE_PATH
        self.tree = self._load_tree(path)

    @staticmethod
    def _load_tree(path: Path) -> dict:
        """Charge l'arbre de décision depuis le fichier JSON."""
        if not path.exists():
            raise FileNotFoundError(
                f"Arbre de décision introuvable : {path}\n"
                f"Placez le fichier decision_tree.json dans {path.parent}/"
            )
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def compute(self, reponses: dict) -> dict:
        """
        Calcule les UO à partir des réponses du formulaire.

        Args:
            reponses: Dictionnaire {question_id: valeur} tel que
                      produit par le formulaire.

        Returns:
            {
                "total_uo": float,
                "par_module": {
                    "has_sale": {"label": "Ventes", "uo": 12.5, "actif": True},
                    ...
                    "_general": {"label": "Paramètres généraux", "uo": 3.0, "actif": True}
                },
                "lignes": [UOLine.to_dict(), ...]
            }
        """
        lignes: list[UOLine] = []

        for question in self.tree["questions"]:
            current_module = self._detect_module(question)
            self._process_node(question, reponses, current_module, lignes)

        # Agrégation par module
        par_module = self._aggregate_by_module(lignes, reponses)
        total = sum(line.uo_value for line in lignes)

        result = {
            "total_uo": round(total, 2),
            "par_module": par_module,
            "lignes": [line.to_dict() for line in lignes],
        }

        logger.info(
            f"Chiffrage UO calculé : {result['total_uo']}j "
            f"({len(lignes)} lignes, {len(par_module)} modules)"
        )

        return result

    def _detect_module(self, question: dict) -> str | None:
        """
        Détermine si une question racine est un module.

        Les questions has_* avec uo_base_module sont des modules.
        Les autres sont des questions générales (module=None → '_general').
        """
        qid = question.get("id", "")
        if "uo_base_module" in question or qid.startswith("has_"):
            return qid
        return None

    def _process_node(
        self,
        node: dict,
        reponses: dict,
        current_module: str | None,
        lignes: list[UOLine],
    ):
        """
        Traite un nœud de l'arbre récursivement.

        Vérifie si la question a une réponse, calcule les UO le cas
        échéant, puis descend dans les enfants visibles.
        """
        qid = node.get("id")
        if not qid:
            return

        answer = reponses.get(qid)

        # Si pas de réponse, on s'arrête (la branche n'est pas active)
        if answer is None:
            return

        # ── Calcul UO de ce nœud ──────────────────────────

        # 1. uo_base_module : coût fixe d'activation du module
        if "uo_base_module" in node and answer is True:
            lignes.append(UOLine(
                question_id=qid,
                label=node.get("label", qid),
                uo_type="base_module",
                uo_value=float(node["uo_base_module"]),
                module=current_module,
                detail=f"Activation module → {node['uo_base_module']}j",
            ))

        # 2. uo : coût fixe conditionnel
        if "uo" in node:
            uo_val = self._compute_uo_fixed(node, answer)
            if uo_val > 0:
                lignes.append(UOLine(
                    question_id=qid,
                    label=node.get("label", qid),
                    uo_type="uo",
                    uo_value=uo_val,
                    module=current_module,
                    detail=f"Fixe → {uo_val}j",
                ))

        # 3. uo_map : lookup par valeur sélectionnée
        if "uo_map" in node and answer is not None:
            uo_val = float(node["uo_map"].get(str(answer), 0))
            if uo_val > 0:
                lignes.append(UOLine(
                    question_id=qid,
                    label=node.get("label", qid),
                    uo_type="uo_map",
                    uo_value=uo_val,
                    module=current_module,
                    detail=f'"{answer}" → {uo_val}j',
                ))

        # 4. uo_per_item : UO × nombre d'items cochés
        if "uo_per_item" in node and isinstance(answer, list) and len(answer) > 0:
            per_item = float(node["uo_per_item"])
            uo_val = per_item * len(answer)
            lignes.append(UOLine(
                question_id=qid,
                label=node.get("label", qid),
                uo_type="uo_per_item",
                uo_value=uo_val,
                module=current_module,
                detail=f"{len(answer)} items × {per_item}j = {uo_val}j",
            ))

        # 5. uo_per_unit : UO × valeur numérique
        if "uo_per_unit" in node and isinstance(answer, (int, float)) and answer > 0:
            per_unit = float(node["uo_per_unit"])
            uo_val = per_unit * answer
            lignes.append(UOLine(
                question_id=qid,
                label=node.get("label", qid),
                uo_type="uo_per_unit",
                uo_value=round(uo_val, 2),
                module=current_module,
                detail=f"{answer} × {per_unit}j = {round(uo_val, 2)}j",
            ))

        # ── Descente dans les enfants ─────────────────────

        # children : visibles si le parent est True (boolean)
        #            ou si show_if est satisfait
        if "children" in node:
            for child in node["children"]:
                if self._child_visible(child, node, answer, reponses):
                    self._process_node(child, reponses, current_module, lignes)

        # children_map : visibles si la valeur sélectionnée correspond
        if "children_map" in node and isinstance(answer, str):
            children = node["children_map"].get(answer, [])
            for child in children:
                self._process_node(child, reponses, current_module, lignes)

        # children_if_contains : visibles si l'option est dans la multi-sélection
        if "children_if_contains" in node and isinstance(answer, list):
            for option, children in node["children_if_contains"].items():
                if option in answer:
                    for child in children:
                        self._process_node(child, reponses, current_module, lignes)

    @staticmethod
    def _compute_uo_fixed(node: dict, answer) -> float:
        """
        Calcule le UO fixe (champ 'uo').

        Pour un boolean : ajouté si answer == True
        Pour un multi_select : ajouté si la liste n'est pas vide
        Pour les autres types : ajouté si une réponse existe
        """
        uo_val = float(node["uo"])
        node_type = node.get("type", "")

        if node_type == "boolean":
            return uo_val if answer is True else 0
        elif node_type == "multi_select":
            return uo_val if isinstance(answer, list) and len(answer) > 0 else 0
        else:
            # Pour tout autre type, on ajoute si une valeur est présente
            return uo_val if answer else 0

    @staticmethod
    def _child_visible(child: dict, parent: dict, parent_answer, reponses: dict) -> bool:
        """
        Détermine si un enfant (children[]) est visible
        en fonction de la réponse du parent et du show_if de l'enfant.
        """
        show_if = child.get("show_if")

        if show_if is None:
            # Pas de show_if → visible si le parent boolean est True
            if parent.get("type") == "boolean":
                return parent_answer is True
            return True

        # show_if avec un seuil numérique
        # La valeur de référence est soit le parent, soit un autre champ (parent_id)
        ref_id = show_if.get("parent_id", parent.get("id"))
        ref_val = reponses.get(ref_id)

        if ref_val is None:
            return False

        try:
            ref_num = float(ref_val)
        except (ValueError, TypeError):
            return False

        if "gt" in show_if:
            return ref_num > show_if["gt"]
        if "gte" in show_if:
            return ref_num >= show_if["gte"]
        if "lt" in show_if:
            return ref_num < show_if["lt"]
        if "lte" in show_if:
            return ref_num <= show_if["lte"]

        return True

    def _aggregate_by_module(self, lignes: list[UOLine], reponses: dict) -> dict:
        """
        Agrège les lignes UO par module.

        Retourne un dictionnaire avec le total et l'état d'activation
        de chaque module, plus un groupe '_general' pour les questions
        hors modules.
        """
        # Mapping des labels de modules
        module_labels = {}
        for q in self.tree["questions"]:
            qid = q.get("id", "")
            if qid.startswith("has_"):
                module_labels[qid] = q.get("label", qid)

        modules = {}

        for line in lignes:
            mod_key = line.module or "_general"

            if mod_key not in modules:
                modules[mod_key] = {
                    "label": module_labels.get(mod_key, "Paramètres généraux"),
                    "uo": 0,
                    "actif": True,
                    "lignes_count": 0,
                }

            modules[mod_key]["uo"] = round(modules[mod_key]["uo"] + line.uo_value, 2)
            modules[mod_key]["lignes_count"] += 1

        # Marque les modules non activés
        for q in self.tree["questions"]:
            qid = q.get("id", "")
            if qid.startswith("has_") and qid not in modules:
                if reponses.get(qid) is False:
                    modules[qid] = {
                        "label": module_labels.get(qid, qid),
                        "uo": 0,
                        "actif": False,
                        "lignes_count": 0,
                    }

        return modules