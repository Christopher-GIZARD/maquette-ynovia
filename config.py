"""
Ynov'iT Presales Pipeline — Configuration

Centralise toutes les valeurs de configuration.
Les secrets sont lus depuis les variables d'environnement
ou un fichier .env à la racine du projet.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Charge le .env s'il existe
load_dotenv()

# ── Chemins ────────────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent
OUTPUTS_DIR = BASE_DIR / "outputs"
FRONTEND_DIR = BASE_DIR / "frontend"
PROMPTS_DIR = BASE_DIR / "prompts"
DATA_DIR = BASE_DIR / "data"

DECISION_TREE_PATH = DATA_DIR / "decision_tree.json"
ODOO_MODULES_MAP_PATH = DATA_DIR / "odoo_modules_map.json"

# Crée les répertoires s'ils n'existent pas
OUTPUTS_DIR.mkdir(exist_ok=True)
PROMPTS_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)

# ── API Claude ─────────────────────────────────────────────

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514")
CLAUDE_MAX_TOKENS = int(os.getenv("CLAUDE_MAX_TOKENS", "8096"))
CLAUDE_TEMPERATURE = float(os.getenv("CLAUDE_TEMPERATURE", "0.3"))

# Mode : "api" (appels réels) ou "mock" (réponses simulées pour le dev)
# Si pas de clé API définie, bascule automatiquement en mock
CLAUDE_MODE = os.getenv("CLAUDE_MODE", "auto")  # auto | api | mock

# ── API Pappers ────────────────────────────────────────────

PAPPERS_API_KEY = os.getenv("PAPPERS_API_KEY", "")

# ── Pipeline ───────────────────────────────────────────────

# Nombre de projets similaires à injecter dans le contexte chiffrage
SIMILAR_PROJECTS_LIMIT = int(os.getenv("SIMILAR_PROJECTS_LIMIT", "5"))

# ── Serveur ────────────────────────────────────────────────

SERVER_HOST = os.getenv("SERVER_HOST", "0.0.0.0")
SERVER_PORT = int(os.getenv("SERVER_PORT", "8000"))