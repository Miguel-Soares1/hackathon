"""Painel de monitoramento (Spec 4, ADR-005). Executar com: streamlit run dashboard/app.py"""
import sys
from datetime import timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import hmac  # noqa: E402
import html  # noqa: E402
import os  # noqa: E402

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from triagem import corrections, incidents, metrics, tickets  # noqa: E402
from triagem.domain import ASSUNTOS, EQUIPES, SENTIMENTOS, URGENCIAS  # noqa: E402

FUSO = ZoneInfo("America/Sao_Paulo")
ORDEM_URGENCIA = {"critica": 0, "alta": 1, "media": 2, "baixa": 3, None: 4}
ROTULO_ESTADO = {
    "estourado": "🔴 estourado", "em_risco": "🟠 em risco", "no_prazo": "🟢 no prazo",
    "respondido": "✅ respondido", "aguardando_classificacao": "⏳ classificando",
}
POLITICA_TEXTO = {
    "normal": ("success", "Error budget saudável: desenvolvimento de funcionalidades segue."),
    "alerta": ("warning", "Mais de 50% do error budget consumido: revisar tickets em risco e a política de SLA."),
    "congelar_funcionalidades": ("error", "Error budget esgotado: congelar funcionalidades novas e corrigir as causas dos atrasos."),
    "sem_dados": ("info", "Ainda não há tickets com desfecho para calcular o SLI."),
}

PAGINAS = [
    ("dashboard", "Dashboard", ":material/dashboard:"),
    ("atendimento", "Atendimento", ":material/forum:"),
    ("incidentes", "Incidentes", ":material/crisis_alert:"),
    ("correcoes", "Correções", ":material/edit_note:"),
]
COR_URGENCIA = {"critica": "#f87171", "alta": "#fb923c", "media": "#facc15", "baixa": "#4ade80"}
COR_SLA = {"estourado": "#f87171", "em_risco": "#fb923c", "no_prazo": "#4ade80", "respondido": "#8fb0c6"}
ROTULO_SLA_CURTO = {"estourado": "prazo estourado", "em_risco": "prazo em risco", "no_prazo": "no prazo",
                    "respondido": "1ª resposta feita", "aguardando_classificacao": "classificando"}

CSS = """
<style>
.stApp { background: radial-gradient(1200px 600px at 100% 0%, #0b2f4a 0%, #06182a 55%); }
header[data-testid="stHeader"] { background: transparent; }
[data-testid="stSidebar"] { background: linear-gradient(180deg, #082033 0%, #061a2c 100%); border-right: 1px solid #12354f; }
[data-testid="stSidebar"] .marca { display:flex; align-items:center; gap:10px; margin: 4px 0 18px; }
[data-testid="stSidebar"] .marca .logo { width:34px; height:34px; border-radius:10px; background:#2dd4bf; color:#052a2a;
  display:flex; align-items:center; justify-content:center; font-weight:700; font-size:18px; }
[data-testid="stSidebar"] .marca .nome { font-size:20px; font-weight:600; color:#e6f1f8; letter-spacing:.2px; }
[data-testid="stSidebar"] .menu-titulo { color:#8fb0c6; font-size:13px; margin: 0 0 6px 4px; }
[data-testid="stSidebar"] .stButton > button { width:100%; justify-content:flex-start; text-align:left; border-radius:12px;
  background: transparent; border: 1px solid transparent; color:#cfe3f1; padding: 10px 14px; }
[data-testid="stSidebar"] .stButton > button > div { justify-content:flex-start; width:100%; }
[data-testid="stSidebar"] .stButton > button p { text-align:left; }
[data-testid="stSidebar"] .stButton > button:hover { background:#0d2c46; border-color:#17405f; }
[data-testid="stSidebar"] .stButton > button[kind="primary"] { background: rgba(45,212,191,.12); border-color:#1f7a72; color:#7ff0df; }
.cartao { background:#0a2238; border:1px solid #14405f; border-radius:14px; padding:12px 14px; margin-bottom:4px; }
.cartao.sel { border-color:#2dd4bf; box-shadow: 0 0 0 1px #2dd4bf33; }
.cartao .topo { display:flex; align-items:center; gap:12px; }
.cartao .avatar { width:36px; height:36px; border-radius:50%; border:1px solid #2a5a7c; display:flex; align-items:center;
  justify-content:center; font-weight:600; color:#e6f1f8; flex:none; }
.cartao .nome { font-weight:600; color:#f1f8fd; font-size:15px; }
.cartao .sub { color:#8fb0c6; font-size:12.5px; }
.cartao .linha { margin-top:8px; color:#cfe3f1; font-size:13.5px; }
.cartao .msg { margin-top:6px; color:#e6f1f8; font-size:14px; }
.selo { display:inline-block; border-radius:999px; padding:1px 9px; font-size:11.5px; font-weight:500; margin-right:6px;
  border:1px solid currentColor; }
.linha-chat { display:flex; margin: 4px 0; }
.linha-chat.saida { justify-content:flex-end; }
.bolha { max-width:78%; border-radius:14px; padding:8px 12px; font-size:14px; line-height:1.45; color:#e6f1f8; }
.bolha.entrada { background:#0f3050; border:1px solid #1d4c73; border-top-left-radius:4px; }
.bolha.saida { background:#0f5a55; border:1px solid #1f8f86; border-top-right-radius:4px; }
.bolha .autor { font-size:11px; color:#a9c6d8; margin-bottom:2px; }
.vazio { color:#8fb0c6; padding:18px 4px; }
[data-testid="stMetric"] { background:#0a2238; border:1px solid #14405f; border-radius:14px; padding:12px 14px; }
</style>
"""

st.set_page_config(page_title="Triagem IA", page_icon="🎯", layout="wide")
st.markdown(CSS, unsafe_allow_html=True)


def exigir_senha() -> None:
    """Portão de senha (DASHBOARD_PASSWORD). Em produção a senha é obrigatória (ver docs/deploy.md)."""
    senha = os.getenv("DASHBOARD_PASSWORD", "")
    if not senha:
        if os.getenv("ENVIRONMENT", "development").lower() == "production":
            st.error("DASHBOARD_PASSWORD não configurada: painel bloqueado em produção.")
            st.stop()
        return  # desenvolvimento local sem senha
    if st.session_state.get("autenticado"):
        return
    st.title("🎯 Triagem IA")
    with st.form("login"):
        digitada = st.text_input("Senha do painel", type="password")
        if st.form_submit_button("Entrar"):
            if hmac.compare_digest(digitada.encode(), senha.encode()):
                st.session_state["autenticado"] = True
                st.rerun()
            else:
                st.error("Senha incorreta.")
    st.stop()


exigir_senha()


def local(dt):
    if dt is None or pd.isna(dt):
        return ""
    return dt.replace(tzinfo=timezone.utc).astimezone(FUSO).strftime("%d/%m %H:%M")


def pct(v):
    return "—" if v is None else f"{v:.1f}%"


# ---------------------------------------------------------------- cabeçalho / KPIs
def kpis():
    resumo = metrics.resumo()
    sli, prec = resumo["sli"], resumo["precisao"]
    lista = tickets.listar(limite=1000)
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Tickets", len(lista))
    c2.metric("Em risco / estourados", len(resumo["prazos_em_risco"]))
    c3.metric("Incidentes", resumo["incidentes"])
    c4.metric(f"SLI (meta {sli['alvo_pct']:.0f}%)", pct(sli["sli_pct"]))
    c5.metric("Precisão", pct(prec["agregado"]), help=f"{prec['revisados']} tickets revisados")
    return resumo


def alertas_incidente():
    for inc in incidents.listar_incidentes(apenas_incidentes=True):
        with st.container(border=True):
            st.error(f"🚨 **Incidente — {inc['assunto_predominante'] or 'assunto indefinido'}** · "
                     f"{inc['size']} mensagens · aberto às {local(inc['incident_opened_at'])}")
            st.caption(inc["justificativa"])
            with st.expander("Ver mensagens do grupo"):
                for t in inc["tickets"]:
                    st.write(f"- **{t['cliente'] or 'cliente'}** ({t['canal']}, {local(t['received_at'])}): {t['texto']}")


# ---------------------------------------------------------------- atendimento (fila estilo chat)
def selo(texto, cor):
    return f'<span class="selo" style="color:{cor}">{html.escape(texto)}</span>'


def cartao_html(t, selecionado):
    """Texto do cliente é não confiável: tudo passa por html.escape antes de entrar no HTML."""
    nome = html.escape(t["cliente"] or "Cliente sem identificação")
    inicial = html.escape((t["cliente"] or "?").strip()[:1].upper() or "?")
    s = t["sla"]
    urg = selo(t["urgencia"], COR_URGENCIA.get(t["urgencia"], "#8fb0c6")) if t["urgencia"] else ""
    prazo = selo(ROTULO_SLA_CURTO.get(s["estado"], s["estado"]), COR_SLA.get(s["estado"], "#8fb0c6"))
    equipe = html.escape((t["equipe"] or "a definir").replace("_", " "))
    assunto = html.escape(t["assunto"] or "classificando")
    ultimo = t.get("ultima_texto") or t["texto"]
    texto = html.escape(ultimo[:110] + ("…" if len(ultimo) > 110 else ""))
    nova = selo("cliente respondeu", "#2dd4bf") if t["first_response_at"] and t["aguardando"] else ""
    return (
        f'<div class="cartao{" sel" if selecionado else ""}"><div class="topo"><div class="avatar">{inicial}</div>'
        f'<div><div class="nome">{nome}</div><div class="sub">{html.escape(t["canal"])} · {local(t["received_at"])}</div></div></div>'
        f'<div class="linha">{nova}{urg}{prazo}</div>'
        f'<div class="linha"><b>Fila:</b> {equipe} · <b>Assunto:</b> {assunto}</div>'
        f'<div class="msg">{texto}</div></div>'
    )


def lista_de_cartoes(itens, chave):
    if not itens:
        st.markdown('<div class="vazio">Nenhum atendimento aqui.</div>', unsafe_allow_html=True)
    for t in itens:
        tid = t["ticket_id"]
        st.markdown(cartao_html(t, st.session_state.get("ticket_sel") == tid), unsafe_allow_html=True)
        st.button("Abrir atendimento", key=f"abrir_{chave}_{tid}", on_click=st.session_state.__setitem__,
                  args=("ticket_sel", tid), width="stretch")


def pagina_atendimento():
    todos = tickets.listar(limite=300)
    busca = st.text_input("Buscar", placeholder="Pesquisar cliente, canal ou mensagem…", label_visibility="collapsed")
    if busca.strip():
        q = busca.strip().lower()
        todos = [t for t in todos if q in " ".join([t["cliente"] or "", t["canal"], t["texto"], t["assunto"] or ""]).lower()]
    espera = [t for t in todos if t["aguardando"]]
    espera.sort(key=lambda t: (ORDEM_URGENCIA.get(t["urgencia"], 4), -(t["sla"]["consumido_pct"] or 0)))
    respondidos = [t for t in todos if not t["aguardando"]]

    esq, dir_ = st.columns([2, 3], gap="large")
    with esq:
        aba_e, aba_r = st.tabs([f"Em espera ({len(espera)})", f"Respondidos ({len(respondidos)})"])
        with aba_e:
            lista_de_cartoes(espera[:50], "e")
        with aba_r:
            lista_de_cartoes(respondidos[:50], "r")
    with dir_:
        sel = st.session_state.get("ticket_sel")
        atual = next((t for t in todos if t["ticket_id"] == sel), None)
        if atual is None:
            st.markdown('<div class="vazio">Escolha um atendimento na lista para ver a triagem, a resposta sugerida e corrigir a IA.</div>',
                        unsafe_allow_html=True)
        else:
            painel_ticket(atual)


def bolha_html(m):
    """Mensagem do chat. O texto vem do cliente (não confiável): sempre escapado."""
    saida = m["direcao"] == "saida"
    autor = html.escape(m["autor"] or ("Atendente" if saida else "Cliente"))
    corpo = html.escape(m["texto"]).replace("\n", "<br>")
    return (f'<div class="linha-chat {"saida" if saida else "entrada"}"><div class="bolha {"saida" if saida else "entrada"}">'
            f'<div class="autor">{autor} · {local(m["created_at"])}</div>{corpo}</div></div>')


def chat_conversa(t):
    tid = t["ticket_id"]
    st.markdown(f"**{html.escape(t['cliente'] or 'Cliente sem identificação')}** · {html.escape(t['canal'])}")
    with st.container(height=380, border=True):
        for m in tickets.mensagens(tid):
            st.markdown(bolha_html(m), unsafe_allow_html=True)

    chave = f"chat_texto_{tid}"
    if t["status"] == "classificado" and t["resposta_sugerida"]:
        st.button("💡 Usar resposta sugerida pela IA", key=f"sug{tid}", on_click=st.session_state.__setitem__,
                  args=(chave, t["resposta_sugerida"]))
    with st.form(f"chat{tid}", clear_on_submit=True):
        texto = st.text_area("Mensagem", key=chave, height=90, max_chars=2000, placeholder="Escreva a resposta ao cliente…",
                             label_visibility="collapsed")
        if st.form_submit_button("Enviar", type="primary"):
            try:
                tickets.responder_chat(tid, texto, st.session_state.get("atendente") or "Atendente")
                st.rerun()
            except ValueError:
                st.warning("Escreva uma mensagem antes de enviar.")
    st.caption("Modo demonstração: a resposta fica registrada nesta conversa. O envio ao canal do cliente "
               "(WhatsApp, e-mail, chat) será integrado depois.")


def painel_triagem(t):
    escolhido = t["ticket_id"]
    if t["status"] != "classificado":
        st.info("A IA ainda está classificando este atendimento.")
        return
    s = t["sla"]
    st.caption(f"Prazo: {ROTULO_ESTADO.get(s['estado'])} — {s['prazo_minutos']} min · vence {local(s['vence_em'])} · origem da triagem: {t['origem']}")
    st.markdown("**Resposta sugerida**")
    st.info(t["resposta_sugerida"])
    st.caption("Confiança: " + " · ".join(f"{d} {float(t['conf_' + d]) * 100:.0f}%" for d in ("assunto", "urgencia", "sentimento", "equipe")))

    b1, b2 = st.columns(2)
    if b1.button("✓ Triagem correta", key=f"ok{escolhido}", width="stretch"):
        corrections.confirmar_revisao(escolhido)
        st.rerun()
    if b2.button("📨 Marcar respondido", key=f"resp{escolhido}", disabled=t["first_response_at"] is not None, width="stretch"):
        tickets.marcar_respondido(escolhido)
        st.rerun()

    with st.form(f"form{escolhido}"):
        st.markdown("**Corrigir triagem**")
        c = st.columns(4)
        assunto = c[0].selectbox("Assunto", ASSUNTOS, index=ASSUNTOS.index(t["assunto"]))
        urgencia = c[1].selectbox("Urgência", URGENCIAS, index=URGENCIAS.index(t["urgencia"]))
        sentimento = c[2].selectbox("Sentimento", SENTIMENTOS, index=SENTIMENTOS.index(t["sentimento"]))
        equipe = c[3].selectbox("Equipe", EQUIPES, index=EQUIPES.index(t["equipe"]))
        resposta = st.text_area("Resposta", value=t["resposta_sugerida"], max_chars=2000)
        if st.form_submit_button("Salvar correção"):
            try:
                reg = corrections.registrar_correcoes(
                    escolhido,
                    {"assunto": assunto, "urgencia": urgencia, "sentimento": sentimento,
                     "equipe": equipe, "resposta_sugerida": resposta},
                )
                st.success(f"{len(reg)} campo(s) corrigido(s)." if reg else "Nenhuma diferença; triagem confirmada.")
                st.rerun()
            except corrections.CorrecaoInvalida as exc:
                st.error(str(exc))


def painel_ticket(t):
    chat_conversa(t)
    with st.expander("Triagem da IA e correções"):
        painel_triagem(t)


# ---------------------------------------------------------------- métricas
def aba_metricas(resumo):
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Principais motivos de contato")
        motivos = resumo["motivos_contato"]
        if motivos:
            st.bar_chart(pd.DataFrame(motivos).set_index("assunto")["total"], color="#2dd4bf")
        else:
            st.caption("Sem dados.")
    with c2:
        st.subheader("Precisão da triagem")
        p = resumo["precisao"]
        if p["revisados"] == 0:
            st.caption("Revise tickets (confirmar ou corrigir) para medir a taxa de acerto.")
        else:
            df = pd.DataFrame({
                "Todas": p["por_dimensao"],
                "IA (LLM)": resumo["precisao_llm"]["por_dimensao"] or {},
                "Plano B": resumo["precisao_fallback"]["por_dimensao"] or {},
            })
            st.dataframe(df.style.format("{:.1f}%", na_rep="—"), width="stretch")
            st.caption(f"Agregado (4 dimensões): {pct(p['agregado'])} em {p['revisados']} tickets revisados · "
                       f"LLM: {pct(resumo['precisao_llm']['agregado'])} · plano B: {pct(resumo['precisao_fallback']['agregado'])}")

    st.subheader("SLI e error budget")
    sli = resumo["sli"]
    nivel, msg = POLITICA_TEXTO[sli["politica"]]
    getattr(st, nivel)(msg)
    a, b, c = st.columns(3)
    a.metric("SLI (janela %d dias)" % sli["janela_dias"], pct(sli["sli_pct"]), help=f"Meta: {sli['alvo_pct']:.0f}%")
    b.metric("Violações / orçamento", f"{sli['violacoes']} / {sli['orcamento']}")
    c.metric("Orçamento consumido", pct(sli["consumo_orcamento_pct"]))

    st.subheader("Prazos de resposta em risco")
    risco = resumo["prazos_em_risco"]
    if risco:
        st.dataframe(pd.DataFrame(risco).rename(columns={"ticket_id": "#", "urgencia": "Urgência", "estado": "Estado", "consumido_pct": "Consumido %"}),
                     hide_index=True, width="stretch")
    else:
        st.success("Nenhum ticket com prazo em risco.")


# ---------------------------------------------------------------- principal
def pagina_incidentes():
    todos = st.toggle("Mostrar também grupos que ainda não são incidente", value=False)
    incs = incidents.listar_incidentes(apenas_incidentes=not todos)
    if not incs:
        st.success("Nenhum incidente detectado.")
    for g in incs:
        with st.expander(f"Grupo #{g['id']} · {g['status']} · {g['size']} mensagens · {g['assunto_predominante'] or '—'}"):
            st.caption(g["justificativa"] or "Ainda abaixo do volume mínimo de incidente.")
            st.dataframe(pd.DataFrame(g["tickets"])[["id", "cliente", "canal", "texto"]], hide_index=True, width="stretch")


def pagina_correcoes():
    hist = corrections.historico()
    if hist:
        st.dataframe(pd.DataFrame(hist), hide_index=True, width="stretch")
    else:
        st.caption("Nenhuma correção registrada ainda.")


def menu_lateral() -> str:
    st.session_state.setdefault("pagina", "dashboard")
    st.sidebar.markdown('<div class="marca"><div class="logo">T</div><div class="nome">Triagem IA</div></div>'
                        '<div class="menu-titulo">Menu</div>', unsafe_allow_html=True)
    for chave, rotulo, icone in PAGINAS:
        ativo = st.session_state["pagina"] == chave
        if st.sidebar.button(rotulo, icon=icone, key=f"nav_{chave}", type="primary" if ativo else "secondary", width="stretch"):
            st.session_state["pagina"] = chave
            st.rerun()
    st.sidebar.divider()
    st.sidebar.text_input("Seu nome no chat", value="Atendente", key="atendente", max_chars=60)
    intervalo = st.sidebar.number_input("Atualização automática (s)", min_value=3, max_value=120, value=10, step=1)
    st.sidebar.caption("Datas exibidas em horário de Brasília.")
    return int(intervalo), st.session_state["pagina"]


intervalo, pagina = menu_lateral()
TITULOS = {chave: rotulo for chave, rotulo, _ in PAGINAS}
st.title(TITULOS[pagina])


def corpo():
    if pagina == "dashboard":
        resumo = kpis()
        alertas_incidente()
        aba_metricas(resumo)
    elif pagina == "atendimento":
        pagina_atendimento()
    elif pagina == "incidentes":
        pagina_incidentes()
    else:
        pagina_correcoes()


st.fragment(run_every=intervalo)(corpo)()
