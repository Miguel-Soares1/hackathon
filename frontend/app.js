// Painel da Triagem IA: HTML/CSS/JS puros, sem dependências. Consome a API do mesmo servidor.
"use strict";

const ORDEM_URGENCIA = { critica: 0, alta: 1, media: 2, baixa: 3 };
const ROTULO_ESTADO = {
  estourado: "🔴 estourado", em_risco: "🟠 em risco", no_prazo: "🟢 no prazo",
  respondido: "✅ respondido", aguardando_classificacao: "⏳ classificando",
};
const COR_ESTADO = { estourado: "var(--critica)", em_risco: "var(--alta)", no_prazo: "var(--ok)", respondido: "var(--muted)" };
const POLITICA_TEXTO = {
  normal: "Error budget saudável: desenvolvimento de funcionalidades segue.",
  alerta: "Mais de 50% do error budget consumido: revisar tickets em risco e a política de SLA.",
  congelar_funcionalidades: "Error budget esgotado: congelar funcionalidades novas e corrigir as causas dos atrasos.",
  sem_dados: "Ainda não há tickets com desfecho para calcular o SLI.",
};
const DIMS = ["assunto", "urgencia", "sentimento", "equipe"];
const nomeIdioma = (c) => (estado.dominio?.idiomas?.[c] ? `${estado.dominio.idiomas[c]} (${c})` : c || "—");
const tagIdioma = (c) => (c ? `<span class="idioma" title="${esc(nomeIdioma(c))}">${esc(c.toUpperCase())}</span>` : "—");

const estado = {
  chave: lerChave(),
  dominio: null,
  tickets: [],
  resumo: null,
  selecionado: null,
  editando: false, // não redesenhar o formulário enquanto o atendente digita
  aba: "fila",
  timer: null,
};

// ---------------------------------------------------------------- utilidades
const $ = (sel) => document.querySelector(sel);

function esc(v) {
  return String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function lerChave() {
  try { return sessionStorage.getItem("triagem.chave") || ""; } catch { return ""; }
}
function salvarChave(v) {
  try { v ? sessionStorage.setItem("triagem.chave", v) : sessionStorage.removeItem("triagem.chave"); } catch { /* aba privada */ }
}

// A API devolve datas em UTC sem fuso ("2026-10-17T14:05:28").
function hora(iso) {
  if (!iso) return "";
  const d = new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : iso + "Z");
  return d.toLocaleString("pt-BR", { timeZone: "America/Sao_Paulo", day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

const pct = (v) => (v === null || v === undefined ? "—" : `${Number(v).toFixed(1)}%`);
const pill = (u) => (u ? `<span class="pill u-${esc(u)}">${esc(u)}</span>` : "—");

class NaoAutorizado extends Error {}

async function api(caminho, opcoes = {}) {
  const resp = await fetch(caminho, {
    ...opcoes,
    headers: { "X-API-Key": estado.chave, ...(opcoes.body ? { "Content-Type": "application/json" } : {}) },
  });
  if (resp.status === 401) throw new NaoAutorizado();
  if (!resp.ok) {
    let msg = `erro ${resp.status}`;
    try { msg = (await resp.json()).detail || msg; } catch { /* corpo vazio */ }
    throw new Error(msg);
  }
  return resp.status === 204 ? null : resp.json();
}

// ---------------------------------------------------------------- carga e ciclo
async function carregar() {
  try {
    const [tickets, resumo, incidentes] = await Promise.all([
      api("/tickets?limite=500"),
      api("/metricas"),
      api(`/incidentes?todos_os_grupos=${$("#todos-grupos").checked}`),
    ]);
    estado.tickets = tickets;
    estado.resumo = resumo;
    renderKpis();
    renderAlertas(incidentes.filter((g) => g.status === "incidente"));
    renderFila();
    if (!estado.editando) renderDetalhe();
    renderIncidentes(incidentes);
    renderMetricas();
    if (estado.aba === "correcoes") renderCorrecoes(await api("/correcoes"));
    $("#status").textContent = `atualizado às ${new Date().toLocaleTimeString("pt-BR")}`;
  } catch (e) {
    if (e instanceof NaoAutorizado) return sair("Chave inválida ou expirada.");
    $("#status").textContent = `⚠ ${e.message}`;
  }
}

function agendar() {
  clearInterval(estado.timer);
  const s = Number($("#intervalo").value);
  if (s > 0) estado.timer = setInterval(carregar, s * 1000);
}

// ---------------------------------------------------------------- render: topo
function renderKpis() {
  const r = estado.resumo;
  const itens = [
    ["Tickets", estado.tickets.length],
    ["Prazos em risco / estourados", r.prazos_em_risco.length],
    ["Incidentes detectados", r.incidentes],
    [`SLI (meta ${r.sli.alvo_pct.toFixed(0)}%)`, pct(r.sli.sli_pct)],
    [`Precisão da triagem (${r.precisao.revisados} revisados)`, pct(r.precisao.agregado)],
  ];
  $("#kpis").innerHTML = itens
    .map(([rot, val]) => `<div class="kpi"><div class="valor">${esc(val)}</div><div class="rotulo">${esc(rot)}</div></div>`)
    .join("");
}

function renderAlertas(incidentes) {
  $("#alertas").innerHTML = incidentes
    .map((g) => `<div class="alerta" role="alert">🚨 <strong>Incidente — ${esc(g.assunto_predominante || "assunto indefinido")}</strong>
      · ${g.size} mensagens · aberto às ${esc(hora(g.incident_opened_at))}<br><span class="muted">${esc(g.justificativa)}</span></div>`)
    .join("");
}

// ---------------------------------------------------------------- render: fila
function renderFila() {
  const soAbertos = $("#so-abertos").checked;
  const lista = estado.tickets
    .filter((t) => !(soAbertos && t.first_response_at))
    .sort((a, b) => (ORDEM_URGENCIA[a.urgencia] ?? 4) - (ORDEM_URGENCIA[b.urgencia] ?? 4)
      || (b.sla.consumido_pct ?? 0) - (a.sla.consumido_pct ?? 0));

  const linhas = lista.map((t) => {
    const c = Math.min(t.sla.consumido_pct ?? 0, 100);
    return `<tr data-id="${t.ticket_id}" class="${t.ticket_id === estado.selecionado ? "selecionada" : ""}">
      <td>#${t.ticket_id}</td>
      <td>${esc(ROTULO_ESTADO[t.sla.estado] || t.sla.estado)}
        <div class="progresso" title="${esc(t.sla.consumido_pct ?? 0)}% do prazo"><span style="width:${c}%;background:${COR_ESTADO[t.sla.estado] || "var(--muted)"}"></span></div></td>
      <td>${pill(t.urgencia)}</td>
      <td>${esc(t.assunto || "—")}</td>
      <td>${esc(t.sentimento || "—")}</td>
      <td>${tagIdioma(t.idioma)}</td>
      <td>${esc(t.equipe || "—")}</td>
      <td>${esc(t.origem || "—")}${t.revisado ? " ✔" : ""}</td>
      <td class="texto"><b>${esc(t.cliente || "")}</b> ${esc(t.texto)}</td>
      <td>${esc(hora(t.received_at))}</td>
    </tr>`;
  });
  $("#tabela-fila").innerHTML = `<thead><tr><th>#</th><th>Prazo</th><th>Urgência</th><th>Assunto</th><th>Sentimento</th><th>Idioma</th>
    <th>Equipe</th><th>Origem</th><th>Mensagem</th><th>Recebido</th></tr></thead>
    <tbody>${linhas.join("") || `<tr><td colspan="10" class="muted">Nenhum ticket.</td></tr>`}</tbody>`;
}

function opcoes(valores, atual) {
  return valores.map((v) => `<option ${v === atual ? "selected" : ""}>${esc(v)}</option>`).join("");
}

function renderDetalhe() {
  const t = estado.tickets.find((x) => x.ticket_id === estado.selecionado);
  const painel = $("#detalhe");
  if (!t) {
    painel.innerHTML = `<p class="muted">Clique em um ticket para atender.</p>`;
    return;
  }
  const s = t.sla;
  const cabecalho = `<div><h2>#${t.ticket_id} · ${esc(t.cliente || "Cliente")}</h2>
    <p class="muted">${esc(t.canal)} · ${esc(hora(t.received_at))}</p></div>
    <p class="mensagem">${esc(t.texto)}</p>`;
  if (t.status !== "classificado") {
    painel.innerHTML = `${cabecalho}<p class="muted">⏳ A IA ainda está classificando este ticket…</p>`;
    return;
  }
  const d = estado.dominio;
  painel.innerHTML = `${cabecalho}
    <p class="muted">Prazo: ${esc(ROTULO_ESTADO[s.estado])} — ${s.prazo_minutos} min · vence ${esc(hora(s.vence_em))} · triagem: ${esc(t.origem)}</p>
    <div><h3>Resposta sugerida</h3><div class="resposta" lang="${esc(t.idioma || "pt")}">${esc(t.resposta_sugerida)}</div></div>
    <p class="muted">🌐 Cliente escreveu em ${esc(nomeIdioma(t.idioma))}${t.idioma && t.idioma !== "pt" ? " · resposta sugerida no mesmo idioma" : ""}</p>
    <p class="muted">Confiança: ${DIMS.map((k) => `${k} ${Math.round(Number(t["conf_" + k]) * 100)}%`).join(" · ")}</p>
    ${t.exemplos
      ? `<p class="aprendizado">🧠 Prompt ${esc(t.prompt_version)} · aprendeu com tickets já revisados parecidos: ${t.exemplos.split(",").map((i) => `#${esc(i)}`).join(", ")}</p>`
      : `<p class="muted">Prompt ${esc(t.prompt_version || "—")} · sem exemplos revisados parecidos</p>`}
    <div class="acoes">
      <button class="btn" data-acao="revisar" ${t.revisado ? "disabled" : ""}>✓ Triagem correta</button>
      <button class="btn" data-acao="responder" ${t.first_response_at ? "disabled" : ""}>📨 Marcar respondido</button>
    </div>
    <form id="form-correcao">
      <h3>Corrigir triagem</h3>
      <div class="grade-campos">
        <label>Assunto <select name="assunto">${opcoes(d.assuntos, t.assunto)}</select></label>
        <label>Urgência <select name="urgencia">${opcoes(d.urgencias, t.urgencia)}</select></label>
        <label>Sentimento <select name="sentimento">${opcoes(d.sentimentos, t.sentimento)}</select></label>
        <label>Equipe <select name="equipe">${opcoes(d.equipes, t.equipe)}</select></label>
      </div>
      <label>Resposta <textarea name="resposta_sugerida" rows="4" maxlength="2000">${esc(t.resposta_sugerida)}</textarea></label>
      <p><button type="submit" class="btn primario">Salvar correção</button> <span id="correcao-status" class="muted" aria-live="polite"></span></p>
    </form>`;
}

// ---------------------------------------------------------------- render: incidentes, métricas, correções
function renderIncidentes(grupos) {
  $("#lista-incidentes").innerHTML = grupos.length
    ? grupos.map((g) => `<details class="card grupo" ${g.status === "incidente" ? "open" : ""}>
        <summary>${g.status === "incidente" ? "🚨" : "•"} Grupo #${g.id} · ${esc(g.status)} · ${g.size} mensagens · ${esc(g.assunto_predominante || "—")}</summary>
        <p class="muted">${esc(g.justificativa || "Ainda abaixo do volume mínimo de incidente.")}</p>
        <ul>${g.tickets.map((t) => `<li><b>${esc(t.cliente || "cliente")}</b> (${esc(t.canal)}, ${esc(hora(t.received_at))}): ${esc(t.texto)}</li>`).join("")}</ul>
      </details>`).join("")
    : `<p class="card">✅ Nenhum incidente detectado.</p>`;
}

function renderMetricas() {
  const r = estado.resumo;
  const max = Math.max(1, ...r.motivos_contato.map((m) => m.total));
  const motivos = r.motivos_contato.length
    ? `<div class="barras">${r.motivos_contato.map((m) => `<div class="barra-linha"><span>${esc(m.assunto)}</span>
        <div class="barra" style="width:${(m.total / max) * 100}%"></div><span>${m.total}</span></div>`).join("")}</div>`
    : `<p class="muted">Sem dados.</p>`;

  const totalIdiomas = r.idiomas.reduce((a, i) => a + i.total, 0);
  const idiomas = r.idiomas.length
    ? `<div class="barras">${r.idiomas.map((i) => `<div class="barra-linha"><span>${esc(nomeIdioma(i.idioma))}</span>
        <div class="barra" style="width:${(i.total / totalIdiomas) * 100}%"></div><span>${i.total}</span></div>`).join("")}</div>`
    : `<p class="muted">Sem dados.</p>`;

  const p = r.precisao;
  const dimsPrec = ["assunto", "urgencia", "sentimento", "equipe", "resposta_sugerida"];
  const precisao = p.revisados === 0
    ? `<p class="muted">Revise tickets (confirmar ou corrigir) para medir a taxa de acerto.</p>`
    : `<table class="tabela tabela-simples"><thead><tr><th>Dimensão</th><th>Todas</th><th>IA (LLM)</th><th>Plano B</th></tr></thead><tbody>
        ${dimsPrec.map((k) => `<tr><td>${k}</td><td>${pct(p.por_dimensao[k])}</td><td>${pct(r.precisao_llm.por_dimensao[k])}</td><td>${pct(r.precisao_fallback.por_dimensao[k])}</td></tr>`).join("")}
        <tr><td><b>agregado</b></td><td><b>${pct(p.agregado)}</b></td><td>${pct(r.precisao_llm.agregado)}</td><td>${pct(r.precisao_fallback.agregado)}</td></tr>
      </tbody></table><p class="muted">${p.revisados} tickets revisados.</p>`;

  const versoes = r.precisao_por_versao || [];
  const evolucao = versoes.length
    ? `<table class="tabela tabela-simples"><thead><tr><th>Versão</th><th>Revisados</th>${DIMS.map((k) => `<th>${k}</th>`).join("")}<th>Agregado</th></tr></thead><tbody>
        ${versoes.map((v) => `<tr><td>${esc(v.prompt_version)}</td><td>${v.revisados}</td>${DIMS.map((k) => `<td>${pct(v.por_dimensao[k])}</td>`).join("")}<td><b>${pct(v.agregado)}</b></td></tr>`).join("")}
      </tbody></table>
      <p class="muted"><code>+fewshot</code> = a IA recebeu como exemplo tickets parecidos já revisados pelos atendentes · <code>regras</code> = plano B sem IA.</p>`
    : `<p class="muted">Revise tickets para comparar as versões do prompt.</p>`;

  const sli = r.sli;
  const risco = r.prazos_em_risco.length
    ? `<table class="tabela tabela-simples"><thead><tr><th>#</th><th>Urgência</th><th>Estado</th><th>Consumido</th></tr></thead><tbody>
        ${r.prazos_em_risco.map((x) => `<tr><td>#${x.ticket_id}</td><td>${pill(x.urgencia)}</td><td>${esc(ROTULO_ESTADO[x.estado])}</td><td>${pct(x.consumido_pct)}</td></tr>`).join("")}
      </tbody></table>`
    : `<p>✅ Nenhum ticket com prazo em risco.</p>`;

  $("#metricas").innerHTML = `
    <div class="card"><h2>Principais motivos de contato</h2>${motivos}</div>
    <div class="card"><h2>Idiomas dos clientes</h2>${idiomas}</div>
    <div class="card"><h2>Precisão da triagem</h2>${precisao}</div>
    <div class="card"><h2>Evolução da IA por versão do prompt</h2>${evolucao}</div>
    <div class="card"><h2>SLI e error budget</h2>
      <div class="politica ${esc(sli.politica)}">${esc(POLITICA_TEXTO[sli.politica])}</div>
      <p>SLI (janela ${sli.janela_dias} dias): <b>${pct(sli.sli_pct)}</b> · meta ${sli.alvo_pct.toFixed(0)}%</p>
      <p>Violações / orçamento: <b>${sli.violacoes} / ${sli.orcamento}</b> · orçamento consumido: <b>${pct(sli.consumo_orcamento_pct)}</b></p>
    </div>
    <div class="card"><h2>Prazos de resposta em risco</h2>${risco}</div>`;
}

function renderCorrecoes(hist) {
  $("#tabela-correcoes").innerHTML = `<thead><tr><th>Quando</th><th>Ticket</th><th>Dimensão</th><th>IA disse</th><th>Atendente corrigiu</th></tr></thead>
    <tbody>${hist.map((c) => `<tr><td>${esc(hora(c.created_at))}</td><td>#${c.ticket_id}</td><td>${esc(c.dimensao)}</td>
      <td class="texto">${esc(c.valor_original)}</td><td class="texto">${esc(c.valor_corrigido)}</td></tr>`).join("")
      || `<tr><td colspan="5" class="muted">Nenhuma correção registrada ainda.</td></tr>`}</tbody>`;
}

// ---------------------------------------------------------------- ações
async function acaoDetalhe(acao) {
  const id = estado.selecionado;
  try {
    if (acao === "revisar") await api(`/tickets/${id}/revisao`, { method: "POST" });
    if (acao === "responder") await api(`/tickets/${id}/resposta`, { method: "POST", body: "{}" });
  } catch (e) {
    alertaStatus(e.message);
  }
  estado.editando = false;
  await carregar();
}

async function salvarCorrecao(form) {
  const t = estado.tickets.find((x) => x.ticket_id === estado.selecionado);
  const dados = Object.fromEntries(new FormData(form));
  try {
    const r = await api(`/tickets/${t.ticket_id}/correcoes`, { method: "POST", body: JSON.stringify(dados) });
    estado.editando = false;
    await carregar();
    $("#correcao-status").textContent = r.correcoes_registradas.length
      ? `${r.correcoes_registradas.length} campo(s) corrigido(s).` : "Nenhuma diferença; triagem confirmada.";
  } catch (e) {
    $("#correcao-status").textContent = `⚠ ${e.message}`;
  }
}

function alertaStatus(msg) {
  $("#status").textContent = `⚠ ${msg}`;
}

async function enviarMensagem(form) {
  const dados = Object.fromEntries(new FormData(form));
  if (!dados.cliente) delete dados.cliente;
  const st = $("#nova-status");
  try {
    const r = await api("/webhook/mensagens", { method: "POST", body: JSON.stringify(dados) });
    st.textContent = `✅ Ticket #${r.ticket_id} recebido. Veja na fila em instantes.`;
    form.texto.value = "";
    setTimeout(carregar, 1500);
  } catch (e) {
    st.textContent = `⚠ ${e.message}`;
  }
}

function trocarAba(aba) {
  estado.aba = aba;
  document.querySelectorAll(".abas button").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.aba === aba)));
  document.querySelectorAll(".aba").forEach((s) => { s.hidden = s.id !== `aba-${aba}`; });
  if (aba === "correcoes") api("/correcoes").then(renderCorrecoes).catch((e) => alertaStatus(e.message));
}

// ---------------------------------------------------------------- acesso
async function entrar() {
  try {
    estado.dominio = await api("/dominio");
  } catch (e) {
    return sair(e instanceof NaoAutorizado ? "Chave inválida." : `Servidor indisponível: ${e.message}`);
  }
  $("#login").hidden = true;
  $("#app").hidden = false;
  await carregar();
  agendar();
}

function sair(erro) {
  clearInterval(estado.timer);
  estado.chave = "";
  salvarChave("");
  $("#app").hidden = true;
  $("#login").hidden = false;
  const p = $("#login-erro");
  p.hidden = !erro;
  p.textContent = erro || "";
}

// ---------------------------------------------------------------- eventos
document.addEventListener("DOMContentLoaded", () => {
  $("#form-login").addEventListener("submit", (ev) => {
    ev.preventDefault();
    estado.chave = $("#chave").value.trim();
    salvarChave(estado.chave);
    entrar();
  });
  $("#sair").addEventListener("click", () => sair());
  $("#intervalo").addEventListener("change", agendar);
  $("#so-abertos").addEventListener("change", renderFila);
  $("#todos-grupos").addEventListener("change", carregar);
  document.querySelector(".abas").addEventListener("click", (ev) => {
    const b = ev.target.closest("button[data-aba]");
    if (b) trocarAba(b.dataset.aba);
  });

  $("#tabela-fila").addEventListener("click", (ev) => {
    const tr = ev.target.closest("tr[data-id]");
    if (!tr) return;
    estado.selecionado = Number(tr.dataset.id);
    estado.editando = false;
    renderFila();
    renderDetalhe();
  });

  const detalhe = $("#detalhe");
  detalhe.addEventListener("click", (ev) => {
    const b = ev.target.closest("button[data-acao]");
    if (b) acaoDetalhe(b.dataset.acao);
  });
  detalhe.addEventListener("input", () => { estado.editando = true; });
  detalhe.addEventListener("submit", (ev) => {
    if (ev.target.id !== "form-correcao") return;
    ev.preventDefault();
    salvarCorrecao(ev.target);
  });

  $("#form-nova").addEventListener("submit", (ev) => {
    ev.preventDefault();
    enviarMensagem(ev.target);
  });

  if (estado.chave) entrar(); else sair();
});
