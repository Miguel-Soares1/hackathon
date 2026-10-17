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
const ORDEM_ESTADO = { estourado: 0, em_risco: 1, no_prazo: 2, aguardando_classificacao: 3, respondido: 4 };
// Filtro das chamadas, o mesmo no Dashboard e no Atendimento (guardado neste navegador).
const URGENCIAS_FILTRO = [["critica", "crítica"], ["alta", "alta"], ["media", "média"], ["baixa", "baixa"], ["", "sem triagem"]];
const ESTADOS_FILTRO = [["estourado", "estourado"], ["em_risco", "em risco"], ["no_prazo", "no prazo"],
  ["respondido", "respondido"], ["aguardando_classificacao", "classificando"]];
const FILTRO_PADRAO = {
  modo: "ia", // ia = todas na ordem da IA · prioridade = só as de maior prioridade · personalizado
  ordem: "urgencia",
  inverter: false,
  urgencias: URGENCIAS_FILTRO.map(([v]) => v),
  estados: ESTADOS_FILTRO.map(([v]) => v),
  consumidoMin: 0,
};
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
  encerrando: false, // formulário de encerramento aberto no detalhe
  relatorios: {}, // relatório já carregado por ticket (não muda depois do encerramento)
  timer: null,
  filtro: lerFiltro(),
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
    renderBadgeIncidentes();
    renderMetricas();
    renderChamadas();
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

// A conversa aberta no Atendimento é um chat: atualiza a cada 3 s, sem esperar o ciclo do painel.
setInterval(() => {
  if (estado.chave && estado.pagina === "atendimento" && estado.selecionado && !document.hidden) carregarConversa(estado.selecionado);
}, 3000);

// ---------------------------------------------------------------- dashboard
function renderKpis() {
  const r = estado.resumo;
  const itens = [
    ["Tickets", estado.tickets.length],
    ["Em risco / estourados", r.prazos_em_risco.length],
    [`SLI (meta ${r.sli.alvo_pct.toFixed(0)}%)`, pct(r.sli.sli_pct)],
    [`Precisão (${r.precisao.revisados} revisados)`, pct(r.precisao.agregado)],
  ];
  $("#kpis").innerHTML = itens
    .map(([rot, val]) => `<div class="kpi"><div class="rotulo">${esc(rot)}</div><div class="valor">${esc(val)}</div></div>`)
    .join("");
}

// Total de incidentes no menu lateral, como o contador de atendimentos em espera.
function renderBadgeIncidentes() {
  const badge = $("#badge-incidentes");
  const total = estado.resumo.incidentes;
  badge.hidden = !total;
  badge.textContent = total;
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
    </div></div>`;
}

// ---------------------------------------------------------------- filtro das chamadas (Dashboard e Atendimento)
function lerFiltro() {
  try {
    const salvo = JSON.parse(lerArmazenado(localStorage, "triagem.filtro") || "{}");
    return { ...FILTRO_PADRAO, ...salvo };
  } catch {
    return { ...FILTRO_PADRAO };
  }
}

// Prioridade da IA: urgência que ela atribuiu, depois o estado do prazo e o quanto do prazo já foi consumido.
function porPrioridadeIa(a, b) {
  return (ORDEM_URGENCIA[a.urgencia] ?? 4) - (ORDEM_URGENCIA[b.urgencia] ?? 4)
    || (ORDEM_ESTADO[a.sla.estado] ?? 5) - (ORDEM_ESTADO[b.sla.estado] ?? 5)
    || (b.sla.consumido_pct ?? 0) - (a.sla.consumido_pct ?? 0);
}

const COMPARADORES = {
  numero: (a, b) => a.ticket_id - b.ticket_id,
  urgencia: (a, b) => (ORDEM_URGENCIA[a.urgencia] ?? 4) - (ORDEM_URGENCIA[b.urgencia] ?? 4),
  estado: (a, b) => (ORDEM_ESTADO[a.sla.estado] ?? 5) - (ORDEM_ESTADO[b.sla.estado] ?? 5),
  consumido: (a, b) => (b.sla.consumido_pct ?? 0) - (a.sla.consumido_pct ?? 0),
};

const maiorPrioridade = (t) => ["critica", "alta"].includes(t.urgencia) || ["estourado", "em_risco"].includes(t.sla.estado);

function aplicarFiltro(tickets) {
  const f = estado.filtro;
  if (f.modo === "ia") return [...tickets].sort(porPrioridadeIa);
  if (f.modo === "prioridade") return tickets.filter(maiorPrioridade).sort(porPrioridadeIa);
  const sentido = f.inverter ? -1 : 1;
  const comparar = COMPARADORES[f.ordem] || COMPARADORES.urgencia;
  return tickets
    .filter((t) => f.urgencias.includes(t.urgencia || "")
      && f.estados.includes(t.sla.estado)
      && (t.sla.consumido_pct ?? 0) >= f.consumidoMin)
    .sort((a, b) => sentido * comparar(a, b) || porPrioridadeIa(a, b));
}

const caixas = (nome, itens, marcados) => itens
  .map(([v, rot]) => `<label class="chip"><input type="checkbox" name="${nome}" value="${esc(v)}" ${marcados.includes(v) ? "checked" : ""}> ${esc(rot)}</label>`)
  .join("");

function htmlFiltros() {
  const f = estado.filtro;
  const sel = (v, atual, rot) => `<option value="${v}" ${String(v) === String(atual) ? "selected" : ""}>${rot}</option>`;
  return `
    <div class="filtros-linha">
      <label>Mostrar <select name="modo">
        ${sel("ia", f.modo, "Todas, na ordem de prioridade da IA")}
        ${sel("prioridade", f.modo, "Só as de maior prioridade (IA)")}
        ${sel("personalizado", f.modo, "Personalizado")}
      </select></label>
      <button type="button" class="btn" data-acao="limpar-filtro">Limpar filtros</button>
      <span class="contagem muted" aria-live="polite"></span>
    </div>
    <div class="filtros-personalizado" ${f.modo === "personalizado" ? "" : "hidden"}>
      <div class="filtros-linha">
        <label>Ordenar por <select name="ordem">
          ${sel("numero", f.ordem, "Número (#)")}
          ${sel("urgencia", f.ordem, "Urgência (crítica primeiro)")}
          ${sel("estado", f.ordem, "Estado do prazo (estourado primeiro)")}
          ${sel("consumido", f.ordem, "Prazo consumido (maior primeiro)")}
        </select></label>
        <label class="toggle"><input type="checkbox" name="inverter" ${f.inverter ? "checked" : ""}> Inverter a ordem</label>
        <label>Prazo consumido <select name="consumidoMin">
          ${[0, 25, 50, 75, 100].map((v) => sel(v, f.consumidoMin, v ? `≥ ${v}%` : "qualquer")).join("")}
        </select></label>
      </div>
      <fieldset class="chips"><legend>Urgência</legend>${caixas("urgencias", URGENCIAS_FILTRO, f.urgencias)}</fieldset>
      <fieldset class="chips"><legend>Estado</legend>${caixas("estados", ESTADOS_FILTRO, f.estados)}</fieldset>
    </div>
    <p class="muted legenda-filtro" ${f.modo === "prioridade" ? "" : "hidden"}>Urgência crítica ou alta, ou prazo estourado ou em risco.</p>`;
}

function renderFiltros() {
  document.querySelectorAll(".filtros").forEach((caixa) => { caixa.innerHTML = htmlFiltros(); });
}

function lerFiltrosDe(caixa) {
  const marcados = (nome) => [...caixa.querySelectorAll(`input[name="${nome}"]:checked`)].map((i) => i.value);
  return {
    modo: caixa.querySelector('[name="modo"]').value,
    ordem: caixa.querySelector('[name="ordem"]').value,
    inverter: caixa.querySelector('[name="inverter"]').checked,
    urgencias: marcados("urgencias"),
    estados: marcados("estados"),
    consumidoMin: Number(caixa.querySelector('[name="consumidoMin"]').value),
  };
}

function mudarFiltro(novo) {
  estado.filtro = novo;
  gravarArmazenado(localStorage, "triagem.filtro", JSON.stringify(novo));
  // As duas barras (Dashboard e Atendimento) mostram o mesmo filtro.
  document.querySelectorAll(".filtros").forEach((caixa) => {
    caixa.querySelector('[name="modo"]').value = novo.modo;
    caixa.querySelector('[name="ordem"]').value = novo.ordem;
    caixa.querySelector('[name="inverter"]').checked = novo.inverter;
    caixa.querySelector('[name="consumidoMin"]').value = String(novo.consumidoMin);
    caixa.querySelectorAll('input[name="urgencias"]').forEach((i) => { i.checked = novo.urgencias.includes(i.value); });
    caixa.querySelectorAll('input[name="estados"]').forEach((i) => { i.checked = novo.estados.includes(i.value); });
    caixa.querySelector(".filtros-personalizado").hidden = novo.modo !== "personalizado";
    caixa.querySelector(".legenda-filtro").hidden = novo.modo !== "prioridade";
  });
  renderChamadas();
  renderCartoes();
}

function contagem(contexto, mostradas, total) {
  const el = document.querySelector(`.filtros[data-contexto="${contexto}"] .contagem`);
  if (el) el.textContent = mostradas === total ? `${total} chamada(s)` : `${mostradas} de ${total} chamada(s)`;
}

// ---------------------------------------------------------------- dashboard: tabela de chamadas em espera
function renderChamadas() {
  const espera = estado.tickets.filter(aguardando);
  const lista = aplicarFiltro(espera);
  contagem("dashboard", lista.length, espera.length);
  const linhas = lista.slice(0, 50);
  $("#tabela-chamadas").innerHTML = linhas.length
    ? `<table class="tabela chamadas"><thead><tr><th>#</th><th>Cliente</th><th>Urgência</th><th>Estado</th><th>Consumido</th><th>Assunto</th></tr></thead><tbody>
        ${linhas.map((t) => `<tr data-id="${t.ticket_id}" tabindex="0" title="Abrir no Atendimento">
          <td>#${t.ticket_id}</td><td>${esc(t.cliente || "—")}</td><td>${pill(t.urgencia)}</td>
          <td>${esc(ROTULO_ESTADO[t.sla.estado] || t.sla.estado)}</td><td>${pct(t.sla.consumido_pct)}</td><td>${esc(t.assunto || "classificando")}</td></tr>`).join("")}
      </tbody></table>${lista.length > linhas.length ? `<p class="muted">Mostrando as 50 primeiras de ${lista.length}.</p>` : ""}`
    : `<p class="muted">${espera.length ? "Nenhuma chamada com esses filtros." : "✅ Nenhuma chamada em espera."}</p>`;
}

// ---------------------------------------------------------------- atendimento: fila estilo chat
function filtrados() {
  const q = $("#busca").value.trim().toLowerCase();
  const todos = q
    ? estado.tickets.filter((t) => [t.cliente, t.canal, t.texto, t.ultima_texto, t.assunto].join(" ").toLowerCase().includes(q))
    : estado.tickets;
  return {
    espera: aplicarFiltro(todos.filter(aguardando)),
    respondidos: aplicarFiltro(todos.filter((t) => !aguardando(t) && !t.encerrado)),
    encerrados: aplicarFiltro(todos.filter((t) => t.encerrado)),
  };
}

const listaDe = (t) => (t.encerrado ? "encerrados" : aguardando(t) ? "espera" : "respondidos");

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
  const listas = filtrados();
  for (const [nome, itens] of Object.entries(listas)) $(`#qtd-${nome}`).textContent = itens.length;
  const badge = $("#badge-espera");
  const totalEspera = estado.tickets.filter(aguardando).length;
  badge.hidden = !totalEspera;
  badge.textContent = totalEspera;
  const atual = listas[estado.lista];
  contagem("atendimento", atual.length, estado.tickets.filter((t) => listaDe(t) === estado.lista).length);
  const itens = atual.slice(0, 80);
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
      <div class="sub">#${t.ticket_id} · ${esc(t.canal)} · ${esc(hora(t.received_at))} · ${esc(t.encerrado ? "🔒 encerrado" : ROTULO_ESTADO[t.sla.estado] || t.sla.estado)}</div></div>
      ${t.encerrado ? "" : `<button type="button" class="btn encerrar" data-acao="abrir-encerramento" ${estado.encerrando ? "disabled" : ""}>✔ Encerrar atendimento</button>`}</div>
    <div id="conversa" class="conversa" aria-live="polite">${bolha({ direcao: "entrada", autor: t.cliente, texto: t.texto, created_at: t.received_at })}</div>
    ${t.encerrado ? `<div id="relatorio" class="relatorio">${estado.relatorios[t.ticket_id] ? htmlRelatorio(estado.relatorios[t.ticket_id]) : `<p class="muted">Carregando o relatório…</p>`}</div>`
      : estado.encerrando ? formEncerramento() : formChat(t, classificado)}
    <details class="triagem" id="triagem" ${estado.triagemAberta ? "open" : ""}>
      <summary>Triagem da IA e correções</summary>
      <div class="corpo">${classificado ? triagem(t) : `<p class="muted">⏳ A IA ainda está classificando este atendimento.</p>`}</div>
    </details>`;
  carregarConversa(t.ticket_id);
  if (t.encerrado && !estado.relatorios[t.ticket_id]) carregarRelatorio(t.ticket_id);
}

function formChat(t, classificado) {
  return `
    <form id="form-chat" class="form-chat">
      <textarea name="texto" maxlength="2000" required placeholder="Escreva a resposta ao cliente…" aria-label="Resposta ao cliente"></textarea>
      <div class="acoes-chat">
        <button type="submit" class="btn primario">Enviar</button>
        ${classificado && t.resposta_sugerida ? `<button type="button" class="btn sugestao" data-acao="sugestao">💡 Usar resposta sugerida pela IA</button>` : ""}
      </div>
    </form>
    <p class="nota">Modo demonstração: a resposta fica registrada nesta conversa e conta como 1ª resposta (SLA). O envio ao canal do cliente (WhatsApp, e-mail, chat) será integrado depois.</p>`;
}

// ---------------------------------------------------------------- encerramento e relatório
function formEncerramento() {
  const desfechos = Object.entries(estado.dominio.desfechos || { resolvido: "resolvido" });
  return `
    <form id="form-encerrar" class="card encerramento">
      <h3>Encerrar atendimento</h3>
      <label>Como terminou? <select name="desfecho">${desfechos.map(([v, rot]) => `<option value="${esc(v)}">${esc(rot)}</option>`).join("")}</select></label>
      <label>Observação para o relatório (opcional) <textarea name="observacao" rows="3" maxlength="2000" placeholder="Ex.: estorno solicitado ao financeiro"></textarea></label>
      <div class="acoes-chat">
        <button type="submit" class="btn primario">Encerrar e gerar relatório</button>
        <button type="button" class="btn" data-acao="cancelar-encerramento">Cancelar</button>
        <span id="encerrar-status" class="muted" aria-live="polite"></span>
      </div>
      <p class="nota">Depois de encerrado, o atendimento não recebe mais respostas. Se o cliente escrever de novo, abre um novo atendimento.</p>
    </form>`;
}

function duracao(min) {
  if (min === null || min === undefined) return "—";
  if (min < 60) return `${Math.round(min)} min`;
  const h = Math.floor(min / 60);
  return h < 24 ? `${h} h ${Math.round(min % 60)} min` : `${Math.floor(h / 24)} d ${h % 24} h`;
}

function htmlRelatorio(r) {
  const d = r.dados;
  const tr = d.triagem;
  const prazo = d.sla.cumpriu === null || d.sla.cumpriu === undefined ? "—" : d.sla.cumpriu ? "✅ cumprido" : "🔴 estourado";
  return `
    <div class="cab-relatorio"><h3>📄 Relatório do atendimento #${r.ticket_id}</h3>${selo(r.desfecho_rotulo, r.desfecho === "resolvido" ? "s-no_prazo" : "s-em_risco")}</div>
    <p class="muted">Encerrado por ${esc(r.atendente || "atendente")} em ${esc(hora(r.gerado_em))}</p>
    <div class="resposta">${esc(r.resumo)}</div>
    ${r.proximos_passos ? `<p><b>Próximos passos:</b> ${esc(r.proximos_passos)}</p>` : ""}
    ${r.observacao ? `<p><b>Observação do atendente:</b> ${esc(r.observacao)}</p>` : ""}
    <dl class="numeros">
      <div><dt>Cliente</dt><dd>${esc(d.cliente || "sem identificação")} · ${esc(d.canal)}</dd></div>
      <div><dt>Duração</dt><dd>${duracao(d.duracao_min)}</dd></div>
      <div><dt>1ª resposta</dt><dd>${d.sem_resposta ? "encerrado sem resposta" : duracao(d.primeira_resposta_min)}</dd></div>
      <div><dt>Prazo (SLA)</dt><dd>${prazo}${d.sla.prazo_minutos ? ` · ${duracao(d.sla.prazo_minutos)}` : ""}</dd></div>
      <div><dt>Mensagens</dt><dd>${d.mensagens.cliente} do cliente · ${d.mensagens.atendente} do atendente</dd></div>
      <div><dt>Idioma</dt><dd>${esc(nomeIdioma(d.idioma))}</dd></div>
      <div><dt>Triagem final</dt><dd>${pill(tr.urgencia)} ${esc(tr.assunto || "—")} · ${esc(tr.sentimento || "—")} · ${esc((tr.equipe || "—").replace("_", " "))}</dd></div>
      <div><dt>Revisão da IA</dt><dd>${tr.corrigida ? "corrigida pelo atendente" : tr.revisada ? "confirmada" : "não revisada"}</dd></div>
    </dl>
    <p class="nota">Resumo ${r.origem_resumo === "llm" ? "escrito pela IA a partir da conversa" : "automático (IA indisponível)"}.</p>`;
}

async function carregarRelatorio(id) {
  try {
    const r = await api(`/tickets/${id}/relatorio`);
    estado.relatorios[id] = r;
    const caixa = $("#relatorio");
    if (estado.selecionado === id && caixa) caixa.innerHTML = htmlRelatorio(r);
  } catch (e) {
    if (e instanceof NaoAutorizado) return sair("Chave inválida ou expirada.");
    const caixa = $("#relatorio");
    if (caixa) caixa.innerHTML = `<p class="muted">⚠ ${esc(e.message)}</p>`;
  }
}

async function encerrarAtendimento(form) {
  const id = estado.selecionado;
  const dados = Object.fromEntries(new FormData(form));
  dados.autor = $("#atendente").value.trim() || "Atendente";
  const botao = form.querySelector('button[type="submit"]');
  botao.disabled = true;
  $("#encerrar-status").textContent = "Gerando o relatório…";
  try {
    estado.relatorios[id] = await api(`/tickets/${id}/encerramento`, { method: "POST", body: JSON.stringify(dados) });
    estado.encerrando = false;
    estado.editando = false;
    estado.lista = "encerrados";
    document.querySelectorAll(".abas-lista button").forEach((x) => x.setAttribute("aria-selected", String(x.dataset.lista === "encerrados")));
    await carregar(); // o detalhe redesenha com o relatório
  } catch (e) {
    botao.disabled = false;
    $("#encerrar-status").textContent = `⚠ ${e.message}`;
  }
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
  if (acao === "abrir-encerramento" || acao === "cancelar-encerramento") {
    estado.encerrando = acao === "abrir-encerramento";
    estado.editando = estado.encerrando; // não redesenhar o formulário enquanto o atendente escolhe
    renderDetalhe();
    return;
  }
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

function abrirNoAtendimento(id) {
  const t = estado.tickets.find((x) => x.ticket_id === id);
  estado.lista = t ? listaDe(t) : "espera";
  document.querySelectorAll(".abas-lista button").forEach((x) => x.setAttribute("aria-selected", String(x.dataset.lista === estado.lista)));
  irPara("atendimento");
  abrirTicket(id);
}

function abrirTicket(id) {
  estado.selecionado = id;
  estado.editando = false;
  estado.encerrando = false;
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
  renderFiltros();
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
  document.querySelectorAll(".filtros").forEach((caixa) => {
    caixa.addEventListener("change", () => mudarFiltro(lerFiltrosDe(caixa)));
    caixa.addEventListener("click", (ev) => {
      if (ev.target.closest('[data-acao="limpar-filtro"]')) mudarFiltro({ ...FILTRO_PADRAO });
    });
  });
  const tabela = $("#tabela-chamadas");
  tabela.addEventListener("click", (ev) => {
    const tr = ev.target.closest("tr[data-id]");
    if (tr) abrirNoAtendimento(Number(tr.dataset.id));
  });
  tabela.addEventListener("keydown", (ev) => {
    const tr = ev.target.closest("tr[data-id]");
    if (tr && (ev.key === "Enter" || ev.key === " ")) { ev.preventDefault(); abrirNoAtendimento(Number(tr.dataset.id)); }
  });
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
    } else if (ev.target.id === "form-encerrar") {
      ev.preventDefault();
      encerrarAtendimento(ev.target);
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
