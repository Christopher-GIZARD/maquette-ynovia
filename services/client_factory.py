"""
Ynov'iT Presales Pipeline — Factory Client Claude

Instancie le bon client Claude selon la configuration :
- CLAUDE_MODE=api   → ClaudeClient (appels API réels)
- CLAUDE_MODE=mock  → MockClaudeClient (réponses simulées)
- CLAUDE_MODE=auto  → mock si pas de clé API, api sinon
"""

import logging

import config

logger = logging.getLogger("presales.claude")


def get_claude_client():
    """
    Factory qui retourne le bon client Claude.

    Logique :
    - Si CLAUDE_MODE=mock → MockClaudeClient
    - Si CLAUDE_MODE=api  → ClaudeClient (crash si pas de clé)
    - Si CLAUDE_MODE=auto → mock si pas de clé, api sinon

    Returns:
        ClaudeClient ou MockClaudeClient
    """
    mode = config.CLAUDE_MODE.lower()

    if mode == "mock":
        logger.info("Mode MOCK activé (CLAUDE_MODE=mock)")
        from services.mock_claude_client import MockClaudeClient
        return MockClaudeClient()

    if mode == "api":
        logger.info("Mode API activé (CLAUDE_MODE=api)")
        from services.claude_client import ClaudeClient
        return ClaudeClient()

    # Mode auto : détection automatique
    if config.ANTHROPIC_API_KEY:
        logger.info("Mode AUTO → API détectée (clé API présente)")
        from services.claude_client import ClaudeClient
        return ClaudeClient()
    else:
        logger.info(
            "Mode AUTO → MOCK activé (pas de clé API). "
            "Définissez ANTHROPIC_API_KEY dans .env pour utiliser l'API."
        )
        from services.mock_claude_client import MockClaudeClient
        return MockClaudeClient()