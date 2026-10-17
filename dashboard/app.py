"""Painel de monitoramento (Spec 4, ADR-005). Executar com: streamlit run dashboard/app.py"""
import sys
from datetime import timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import hmac  # noqa: E402
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

st.set_page_config(page_title="Triagem IA", page_icon="🎯", layout="wide")


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
    c2.metric("Prazos em risco/estourados", len(resumo["prazos_em_risco"]))
    c3.metric("Incidentes detectados", resumo["incidentes"])
    c4.metric(f"SLI (meta {sli['alvo_pct']:.0f}%)", pct(sli["sli_pct"]))
    c5.metric("Precisão da triagem", pct(prec["agregado"]), help=f"{prec['revisados']} tickets revisados")
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


# ---------------------------------------------------------------- fila
def tabela_fila(lista):
    linhas = []
    for t in lista:
        s = t["sla"]
        linhas.append({
            "#": t["ticket_id"],
            "Prazo": ROTULO_ESTADO.get(s["estado"], s["estado"]),
            "Consumido": s["consumido_pct"],
            "Urgência": t["urgencia"] or "—",
            "Assunto": t["assunto"] or "—",
            "Sentimento": t["sentimento"] or "—",
            "Equipe": t["equipe"] or "—",
            "Origem": t["origem"] or "—",
            "Revisado": "✔" if t["revisado"] else "",
            "Cliente": t["cliente"] or "",
            "Mensagem": t["texto"],
            "Recebido": local(t["received_at"]),
        })
    df = pd.DataFrame(linhas)
    st.dataframe(
        df, hide_index=True, width="stretch",
        column_config={"Consumido": st.column_config.ProgressColumn("Prazo consumido", format="%.0f%%", min_value=0, max_value=100)},
    )


def painel_ticket(lista):
    ids = [t["ticket_id"] for t in lista if t["status"] == "classificado"]
    if not ids:
        st.info("Nenhum ticket classificado ainda.")
        return
    escolhido = st.selectbox("Atender ticket", ids, format_func=lambda i: f"#{i}", key="ticket_sel")
    t = next(x for x in lista if x["ticket_id"] == escolhido)
    with st.container(border=True):
        st.markdown(f"**{t['cliente'] or 'Cliente'}** · {t['canal']} · {local(t['received_at'])}")
        st.write(t["texto"])
        s = t["sla"]
        st.caption(f"Prazo: {ROTULO_ESTADO.get(s['estado'])} — {s['prazo_minutos']} min · vence {local(s['vence_em'])} · origem da triagem: {t['origem']}")
        st.markdown("**Resposta sugerida**")
        st.info(t["resposta_sugerida"])
        st.caption("Confiança: " + " · ".join(f"{d} {float(t['conf_' + d]) * 100:.0f}%" for d in ("assunto", "urgencia", "sentimento", "equipe")))

        b1, b2, _ = st.columns([1, 1, 3])
        if b1.button("✓ Triagem correta", key=f"ok{escolhido}"):
            corrections.confirmar_revisao(escolhido)
            st.rerun()
        if b2.button("📨 Marcar respondido", key=f"resp{escolhido}", disabled=t["first_response_at"] is not None):
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


# ---------------------------------------------------------------- métricas
def aba_metricas(resumo):
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Principais motivos de contato")
        motivos = resumo["motivos_contato"]
        if motivos:
            st.bar_chart(pd.DataFrame(motivos).set_index("assunto")["total"])
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
st.title("🎯 Triagem IA — painel de atendimento")
intervalo = st.sidebar.number_input("Atualização automática (s)", min_value=3, max_value=120, value=10, step=1)
st.sidebar.caption("Datas exibidas em horário de Brasília.")


def corpo():
    resumo = kpis()
    alertas_incidente()
    aba_fila, aba_inc, aba_met, aba_corr = st.tabs(["📋 Fila", "🚨 Incidentes", "📊 Métricas", "📝 Correções"])
    with aba_fila:
        lista = tickets.listar(limite=300)
        apenas_abertos = st.toggle("Somente sem resposta", value=True)
        visiveis = [t for t in lista if not (apenas_abertos and t["first_response_at"])]
        visiveis.sort(key=lambda t: (ORDEM_URGENCIA.get(t["urgencia"], 4), -(t["sla"]["consumido_pct"] or 0)))
        tabela_fila(visiveis)
        painel_ticket(lista)
    with aba_inc:
        todos = st.toggle("Mostrar também grupos que ainda não são incidente", value=False)
        incs = incidents.listar_incidentes(apenas_incidentes=not todos)
        if not incs:
            st.success("Nenhum incidente detectado.")
        for g in incs:
            with st.expander(f"Grupo #{g['id']} · {g['status']} · {g['size']} mensagens · {g['assunto_predominante'] or '—'}"):
                st.caption(g["justificativa"] or "Ainda abaixo do volume mínimo de incidente.")
                st.dataframe(pd.DataFrame(g["tickets"])[["id", "cliente", "canal", "texto"]], hide_index=True, width="stretch")
    with aba_met:
        aba_metricas(resumo)
    with aba_corr:
        hist = corrections.historico()
        if hist:
            st.dataframe(pd.DataFrame(hist), hide_index=True, width="stretch")
        else:
            st.caption("Nenhuma correção registrada ainda.")


st.fragment(run_every=int(intervalo))(corpo)()
