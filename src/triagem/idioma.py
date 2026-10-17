"""Detecção local de idioma (ADR-015): palavras funcionais e acentos típicos, sem rede e sem modelo.

Serve para o plano B escolher a resposta no idioma do cliente e para conferir se a resposta sugerida pelo LLM
saiu no mesmo idioma da mensagem. Em textos curtos ou sem sinais, assume português (o público principal).
"""
import re
import unicodedata
from dataclasses import dataclass

IDIOMAS = {
    "pt": "português",
    "en": "inglês",
    "es": "espanhol",
    "fr": "francês",
    "it": "italiano",
    "de": "alemão",
}
PADRAO = "pt"

# Palavras sem acento (como saem de `_tokens`). Ficam de fora as que se confundem entre idiomas
# (ex.: "no", "la", "mas", "esta", "aqui", "posso", "porque", "mes").
PALAVRAS = {
    "pt": {"nao", "voce", "voces", "estou", "meu", "minha", "meus", "minhas", "com", "uma", "isso", "isto",
           "obrigado", "obrigada", "ja", "sao", "foi", "tem", "quero", "preciso", "consigo", "ainda", "tambem",
           "muito", "muita", "hoje", "bom", "boa", "ola", "oi", "pelo", "pela", "seu", "sua", "nossa", "conta",
           "senha", "fatura", "cobranca", "atendimento", "estao", "fiz", "consegui", "entao", "vcs", "pq"},
    "en": {"the", "and", "is", "are", "my", "i", "you", "your", "not", "cannot", "can", "with", "for", "this",
           "that", "it", "to", "of", "have", "has", "was", "please", "thanks", "thank", "hello", "hi", "account",
           "payment", "working", "doesn", "don", "im", "we", "our", "what", "how", "why", "when", "will", "would",
           "still", "since", "been", "be", "an", "at", "on", "from", "help", "password", "card", "refund", "invoice", "thx", "good", "now", "all"},
    "es": {"usted", "ustedes", "estoy", "mi", "mis", "con", "el", "los", "las", "del", "es", "pero", "muy", "hoy",
           "gracias", "quiero", "necesito", "puedo", "tengo", "hola", "tambien", "cuenta", "pago", "factura",
           "contrasena", "ayuda", "ya", "cuando", "donde", "sin", "dinero", "desde", "hace"},
    "fr": {"le", "les", "je", "ne", "pas", "vous", "est", "et", "mon", "une", "des", "avec", "pour", "bonjour",
           "merci", "ca", "suis", "nous", "votre", "au", "aux", "sur", "dans", "compte", "paiement", "aide", "j"},
    "it": {"il", "non", "sono", "mio", "mia", "per", "che", "grazie", "ciao", "buongiorno", "gli", "della",
           "dello", "questo", "questa", "ho", "hai", "voglio", "aiuto", "conto", "perche", "molto", "anche",
           "ancora", "di", "essere", "riesco"},
    "de": {"der", "die", "das", "und", "ist", "nicht", "ich", "mein", "meine", "mit", "fur", "ein", "eine",
           "danke", "hallo", "bitte", "funktioniert", "kann", "auf", "zu", "den", "dem", "sie", "wir", "konto",
           "zahlung", "hilfe", "habe", "mir", "mich", "keine"},
}
# Caracteres que quase só aparecem em um idioma (contados no texto original, em minúsculas).
MARCAS = {"pt": "ãõ", "es": "ñ¿¡", "de": "ßäöü"}


@dataclass(frozen=True)
class Deteccao:
    codigo: str
    confianca: float  # fração dos sinais que apontam para o idioma escolhido (0 a 1)
    forte: bool  # sinais suficientes e sem empate: pode ser usado para recusar uma resposta


def _sem_acento(texto: str) -> str:
    s = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def detectar(texto: str) -> Deteccao:
    tokens = re.findall(r"[a-z]+", _sem_acento(texto))
    minusculo = texto.lower()
    pontos = {}
    for codigo, palavras in PALAVRAS.items():
        n = sum(1 for t in tokens if t in palavras)
        n += min(3, sum(minusculo.count(c) for c in MARCAS.get(codigo, "")))
        pontos[codigo] = n
    ordem = sorted(pontos.items(), key=lambda kv: (-kv[1], kv[0] != PADRAO))
    (melhor, p1), (_, p2) = ordem[0], ordem[1]
    total = sum(pontos.values())
    if p1 == 0:
        return Deteccao(PADRAO, 0.0, False)
    return Deteccao(melhor, round(p1 / total, 3), p1 >= 3 and p1 >= 2 * p2)


def normalizar_codigo(valor) -> str:
    """'pt-BR' -> 'pt', 'EN' -> 'en', 'Português'/'english' -> código; '' se não der para entender."""
    s = _sem_acento(str(valor or "")).strip()
    nomes = {_sem_acento(n): c for c, n in IDIOMAS.items()}
    nomes.update({"portuguese": "pt", "english": "en", "spanish": "es", "espanol": "es", "french": "fr",
                  "francais": "fr", "italian": "it", "german": "de", "deutsch": "de"})
    if s in nomes:
        return nomes[s]
    codigo = re.split(r"[-_]", s)[0]
    return codigo if re.fullmatch(r"[a-z]{2}", codigo) else ""
