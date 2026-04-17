"""
Ynov'iT Presales Pipeline — PDF Ingester

Extrait le texte des PDF de documentation Odoo, le découpe
en chunks intelligents (par section/module), et l'indexe
dans ChromaDB pour la recherche RAG.

Usage CLI:
    python -m services.rag.pdf_ingester chemin/vers/doc.pdf --collection odoo_user_docs

Usage Python:
    from services.rag.pdf_ingester import ingest_pdf
    stats = ingest_pdf("doc.pdf", collection="odoo_user_docs")
"""

import re
import logging
import hashlib
from pathlib import Path

import fitz  # PyMuPDF

from services.rag.embedder import get_embedder
from services.rag.vector_store import VectorStore

logger = logging.getLogger("presales.rag.ingester")

# Sections connues de la doc Odoo user et leur mapping module
ODOO_SECTIONS = {
    "Odoo essentials": "base",
    "General settings": "base",
    "Accounting and Invoicing": "account",
    "Achats": "purchase",
    "Payroll": "hr_payroll",
    "CRM": "crm",
    "Ventes": "sale",
    "Sales": "sale",
    "Point de Vente": "pos",
    "Email Marketing": "marketing",
    "Abonnements": "sale_subscription",
    "Subscriptions": "sale_subscription",
    "Rental": "rental",
    "Site web": "website",
    "Website": "website",
    "eCommerce": "website_sale",
    "eLearning": "elearning",
    "Inventaire": "stock",
    "Inventory": "stock",
    "Production": "mrp",
    "Manufacturing": "mrp",
    "Helpdesk": "helpdesk",
    "Barcode": "barcode",
    "Quality": "quality",
    "Maintenance": "maintenance",
    "Repairs": "repair",
    "Attendances": "hr_attendance",
    "Employees": "hr",
    "Planning": "planning",
    "Time off": "hr_holidays",
    "Recruitment": "hr_recruitment",
    "Events": "event",
    "Projet": "project",
    "Project": "project",
    "Feuilles de temps": "hr_timesheet",
    "Timesheets": "hr_timesheet",
    "Assistance": "helpdesk",
    "Field Service": "field_service",
    "Services sur Site": "field_service",
    "Studio": "studio",
    "Documents": "documents",
    "Dépenses": "hr_expense",
    "Expenses": "hr_expense",
    "Fleet": "fleet",
    "Lunch": "lunch",
}

CHUNK_SIZE = 1500
CHUNK_OVERLAP = 200


def ingest_pdf(
    pdf_path: str | Path,
    collection: str = "odoo_user_docs",
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
) -> dict:
    """
    Ingère un PDF dans la base vectorielle.

    Returns:
        Dict avec les stats d'ingestion
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF introuvable : {pdf_path}")

    logger.info(f"Début ingestion : {pdf_path.name} -> collection '{collection}'")

    # 1. Extraction
    logger.info("Étape 1/4 — Extraction du texte")
    pages = _extract_pages(pdf_path)
    total_chars = sum(len(p["text"]) for p in pages)
    logger.info(f"  {len(pages)} pages, {total_chars:,} caractères")

    # 2. Sections
    logger.info("Étape 2/4 — Détection des sections")
    pages = _detect_sections(pages)
    modules_found = set(p["module"] for p in pages if p["module"])
    logger.info(f"  {len(modules_found)} modules : {sorted(modules_found)}")

    # 3. Chunks
    logger.info("Étape 3/4 — Découpage en chunks")
    chunks = _build_chunks(pages, chunk_size, chunk_overlap)
    avg_size = sum(len(c["text"]) for c in chunks) // max(len(chunks), 1)
    logger.info(f"  {len(chunks)} chunks (moy: {avg_size} chars)")

    # 4. Embeddings + stockage
    logger.info("Étape 4/4 — Embeddings et stockage")
    embedder = get_embedder()
    store = VectorStore()
    store.delete_collection(collection)

    texts = [c["text"] for c in chunks]
    all_embeddings = []
    batch_size = 256
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        all_embeddings.extend(embedder.embed(batch))
        if (i + batch_size) % 1024 == 0:
            logger.info(f"  Embeddings : {min(i + batch_size, len(texts))}/{len(texts)}")

    store.add_chunks(collection, chunks, all_embeddings)

    stats = {
        "pdf": pdf_path.name,
        "collection": collection,
        "pages": len(pages),
        "total_chars": total_chars,
        "chunks": len(chunks),
        "modules": sorted(modules_found),
    }
    logger.info(f"Ingestion terminée : {len(chunks)} chunks dans '{collection}'")
    return stats


def _extract_pages(pdf_path: Path) -> list[dict]:
    doc = fitz.open(str(pdf_path))
    pages = []
    for i, page in enumerate(doc):
        text = page.get_text("text").strip()
        if len(text) > 30:
            pages.append({"page_num": i, "text": text})
    doc.close()
    return pages


def _detect_sections(pages: list[dict]) -> list[dict]:
    current_module = "base"
    current_section = "Introduction"

    for page in pages:
        first_line = page["text"].split("\n")[0].strip()
        for section_name, module in ODOO_SECTIONS.items():
            if first_line.lower() == section_name.lower():
                current_module = module
                current_section = section_name
                break
        page["module"] = current_module
        page["section"] = current_section

    return pages


def _build_chunks(pages, chunk_size, overlap):
    chunks = []
    current_module = None
    buffer = ""

    for page in pages:
        if page["module"] != current_module:
            if buffer.strip():
                chunks.extend(_split_text(buffer, current_module or "base",
                                          current_section or "", chunk_size, overlap))
            buffer = ""
            current_module = page["module"]
            current_section = page["section"]
        buffer += "\n\n" + page["text"]

    if buffer.strip():
        chunks.extend(_split_text(buffer, current_module or "base",
                                  current_section or "", chunk_size, overlap))
    return chunks


def _split_text(text, module, section, chunk_size, overlap):
    chunks = []
    text = text.strip()
    if not text:
        return chunks

    sentences = re.split(r'(?<=[.!?])\s+', text)
    current_chunk = ""

    for sentence in sentences:
        if len(current_chunk) + len(sentence) > chunk_size and current_chunk:
            chunk_id = f"{module}_{len(chunks):04d}_{hashlib.md5(current_chunk.encode()).hexdigest()[:8]}"
            chunks.append({
                "id": chunk_id,
                "text": current_chunk.strip(),
                "metadata": {"module": module, "section": section, "source": "odoo_docs"},
            })
            words = current_chunk.split()
            overlap_words = max(1, overlap * len(words) // max(len(current_chunk), 1))
            current_chunk = " ".join(words[-overlap_words:]) + " "
        current_chunk += sentence + " "

    if current_chunk.strip():
        chunk_id = f"{module}_{len(chunks):04d}_{hashlib.md5(current_chunk.encode()).hexdigest()[:8]}"
        chunks.append({
            "id": chunk_id,
            "text": current_chunk.strip(),
            "metadata": {"module": module, "section": section, "source": "odoo_docs"},
        })

    return chunks


if __name__ == "__main__":
    import sys, json
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    if len(sys.argv) < 2:
        print("Usage: python -m services.rag.pdf_ingester <pdf_path> [--collection <name>]")
        sys.exit(1)

    pdf = sys.argv[1]
    coll = "odoo_user_docs"
    if "--collection" in sys.argv:
        coll = sys.argv[sys.argv.index("--collection") + 1]

    stats = ingest_pdf(pdf, collection=coll)
    print(json.dumps(stats, indent=2))
