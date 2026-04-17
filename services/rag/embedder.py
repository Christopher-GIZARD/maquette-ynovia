"""
Ynov'iT Presales Pipeline — Embedder local

Génère des embeddings vectoriels à partir de texte en utilisant
sentence-transformers. Tourne 100% en local, sans API externe.

Modèle par défaut : all-MiniLM-L6-v2
- 384 dimensions
- Rapide (~4000 phrases/seconde sur CPU)
- Bon pour la recherche sémantique en anglais et français
"""

import logging
from functools import lru_cache

from sentence_transformers import SentenceTransformer

logger = logging.getLogger("presales.rag.embedder")

DEFAULT_MODEL = "all-MiniLM-L6-v2"


class Embedder:
    """Génère des embeddings vectoriels à partir de texte."""

    def __init__(self, model_name: str = DEFAULT_MODEL):
        logger.info(f"Chargement du modèle d'embeddings : {model_name}")
        self.model = SentenceTransformer(model_name)
        self.dimension = self.model.get_sentence_embedding_dimension()
        logger.info(f"Modèle chargé — {self.dimension} dimensions")

    def embed(self, texts: list[str]) -> list[list[float]]:
        """
        Génère les embeddings pour une liste de textes.

        Args:
            texts: Liste de chaînes de texte

        Returns:
            Liste de vecteurs (list[float]) de dimension self.dimension
        """
        embeddings = self.model.encode(texts, show_progress_bar=len(texts) > 100)
        return embeddings.tolist()

    def embed_single(self, text: str) -> list[float]:
        """Génère l'embedding pour un seul texte."""
        return self.embed([text])[0]


@lru_cache(maxsize=1)
def get_embedder() -> Embedder:
    """Singleton — le modèle n'est chargé qu'une seule fois."""
    return Embedder()
