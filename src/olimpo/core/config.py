"""Configuração central. Tudo vem de variável de ambiente — ver .env.example."""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- ambiente ---------------------------------------------------------
    olimpo_env: Literal["development", "staging", "production"] = "development"
    log_level: str = "INFO"

    # Interruptor mestre: com False nada é enviado ao android-orchestrator;
    # as ações são gravadas em dryrun/. Padrão seguro.
    dispatch_enabled: bool = False
    # Parada total: todos os agentes ficam inertes.
    global_kill_switch: bool = False

    # --- infra ------------------------------------------------------------
    database_url: str = "postgresql+asyncpg://olimpo:olimpo@postgres:5432/olimpo"
    database_pool_size: int = Field(default=4, ge=1, le=50)
    database_max_overflow: int = Field(default=2, ge=0, le=50)
    redis_url: str = "redis://redis:6379/0"

    secret_key: str = ""
    api_token: str = ""

    # --- LLM --------------------------------------------------------------
    llm_gateway_url: str = "http://litellm:4000"
    litellm_master_key: str = ""
    llm_daily_budget_usd: float = 5.0

    # Geração de personas: chamada direta ao Gemini, exclusivamente no backend.
    gemini_api_key: str = ""
    gemini_persona_model: str = "gemini-3.8-flash"
    gemini_persona_fallback_model: str = "gemini-3.6-flash"
    persona_generation_max_output_tokens: int = Field(default=8192, ge=2048, le=16384)

    # --- geração de mídia -------------------------------------------------
    # A geração com IMAGEM DE REFERÊNCIA e a de vídeo não passam pelo
    # gateway: ele só expõe texto→imagem. Ver media/providers/base.py.
    fal_api_key: str = ""
    openai_image_key: str = ""
    replicate_api_key: str = ""
    cloudflare_account_id: str = ""
    cloudflare_api_token: str = ""

    # --- serviços externos ------------------------------------------------
    # Semente do primeiro nó numa instalação nova. A lista real de servidores
    # vive em `orchestrator_nodes` — o serviço não tem índice de frota, e não
    # tem webhook: a confirmação é por polling. Ver ADR-0011.
    orchestrator_url: str = ""
    orchestrator_token: str = ""

    persona_engine_url: str = ""
    persona_engine_token: str = ""

    android_manager_url: str = ""
    android_manager_token: str = ""

    media_forge_url: str = ""
    media_forge_token: str = ""

    # --- operação ---------------------------------------------------------
    worker_concurrency: int = 8

    # Anti-detecção. Ver docs/06-campanhas.md §5.
    campaign_jitter_min_minutes: int = 25
    campaign_jitter_max_minutes: int = 240
    campaign_max_participation: float = Field(default=0.6, ge=0.0, le=1.0)
    account_max_actions_per_hour: int = 12

    l2_sampling_rate: float = Field(default=0.10, ge=0.0, le=1.0)

    # Caminho onde o modo dry-run grava o que teria sido publicado.
    dryrun_dir: str = "/app/dryrun"
    media_root: str = "/app/media"

    @property
    def sync_database_url(self) -> str:
        """URL síncrona — o runner de migrações usa psycopg, não asyncpg."""
        value = self.database_url.strip()
        value = value.replace("postgres://", "postgresql://", 1)
        value = value.replace("postgresql+asyncpg://", "postgresql://", 1)
        return value

    @property
    def async_database_url(self) -> str:
        """Normaliza URLs Supabase/Postgres para o driver assíncrono do SQLAlchemy."""
        value = self.database_url.strip()
        value = value.replace("postgres://", "postgresql://", 1)
        if value.startswith("postgresql://"):
            value = value.replace("postgresql://", "postgresql+asyncpg://", 1)
        # asyncpg aceita sslmode na URI libpq, como a connection string do
        # Supabase fornece.
        return value

    @property
    def is_production(self) -> bool:
        return self.olimpo_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

