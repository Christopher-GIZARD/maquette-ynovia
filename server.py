"""
Ynov'iT Presales Pipeline — Serveur FastAPI

Point d'entrée de l'application.
- Sert le formulaire HTML
- Reçoit les soumissions du formulaire
- Lance le pipeline en arrière-plan via l'orchestrateur
- Expose le statut et les livrables générés

Lancer avec : uvicorn server:app --reload --port 8000
"""

import json
import uuid
import logging
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import config
from orchestrator import Pipeline
from services.pappers import PappersClient

# ── Configuration ──────────────────────────────────────────

OUTPUTS_DIR = config.OUTPUTS_DIR
FRONTEND_DIR = config.FRONTEND_DIR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("presales")

# ── Initialisation du pipeline ─────────────────────────────

pipeline = Pipeline()

# ── App FastAPI ────────────────────────────────────────────

app = FastAPI(
    title="Ynov'iT Presales Pipeline",
    version="0.1.0",
    description="Pipeline de génération automatique des livrables avant-vente Odoo"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Modèles Pydantic ──────────────────────────────────────

class FormMeta(BaseModel):
    genere_le: str
    version_questionnaire: str = "5.0"
    outil: str = "Formulaire Avant-Vente Ynov'iT Odoo"


class ReponseDetail(BaseModel):
    id: str
    label: str
    valeur: bool | int | float | str | list | None = None


class FormSubmission(BaseModel):
    meta: FormMeta
    societe: dict
    reponses: dict
    reponses_detail: list[ReponseDetail]


# ── Helpers statut ─────────────────────────────────────────

def read_status(project_dir: Path) -> dict:
    """Lit le fichier status.json d'un projet."""
    status_path = project_dir / "status.json"
    if not status_path.exists():
        return None
    return json.loads(status_path.read_text(encoding="utf-8"))


def write_status(
    project_dir: Path,
    state: str,
    message: str,
    progress: int = 0,
    files: list[str] | None = None
):
    """Met à jour le fichier status.json d'un projet."""
    status = {
        "state": state,
        "message": message,
        "progress": progress,
        "updated_at": datetime.now().isoformat(),
        "files": files or []
    }
    status_path = project_dir / "status.json"
    status_path.write_text(
        json.dumps(status, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    logger.info(f"[{project_dir.name}] {state} — {message} ({progress}%)")


# ── Pipeline (arrière-plan) ────────────────────────────────

def run_pipeline_background(project_id: str, project_dir: Path, data: dict):
    """
    Wrapper qui lance l'orchestrateur en arrière-plan
    et met à jour le statut à chaque étape.
    """
    try:
        def on_progress(message: str, progress: int):
            write_status(project_dir, "running", message, progress)

        pipeline.run(
            data=data,
            output_dir=project_dir,
            on_progress=on_progress,
        )

        generated_files = [
            f.name for f in project_dir.iterdir()
            if f.suffix != ".json" and f.name != "debug"
        ]

        write_status(project_dir, "done",
                     "Tous les livrables ont été générés avec succès.",
                     progress=100,
                     files=sorted(generated_files))

    except Exception as e:
        logger.exception(f"[{project_id}] Erreur pipeline")
        write_status(project_dir, "error",
                     f"Erreur lors de la génération : {str(e)}")


# ── Endpoints API ──────────────────────────────────────────

@app.get("/api/config")
async def get_config():
    """Expose la configuration publique (features activées)."""
    return {"pappers_enabled": bool(config.PAPPERS_API_KEY)}


@app.get("/api/pappers/{siren}")
async def enrich_pappers(siren: str):
    """Enrichit les données société via l'API Pappers à partir du SIREN."""
    if not config.PAPPERS_API_KEY:
        raise HTTPException(status_code=503, detail="API Pappers non configurée")

    client = PappersClient()
    data = client.enrich(siren)

    if "_pappers_error" in data:
        raise HTTPException(status_code=502, detail=data["_pappers_error"])

    return data


@app.post("/api/submit", response_model=dict)
async def submit_form(data: FormSubmission, background_tasks: BackgroundTasks):
    """
    Reçoit le formulaire, sauvegarde les réponses,
    et lance le pipeline en arrière-plan.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    short_id = uuid.uuid4().hex[:6]

    slug = data.societe.get("raison_sociale", "prospect")
    slug = "".join(c if c.isalnum() else "_" for c in slug).strip("_").lower()
    slug = slug[:30]

    project_id = f"{timestamp}_{slug}_{short_id}"
    project_dir = OUTPUTS_DIR / project_id
    project_dir.mkdir(parents=True)

    input_path = project_dir / "input.json"
    input_path.write_text(
        data.model_dump_json(indent=2),
        encoding="utf-8"
    )

    write_status(project_dir, "pending", "Pipeline en attente de lancement…")

    background_tasks.add_task(
        run_pipeline_background,
        project_id,
        project_dir,
        data.model_dump()
    )

    logger.info(f"Nouveau projet soumis : {project_id}")

    return {
        "project_id": project_id,
        "status": "pending",
        "message": "Formulaire enregistré. La génération est en cours."
    }


@app.get("/api/status/{project_id}")
async def get_status(project_id: str):
    """Retourne l'état d'avancement du pipeline pour un projet."""
    project_dir = OUTPUTS_DIR / project_id

    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="Projet introuvable")

    status = read_status(project_dir)
    if status is None:
        raise HTTPException(status_code=404, detail="Statut introuvable")

    status["project_id"] = project_id
    return status


@app.get("/api/download/{project_id}/{filename}")
async def download_file(project_id: str, filename: str):
    """Télécharge un livrable généré."""
    project_dir = OUTPUTS_DIR / project_id
    file_path = (project_dir / filename).resolve()

    if not str(file_path).startswith(str(project_dir.resolve())):
        raise HTTPException(status_code=403, detail="Accès interdit")

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Fichier introuvable")

    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="application/octet-stream"
    )


@app.get("/api/projects")
async def list_projects():
    """Liste tous les projets avec leur statut."""
    projects = []
    for project_dir in sorted(OUTPUTS_DIR.iterdir(), reverse=True):
        if not project_dir.is_dir():
            continue
        status = read_status(project_dir)
        if status:
            status["project_id"] = project_dir.name
            projects.append(status)

    return {"projects": projects}


# ── Servir le frontend ─────────────────────────────────────

if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
else:
    logger.warning(
        f"Le dossier frontend/ n'existe pas ({FRONTEND_DIR}). "
        "Le formulaire ne sera pas servi."
    )


# ── Point d'entrée direct ─────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True, log_level="info")