from datetime import datetime, timedelta

from sqlalchemy import text

from triagem import metrics, tickets
from triagem.pipeline import processar_ticket

AGORA = datetime(2026, 10, 17, 12, 0, 0)


def ticket(db, texto, minutos_atras, respondido_apos=None):
    """Cria e classifica um ticket (plano B), com datas controladas."""
    recebido = AGORA - timedelta(minutes=minutos_atras)
    with db.begin() as conn:
        tid = int(conn.execute(
            text("INSERT INTO tickets (canal, texto, status, received_at, first_response_at) "
                 "VALUES ('chat', :t, 'pendente', :r, :f)"),
            {"t": texto, "r": recebido,
             "f": recebido + timedelta(minutes=respondido_apos) if respondido_apos is not None else None},
        ).lastrowid)
    processar_ticket(tid)
    return tid


def test_motivos_de_contato_contam_por_assunto(db):
    ticket(db, "Meu pix falhou", 5)
    ticket(db, "Pagamento com cartão recusado", 5)
    ticket(db, "Quero cancelar meu plano", 5)
    assert metrics.motivos_contato() == [
        {"assunto": "pagamento", "total": 2}, {"assunto": "cancelamento", "total": 1},
    ]


def test_prazos_em_risco_listam_so_abertos_criticos_ordenados(db):
    a = ticket(db, "O sistema caiu, urgente!", 12)             # crítica 15 min -> 80%
    b = ticket(db, "O sistema caiu, urgente!", 20)             # crítica -> 133% estourado
    ticket(db, "O sistema caiu, urgente!", 2)                  # no prazo
    ticket(db, "O sistema caiu, urgente!", 30, respondido_apos=5)  # respondido: não entra
    ids = [t["ticket_id"] for t in metrics.prazos_em_risco(AGORA)]
    assert ids == [b, a]


def test_sli_considera_respondidos_e_estourados(db):
    ticket(db, "Preciso de ajuda com a fatura", 30, respondido_apos=10)      # baixa, cumpriu
    ticket(db, "O sistema caiu, urgente!", 30)                                # crítica estourada
    ticket(db, "O sistema caiu, urgente!", 3)                                 # ainda no prazo: fora do SLI
    sli = metrics.sli_slo(AGORA)
    assert (sli["total"], sli["violacoes"], sli["sli_pct"]) == (2, 1, 50.0)
    assert sli["politica"] == "congelar_funcionalidades"


def test_resumo_tem_todas_as_secoes(db):
    ticket(db, "Meu pix falhou", 5)
    r = metrics.resumo(AGORA)
    assert set(r) >= {"motivos_contato", "prazos_em_risco", "sli", "precisao", "precisao_llm", "precisao_fallback", "incidentes"}


def test_ticket_pendente_nao_tem_prazo(db):
    with db.begin() as conn:
        tid = int(conn.execute(text(
            "INSERT INTO tickets (canal, texto, status, received_at) VALUES ('chat', 'mensagem qualquer', 'pendente', :r)"),
            {"r": AGORA}).lastrowid)
    assert tickets.obter(tid, AGORA)["sla"]["estado"] == "aguardando_classificacao"


def test_pipeline_ignora_ticket_ja_classificado(db):
    tid = ticket(db, "Meu pix falhou", 5)
    assert processar_ticket(tid) == "ignorado"
    assert processar_ticket(999999) == "ignorado"


def test_classificar_e_responder_ao_mesmo_tempo_nao_gera_deadlock(db):
    """Regressão: a classificação em background e o registro da resposta disputavam o mesmo ticket."""
    from concurrent.futures import ThreadPoolExecutor

    ids = []
    with db.begin() as conn:
        for i in range(30):
            ids.append(int(conn.execute(
                text("INSERT INTO tickets (canal, texto, status, received_at) VALUES ('chat', :t, 'pendente', :r)"),
                {"t": f"Meu pix falhou, caso {i}", "r": AGORA - timedelta(minutes=20)},
            ).lastrowid))

    def classificar(i):
        return processar_ticket(i)

    def responder(i):
        return tickets.marcar_respondido(i, AGORA - timedelta(minutes=5))["ticket_id"]

    with ThreadPoolExecutor(max_workers=8) as pool:
        f1 = [pool.submit(classificar, i) for i in ids]
        f2 = [pool.submit(responder, i) for i in ids]
        resultados = [f.result() for f in f1]  # qualquer exceção de deadlock apareceria aqui
        [f.result() for f in f2]

    assert resultados == ["classificado"] * 30
    assert all(t["status"] == "classificado" and t["first_response_at"] for t in tickets.listar(limite=100))
