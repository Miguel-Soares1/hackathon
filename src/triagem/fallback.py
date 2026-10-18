"""Plano B (ADR-009): classificação por palavras-chave quando o LLM falha. Confiança sempre baixa.

Responde no idioma do cliente (ADR-015): português, inglês ou espanhol; outros idiomas recebem a resposta em inglês.
As palavras-chave são em português, com alguns termos em inglês e espanhol.
"""
import re

from .domain import Classificacao, normalizar
from .idioma import detectar

# assunto -> (palavras-chave, equipe, resposta sugerida)
REGRAS = {
    "pagamento": (
        ["pix", "pagamento", "pagar", "cartao", "boleto", "transacao", "checkout", "payment", "pay", "card", "tarjeta"],
        "financeiro",
        "Olá! Vimos a dificuldade com o seu pagamento e já estamos verificando. "
        "Pode nos enviar o horário aproximado da falha e o comprovante, se houver?",
    ),
    "cobranca": (
        ["fatura", "cobranca", "cobrado", "cobrada", "estorno", "nota fiscal", "segunda via", "vencimento", "reembolso",
         "invoice", "charged", "refund", "bill", "factura", "cobro"],
        "financeiro",
        "Olá! Vamos revisar a sua cobrança. Pode confirmar o mês da fatura? "
        "Se houver erro, solicitaremos o estorno imediatamente.",
    ),
    "acesso": (
        ["login", "senha", "acessar", "acesso", "entrar", "bloqueado", "autenticacao", "codigo de verificacao",
         "password", "log in", "sign in", "contrasena"],
        "suporte_tecnico",
        "Olá! Vamos ajudar com o seu acesso. Enviamos um link de redefinição de senha para o e-mail "
        "cadastrado. Se não chegar, nos avise.",
    ),
    "instabilidade": (
        ["fora do ar", "erro", "travou", "lento", "lentidao", "caiu", "instavel", "parou", "bug", "errados", "errado",
         "error", "crash", "slow", "down"],
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
        ["reclamacao", "reclamar", "inaceitavel", "absurdo", "pessimo", "horrivel", "demoraram", "irritado",
         "complaint", "terrible", "awful", "queja"],
        "atendimento",
        "Olá! Lamentamos a experiência e queremos corrigir isso. Pode nos contar mais detalhes para "
        "priorizarmos o seu caso?",
    ),
    "elogio": (
        ["parabens", "excelente", "otimo", "obrigado", "obrigada", "thanks", "thank you", "great", "gracias"],
        "atendimento",
        "Olá! Ficamos muito felizes com o seu retorno e vamos repassá-lo à equipe. Obrigado!",
    ),
    "duvida": (
        ["como", "duvida", "onde", "qual", "posso", "quero saber", "how", "where", "donde"],
        "atendimento",
        "Olá! Claro, vamos ajudar. Segue o passo a passo para o que você precisa; qualquer dúvida, é só responder.",
    ),
}

URGENCIA_CRITICA = ["urgente", "fora do ar", "perdendo", "prejuizo", "ninguem consegue", "caiu", "agora",
                    "urgent", "asap", "losing", "perdiendo"]
URGENCIA_ALTA = ["nao consigo", "bloqueado", "travou", "parou", "duas vezes", "indevid", "inaceitavel", "absurdo",
                 "cannot", "can t", "blocked", "no puedo"]
URGENCIA_MEDIA = ["cancelar", "reclamacao", "demora", "dias", "erro", "lento", "error", "slow"]

NEGATIVO = ["horrivel", "pessimo", "absurdo", "inaceitavel", "cansado", "irritado", "prejuizo", "perdendo",
            "nunca", "urgente", "problema", "erro", "nao consigo", "nao funciona", "travou", "caiu",
            "terrible", "awful", "angry", "not working", "problem", "cannot", "can t", "no funciona", "no puedo"]
POSITIVO = ["parabens", "obrigado", "obrigada", "otimo", "excelente", "perfeito", "thanks", "thank you", "great",
            "excellent", "gracias"]

# Respostas prontas em outros idiomas (a de português fica em REGRAS).
RESPOSTAS = {
    "en": {
        "pagamento": "Hello! We are aware of the problem with your payment and are already looking into it. "
                     "Could you send us the approximate time of the failure and the receipt, if you have one?",
        "cobranca": "Hello! We will review your bill. Could you confirm the month of the invoice? "
                    "If there is a mistake, we will request a refund right away.",
        "acesso": "Hello! We will help you with your access. We have sent a password reset link to your registered "
                  "email. Please let us know if it does not arrive.",
        "instabilidade": "Hello! Thank you for letting us know. Our technical team is already looking into it and we "
                         "will get back to you as soon as there is an update.",
        "cancelamento": "Hello! We are sorry to see you go. Before we proceed, could you tell us the reason, so we can "
                        "try to solve it or offer an alternative?",
        "reclamacao": "Hello! We are sorry about your experience and we want to make it right. Could you share more "
                      "details so we can prioritize your case?",
        "elogio": "Hello! We are very happy with your feedback and will share it with the team. Thank you!",
        "duvida": "Hello! Of course, we are happy to help. Please tell us a bit more about what you need and we will "
                  "guide you step by step.",
    },
    "es": {
        "pagamento": "¡Hola! Vimos el problema con su pago y ya lo estamos revisando. "
                     "¿Puede enviarnos la hora aproximada del fallo y el comprobante, si lo tiene?",
        "cobranca": "¡Hola! Vamos a revisar su cobro. ¿Puede confirmar el mes de la factura? "
                    "Si hay un error, solicitaremos el reembolso de inmediato.",
        "acesso": "¡Hola! Vamos a ayudarle con su acceso. Enviamos un enlace para restablecer la contraseña a su "
                  "correo registrado. Si no llega, avísenos.",
        "instabilidade": "¡Hola! Gracias por avisarnos. Nuestro equipo técnico ya lo está analizando y le "
                         "responderemos en cuanto tengamos novedades.",
        "cancelamento": "¡Hola! Lamentamos que quiera irse. Antes de continuar, ¿podría contarnos el motivo para "
                        "intentar resolverlo u ofrecerle una alternativa?",
        "reclamacao": "¡Hola! Lamentamos su experiencia y queremos solucionarlo. ¿Puede darnos más detalles para "
                      "priorizar su caso?",
        "elogio": "¡Hola! Nos alegra mucho su comentario y lo compartiremos con el equipo. ¡Gracias!",
        "duvida": "¡Hola! Claro, con gusto le ayudamos. Cuéntenos un poco más sobre lo que necesita y le guiaremos "
                  "paso a paso.",
    },
}
IDIOMA_RESPOSTA_PADRAO = "en"  # para idiomas sem resposta pronta (fr, it, de...)

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
    idioma = detectar(texto).codigo
    if idioma != "pt":
        resposta = RESPOSTAS.get(idioma, RESPOSTAS[IDIOMA_RESPOSTA_PADRAO])[melhor]

    urgencia, sinal = "baixa", None
    for nivel, chaves in (("critica", URGENCIA_CRITICA), ("alta", URGENCIA_ALTA), ("media", URGENCIA_MEDIA)):
        sinal = next((c for c in chaves if _contem(norm, c)), None)
        if sinal:
            urgencia = nivel
            break
    justificativa = (
        f"Plano B por regras: o termo “{sinal}” na mensagem indica urgência {urgencia}." if sinal
        else "Plano B por regras: nenhum sinal de urgência na mensagem."
    )

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
        idioma=idioma,
        confianca={"assunto": base, "urgencia": 0.35, "sentimento": 0.35, "equipe": base},
        justificativa=justificativa,
        origem="fallback",
        prompt_version="regras",
    )
