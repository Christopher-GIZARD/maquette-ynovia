"""
Ynov'iT Presales Pipeline — Client Claude

Wrapper autour du SDK Anthropic.
Tous les agents passent par ce service pour appeler Claude.

Responsabilités :
- Gestion du modèle et des paramètres
- Retries en cas d'erreur réseau ou rate limit
- Logging des appels (durée, tokens utilisés)
- Extraction du texte de la réponse
"""

import json
import time
import logging

import anthropic

import config

logger = logging.getLogger("presales.claude")


class ClaudeClient:
    """Client centralisé pour les appels à l'API Claude."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ):
        self.api_key = api_key or config.ANTHROPIC_API_KEY
        self.model = model or config.CLAUDE_MODEL
        self.max_tokens = max_tokens or config.CLAUDE_MAX_TOKENS
        self.temperature = temperature or config.CLAUDE_TEMPERATURE

        if not self.api_key:
            raise ValueError(
                "Clé API Anthropic manquante. "
                "Définissez ANTHROPIC_API_KEY dans le .env ou en variable d'environnement."
            )

        self.client = anthropic.Anthropic(api_key=self.api_key)

    def send(
        self,
        system: str,
        message: str,
        max_tokens: int | None = None,
        temperature: float | None = None,
        max_retries: int = 3,
    ) -> str:
        """
        Envoie un message à Claude et retourne le texte de la réponse.

        Args:
            system: Le prompt système (rôle et instructions de l'agent)
            message: Le message utilisateur (données du prospect, contexte)
            max_tokens: Override du max_tokens par défaut
            temperature: Override de la température par défaut
            max_retries: Nombre de tentatives en cas d'erreur transitoire

        Returns:
            Le texte de la réponse de Claude

        Raises:
            anthropic.APIError: Si l'appel échoue après toutes les tentatives
        """
        tokens = max_tokens or self.max_tokens
        temp = temperature if temperature is not None else self.temperature

        for attempt in range(1, max_retries + 1):
            try:
                logger.info(
                    f"Appel Claude ({self.model}) — "
                    f"tentative {attempt}/{max_retries} — "
                    f"system={len(system)} chars, message={len(message)} chars"
                )

                start = time.time()

                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=tokens,
                    temperature=temp,
                    system=system,
                    messages=[
                        {"role": "user", "content": message}
                    ]
                )

                elapsed = time.time() - start
                usage = response.usage

                logger.info(
                    f"Réponse reçue en {elapsed:.1f}s — "
                    f"input_tokens={usage.input_tokens}, "
                    f"output_tokens={usage.output_tokens}, "
                    f"stop_reason={response.stop_reason}"
                )

                # Extrait le texte de la réponse
                return self._extract_text(response)

            except anthropic.RateLimitError:
                wait = 2 ** attempt
                logger.warning(
                    f"Rate limit atteint — attente {wait}s avant retry"
                )
                time.sleep(wait)

            except anthropic.APIConnectionError as e:
                if attempt == max_retries:
                    raise
                wait = 2 ** attempt
                logger.warning(
                    f"Erreur connexion ({e}) — retry dans {wait}s"
                )
                time.sleep(wait)

        # Ne devrait pas arriver, mais au cas où
        raise RuntimeError("Nombre maximum de tentatives dépassé")

    def send_json(
        self,
        system: str,
        message: str,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> dict:
        """
        Comme send(), mais parse la réponse en JSON.

        Le prompt système devrait inclure une instruction
        demandant à Claude de répondre uniquement en JSON.

        Returns:
            La réponse parsée en dictionnaire

        Raises:
            json.JSONDecodeError: Si la réponse n'est pas du JSON valide
        """
        raw = self.send(system, message, max_tokens, temperature)

        # Claude entoure parfois le JSON de backticks markdown
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            # Retire ```json ... ``` ou ``` ... ```
            lines = cleaned.split("\n")
            # Retire la première et la dernière ligne si ce sont des backticks
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines)

        return json.loads(cleaned)

    @staticmethod
    def _extract_text(response) -> str:
        """Extrait le contenu texte de la réponse Claude."""
        parts = []
        for block in response.content:
            if block.type == "text":
                parts.append(block.text)
        return "\n".join(parts)