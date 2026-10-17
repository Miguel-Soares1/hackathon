"""Vocabulário controlado da triagem e o modelo validado da classificação."""
import unicodedata

from pydantic import BaseModel, Field, field_validator

from .idioma import normalizar_codigo

ASSUNTOS = ("cobranca", "pagamento", "acesso", "instabilidade", "cancelamento", "reclamacao", "duvida", "elogio")
URGENCIAS = ("baixa", "media", "alta", "critica")
SENTIMENTOS = ("positivo", "neutro", "negativo")
EQUIPES = ("financeiro", "suporte_tecnico", "engenharia", "retencao", "atendimento")

DIMENSOES_CLASSIFICACAO = ("assunto", "urgencia", "sentimento", "equipe")
DIMENSOES = DIMENSOES_CLASSIFICACAO + ("resposta_sugerida",)

VALORES_PERMITIDOS = {
    "assunto": ASSUNTOS,
    "urgencia": URGENCIAS,
    "sentimento": SENTIMENTOS,
    "equipe": EQUIPES,
}

MAX_RESPOSTA = 2000


def normalizar(valor: str) -> str:
    """minúsculas, sem acento e sem espaços nas pontas ('Média ' -> 'media')."""
    s = unicodedata.normalize("NFD", str(valor).strip().lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


class Classificacao(BaseModel):
    assunto: str
    urgencia: str
    sentimento: str
    equipe: str
    resposta_sugerida: str = Field(min_length=1, max_length=MAX_RESPOSTA)
    # Código ISO 639-1 do idioma do cliente; vazio = não informado (o classificador completa, ADR-015).
    idioma: str = ""
    confianca: dict[str, float]
    origem: str = "llm"
    # Preenchidos pelo classificador, nunca pela resposta do LLM (ver classifier.chamar_llm).
    prompt_version: str = "v2"
    exemplos: list[int] = Field(default_factory=list)

    @field_validator("assunto", "urgencia", "sentimento", "equipe", mode="before")
    @classmethod
    def _valor_permitido(cls, v, info):
        valor = normalizar(v)
        if valor not in VALORES_PERMITIDOS[info.field_name]:
            raise ValueError(f"{info.field_name} fora do conjunto permitido: {valor!r}")
        return valor

    @field_validator("idioma", mode="before")
    @classmethod
    def _idioma(cls, v):
        # Tolerante: um idioma ilegível não invalida a classificação inteira.
        return normalizar_codigo(v)

    @field_validator("resposta_sugerida", mode="before")
    @classmethod
    def _resposta_texto(cls, v):
        if not isinstance(v, str):
            raise ValueError("resposta_sugerida deve ser texto")
        return v.strip()

    @field_validator("confianca")
    @classmethod
    def _confianca_valida(cls, v):
        faltando = [d for d in DIMENSOES_CLASSIFICACAO if d not in v]
        if faltando:
            raise ValueError(f"confianca sem as dimensões: {faltando}")
        for dim in DIMENSOES_CLASSIFICACAO:
            if not 0.0 <= v[dim] <= 1.0:
                raise ValueError(f"confianca.{dim} deve estar entre 0 e 1")
        return {dim: float(v[dim]) for dim in DIMENSOES_CLASSIFICACAO}

    @field_validator("origem")
    @classmethod
    def _origem(cls, v):
        if v not in ("llm", "fallback"):
            raise ValueError("origem deve ser 'llm' ou 'fallback'")
        return v
