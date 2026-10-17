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
        embedding_backend=os.getenv("EMBEDDING_BACKEND", "sbert").lower(),
        embedding_model=os.getenv(
            "EMBEDDING_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
        ),
    )
