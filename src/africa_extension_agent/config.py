"""Central configuration. Everything overridable via environment variables."""
from __future__ import annotations

import os
from pathlib import Path

DB_PATH = Path(os.environ.get("EXTENSION_AGENT_DB", Path.cwd() / "data" / "extension.sqlite"))

# Any Pydantic AI model string. Examples:
#   mistral:mistral-large-latest   (needs MISTRAL_API_KEY)
#   ollama:mistral-nemo            (open-weight, local, needs `ollama serve`)
DEFAULT_MODEL = os.environ.get("EXTENSION_AGENT_MODEL", "mistral:mistral-large-latest")

MAX_TOOL_CALLS = int(os.environ.get("EXTENSION_AGENT_MAX_TOOL_CALLS", "12"))
