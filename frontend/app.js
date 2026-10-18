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
const TITULOS = { atendimento: "Atendimento", incidentes: "Incidentes" };
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
  // Sessão do usuário (ADR-018): "manter conectado" guarda no localStorage (30 dias); senão só nesta aba.
  token: lerArmazenado(localStorage, "triagem.sessao") || lerArmazenado(sessionStorage, "triagem.sessao"),
  usuario: null,
  dominio: null,
  tickets: [],
  resumo: null,
  pagina: "atendimento",
  lista: "espera",
  canal: "",
  selecionado: null,
  editando: false, // não redesenhar o detalhe enquanto o atendente digita
  triagemAberta: false,
  encerrando: false, // formulário de encerramento aberto no detalhe
  relatorios: {}, // relatório já carregado por ticket (não muda depois do encerramento)
  timer: null,
  midiaUrls: {}, // id da mídia -> URL local (blob) já baixada, para não baixar a cada atualização
  anexos: [], // imagem/áudio a enviar na resposta do chat: { tipo, mime, dados_base64, nome, url }
  gravador: null,
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

// Canal de origem do cliente: rótulo, cor e ícone genérico (sem logotipos de marca).
const CANAIS = {
  whatsapp: { rotulo: "WhatsApp", ic: '<path d="M4 20l1.3-3.9A8 8 0 1 1 8 18.8z"/><path d="M9 9.5c.3 1.6 1.9 3.3 3.6 3.8l1-1 1.6.7-.3 1.4c-2.9.2-6-2.9-5.9-5.9l1.4-.3.7 1.6z"/>' },
  instagram: { rotulo: "Instagram", ic: '<rect x="3.5" y="3.5" width="17" height="17" rx="5"/><circle cx="12" cy="12" r="4"/><circle cx="17.2" cy="6.8" r=".6"/>' },
  email: { rotulo: "E-mail", ic: '<rect x="3" y="5" width="18" height="14" rx="2.5"/><path d="m4 7 8 6 8-6"/>' },
  chat: { rotulo: "Chat do site", ic: '<path d="M21 11.5a8.4 8.4 0 0 1-12.3 7.4L3 21l2.1-5.7A8.4 8.4 0 1 1 21 11.5z"/>' },
  formulario: { rotulo: "Formulário", ic: '<rect x="5" y="3" width="14" height="18" rx="2"/><path d="M9 8h6M9 12h6M9 16h4"/>' },
  outro: { rotulo: "Outro canal", ic: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>' },
};
function chaveCanal(c) {
  const v = String(c || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().replace(/[^a-z]/g, "");
  if (v.startsWith("whats")) return "whatsapp";
  if (v.startsWith("insta")) return "instagram";
  if (v.startsWith("email") || v === "mail") return "email";
  if (v.startsWith("formulario") || v === "web") return "formulario";
  if (v.startsWith("chat")) return "chat";
  return "outro";
}
const svgCanal = (k) => `<svg viewBox="0 0 24 24" aria-hidden="true">${CANAIS[k].ic}</svg>`;
function tagCanal(canal) {
  const k = chaveCanal(canal);
  return `<span class="canal c-${k}">${svgCanal(k)}${esc(CANAIS[k].rotulo)}</span>`;
}
// Nome amigável + contato: "Ana (5511...)" -> Ana / 5511...; "instagram:ana.r" -> @ana.r
function telefone(n) {
  const d = String(n).replace(/\D/g, "");
  const m = d.match(/^55(\d{2})(\d{4,5})(\d{4})$/);
  return m ? `+55 (${m[1]}) ${m[2]}-${m[3]}` : "+" + d;
}
function contato(t) {
  const bruto = (t.cliente || "").trim();
  if (!bruto) return { nome: "Cliente sem identificação", detalhe: "" };
  const ig = bruto.match(/^instagram:(.+)$/i);
  if (ig) return { nome: "@" + ig[1], detalhe: "" };
  const wa = bruto.match(/^(.*?)\s*\((\+?\d{8,15})\)$/);
  if (wa) return { nome: wa[1] || wa[2], detalhe: telefone(wa[2]) };
  return { nome: bruto, detalhe: "" };
}
function avatar(t, grande) {
  const k = chaveCanal(t.canal);
  return `<div class="avatar${grande ? " grande" : ""}">${inicial(contato(t).nome)}<span class="avatar-canal c-${k}" title="${esc(CANAIS[k].rotulo)}">${svgCanal(k)}</span></div>`;
}
const horaCurta = (iso) => (hora(iso).split(", ")[1] || hora(iso));

class NaoAutorizado extends Error {}

async function api(caminho, opcoes = {}) {
  const resp = await fetch(caminho, {
    ...opcoes,
    headers: { ...(estado.token ? { Authorization: `Bearer ${estado.token}` } : {}),
      ...(opcoes.body ? { "Content-Type": "application/json" } : {}) },
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
      api("/tickets?limite=1000"),
      api("/metricas"),
      api(`/incidentes?todos_os_grupos=${$("#todos-grupos").checked}`),
    ]);
    estado.tickets = tickets;
    estado.resumo = resumo;
    renderBadgeIncidentes();
    renderCartoes();
    if (!estado.editando && !tocandoAudio() && !estado.anexos.length && !estado.gravador) renderDetalhe();
    else if (estado.selecionado) carregarConversa(estado.selecionado); // a conversa continua atualizando
    renderIncidentes(incidentes);
    const agora = `Atualizado às ${new Date().toLocaleTimeString("pt-BR")}`;
    $("#status").textContent = agora;
  } catch (e) {
    if (e instanceof NaoAutorizado) return sair("Sua sessão expirou. Entre de novo.");
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
  if (estado.token && estado.pagina === "atendimento" && estado.selecionado && !document.hidden) carregarConversa(estado.selecionado);
}, 3000);

// Situação de cada cliente: em espera (falta responder), em atendimento (respondido e em aberto), cancelado, encerrado.
function situacao(t) {
  if (t.desfecho) return t.desfecho === "cancelado" ? "cancelado" : "encerrado";
  if (t.ia_atendendo) return "ia"; // urgência baixa ou média: a IA responde sozinha (ADR-019)
  return aguardando(t) ? "espera" : "atendimento";
}

// Total de incidentes no menu lateral, como o contador de atendimentos em espera.
function renderBadgeIncidentes() {
  const badge = $("#badge-incidentes");
  const total = estado.resumo.incidentes;
  badge.hidden = !total;
  badge.textContent = total;
}

// ---------------------------------------------------------------- filtro das chamadas (Atendimento)
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
  // A barra de filtros do Atendimento.
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
  renderCartoes();
}

function contagem(contexto, mostradas, total) {
  const el = document.querySelector(`.filtros[data-contexto="${contexto}"] .contagem`);
  if (el) el.textContent = mostradas === total ? `${total} chamada(s)` : `${mostradas} de ${total} chamada(s)`;
}

// ---------------------------------------------------------------- atendimento: fila estilo chat
function filtrados() {
  const q = $("#busca").value.trim().toLowerCase();
  const base = estado.canal ? estado.tickets.filter((t) => chaveCanal(t.canal) === estado.canal) : estado.tickets;
  const todos = q
    ? base.filter((t) => [t.cliente, t.canal, t.texto, t.ultima_texto, t.assunto].join(" ").toLowerCase().includes(q))
    : base;
  return {
    espera: aplicarFiltro(todos.filter((t) => situacao(t) === "espera")),
    ia: aplicarFiltro(todos.filter((t) => situacao(t) === "ia")),
    atendimento: aplicarFiltro(todos.filter((t) => situacao(t) === "atendimento")),
    finalizados: aplicarFiltro(todos.filter((t) => t.desfecho)),
  };
}

const listaDe = (t) => (t.desfecho ? "finalizados" : situacao(t));

// O texto vem do cliente (não confiável): tudo passa por esc() (threat model T19).
function cartao(t) {
  const c = contato(t);
  const ultimo = t.ultima_texto || t.texto || "";
  const marcas = [];
  if (t.desfecho) marcas.push(selo(t.desfecho, t.desfecho === "cancelado" ? "u-critica" : "s-no_prazo"));
  else {
    if (t.ia_atendendo) marcas.push(selo("🤖 IA atendendo", "s-ia"));
    else if (t.escalado_em && aguardando(t)) marcas.push(`<span class="selo s-escalado" title="${esc(t.motivo_escalada || "")}">↗ veio da IA</span>`);
    else if (t.first_response_at && aguardando(t)) marcas.push(selo("nova mensagem", "s-novo"));
    if (t.urgencia === "critica" || t.urgencia === "alta") marcas.push(pill(t.urgencia));
    if (aguardando(t) && (t.sla.estado === "estourado" || t.sla.estado === "em_risco")) marcas.push(selo(ROTULO_SLA_CURTO[t.sla.estado], `s-${esc(t.sla.estado)}`));
  }
  return `<button type="button" class="cartao${t.ticket_id === estado.selecionado ? " sel" : ""}" data-id="${t.ticket_id}">
    ${avatar(t)}
    <div class="cartao-corpo">
      <div class="cartao-linha"><span class="nome">${esc(c.nome)}</span><span class="quando">${esc(horaCurta(t.ultima_entrada_at || t.received_at))}</span></div>
      <div class="cartao-linha">${tagCanal(t.canal)}${marcas.join("")}</div>
      <div class="msg">${iconesMidia(t)}${esc(ultimo)}</div>
    </div>
  </button>`;
}

function renderCartoes() {
  const listas = filtrados();
  $("#qtd-espera").textContent = listas.espera.length;
  $("#qtd-ia").textContent = listas.ia.length;
  $("#qtd-atendimento").textContent = listas.atendimento.length;
  $("#qtd-finalizados").textContent = listas.finalizados.length;
  const badge = $("#badge-espera");
  const totalEspera = estado.tickets.filter((t) => situacao(t) === "espera").length;
  badge.hidden = !totalEspera;
  badge.textContent = totalEspera;
  const atual = listas[estado.lista] || listas.espera;
  contagem("atendimento", atual.length, estado.tickets.filter((t) => listaDe(t) === (listas[estado.lista] ? estado.lista : "espera")).length);
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
    painel.innerHTML = `<div class="vazio">Escolha um atendimento na lista para conversar com o cliente.</div>`;
    return;
  }
  const classificado = t.status === "classificado";
  const c = contato(t);
  const acoes = t.desfecho
    ? `<span class="finalizado">${t.desfecho === "cancelado" ? "Cancelado" : "Encerrado"} · ${esc(horaCurta(t.encerrado_em))}</span><button type="button" class="btn pequeno" data-acao="reabrir">↺ Reabrir</button>`
    : `<button type="button" class="btn pequeno ok" data-acao="abrir-encerramento" ${estado.encerrando ? "disabled" : ""}>✓ Encerrar</button><button type="button" class="btn pequeno perigo" data-acao="cancelar">✕ Cancelar</button>`;
  // Conversa (ADR-016): a primeira mensagem do cliente aparece até a conversa carregar.
  painel.innerHTML = `
    <div class="cab-chat">${avatar(t, true)}
      <div class="cab-info"><div class="nome">${esc(c.nome)}</div>
        <div class="sub">${tagCanal(t.canal)}${c.detalhe ? `<span>${esc(c.detalhe)}</span>` : ""}<span>#${t.ticket_id}</span></div></div>
      <div class="cab-acoes">${acoes}</div></div>
    ${t.ia_atendendo ? `<div class="aviso-ia">🤖 A IA está atendendo este cliente (urgência ${esc(t.urgencia)}). Se você responder, o atendimento passa a ser seu.</div>`
      : t.escalado_em ? `<div class="aviso-ia escalado">↗ ${esc(t.motivo_escalada && t.motivo_escalada.startsWith("assumido") ? t.motivo_escalada.replace("assumido por", "Assumido da IA por") : `A IA passou para um atendente: ${t.motivo_escalada || ""}`)}</div>` : ""}
    <div id="conversa" class="conversa" aria-live="polite">${bolha({ direcao: "entrada", autor: t.cliente, texto: t.texto, created_at: t.received_at })}</div>
    ${renderMidias(t)}
    ${t.desfecho ? `<div id="relatorio" class="relatorio">${estado.relatorios[t.ticket_id] ? htmlRelatorio(estado.relatorios[t.ticket_id]) : `<p class="muted">Carregando o relatório…</p>`}</div>`
      : estado.encerrando ? formEncerramento() : `
    <form id="form-chat" class="form-chat">
      ${classificado && t.resposta_sugerida ? `<button type="button" class="btn sugestao pequeno" data-acao="sugestao" title="A IA escreve na hora uma resposta para a última mensagem do cliente, considerando a conversa">💡 Sugerir resposta para a última mensagem</button>` : ""}
      <ul id="lista-anexos" class="anexos"></ul>
      <div class="compositor">
        <textarea name="texto" rows="2" maxlength="2000" placeholder="Responder pelo ${esc(CANAIS[chaveCanal(t.canal)].rotulo)}…" aria-label="Resposta ao cliente"></textarea>
        <button type="submit" class="btn primario" aria-label="Enviar">Enviar</button>
      </div>
      <div class="ferramentas-chat">
        <button type="button" id="anexar" class="btn pequeno">📎 Anexar imagem</button>
        <button type="button" id="gravar" class="btn pequeno" aria-pressed="${estado.gravador ? "true" : "false"}">${estado.gravador ? "⏹ Parar gravação" : "🎙 Gravar áudio"}</button>
        <input type="file" id="arquivo" accept="image/jpeg,image/png,image/webp" multiple hidden>
        <span id="chat-status" class="muted" aria-live="polite"></span>
      </div>
    </form>
    `}
    <details class="triagem" id="triagem" ${estado.triagemAberta ? "open" : ""}>
      <summary>Triagem da IA${classificado ? ` <span class="resumo-triagem">${esc(t.assunto || "")} · ${esc((t.equipe || "").replace("_", " "))}</span>` : ""}</summary>
      <div class="corpo">${classificado ? triagem(t) : `<p class="muted">⏳ A IA ainda está ${t.midias?.length ? "lendo as mídias e " : ""}classificando este atendimento.</p>`}</div>
    </details>`;
  carregarConversa(t.ticket_id);
  carregarMidias(t);
  renderAnexos();
  if (t.desfecho && !estado.relatorios[t.ticket_id]) carregarRelatorio(t.ticket_id);
}

// ---------------------------------------------------------------- encerramento e relatório
function formEncerramento() {
  const desfechos = Object.entries(estado.dominio.desfechos || { resolvido: "resolvido" });
  return `
    <form id="form-encerrar" class="card encerramento">
      <h3>Encerrar atendimento</h3>
      <label>Como terminou? <select name="resultado">${desfechos.map(([v, rot]) => `<option value="${esc(v)}">${esc(rot)}</option>`).join("")}</select></label>
      <label>Observação para o relatório (opcional) <textarea name="observacao" rows="3" maxlength="2000" placeholder="Ex.: estorno solicitado ao financeiro"></textarea></label>
      <div class="acoes-chat">
        <button type="submit" class="btn primario">Encerrar e gerar relatório</button>
        <button type="button" class="btn" data-acao="cancelar-encerramento">Voltar</button>
        <span id="encerrar-status" class="muted" aria-live="polite"></span>
      </div>
      <p class="nota">Depois de encerrado, o atendimento não recebe mais respostas (dá para reabrir). Se o cliente escrever de novo, abre um novo atendimento.</p>
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
    <p class="muted">${r.desfecho === "cancelado" ? "Cancelado" : "Encerrado"} por ${esc(r.atendente || "atendente")} em ${esc(hora(r.gerado_em))}</p>
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
    if (e instanceof NaoAutorizado) return sair("Sua sessão expirou. Entre de novo.");
    const caixa = $("#relatorio");
    if (caixa) caixa.innerHTML = `<p class="muted">⚠ ${esc(e.message)}</p>`;
  }
}

async function encerrarAtendimento(form) {
  const id = estado.selecionado;
  const dados = { desfecho: "encerrado", ...Object.fromEntries(new FormData(form)) };
  const botao = form.querySelector('button[type="submit"]');
  botao.disabled = true;
  $("#encerrar-status").textContent = "Gerando o relatório…";
  try {
    estado.relatorios[id] = (await api(`/tickets/${id}/encerrar`, { method: "POST", body: JSON.stringify(dados) })).relatorio;
    estado.encerrando = false;
    estado.editando = false;
    estado.lista = "finalizados";
    document.querySelectorAll(".abas-lista button").forEach((x) => x.setAttribute("aria-selected", String(x.dataset.lista === "finalizados")));
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
    <div><h3>Resposta sugerida</h3><div class="resposta" lang="${esc(t.idioma || "pt")}">${esc(t.resposta_sugerida)}</div>
      <p class="muted">${t.sugestao_atualizada ? "💬 Para a última mensagem do cliente, com a conversa como contexto." : t.sugestao_mensagem_id ? "✏️ Texto corrigido pelo atendente." : "💬 Para a mensagem que abriu o atendimento."}</p></div>
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
const AUTOR_IA = "Assistente NEXUS (IA)";

function bolha(m) {
  const lado = m.direcao === "saida" ? (m.autor === AUTOR_IA ? "saida ia" : "saida") : "entrada";
  const autor = lado === "saida" ? m.autor || "Atendente" : contato({ cliente: m.autor }).nome.replace("Cliente sem identificação", "Cliente");
  const anexos = (m.midias || []).map((x) => `<div class="bolha-midia" data-midia="${x.id}">${x.tipo === "audio" ? "🎙 Áudio" : "📷 Imagem"} <span class="muted">carregando…</span></div>`).join("");
  return `<div class="bolha ${lado}">${anexos}${esc(m.texto)}<div class="bolha-autor">${esc(autor)} · ${esc(horaCurta(m.created_at))}</div></div>`;
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
    mostrarMidias(id, msgs.flatMap((m) => m.midias || []));
  } catch (e) {
    if (e instanceof NaoAutorizado) return sair("Sua sessão expirou. Entre de novo.");
    alertaStatus(e.message);
  }
}

async function enviarChat(form) {
  const id = estado.selecionado;
  const texto = form.texto.value.trim();
  if (estado.gravador) return void ($("#chat-status").textContent = "⚠ Pare a gravação antes de enviar.");
  if (!texto && !estado.anexos.length) return;
  const midias = estado.anexos.map(({ tipo, mime, dados_base64 }) => ({ tipo, mime, dados_base64 }));
  try {
    await api(`/tickets/${id}/mensagens`, { method: "POST", body: JSON.stringify({ texto, midias }) }); // assina quem está logado
    form.texto.value = "";
    limparAnexos();
    estado.editando = false;
    await carregar(); // a 1ª resposta muda o prazo (SLA) e o ticket sai de "Em espera"
  } catch (e) {
    alertaStatus(e.message);
  }
}

// ---------------------------------------------------------------- resposta sugerida para a última mensagem
// A IA escreve na hora, com a conversa inteira como contexto; sem a IA, usa a sugestão que já existia.
async function sugerirResposta(id) {
  const botao = $('#detalhe button[data-acao="sugestao"]');
  const caixa = $("#form-chat textarea");
  if (!botao || !caixa) return;
  const rotulo = botao.textContent;
  botao.disabled = true;
  botao.textContent = "⏳ Gerando sugestão…";
  estado.editando = true; // não redesenha o detalhe enquanto a IA responde
  try {
    const r = await api(`/tickets/${id}/sugestao`, { method: "POST" });
    if (estado.selecionado !== id) return; // o atendente trocou de ticket enquanto a IA respondia
    caixa.value = r.resposta_sugerida || "";
    caixa.focus();
    const t = estado.tickets.find((x) => x.ticket_id === id);
    if (t && r.atualizada) { t.resposta_sugerida = r.resposta_sugerida; t.sugestao_atualizada = 1; t.sugestao_mensagem_id = r.mensagem_id; }
    if (!r.atualizada) alertaStatus("A IA não respondeu agora: usei a última sugestão disponível.");
  } catch (e) {
    if (e instanceof NaoAutorizado) return sair("Sua sessão expirou. Entre de novo.");
    alertaStatus(e.message);
  } finally {
    botao.disabled = false;
    botao.textContent = rotulo;
  }
}

// ---------------------------------------------------------------- mídias do cliente (áudio e foto, ADR-017)
const ESTADO_MIDIA = { pendente: "⏳ a IA está lendo…", lido: "✓ lido pela IA (o texto está na conversa)", erro: "⚠ a IA não conseguiu ler" };

// Redesenhar o detalhe interromperia o áudio que o atendente está ouvindo.
function tocandoAudio() {
  return [...document.querySelectorAll("#detalhe audio")].some((a) => !a.paused);
}

function iconesMidia(t) {
  return (t.midias || []).map((m) => (m.tipo === "audio" ? "🎙 " : "📷 ")).join("");
}

function renderMidias(t) {
  if (!t.midias || !t.midias.length) return "";
  return `<div class="midias">${t.midias.map((m) => `
    <div class="midia">
      <div data-midia="${m.id}">${m.tipo === "audio" ? "🎙 Áudio" : "📷 Foto"} <span class="muted">carregando…</span></div>
      <span class="estado-midia ${m.status === "erro" ? "erro" : "muted"}">${esc(ESTADO_MIDIA[m.status] || m.status)}</span>
    </div>`).join("")}</div>`;
}

function carregarMidias(t) {
  return mostrarMidias(t.ticket_id, t.midias || []);
}

// <img>/<audio> não mandam o header de autorização: baixa com a sessão e mostra a partir de uma URL local (blob).
async function mostrarMidias(ticketId, lista) {
  for (const m of lista) {
    try {
      if (!estado.midiaUrls[m.id]) {
        const resp = await fetch(`/tickets/${ticketId}/midias/${m.id}`, { headers: { Authorization: `Bearer ${estado.token}` } });
        if (!resp.ok) throw new Error(`erro ${resp.status}`);
        estado.midiaUrls[m.id] = URL.createObjectURL(await resp.blob());
      }
      const alvo = document.querySelector(`[data-midia="${m.id}"]`);
      if (!alvo) continue; // o atendente trocou de ticket enquanto baixava
      const url = estado.midiaUrls[m.id];
      alvo.innerHTML = m.tipo === "audio" ? `<audio controls preload="metadata" src="${url}"></audio>`
        : `<a href="${url}" target="_blank" rel="noopener"><img src="${url}" alt="Imagem da conversa"></a>`;
    } catch (e) {
      const alvo = document.querySelector(`[data-midia="${m.id}"] .muted`);
      if (alvo) alvo.textContent = `não foi possível carregar (${e.message})`;
    }
  }
}

// ---------------------------------------------------------------- imagem e áudio na resposta do chat (ADR-017)
const MAX_ANEXOS = 3;
const MAX_MB = 8;

function lerBase64(blob) {
  return new Promise((ok, falha) => {
    const r = new FileReader();
    r.onload = () => ok(String(r.result).split(",")[1] || "");
    r.onerror = () => falha(r.error);
    r.readAsDataURL(blob);
  });
}

async function adicionarAnexo(blob, nome) {
  const st = $("#chat-status");
  const mime = blob.type || "";
  const tipo = mime.startsWith("image/") ? "imagem" : mime.startsWith("audio/") ? "audio" : null;
  if (!tipo) return void (st.textContent = `⚠ ${nome}: envie uma imagem (JPG, PNG, WebP) ou um áudio.`);
  if (estado.anexos.length >= MAX_ANEXOS) return void (st.textContent = `⚠ No máximo ${MAX_ANEXOS} anexos por mensagem.`);
  if (blob.size > MAX_MB * 1024 * 1024) return void (st.textContent = `⚠ ${nome}: maior que ${MAX_MB} MB.`);
  estado.anexos.push({ tipo, mime, nome, dados_base64: await lerBase64(blob), url: URL.createObjectURL(blob) });
  st.textContent = "";
  renderAnexos();
}

function renderAnexos() {
  const lista = $("#lista-anexos");
  if (!lista) return;
  lista.innerHTML = estado.anexos.map((a, i) => `<li class="anexo">
    ${a.tipo === "audio" ? `<audio controls src="${a.url}"></audio>` : `<img src="${a.url}" alt="">`}
    <span class="muted">${esc(a.nome)}</span>
    <button type="button" class="btn pequeno" data-remover="${i}" aria-label="Remover ${esc(a.nome)}">Remover</button>
  </li>`).join("");
}

function limparAnexos() {
  estado.anexos.forEach((a) => URL.revokeObjectURL(a.url));
  estado.anexos = [];
  renderAnexos();
}

async function alternarGravacao() {
  const st = $("#chat-status");
  if (estado.gravador) return estado.gravador.stop();
  let fluxo;
  try {
    fluxo = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch {
    return void (st.textContent = "⚠ Sem acesso ao microfone. Permita o uso no navegador e tente de novo.");
  }
  const gravador = new MediaRecorder(fluxo);
  const pedacos = [];
  gravador.ondataavailable = (ev) => { if (ev.data.size) pedacos.push(ev.data); };
  gravador.onstop = () => {
    fluxo.getTracks().forEach((faixa) => faixa.stop());
    estado.gravador = null;
    const botao = $("#gravar");
    if (botao) {
      botao.setAttribute("aria-pressed", "false");
      botao.textContent = "🎙 Gravar áudio";
    }
    if ($("#chat-status")) $("#chat-status").textContent = "";
    if (gravador.descartar) return; // o atendente trocou de atendimento no meio da gravação
    const blob = new Blob(pedacos, { type: gravador.mimeType || "audio/webm" });
    adicionarAnexo(blob, `gravação ${new Date().toLocaleTimeString("pt-BR")}`);
  };
  gravador.start();
  estado.gravador = gravador;
  const botao = $("#gravar");
  botao.setAttribute("aria-pressed", "true");
  botao.textContent = "⏹ Parar gravação";
  st.textContent = "🔴 Gravando… clique em “Parar gravação” quando terminar.";
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

// ---------------------------------------------------------------- ações
async function acaoDetalhe(acao) {
  const id = estado.selecionado;
  if (acao === "abrir-encerramento" || acao === "cancelar-encerramento") {
    estado.encerrando = acao === "abrir-encerramento";
    estado.editando = estado.encerrando; // não redesenhar o formulário enquanto o atendente escolhe
    renderDetalhe();
    return;
  }
  if (acao === "sugestao") return sugerirResposta(id);
  try {
    if (acao === "revisar") await api(`/tickets/${id}/revisao`, { method: "POST" });
    if (acao === "responder") await api(`/tickets/${id}/resposta`, { method: "POST", body: "{}" });
    if (acao === "cancelar") {
      estado.relatorios[id] = (await api(`/tickets/${id}/encerrar`, { method: "POST", body: JSON.stringify({ desfecho: "cancelado" }) })).relatorio;
    }
    if (acao === "reabrir") {
      await api(`/tickets/${id}/reabrir`, { method: "POST" });
      delete estado.relatorios[id]; // reabrir descarta o relatório; um novo sai no próximo encerramento
    }
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

function irPara(pagina) {
  estado.pagina = pagina;
  document.querySelectorAll(".menu button").forEach((b) => {
    if (b.dataset.pagina === pagina) b.setAttribute("aria-current", "page"); else b.removeAttribute("aria-current");
  });
  document.querySelectorAll(".pagina").forEach((s) => { s.hidden = s.id !== `pagina-${pagina}`; });
  $("#titulo").textContent = TITULOS[pagina];
  gravarArmazenado(sessionStorage, "triagem.pagina", pagina);
}

function abrirTicket(id) {
  if (id !== estado.selecionado) { // anexos e gravação pertencem ao atendimento que estava aberto
    if (estado.gravador) {
      estado.gravador.descartar = true;
      estado.gravador.stop();
    }
    limparAnexos();
  }
  estado.selecionado = id;
  estado.editando = false;
  estado.encerrando = false;
  renderCartoes();
  renderDetalhe();
}

// ---------------------------------------------------------------- acesso (usuário e senha, ADR-018)
function guardarSessao(token, manter) {
  estado.token = token;
  gravarArmazenado(localStorage, "triagem.sessao", manter ? token : "");
  gravarArmazenado(sessionStorage, "triagem.sessao", manter ? "" : token);
}

async function postPublico(caminho, corpo) {
  const resp = await fetch(caminho, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(corpo) });
  const dados = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(dados.detail || (Array.isArray(dados.erros) ? dados.erros.map((e) => e.erro).join("; ") : `erro ${resp.status}`));
  return dados;
}

async function entrar() {
  try {
    estado.usuario = await api("/auth/eu");
    estado.dominio = await api("/dominio");
  } catch (e) {
    return sair(e instanceof NaoAutorizado ? "Sua sessão expirou. Entre de novo." : `Servidor indisponível: ${e.message}`);
  }
  const u = estado.usuario;
  $("#eu-nome").textContent = u.nome;
  $("#eu-papel").textContent = `${u.usuario} · ${u.papel === "admin" ? "administrador" : "atendente"}`;
  $("#eu-inicial").textContent = (u.nome || "?").trim().slice(0, 1).toUpperCase();
  $("#login").hidden = true;
  $("#app").hidden = false;
  renderFiltros();
  const ultima = lerArmazenado(sessionStorage, "triagem.pagina") || "atendimento";
  irPara(TITULOS[ultima] ? ultima : "atendimento");
  await carregar();
  agendar();
}

async function sair(erro) {
  clearInterval(estado.timer);
  if (estado.token && !erro) fetch("/auth/logout", { method: "POST", headers: { Authorization: `Bearer ${estado.token}` } }).catch(() => {});
  guardarSessao("", false);
  estado.usuario = null;
  $("#app").hidden = true;
  $("#login").hidden = false;
  const p = $("#login-erro");
  p.hidden = !erro;
  p.textContent = erro || "";
  // Banco sem usuários: mostra o primeiro acesso (criar o administrador).
  try {
    const { precisa_configurar } = await (await fetch("/auth/estado")).json();
    $("#form-login").hidden = precisa_configurar;
    $("#form-primeiro").hidden = !precisa_configurar;
  } catch { /* servidor fora do ar: fica o login */ }
}

async function fazerLogin() {
  const erro = $("#login-erro");
  erro.hidden = true;
  try {
    const manter = $("#manter").checked;
    const r = await postPublico("/auth/login", { usuario: $("#usuario").value.trim(), senha: $("#senha").value, manter_conectado: manter });
    $("#senha").value = "";
    guardarSessao(r.token, manter);
    entrar();
  } catch (e) {
    erro.hidden = false;
    erro.textContent = e.message;
  }
}

async function criarPrimeiroAdmin(form) {
  const erro = $("#primeiro-erro");
  erro.hidden = true;
  const d = Object.fromEntries(new FormData(form));
  if (d.senha !== d.senha2) { erro.hidden = false; erro.textContent = "As senhas não conferem."; return; }
  try {
    const r = await postPublico("/auth/primeiro-admin", { chave_api: d.chave_api, nome: d.nome, usuario: d.usuario, senha: d.senha });
    form.reset();
    guardarSessao(r.token, true);
    entrar();
  } catch (e) {
    erro.hidden = false;
    erro.textContent = e.message;
  }
}

// ---------------------------------------------------------------- eventos
document.addEventListener("DOMContentLoaded", () => {
  $("#form-login").addEventListener("submit", (ev) => { ev.preventDefault(); fazerLogin(); });
  $("#form-primeiro").addEventListener("submit", (ev) => { ev.preventDefault(); criarPrimeiroAdmin(ev.target); });
  $("#sair").addEventListener("click", () => sair());
  $("#intervalo").addEventListener("change", agendar);
  $("#todos-grupos").addEventListener("change", carregar);
  $(".menu").addEventListener("click", (ev) => {
    const b = ev.target.closest("button[data-pagina]");
    if (b) irPara(b.dataset.pagina);
  });

  $("#busca").addEventListener("input", renderCartoes);
  $("#filtro-canal").addEventListener("click", (ev) => {
    const b = ev.target.closest("button[data-canal]");
    if (!b) return;
    estado.canal = b.dataset.canal;
    document.querySelectorAll("#filtro-canal button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    renderCartoes();
  });
  document.querySelectorAll(".filtros").forEach((caixa) => {
    caixa.addEventListener("change", () => mudarFiltro(lerFiltrosDe(caixa)));
    caixa.addEventListener("click", (ev) => {
      if (ev.target.closest('[data-acao="limpar-filtro"]')) mudarFiltro({ ...FILTRO_PADRAO });
    });
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
    if (ev.target.closest("#anexar")) $("#arquivo").click();
    if (ev.target.closest("#gravar")) alternarGravacao();
    const r = ev.target.closest("button[data-remover]");
    if (r) {
      const [a] = estado.anexos.splice(Number(r.dataset.remover), 1);
      URL.revokeObjectURL(a.url);
      renderAnexos();
    }
  });
  detalhe.addEventListener("change", async (ev) => {
    if (ev.target.id !== "arquivo") return;
    for (const f of ev.target.files) {
      // Este botão é só para imagens; áudio entra pelo botão de gravar.
      if (!(f.type || "").startsWith("image/")) {
        $("#chat-status").textContent = `⚠ ${f.name}: anexe apenas imagens (JPG, PNG, WebP).`;
        continue;
      }
      await adicionarAnexo(f, f.name);
    }
    ev.target.value = ""; // permite escolher o mesmo arquivo de novo
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


  if (estado.token) entrar(); else sair();
});
