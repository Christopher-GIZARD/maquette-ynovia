"""
Ynov'iT Presales Pipeline — Agent de base

Classe abstraite dont tous les agents héritent.

Chaque agent implémente 3 choses :
- prompt_name : quel fichier prompt utiliser
- build_user_message() : comment construire la requête à partir du contexte
- parse_response() : comment interpréter la réponse de Claude

La méthode run() orchestre le tout : charger le prompt,
construire le message, envoyer à Claude, parser la réponse.
"""

import json
import logging
from abc import ABC, abstractmethod
from pathlib import Path

import config
from services.claude_client import ClaudeClient

logger = logging.getLogger("presales.agents")


class Agent(ABC):
    """Classe de base pour tous les agents du pipeline."""

    def __init__(self, claude: ClaudeClient):
        self.claude = claude
        self._system_prompt = None  # Chargé au premier appel (lazy)

    # ── À implémenter par chaque agent ─────────────────────

    @property
    @abstractmethod
    def prompt_name(self) -> str:
        """
        Nom du fichier prompt (sans extension).

        Doit correspondre à un fichier dans prompts/{nom}.txt.
        Ex: "cdc", "chiffrage", "flux", "config_odoo", "licence", "proposition"
        """
        ...

    @abstractmethod
    def build_user_message(self, context: dict) -> str:
        """
        Construit le message utilisateur envoyé à Claude.

        Reçoit le contexte complet du pipeline (réponses formulaire,
        données entreprise, résultats des agents précédents).

        Retourne une chaîne formatée avec les données pertinentes
        pour la mission de cet agent.
        """
        ...

    @abstractmethod
    def parse_response(self, response: str) -> dict:
        """
        Parse la réponse brute de Claude en données structurées.

        Chaque agent retourne un dictionnaire avec les clés
        attendues par les agents suivants et par les générateurs.
        """
        ...

    # ── Logique commune ────────────────────────────────────

    @property
    def system_prompt(self) -> str:
        """Charge le prompt système depuis le fichier (avec cache)."""
        if self._system_prompt is None:
            self._system_prompt = self._load_prompt()
        return self._system_prompt

    def _load_prompt(self) -> str:
        """
        Charge le fichier prompt depuis prompts/{prompt_name}.txt.

        Raise FileNotFoundError si le fichier n'existe pas,
        avec un message clair pour guider le développeur.
        """
        prompt_path = config.PROMPTS_DIR / f"{self.prompt_name}.txt"

        if not prompt_path.exists():
            raise FileNotFoundError(
                f"Prompt introuvable : {prompt_path}\n"
                f"Créez le fichier prompts/{self.prompt_name}.txt "
                f"avec les instructions pour cet agent."
            )

        content = prompt_path.read_text(encoding="utf-8").strip()

        if not content:
            raise ValueError(
                f"Le fichier prompt {prompt_path} est vide."
            )

        logger.debug(
            f"Prompt '{self.prompt_name}' chargé ({len(content)} chars)"
        )
        return content

    def reload_prompt(self):
        """
        Force le rechargement du prompt depuis le fichier.

        Utile en développement quand on itère sur les prompts
        sans redémarrer le serveur.
        """
        self._system_prompt = None
        logger.info(f"Prompt '{self.prompt_name}' sera rechargé au prochain appel")

    def run(self, context: dict) -> dict:
        """
        Exécute l'agent : construit le message, appelle Claude,
        parse la réponse.

        Args:
            context: Dictionnaire partagé du pipeline contenant
                     les réponses, données entreprise, et résultats
                     des agents précédents.

        Returns:
            Dictionnaire avec les résultats structurés de l'agent.
        """
        agent_name = self.__class__.__name__
        logger.info(f"[{agent_name}] Démarrage")

        # 1. Construire le message
        message = self.build_user_message(context)
        logger.debug(f"[{agent_name}] Message construit ({len(message)} chars)")

        # 2. Appeler Claude
        raw_response = self.claude.send(
            system=self.system_prompt,
            message=message
        )
        logger.debug(f"[{agent_name}] Réponse reçue ({len(raw_response)} chars)")

        # Debug : sauvegarder l'échange complet
        self._debug_dump(agent_name, message, raw_response, context)

        # 3. Parser la réponse
        result = self.parse_response(raw_response)
        logger.info(f"[{agent_name}] Terminé — {len(result)} clés dans le résultat")

        return result

    def run_json(self, context: dict) -> dict:
        """
        Variante de run() qui utilise send_json() pour les agents
        dont la réponse est attendue en JSON pur.

        Le prompt système doit contenir l'instruction de répondre
        uniquement en JSON.
        """
        agent_name = self.__class__.__name__
        logger.info(f"[{agent_name}] Démarrage (mode JSON)")

        message = self.build_user_message(context)

        result = self.claude.send_json(
            system=self.system_prompt,
            message=message
        )

        # Debug : sauvegarder l'échange (la réponse est déjà parsée)
        self._debug_dump(agent_name, message, json.dumps(result, indent=2, ensure_ascii=False), context)

        logger.info(f"[{agent_name}] Terminé — {len(result)} clés dans le résultat")
        return result

    def _debug_dump(self, agent_name: str, message: str, response: str, context: dict):
        """
        Sauvegarde l'échange complet avec Claude dans le dossier du projet.

        Crée un sous-dossier debug/ dans le répertoire du projet avec
        un fichier par agent contenant le prompt système, le message
        envoyé, et la réponse reçue.

        Activé uniquement si DEBUG=true dans le .env.
        """
        if not config.DEBUG:
            return

        # Trouver le dossier du projet dans le contexte
        # (injecté par l'orchestrateur via le callback on_progress)
        project_dir = context.get("_project_dir")
        if not project_dir:
            # Fallback : dossier debug global
            project_dir = config.OUTPUTS_DIR / "_debug"

        debug_dir = Path(project_dir) / "debug"
        debug_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{self.prompt_name}.md"
        filepath = debug_dir / filename

        content = f"""# Debug — {agent_name}

## Prompt système ({len(self.system_prompt)} chars)

```
{self.system_prompt}
```

## Message envoyé ({len(message)} chars)

```
{message}
```

## Réponse reçue ({len(response)} chars)

```
{response}
```
"""
        filepath.write_text(content, encoding="utf-8")
        logger.debug(f"[{agent_name}] Debug sauvegardé : {filepath}")