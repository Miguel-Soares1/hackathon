// Painel da Triagem IA: HTML/CSS/JS puros, sem dependências. Consome a API do mesmo servidor.
// Layout da dashboard de atendimento: menu lateral, Dashboard, Atendimento (fila estilo chat), Incidentes e Correções.
"use strict";

const ORDEM_URGENCIA = { critica: 0, alta: 1, media: 2, baixa: 3 };
const ROTULO_ESTADO = {
  estourado: "🔴 estourado", em_risco: "🟠 em risco", no_prazo: "🟢 no prazo",
  respondido: "✅ respondido", aguardando_classificacao: "⏳ classificando",
};
const ROTULO_SLA_CURTO = {
  estourado: "prazo estourado", em_risco: "prazo em risco", no_prazo: "no prazo",
  respondido: "1ª resposta feita", aguardando_classificacao: "classificando",
};
const POLITICA_TEXTO = {
  normal: "Error budget saudável: desenvolvimento de funcionalidades segue.",
  alerta: "Mais de 50% do error budget consumido: revisar tickets em risco e a política de SLA.",
  congelar_funcionalidades: "Error budget esgotado: congelar funcionalidades novas e corrigir as causas dos atrasos.",
  sem_dados: "Ainda não há tickets com desfecho para calcular o SLI.",
};
const TITULOS = { dashboard: "Dashboard", atendimento: "Atendimento", incidentes: "Incidentes", correcoes: "Correções", nova: "Simular mensagem" };
const DIMS = ["assunto", "urgencia", "sentimento", "equipe"];
const nomeIdioma = (c) => (estado.dominio?.idiomas?.[c] ? `${estado.dominio.idiomas[c]} (${c})` : c || "—");

const estado = {
  chave: lerArmazenado(sessionStorage, "triagem.chave"),
  dominio: null,
  tickets: [],
  resumo: null,
  pagina: "dashboard",
  lista: "espera",
  selecionado: null,
  editando: false, // não redesenhar o detalhe enquanto o atendente digita
  triagemAberta: false,
  timer: null,
};

// ---------------------------------------------------------------- utilidades
const $ = (sel) => document.querySelector(sel);

function esc(v) {
  return String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function lerArmazenado(area, chave) {
  try { return area.getItem(chave) || ""; } catch { return ""; }
}
function gravarArmazenado(area, chave, v) {
  try { v ? area.setItem(chave, v) : area.removeItem(chave); } catch { /* aba privada */ }
}

// A API devolve datas em UTC sem fuso ("2026-10-17T14:05:28").
function hora(iso) {
  if (!iso) return "";
  const d = new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : iso + "Z");
  return d.toLocaleString("pt-BR", { timeZone: "America/Sao_Paulo", day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

const pct = (v) => (v === null || v === undefined ? "—" : `${Number(v).toFixed(1)}%`);
const selo = (texto, classe) => `<span class="selo ${classe}">${esc(texto)}</span>`;
const pill = (u) => (u ? selo(u, `u-${esc(u)}`) : "—");
const inicial = (nome) => esc((nome || "?").trim().replace(/^@/, "").slice(0, 1).toUpperCase() || "?");
const aguardando = (t) => t.aguardando ?? !t.first_response_at;

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
    renderMetricas();
    renderCartoes();
    if (!estado.editando) renderDetalhe();
    else if (estado.selecionado) carregarConversa(estado.selecionado); // a conversa continua atualizando
    renderIncidentes(incidentes);
    if (estado.pagina === "correcoes") renderCorrecoes(await api("/correcoes"));
    $("#status").textContent = `Atualizado às ${new Date().toLocaleTimeString("pt-BR")}`;
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

// ---------------------------------------------------------------- dashboard
function renderKpis() {
  const r = estado.resumo;
  const itens = [
    ["Tickets", estado.tickets.length],
    ["Em risco / estourados", r.prazos_em_risco.length],
    ["Incidentes", r.incidentes],
    [`SLI (meta ${r.sli.alvo_pct.toFixed(0)}%)`, pct(r.sli.sli_pct)],
    [`Precisão (${r.precisao.revisados} revisados)`, pct(r.precisao.agregado)],
  ];
  $("#kpis").innerHTML = itens
    .map(([rot, val]) => `<div class="kpi"><div class="rotulo">${esc(rot)}</div><div class="valor">${esc(val)}</div></div>`)
    .join("");
}

function renderAlertas(incidentes) {
  $("#alertas").innerHTML = incidentes
    .map((g) => `<div class="alerta" role="alert">🚨 <strong>Incidente — ${esc(g.assunto_predominante || "assunto indefinido")}</strong>
      · ${g.size} mensagens · aberto às ${esc(hora(g.incident_opened_at))}<br><span class="muted">${esc(g.justificativa)}</span>
      <details><summary>Ver mensagens do grupo</summary><ul>${g.tickets.map((t) =>
        `<li><b>${esc(t.cliente || "cliente")}</b> (${esc(t.canal)}, ${esc(hora(t.received_at))}): ${esc(t.texto)}</li>`).join("")}</ul></details></div>`)
    .join("");
}

function barras(itens, rotulo) {
  const max = Math.max(1, ...itens.map((i) => i.total));
  return itens.length
    ? `<div class="barras">${itens.map((i) => `<div class="barra-linha"><span>${esc(rotulo(i))}</span>
        <div class="barra" style="width:${(i.total / max) * 100}%"></div><span>${i.total}</span></div>`).join("")}</div>`
    : `<p class="muted">Sem dados.</p>`;
}

function renderMetricas() {
  const r = estado.resumo;
  const p = r.precisao;
  const dimsPrec = ["assunto", "urgencia", "sentimento", "equipe", "resposta_sugerida"];
  const precisao = p.revisados === 0
    ? `<p class="muted">Revise tickets (confirmar ou corrigir) para medir a taxa de acerto.</p>`
    : `<table class="tabela"><thead><tr><th>Dimensão</th><th>Todas</th><th>IA (LLM)</th><th>Plano B</th></tr></thead><tbody>
        ${dimsPrec.map((k) => `<tr><td>${k}</td><td>${pct(p.por_dimensao[k])}</td><td>${pct(r.precisao_llm.por_dimensao[k])}</td><td>${pct(r.precisao_fallback.por_dimensao[k])}</td></tr>`).join("")}
        <tr><td><b>agregado</b></td><td><b>${pct(p.agregado)}</b></td><td>${pct(r.precisao_llm.agregado)}</td><td>${pct(r.precisao_fallback.agregado)}</td></tr>
      </tbody></table><p class="muted">${p.revisados} tickets revisados.</p>`;

  const versoes = r.precisao_por_versao || [];
  const evolucao = versoes.length
    ? `<table class="tabela"><thead><tr><th>Versão</th><th>Revisados</th>${DIMS.map((k) => `<th>${k}</th>`).join("")}<th>Agregado</th></tr></thead><tbody>
        ${versoes.map((v) => `<tr><td>${esc(v.prompt_version)}</td><td>${v.revisados}</td>${DIMS.map((k) => `<td>${pct(v.por_dimensao[k])}</td>`).join("")}<td><b>${pct(v.agregado)}</b></td></tr>`).join("")}
      </tbody></table>
      <p class="muted"><code>+fewshot</code> = a IA recebeu como exemplo tickets parecidos já revisados pelos atendentes · <code>regras</code> = plano B sem IA.</p>`
    : `<p class="muted">Revise tickets para comparar as versões do prompt.</p>`;

  const sli = r.sli;
  const risco = r.prazos_em_risco.length
    ? `<table class="tabela"><thead><tr><th>#</th><th>Urgência</th><th>Estado</th><th>Consumido</th></tr></thead><tbody>
        ${r.prazos_em_risco.map((x) => `<tr><td>#${x.ticket_id}</td><td>${pill(x.urgencia)}</td><td>${esc(ROTULO_ESTADO[x.estado])}</td><td>${pct(x.consumido_pct)}</td></tr>`).join("")}
      </tbody></table>`
    : `<p>✅ Nenhum ticket com prazo em risco.</p>`;

  $("#metricas").innerHTML = `
    <div class="card"><h2>Principais motivos de contato</h2>${barras(r.motivos_contato, (m) => m.assunto)}</div>
    <div class="card"><h2>Idiomas dos clientes</h2>${barras(r.idiomas || [], (i) => nomeIdioma(i.idioma))}</div>
    <div class="card"><h2>SLI e error budget</h2>
      <div class="politica ${esc(sli.politica)}">${esc(POLITICA_TEXTO[sli.politica])}</div>
      <p>SLI (janela ${sli.janela_dias} dias): <b>${pct(sli.sli_pct)}</b> · meta ${sli.alvo_pct.toFixed(0)}%</p>
      <p>Violações / orçamento: <b>${sli.violacoes} / ${sli.orcamento}</b> · orçamento consumido: <b>${pct(sli.consumo_orcamento_pct)}</b></p>
    </div>
    <div class="card largo"><div class="lado-a-lado">
      <div><h2>Precisão da triagem</h2>${precisao}</div>
      <div><h2>Evolução da IA por versão do prompt</h2>${evolucao}</div>
    </div></div>
    <div class="card largo"><h2>Prazos de resposta em risco</h2>${risco}</div>`;
}

// ---------------------------------------------------------------- atendimento: fila estilo chat
function filtrados() {
  const q = $("#busca").value.trim().toLowerCase();
  const todos = q
    ? estado.tickets.filter((t) => [t.cliente, t.canal, t.texto, t.ultima_texto, t.assunto].join(" ").toLowerCase().includes(q))
    : estado.tickets;
  const espera = todos.filter(aguardando).sort((a, b) => (ORDEM_URGENCIA[a.urgencia] ?? 4) - (ORDEM_URGENCIA[b.urgencia] ?? 4)
    || (b.sla.consumido_pct ?? 0) - (a.sla.consumido_pct ?? 0));
  const respondidos = todos.filter((t) => !aguardando(t));
  return { espera, respondidos };
}

// O texto vem do cliente (não confiável): tudo passa por esc() (threat model T19).
function cartao(t) {
  const s = t.sla;
  const ultimo = t.ultima_texto || t.texto || "";
  const novo = t.first_response_at && aguardando(t) ? selo("cliente respondeu", "s-novo") : "";
  return `<button type="button" class="cartao${t.ticket_id === estado.selecionado ? " sel" : ""}" data-id="${t.ticket_id}">
    <div class="topo"><div class="avatar">${inicial(t.cliente)}</div>
      <div><div class="nome">${esc(t.cliente || "Cliente sem identificação")}</div>
      <div class="sub">#${t.ticket_id} · ${esc(t.canal)} · ${esc(hora(t.received_at))}</div></div></div>
    <div class="linha-c">${novo}${t.urgencia ? pill(t.urgencia) : ""}${selo(ROTULO_SLA_CURTO[s.estado] || s.estado, `s-${esc(s.estado)}`)}${t.idioma && t.idioma !== "pt" ? selo(t.idioma.toUpperCase(), "s-respondido") : ""}</div>
    <div class="linha-c"><b>Fila:</b> ${esc((t.equipe || "a definir").replace("_", " "))} · <b>Assunto:</b> ${esc(t.assunto || "classificando")}</div>
    <div class="msg">${esc(ultimo.length > 110 ? ultimo.slice(0, 110) + "…" : ultimo)}</div>
  </button>`;
}

function renderCartoes() {
  const { espera, respondidos } = filtrados();
  $("#qtd-espera").textContent = espera.length;
  $("#qtd-respondidos").textContent = respondidos.length;
  const badge = $("#badge-espera");
  const totalEspera = estado.tickets.filter(aguardando).length;
  badge.hidden = !totalEspera;
  badge.textContent = totalEspera;
  const itens = (estado.lista === "espera" ? espera : respondidos).slice(0, 80);
  $("#cartoes").innerHTML = itens.map(cartao).join("") || `<div class="vazio">Nenhum atendimento aqui.</div>`;
}

function opcoes(valores, atual) {
  return valores.map((v) => `<option ${v === atual ? "selected" : ""}>${esc(v)}</option>`).join("");
}

function renderDetalhe() {
  const t = estado.tickets.find((x) => x.ticket_id === estado.selecionado);
  const painel = $("#detalhe");
  if (!t) {
    painel.innerHTML = `<div class="vazio">Escolha um atendimento na lista para conversar com o cliente, ver a triagem e a resposta sugerida, e corrigir a IA.</div>`;
    return;
  }
  const classificado = t.status === "classificado";
  // Conversa (ADR-016): a primeira mensagem do cliente aparece até a conversa carregar.
  painel.innerHTML = `
    <div class="cab-chat"><div class="avatar">${inicial(t.cliente)}</div>
      <div><div class="nome">${esc(t.cliente || "Cliente sem identificação")}</div>
      <div class="sub">#${t.ticket_id} · ${esc(t.canal)} · ${esc(hora(t.received_at))} · ${esc(ROTULO_ESTADO[t.sla.estado] || t.sla.estado)}</div></div></div>
    <div id="conversa" class="conversa" aria-live="polite">${bolha({ direcao: "entrada", autor: t.cliente, texto: t.texto, created_at: t.received_at })}</div>
    <form id="form-chat" class="form-chat">
      <textarea name="texto" maxlength="2000" required placeholder="Escreva a resposta ao cliente…" aria-label="Resposta ao cliente"></textarea>
      <div class="acoes-chat">
        <button type="submit" class="btn primario">Enviar</button>
        ${classificado && t.resposta_sugerida ? `<button type="button" class="btn sugestao" data-acao="sugestao">💡 Usar resposta sugerida pela IA</button>` : ""}
      </div>
    </form>
    <p class="nota">Modo demonstração: a resposta fica registrada nesta conversa e conta como 1ª resposta (SLA). O envio ao canal do cliente (WhatsApp, e-mail, chat) será integrado depois.</p>
    <details class="triagem" id="triagem" ${estado.triagemAberta ? "open" : ""}>
      <summary>Triagem da IA e correções</summary>
      <div class="corpo">${classificado ? triagem(t) : `<p class="muted">⏳ A IA ainda está classificando este atendimento.</p>`}</div>
    </details>`;
  carregarConversa(t.ticket_id);
}

function triagem(t) {
  const s = t.sla;
  const d = estado.dominio;
  return `
    <div>${pill(t.urgencia)}${selo(t.assunto, "s-respondido")}${selo(t.sentimento, "s-respondido")}${selo("→ " + t.equipe.replace("_", " "), "s-novo")}</div>
    <p class="muted">Prazo: ${esc(ROTULO_ESTADO[s.estado])} — ${s.prazo_minutos} min · vence ${esc(hora(s.vence_em))} · origem da triagem: ${esc(t.origem)}</p>
    <div><h3>Resposta sugerida</h3><div class="resposta" lang="${esc(t.idioma || "pt")}">${esc(t.resposta_sugerida)}</div></div>
    <p class="muted">🌐 Cliente escreveu em ${esc(nomeIdioma(t.idioma))}${t.idioma && t.idioma !== "pt" ? " · resposta sugerida no mesmo idioma" : ""}</p>
    <p class="muted">Confiança: ${DIMS.map((k) => `${k} ${Math.round(Number(t["conf_" + k]) * 100)}%`).join(" · ")}</p>
    ${t.exemplos
      ? `<p class="aprendizado">🧠 Prompt ${esc(t.prompt_version)} · aprendeu com tickets já revisados parecidos: ${t.exemplos.split(",").map((i) => `#${esc(i)}`).join(", ")}</p>`
      : `<p class="muted">Prompt ${esc(t.prompt_version || "—")} · sem exemplos revisados parecidos</p>`}
    <div class="acoes">
      <button type="button" class="btn" data-acao="revisar" ${t.revisado ? "disabled" : ""}>✓ Triagem correta</button>
      <button type="button" class="btn" data-acao="responder" ${t.first_response_at ? "disabled" : ""}>📨 Marcar respondido</button>
    </div>
    <form id="form-correcao">
      <h3>Corrigir triagem</h3>
      <div class="grade-campos">
        <label>Assunto <select name="assunto">${opcoes(d.assuntos, t.assunto)}</select></label>
        <label>Urgência <select name="urgencia">${opcoes(d.urgencias, t.urgencia)}</select></label>
        <label>Sentimento <select name="sentimento">${opcoes(d.sentimentos, t.sentimento)}</select></label>
        <label>Equipe <select name="equipe">${opcoes(d.equipes, t.equipe)}</select></label>
      </div>
      <label style="margin-top:8px">Resposta <textarea name="resposta_sugerida" rows="4" maxlength="2000">${esc(t.resposta_sugerida)}</textarea></label>
      <p style="margin-top:8px"><button type="submit" class="btn primario">Salvar correção</button> <span id="correcao-status" class="muted" aria-live="polite"></span></p>
    </form>`;
}

// ---------------------------------------------------------------- conversa (chat do atendimento)
function bolha(m) {
  const lado = m.direcao === "saida" ? "saida" : "entrada";
  return `<div class="bolha ${lado}"><div class="bolha-autor">${esc(m.autor || (lado === "saida" ? "Atendente" : "Cliente"))}
    · ${esc(hora(m.created_at))}</div>${esc(m.texto)}</div>`;
}

async function carregarConversa(id) {
  try {
    const msgs = await api(`/tickets/${id}/mensagens`);
    const caixa = $("#conversa");
    if (estado.selecionado !== id || !caixa || !msgs.length) return; // trocou de ticket enquanto carregava
    const html = msgs.map(bolha).join("");
    if (caixa.dataset.html === html) return; // nada novo: não mexe na rolagem
    caixa.dataset.html = html;
    caixa.innerHTML = html;
    caixa.scrollTop = caixa.scrollHeight;
  } catch (e) {
    if (e instanceof NaoAutorizado) return sair("Chave inválida ou expirada.");
    alertaStatus(e.message);
  }
}

async function enviarChat(form) {
  const id = estado.selecionado;
  const texto = form.texto.value.trim();
  if (!texto) return;
  try {
    await api(`/tickets/${id}/mensagens`, { method: "POST", body: JSON.stringify({ texto, autor: $("#atendente").value.trim() || "Atendente" }) });
    form.texto.value = "";
    estado.editando = false;
    await carregar(); // a 1ª resposta muda o prazo (SLA) e o ticket sai de "Em espera"
  } catch (e) {
    alertaStatus(e.message);
  }
}

// ---------------------------------------------------------------- incidentes e correções
function renderIncidentes(grupos) {
  $("#lista-incidentes").innerHTML = grupos.length
    ? grupos.map((g) => `<details class="card grupo" ${g.status === "incidente" ? "open" : ""}>
        <summary>${g.status === "incidente" ? "🚨" : "•"} Grupo #${g.id} · ${esc(g.status)} · ${g.size} mensagens · ${esc(g.assunto_predominante || "—")}</summary>
        <p class="muted">${esc(g.justificativa || "Ainda abaixo do volume mínimo de incidente.")}</p>
        <ul>${g.tickets.map((t) => `<li><b>${esc(t.cliente || "cliente")}</b> (${esc(t.canal)}, ${esc(hora(t.received_at))}): ${esc(t.texto)}</li>`).join("")}</ul>
      </details>`).join("")
    : `<p class="card">✅ Nenhum incidente detectado.</p>`;
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
  if (acao === "sugestao") {
    const t = estado.tickets.find((x) => x.ticket_id === id);
    const caixa = $("#form-chat textarea");
    caixa.value = t?.resposta_sugerida || "";
    caixa.focus();
    estado.editando = true;
    return;
  }
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
  const dados = Object.fromEntries(new FormData(form));
  try {
    const r = await api(`/tickets/${estado.selecionado}/correcoes`, { method: "POST", body: JSON.stringify(dados) });
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
    st.textContent = `✅ Ticket #${r.ticket_id} recebido. Veja em Atendimento → Em espera em instantes.`;
    form.texto.value = "";
    setTimeout(carregar, 1500);
  } catch (e) {
    st.textContent = `⚠ ${e.message}`;
  }
}

function irPara(pagina) {
  estado.pagina = pagina;
  document.querySelectorAll(".menu button").forEach((b) => {
    if (b.dataset.pagina === pagina) b.setAttribute("aria-current", "page"); else b.removeAttribute("aria-current");
  });
  document.querySelectorAll(".pagina").forEach((s) => { s.hidden = s.id !== `pagina-${pagina}`; });
  $("#titulo").textContent = TITULOS[pagina];
  gravarArmazenado(sessionStorage, "triagem.pagina", pagina);
  if (pagina === "correcoes") api("/correcoes").then(renderCorrecoes).catch((e) => alertaStatus(e.message));
}

function abrirTicket(id) {
  estado.selecionado = id;
  estado.editando = false;
  renderCartoes();
  renderDetalhe();
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
  irPara(lerArmazenado(sessionStorage, "triagem.pagina") || "dashboard");
  await carregar();
  agendar();
}

function sair(erro) {
  clearInterval(estado.timer);
  estado.chave = "";
  gravarArmazenado(sessionStorage, "triagem.chave", "");
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
    gravarArmazenado(sessionStorage, "triagem.chave", estado.chave);
    entrar();
  });
  $("#sair").addEventListener("click", () => sair());
  $("#intervalo").addEventListener("change", agendar);
  $("#todos-grupos").addEventListener("change", carregar);
  $("#atendente").value = lerArmazenado(localStorage, "triagem.atendente") || "Atendente";
  $("#atendente").addEventListener("change", (ev) => gravarArmazenado(localStorage, "triagem.atendente", ev.target.value.trim()));
  $(".menu").addEventListener("click", (ev) => {
    const b = ev.target.closest("button[data-pagina]");
    if (b) irPara(b.dataset.pagina);
  });

  $("#busca").addEventListener("input", renderCartoes);
  $(".abas-lista").addEventListener("click", (ev) => {
    const b = ev.target.closest("button[data-lista]");
    if (!b) return;
    estado.lista = b.dataset.lista;
    document.querySelectorAll(".abas-lista button").forEach((x) => x.setAttribute("aria-selected", String(x === b)));
    renderCartoes();
  });
  $("#cartoes").addEventListener("click", (ev) => {
    const c = ev.target.closest(".cartao[data-id]");
    if (c) abrirTicket(Number(c.dataset.id));
  });

  const detalhe = $("#detalhe");
  detalhe.addEventListener("click", (ev) => {
    const b = ev.target.closest("button[data-acao]");
    if (b) acaoDetalhe(b.dataset.acao);
  });
  detalhe.addEventListener("toggle", (ev) => { if (ev.target.id === "triagem") estado.triagemAberta = ev.target.open; }, true);
  detalhe.addEventListener("input", () => { estado.editando = true; });
  detalhe.addEventListener("submit", (ev) => {
    if (ev.target.id === "form-chat") {
      ev.preventDefault();
      enviarChat(ev.target);
    } else if (ev.target.id === "form-correcao") {
      ev.preventDefault();
      salvarCorrecao(ev.target);
    }
  });
  // Enter envia a resposta do chat; Shift+Enter quebra a linha.
  detalhe.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter" && !ev.shiftKey && ev.target.closest("#form-chat")) {
      ev.preventDefault();
      ev.target.form.requestSubmit();
    }
  });

  $("#form-nova").addEventListener("submit", (ev) => {
    ev.preventDefault();
    enviarMensagem(ev.target);
  });

  if (estado.chave) entrar(); else sair();
});
