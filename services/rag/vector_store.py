"""
Ynov'iT Presales Pipeline — Vector Store (ChromaDB)

Stocke et recherche des chunks de texte par similarité vectorielle.
Les données sont persistées localement dans un dossier.
"""

import logging
from pathlib import Path

import chromadb

import config

logger = logging.getLogger("presales.rag.store")

CHROMA_DIR = config.DATA_DIR / "chroma_db"


class VectorStore:
    """
    Wrapper ChromaDB pour le stockage et la recherche vectorielle.

    Chaque collection correspond à une source de données
    (ex: "odoo_user_docs", "odoo_tech_docs", "project_history").
    """

    def __init__(self, persist_dir: Path | None = None):
        path = persist_dir or CHROMA_DIR
        path.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(path=str(path))
        logger.info(f"ChromaDB initialisé : {path}")

    def get_or_create_collection(self, name: str):
        """Récupère ou crée une collection."""
        return self.client.get_or_create_collection(
            name=name,
            metadata={"hnsw:space": "cosine"},
        )

    def add_chunks(
        self,
        collection_name: str,
        chunks: list[dict],
        embeddings: list[list[float]],
    ):
        """
        Ajoute des chunks avec leurs embeddings dans une collection.

        Args:
            collection_name: Nom de la collection
            chunks: Liste de dicts avec "id", "text", et "metadata"
            embeddings: Embeddings correspondants
        """
        collection = self.get_or_create_collection(collection_name)

        ids = [c["id"] for c in chunks]
        documents = [c["text"] for c in chunks]
        metadatas = [c.get("metadata", {}) for c in chunks]

        # Batch par 500 (limite ChromaDB)
        batch_size = 500
        for start in range(0, len(ids), batch_size):
            end = start + batch_size
            collection.add(
                ids=ids[start:end],
                documents=documents[start:end],
                embeddings=embeddings[start:end],
                metadatas=metadatas[start:end],
            )

        logger.info(
            f"Collection '{collection_name}' : {len(chunks)} chunks ajoutés "
            f"(total : {collection.count()})"
        )

    def search(
        self,
        collection_name: str,
        query_embedding: list[float],
        n_results: int = 5,
        where: dict | None = None,
    ) -> list[dict]:
        """
        Recherche les chunks les plus similaires.

        Args:
            collection_name: Nom de la collection
            query_embedding: Vecteur de la requête
            n_results: Nombre de résultats
            where: Filtre sur les métadonnées (ex: {"module": "sale"})

        Returns:
            Liste de dicts avec "text", "metadata", "distance"
        """
        collection = self.get_or_create_collection(collection_name)

        if collection.count() == 0:
            return []

        query_params = {
            "query_embeddings": [query_embedding],
            "n_results": min(n_results, collection.count()),
        }
        if where:
            query_params["where"] = where

        results = collection.query(**query_params)

        output = []
        for i in range(len(results["ids"][0])):
            output.append({
                "id": results["ids"][0][i],
                "text": results["documents"][0][i],
                "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                "distance": results["distances"][0][i] if results["distances"] else 0,
            })

        return output

    def delete_collection(self, name: str):
        """Supprime une collection entière."""
        try:
            self.client.delete_collection(name)
            logger.info(f"Collection '{name}' supprimée")
        except Exception:
            pass

    def collection_count(self, name: str) -> int:
        """Retourne le nombre de chunks dans une collection."""
        try:
            return self.get_or_create_collection(name).count()
        except Exception:
            return 0
