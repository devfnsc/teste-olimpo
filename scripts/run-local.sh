#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"

if [[ ! -x ".venv/bin/python" ]]; then
  echo "Ambiente Python não encontrado. No Ubuntu/WSL, crie .venv e instale as dependências conforme o README.md."
  exit 1
fi

export PYTHONPATH="$project_root/src${PYTHONPATH:+:$PYTHONPATH}"
export OLIMPO_ENV=development
export DISPATCH_ENABLED=false
export GLOBAL_KILL_SWITCH=true
export INSTAGRAM_PROVIDER=legacy

# Isola esta execução de bancos e serviços configurados em um .env local.
export DATABASE_URL="postgresql+asyncpg://olimpo:olimpo@127.0.0.1:5432/olimpo"
export REDIS_URL="redis://127.0.0.1:6379/0"
export LLM_GATEWAY_URL="http://127.0.0.1:4000"

# Não disponibiliza credenciais para integrações externas nesta execução.
export APPRUNCLOUD_API_KEY=""
export FAL_API_KEY=""
export OPENAI_IMAGE_KEY=""
export REPLICATE_API_KEY=""
export LITELLM_MASTER_KEY=""
export ORCHESTRATOR_URL=""
export ORCHESTRATOR_TOKEN=""
export PERSONA_ENGINE_URL=""
export PERSONA_ENGINE_TOKEN=""
export ANDROID_MANAGER_URL=""
export ANDROID_MANAGER_TOKEN=""
export MEDIA_FORGE_URL=""
export MEDIA_FORGE_TOKEN=""

exec .venv/bin/python -m uvicorn olimpo.api.main:app --reload --host 127.0.0.1 --port 8000

