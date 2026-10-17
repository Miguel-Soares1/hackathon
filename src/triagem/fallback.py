"""Plano B (ADR-009): classificação por palavras-chave quando o LLM falha. Confiança sempre baixa."""
import re

from .domain import Classificacao, normalizar

# assunto -> (palavras-chave, equipe, resposta sugerida)
REGRAS = {
    "pagamento": (
        ["pix", "pagamento", "pagar", "cartao", "boleto", "transacao", "checkout"],
        "financeiro",
        "Olá! Vimos a dificuldade com o seu pagamento e já estamos verificando. "
        "Pode nos enviar o horário aproximado da falha e o comprovante, se houver?",
    ),
    "cobranca": (
        ["fatura", "cobranca", "cobrado", "cobrada", "estorno", "nota fiscal", "segunda via", "vencimento", "reembolso"],
        "financeiro",
        "Olá! Vamos revisar a sua cobrança. Pode confirmar o mês da fatura? "
        "Se houver erro, solicitaremos o estorno imediatamente.",
    ),
    "acesso": (
        ["login", "senha", "acessar", "acesso", "entrar", "bloqueado", "autenticacao", "codigo de verificacao"],
        "suporte_tecnico",
        "Olá! Vamos ajudar com o seu acesso. Enviamos um link de redefinição de senha para o e-mail "
        "cadastrado. Se não chegar, nos avise.",
    ),
    "instabilidade": (
        ["fora do ar", "erro", "travou", "lento", "lentidao", "caiu", "instavel", "parou", "bug", "errados", "errado"],
        "engenharia",
        "Olá! Obrigado por avisar. Nossa equipe técnica já está analisando e retornaremos assim que "
        "houver atualização.",
    ),
    "cancelamento": (
        ["cancelar", "cancelamento", "encerrar", "desistir", "assinatura"],
        "retencao",
        "Olá! Sentiremos a sua falta. Antes de prosseguir, podemos entender o motivo e ver se conseguimos "
        "resolver ou oferecer uma alternativa?",
    ),
    "reclamacao": (
        ["reclamacao", "reclamar", "inaceitavel", "absurdo", "pessimo", "horrivel", "demoraram", "irritado"],
        "atendimento",
        "Olá! Lamentamos a experiência e queremos corrigir isso. Pode nos contar mais detalhes para "
        "priorizarmos o seu caso?",
    ),
    "elogio": (
        ["parabens", "excelente", "otimo", "obrigado", "obrigada"],
        "atendimento",
        "Olá! Ficamos muito felizes com o seu retorno e vamos repassá-lo à equipe. Obrigado!",
    ),
    "duvida": (
        ["como", "duvida", "onde", "qual", "posso", "quero saber"],
        "atendimento",
        "Olá! Claro, vamos ajudar. Segue o passo a passo para o que você precisa; qualquer dúvida, é só responder.",
    ),
}

URGENCIA_CRITICA = ["urgente", "fora do ar", "perdendo", "prejuizo", "ninguem consegue", "caiu", "agora"]
URGENCIA_ALTA = ["nao consigo", "bloqueado", "travou", "parou", "duas vezes", "indevid", "inaceitavel", "absurdo"]
URGENCIA_MEDIA = ["cancelar", "reclamacao", "demora", "dias", "erro", "lento"]

NEGATIVO = ["horrivel", "pessimo", "absurdo", "inaceitavel", "cansado", "irritado", "prejuizo", "perdendo",
            "nunca", "urgente", "problema", "erro", "nao consigo", "nao funciona", "travou", "caiu"]
POSITIVO = ["parabens", "obrigado", "obrigada", "otimo", "excelente", "perfeito"]

DEFAULT_ASSUNTO = "duvida"


def _tokens(texto: str) -> str:
    return " " + re.sub(r"[^a-z0-9]+", " ", normalizar(texto)) + " "


def _contem(norm: str, chave: str) -> bool:
    return f" {chave} " in norm or (len(chave) >= 6 and chave in norm)


def classificar_por_regras(texto: str) -> Classificacao:
    norm = _tokens(texto)

    melhor, hits = DEFAULT_ASSUNTO, 0
    for assunto, (chaves, _, _) in REGRAS.items():
        n = sum(1 for c in chaves if _contem(norm, c))
        if n > hits:
            melhor, hits = assunto, n
    _, equipe, resposta = REGRAS[melhor]

    if any(_contem(norm, c) for c in URGENCIA_CRITICA):
        urgencia = "critica"
    elif any(_contem(norm, c) for c in URGENCIA_ALTA):
        urgencia = "alta"
    elif any(_contem(norm, c) for c in URGENCIA_MEDIA):
        urgencia = "media"
    else:
        urgencia = "baixa"

    neg = sum(1 for c in NEGATIVO if _contem(norm, c))
    if neg and "!" in texto:
        neg += 1
    pos = sum(1 for c in POSITIVO if _contem(norm, c))
    sentimento = "positivo" if pos > neg else "negativo" if neg else "neutro"

    base = round(min(0.55, 0.30 + 0.08 * hits), 3)
    return Classificacao(
        assunto=melhor,
        urgencia=urgencia,
        sentimento=sentimento,
        equipe=equipe,
        resposta_sugerida=resposta,
        confianca={"assunto": base, "urgencia": 0.35, "sentimento": 0.35, "equipe": base},
        origem="fallback",
    )
