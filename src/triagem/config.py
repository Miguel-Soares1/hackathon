"""Configuração lida do ambiente (.env). Nenhum segredo fica no código."""
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    database_url: str
    api_key: str
    deepseek_api_key: str
    deepseek_base_url: str
    deepseek_model: str
    llm_timeout: float
    embedding_backend: str
    embedding_model: str
    environment: str
    docs_enabled: bool
    trust_proxy: bool
    public_rate_per_ip_min: int
    public_rate_global_min: int
    whatsapp_verify_token: str
    whatsapp_app_secret: str
    instagram_verify_token: str
    instagram_app_secret: str
    demo_enabled: bool
    fewshot_k: int = 4
    fewshot_sim_min: float = 0.45
    gemini_api_key: str = ""
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    gemini_model: str = "gemini-3.8-flash"
    midia_timeout: float = 60.0


def _bool(nome: str, padrao: bool) -> bool:
    return os.getenv(nome, "1" if padrao else "0").strip().lower() in ("1", "true", "sim", "yes")


def get_settings() -> Settings:
    """Lê o ambiente a cada chamada (barato) para que os testes possam alterá-lo."""
    return Settings(
        database_url=os.getenv(
            "DATABASE_URL", "mysql+pymysql://hackathon:hackathon@127.0.0.1:3306/hackathon"
        ),
        api_key=os.getenv("API_KEY", ""),
        deepseek_api_key=os.getenv("DEEPSEEK_API_KEY", ""),
        deepseek_base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/"),
        deepseek_model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
        llm_timeout=float(os.getenv("LLM_TIMEOUT_SECONDS", "15")),
        fewshot_k=int(os.getenv("FEWSHOT_K", "4")),
        fewshot_sim_min=float(os.getenv("FEWSHOT_SIM_MIN", "0.45")),
        gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
        gemini_base_url=os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta").rstrip("/"),
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-3.8-flash"),
        midia_timeout=float(os.getenv("MIDIA_TIMEOUT_SECONDS", "60")),
        embedding_backend=os.getenv("EMBEDDING_BACKEND", "onnx").lower(),
        embedding_model=os.getenv(
            "EMBEDDING_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
        ),
        environment=os.getenv("ENVIRONMENT", "development").lower(),
        docs_enabled=_bool("DOCS_ENABLED", True),
        trust_proxy=_bool("TRUST_PROXY", False),
        public_rate_per_ip_min=int(os.getenv("PUBLIC_RATE_PER_IP_MIN", "5")),
        public_rate_global_min=int(os.getenv("PUBLIC_RATE_GLOBAL_MIN", "60")),
        whatsapp_verify_token=os.getenv("WHATSAPP_VERIFY_TOKEN", ""),
        whatsapp_app_secret=os.getenv("WHATSAPP_APP_SECRET", ""),
        instagram_verify_token=os.getenv("INSTAGRAM_VERIFY_TOKEN", ""),
        # O Instagram costuma estar no mesmo app da Meta que o WhatsApp: sem segredo próprio, usa o do app.
        instagram_app_secret=os.getenv("INSTAGRAM_APP_SECRET", "") or os.getenv("WHATSAPP_APP_SECRET", ""),
        # Telas /demo/*: ligadas por padrão em desenvolvimento, sempre desligadas em produção.
        demo_enabled=_bool("DEMO", _bool("DEMO_EMAIL", True)) and os.getenv("ENVIRONMENT", "development").lower() != "production",
    )


CHAVES_FRACAS = {"", "troque-esta-chave", "changeme", "admin", "password", "chave-de-teste"}


def validar_producao(s: Settings) -> None:
    """Em produção, recusa subir com segredos fracos ou ausentes (falha rápida)."""
    if s.environment != "production":
        return
    problemas = []
    if s.api_key in CHAVES_FRACAS or len(s.api_key) < 24:
        problemas.append("API_KEY deve ter pelo menos 24 caracteres e não pode ser um valor de exemplo")
    if "hackathon:hackathon@" in s.database_url:
        problemas.append("DATABASE_URL usa a senha padrão do ambiente de desenvolvimento")
    if problemas:
        raise RuntimeError("Configuração insegura para produção: " + "; ".join(problemas))
