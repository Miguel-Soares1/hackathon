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
const TITULOS = { atendimento: "Atendimento", relatorios: "Relatórios", recorrencia: "Recorrência" };
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
const nomeEquipe = (e) => ({ financeiro: "Financeiro", suporte_tecnico: "Suporte técnico", engenharia: "Engenharia",
  retencao: "Retenção", atendimento: "Atendimento" }[e] || e || "—");
const nomeIdioma = (c) => (estado.dominio?.idiomas?.[c] ? `${estado.dominio.idiomas[c]} (${c})` : c || "—");

const estado = {
  // Sessão do usuário (ADR-018): "manter conectado" guarda no localStorage (30 dias); senão só nesta aba.
  chave: lerArmazenado(sessionStorage, "triagem.chave"),
  plantao: lerArmazenado(localStorage, "triagem.plantao") === "1", // de plantão neste navegador
  dominio: null,
  tickets: [],
  resumo: null,
  pagina: "atendimento",
  lista: "espera",
  canal: "",
  equipe: lerArmazenado(localStorage, "triagem.equipe"), // fila de uma equipe só ("" = todas)
  triagemAberta: false, // painel de triagem (correção) aberto no detalhe
  selecionado: null,
  editando: false, // não redesenhar o detalhe enquanto o atendente digita
  problemas: [],
  incidentes: [],
  periodo: Number(lerArmazenado(localStorage, "triagem.periodo") || 24), // horas; 0 = tudo
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
    headers: { "X-API-Key": estado.chave, "X-Atendente": encodeURIComponent(nomeAtendente()),
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
      api("/incidentes"), // usados na Recorrência
    ]);
    estado.tickets = tickets;
    estado.resumo = resumo;
    renderCartoes();
    if (!estado.editando && !tocandoAudio() && !estado.anexos.length && !estado.gravador) renderDetalhe();
    else if (estado.selecionado) carregarConversa(estado.selecionado); // a conversa continua atualizando
    estado.incidentes = incidentes;
    if (estado.pagina === "recorrencia") renderRecorrencia();
    const agora = `Atualizado às ${new Date().toLocaleTimeString("pt-BR")}`;
    $("#status").textContent = agora;
  } catch (e) {
    if (e instanceof NaoAutorizado) return sair("Sua sessão expirou. Entre de novo.");
    $("#status").textContent = `⚠ ${e.message}`;
  }
}

function agendar() {
  clearInterval(estado.timer);
  const s = Number($("#intervalo")?.value || 10);
  if (s > 0) estado.timer = setInterval(carregar, s * 1000);
}

// A conversa aberta no Atendimento é um chat: atualiza a cada 3 s, sem esperar o ciclo do painel.
setInterval(() => {
  if (estado.chave && estado.pagina === "atendimento" && estado.selecionado && !document.hidden) carregarConversa(estado.selecionado);
}, 3000);

// Situação de cada cliente: em espera (falta responder), em atendimento (respondido e em aberto), cancelado, encerrado.
function situacao(t) {
  if (t.desfecho) return t.desfecho === "cancelado" ? "cancelado" : "encerrado";
  if (t.ia_atendendo) return "ia"; // urgência baixa ou média: a IA responde sozinha (ADR-019)
  return aguardando(t) ? "espera" : "atendimento";
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
  const base = estado.tickets.filter((t) => (!estado.canal || chaveCanal(t.canal) === estado.canal)
    && (!estado.equipe || t.equipe === estado.equipe));
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
  const marca = !t.desfecho && (t.urgencia === "critica" || t.urgencia === "alta") ? pill(t.urgencia) : "";
  return `<button type="button" class="cartao${t.ticket_id === estado.selecionado ? " sel" : ""}${t.urgencia === "critica" && aguardando(t) ? " critico" : ""}" data-id="${t.ticket_id}">
    ${avatar(t)}
    <div class="cartao-corpo">
      <div class="cartao-linha"><span class="nome">${esc(c.nome)}</span>${marca}${t.equipe && !estado.equipe ? `<span class="equipe-tag">${esc(nomeEquipe(t.equipe))}</span>` : ""}<span class="quando">${esc(horaCurta(t.ultima_entrada_at || t.received_at))}</span></div>
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
  const c = contato(t);
  const acoes = t.desfecho
    ? `<span class="finalizado">${t.desfecho === "cancelado" ? "Cancelado" : "Encerrado"} · ${esc(horaCurta(t.encerrado_em))}</span><button type="button" class="btn pequeno" data-acao="reabrir">↺ Reabrir</button>`
    : `<button type="button" class="btn pequeno" data-acao="registrar-problema" title="Registrar este cliente num problema da aba Relatórios">📋 Registrar problema</button><button type="button" class="btn pequeno ok" data-acao="abrir-encerramento" ${estado.encerrando ? "disabled" : ""}>✓ Encerrar</button><button type="button" class="btn pequeno perigo" data-acao="cancelar">✕ Cancelar</button>`;
  // Conversa (ADR-016): a primeira mensagem do cliente aparece até a conversa carregar.
  painel.innerHTML = `
    <div class="cab-chat">${avatar(t, true)}
      <div class="cab-info"><div class="nome">${esc(c.nome)}</div>
        <div class="sub">${c.detalhe ? `<span>${esc(c.detalhe)}</span>` : ""}<span>#${t.ticket_id}</span></div></div>
      <div class="cab-acoes">${acoes}</div></div>
    ${htmlTriagem(t)}
    <div id="conversa" class="conversa" aria-live="polite">${bolha({ direcao: "entrada", autor: t.cliente, texto: t.texto, created_at: t.received_at })}</div>
    ${renderMidias(t)}
    ${t.desfecho ? `<div id="relatorio" class="relatorio">${estado.relatorios[t.ticket_id] ? htmlRelatorio(estado.relatorios[t.ticket_id]) : `<p class="muted">Carregando o relatório…</p>`}</div>`
      : estado.encerrando ? formEncerramento() : `
    <form id="form-chat" class="form-chat">
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
    `}`;
  carregarConversa(t.ticket_id);
  carregarMidias(t);
  renderAnexos();
  if (t.desfecho && !estado.relatorios[t.ticket_id]) carregarRelatorio(t.ticket_id);
}

// ---------------------------------------------------------------- triagem: confirmar ou corrigir (correções do atendente)
// A correção fica registrada (histórico) e mede a precisão da IA; urgência alta/crítica tira a conversa da IA.
function htmlTriagem(t) {
  if (!t.urgencia) return `<div class="triagem-faixa muted">⏳ Classificando…</div>`;
  const d = estado.dominio || {};
  const campo = (nome, rot, valores, atual, nomear) => `<label>${rot}<select name="${nome}">${valores
    .map((v) => `<option value="${esc(v)}" ${v === atual ? "selected" : ""}>${esc(nomear ? nomear(v) : v)}</option>`).join("")}</select></label>`;
  const estadoRev = t.revisado ? (DIMS.some((k) => t[k + "_original"] && t[k + "_original"] !== t[k]) ? "corrigida" : "confirmada") : "";
  return `<details class="triagem-faixa" ${estado.triagemAberta ? "open" : ""}>
    <summary>${pill(t.urgencia)} <span>${esc(nomeAssunto(t.assunto))}</span> · <span>${esc(nomeEquipe(t.equipe))}</span>
      ${estadoRev ? `<span class="muted">· triagem ${estadoRev}</span>` : `<span class="muted">· triagem da IA</span>`}</summary>
    <form id="form-triagem" class="form-triagem">
      ${campo("assunto", "Assunto", d.assuntos || [], t.assunto, nomeAssunto)}
      ${campo("urgencia", "Urgência", d.urgencias || [], t.urgencia)}
      ${campo("sentimento", "Sentimento", d.sentimentos || [], t.sentimento)}
      ${campo("equipe", "Equipe", d.equipes || [], t.equipe, nomeEquipe)}
      <div class="acoes-triagem">
        <button type="button" class="btn pequeno" data-acao="confirmar-triagem" ${t.revisado ? "disabled" : ""}>✓ IA acertou</button>
        <button type="submit" class="btn pequeno primario">Salvar correção</button>
        <span id="triagem-status" class="muted" aria-live="polite"></span>
      </div>
    </form>
  </details>`;
}

async function salvarTriagem(form) {
  const t = estado.tickets.find((x) => x.ticket_id === estado.selecionado);
  const novos = Object.fromEntries(new FormData(form));
  const mudou = Object.fromEntries(Object.entries(novos).filter(([k, v]) => v && v !== t[k]));
  const st = $("#triagem-status");
  if (!Object.keys(mudou).length) return void (st.textContent = "Nada mudou. Se a IA acertou, use “IA acertou”.");
  try {
    const r = await api(`/tickets/${t.ticket_id}/correcoes`, { method: "POST", body: JSON.stringify(mudou) });
    estado.editando = false;
    await carregar();
    $("#status").textContent = r.escalado ? "Correção salva. A urgência subiu: a conversa saiu da IA e foi para a fila de atendentes."
      : `Correção salva (${Object.keys(mudou).length} campo(s)).`;
  } catch (e) {
    st.textContent = `⚠ ${e.message}`;
  }
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
    await api(`/tickets/${id}/mensagens`, { method: "POST", body: JSON.stringify({ texto, midias }) }); // assina com o "Seu nome" (header X-Atendente)
    form.texto.value = "";
    limparAnexos();
    estado.editando = false;
    await carregar(); // a 1ª resposta muda o prazo (SLA) e o ticket sai de "Em espera"
  } catch (e) {
    alertaStatus(e.message);
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

// <img>/<audio> não mandam o header da chave: baixa com a chave e mostra a partir de uma URL local (blob).
async function mostrarMidias(ticketId, lista) {
  for (const m of lista) {
    try {
      if (!estado.midiaUrls[m.id]) {
        const resp = await fetch(`/tickets/${ticketId}/midias/${m.id}`, { headers: { "X-API-Key": estado.chave } });
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

// ---------------------------------------------------------------- ações
async function acaoDetalhe(acao) {
  const id = estado.selecionado;
  if (acao === "abrir-encerramento" || acao === "cancelar-encerramento") {
    estado.encerrando = acao === "abrir-encerramento";
    estado.editando = estado.encerrando; // não redesenhar o formulário enquanto o atendente escolhe
    renderDetalhe();
    return;
  }
  if (acao === "registrar-problema") return abrirRegistroProblema(id);
  try {
    if (acao === "revisar" || acao === "confirmar-triagem") await api(`/tickets/${id}/revisao`, { method: "POST" });
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
  if (acao === "confirmar-triagem") $("#status").textContent = "Triagem confirmada: conta como acerto da IA.";
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
  if (pagina === "relatorios") carregarProblemas();
  if (pagina === "recorrencia") renderRecorrencia();
}

function abrirTicket(id) {
  if (id !== estado.selecionado) { // anexos e gravação pertencem ao atendimento que estava aberto
    estado.triagemAberta = false;
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

// ---------------------------------------------------------------- alerta de problema crítico e plantão (ADR-020)
// Atendimento crítico esperando uma pessoa ou incidente aberto: a faixa pisca para todos; quem está de plantão
// também recebe a notificação do Windows e um aviso sonoro, uma vez por problema.
const avisados = new Set(JSON.parse(lerArmazenado(sessionStorage, "triagem.avisados") || "[]"));

function bipe() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    [0, 0.25, 0.5].forEach((t) => {
      const o = ctx.createOscillator(); const g = ctx.createGain();
      o.frequency.value = 880; g.gain.value = 0.15; o.connect(g); g.connect(ctx.destination);
      o.start(ctx.currentTime + t); o.stop(ctx.currentTime + t + 0.15);
    });
  } catch { /* navegador sem áudio */ }
}

function avisarPlantao(chave, titulo, corpo, abrir) {
  if (avisados.has(chave)) return;
  avisados.add(chave);
  gravarArmazenado(sessionStorage, "triagem.avisados", JSON.stringify([...avisados].slice(-200)));
  if (!estado.plantao) return;
  bipe();
  if ("Notification" in window && Notification.permission === "granted") {
    const n = new Notification(titulo, { body: corpo, tag: chave, requireInteraction: true });
    n.onclick = () => { window.focus(); abrir(); n.close(); };
  }
}

async function verificarAlertas() {
  if (!estado.chave) return;
  let r;
  try { r = await api("/alertas"); } catch { return; }
  const faixa = $("#alerta-critico");
  const itens = [
    ...r.criticos.map((c) => ({ chave: `t${c.ticket_id}`, texto: `CRÍTICO · ${contato(c).nome}: ${c.texto}`, botao: "Atender",
      abrir: () => { irPara("atendimento"); mostrarLista("espera"); abrirTicket(c.ticket_id); } })),
    ...r.incidentes.map((g) => ({ chave: `i${g.id}`, texto: `INCIDENTE · ${g.assunto || "problema"} · ${g.size} clientes`, botao: "Ver",
      abrir: () => irPara("recorrencia") })),
  ];
  faixa.hidden = !itens.length;
  if (!itens.length) return;
  const plantao = estado.plantao ? "Este navegador está de plantão: avisa com som e notificação."
    : "Marque “De plantão” no menu para ser avisado com som e notificação.";
  faixa.innerHTML = itens.slice(0, 3).map((x, i) => `<div class="alerta-linha"><span>🚨 ${esc(x.texto)}</span>
    <button type="button" class="btn pequeno" data-alerta="${i}">${x.botao}</button></div>`).join("")
    + `<div class="alerta-plantao">${esc(plantao)}${itens.length > 3 ? ` · e mais ${itens.length - 3}` : ""}</div>`;
  faixa.onclick = (ev) => { const b = ev.target.closest("[data-alerta]"); if (b) itens[Number(b.dataset.alerta)].abrir(); };
  itens.forEach((x) => avisarPlantao(x.chave, "🚨 Problema crítico", x.texto, x.abrir));
}
setInterval(verificarAlertas, 5000);

function mostrarLista(lista) {
  estado.lista = lista;
  document.querySelectorAll(".abas-lista button").forEach((x) => x.setAttribute("aria-selected", String(x.dataset.lista === lista)));
  renderCartoes();
}

function mudarPlantao(ligado) {
  estado.plantao = ligado;
  gravarArmazenado(localStorage, "triagem.plantao", ligado ? "1" : "");
  if (ligado && "Notification" in window && Notification.permission === "default") Notification.requestPermission();
}

// ---------------------------------------------------------------- recorrência: painel no estilo Grafana
// Tudo é calculado no navegador a partir dos tickets já carregados (período escolhido) e de /metricas (precisão).
const ROTULO_ASSUNTO = { pagamento: "Pagamento", cobranca: "Cobrança", acesso: "Acesso", instabilidade: "Instabilidade",
  cancelamento: "Cancelamento", reclamacao: "Reclamação", duvida: "Dúvida", elogio: "Elogio" };
const CORES = ["#73bf69", "#f2cc0c", "#5794f2", "#ff9830", "#b877d9", "#f2495c", "#8ab8ff", "#96d98d"];
const nomeAssunto = (a) => ROTULO_ASSUNTO[a] || a || "Sem triagem";
const dataUtc = (iso) => new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : iso + "Z");
const corLimiar = (v) => (v === null || v === undefined ? "#8e8e8e" : v >= 85 ? "#73bf69" : v >= 70 ? "#f2cc0c" : "#f2495c");

function noPeriodo(lista, campo) {
  if (!estado.periodo) return lista;
  const desde = Date.now() - estado.periodo * 3600e3;
  return lista.filter((x) => x[campo] && dataUtc(x[campo]).getTime() >= desde);
}

function painel(titulo, corpo, classe = "") {
  return `<section class="gf-painel ${classe}"><h3 class="gf-titulo">${esc(titulo)}</h3><div class="gf-corpo">${corpo}</div></section>`;
}

function stat(titulo, valor, sub, cor) {
  return painel(titulo, `<div class="gf-stat" style="color:${cor || "var(--texto-forte)"}">${esc(valor)}</div><div class="gf-sub">${esc(sub || "")}</div>`, "gf-stat-painel");
}

function barrasGf(itens, total, unidade = "") {
  const max = Math.max(1, ...itens.map((i) => i.n));
  return itens.length ? `<div class="gf-barras">${itens.map((i, k) => `<div class="gf-barra-linha">
      <span class="gf-rotulo">${esc(i.rotulo)}</span>
      <div class="gf-trilho"><div class="gf-barra" style="width:${(i.n / max) * 100}%;background:${i.cor || CORES[k % CORES.length]}"></div></div>
      <span class="gf-valor">${i.n}${unidade}${total ? `<small> ${Math.round((i.n / total) * 100)}%</small>` : ""}</span></div>`).join("")}</div>`
    : `<p class="gf-vazio">Sem dados no período.</p>`;
}

// Série temporal: casos por hora (24 h) ou por dia, total e os 3 motivos mais frequentes.
function serieTemporal(tickets, top) {
  const fim = Date.now();
  const inicio = estado.periodo ? fim - estado.periodo * 3600e3
    : Math.min(fim - 86400e3, ...tickets.map((t) => dataUtc(t.received_at).getTime()));
  const porHora = fim - inicio <= 72 * 3600e3; // até 3 dias: pontos por hora; acima disso, por dia
  const passo = porHora ? 3600e3 : 86400e3;
  const n = Math.max(2, Math.min(60, Math.ceil((fim - inicio) / passo)));
  const base = fim - n * passo;
  const contar = (filtro) => {
    const v = new Array(n).fill(0);
    tickets.filter(filtro).forEach((t) => { const i = Math.floor((dataUtc(t.received_at).getTime() - base) / passo); if (i >= 0 && i < n) v[i] += 1; });
    return v;
  };
  const series = [{ nome: "Total", cor: "#c7d0d9", v: contar(() => true), tracejada: true },
    ...top.map((a, k) => ({ nome: nomeAssunto(a), cor: CORES[k], v: contar((t) => t.assunto === a) }))];
  const max = Math.max(1, ...series.flatMap((s) => s.v));
  const W = 600, H = 170, E = 28, T = 8, B = 22;
  const x = (i) => E + (i * (W - E - 6)) / (n - 1);
  const y = (v) => T + (H - T - B) * (1 - v / max);
  const linhas = [0, 0.5, 1].map((f) => `<line x1="${E}" x2="${W - 6}" y1="${y(max * f)}" y2="${y(max * f)}" class="gf-grade-linha"/>
    <text x="${E - 6}" y="${y(max * f) + 4}" class="gf-eixo" text-anchor="end">${Math.round(max * f)}</text>`).join("");
  const rotulo = (i) => {
    const d = new Date(base + i * passo);
    return porHora ? d.toLocaleString("pt-BR", { timeZone: "America/Sao_Paulo", day: "2-digit", month: "2-digit", hour: "2-digit" }) + "h"
      : d.toLocaleDateString("pt-BR", { timeZone: "America/Sao_Paulo", day: "2-digit", month: "2-digit" });
  };
  const marcas = [...new Set([0, Math.floor((n - 1) / 2), n - 1])].map((i) => `<text x="${x(i)}" y="${H - 6}" class="gf-eixo" text-anchor="middle">${rotulo(i)}</text>`).join("");
  const caminhos = series.map((s) => `<polyline fill="none" stroke="${s.cor}" stroke-width="${s.tracejada ? 1.5 : 2}"
    ${s.tracejada ? 'stroke-dasharray="4 4"' : ""} points="${s.v.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ")}"/>`).join("");
  const legenda = series.map((s) => `<span><i style="background:${s.cor}"></i>${esc(s.nome)} <b>${s.v.reduce((a, b) => a + b, 0)}</b></span>`).join("");
  return `<svg viewBox="0 0 ${W} ${H}" class="gf-serie" role="img" aria-label="Casos ao longo do tempo">${linhas}${marcas}${caminhos}</svg>
    <div class="gf-legenda">${legenda}</div>`;
}

// Solicitações abertas com prazo de 1ª resposta estourado ou perto de estourar (agora, independe do período).
function htmlPrazos(lista) {
  if (!lista.length) return `<p class="gf-vazio">Nenhum prazo em risco agora.</p>`;
  const porId = Object.fromEntries(estado.tickets.map((t) => [t.ticket_id, t]));
  return `<table class="gf-tabela"><thead><tr><th>Cliente</th><th>Urgência</th><th>Equipe</th><th>Prazo</th><th>Consumido</th></tr></thead><tbody>
    ${lista.slice(0, 8).map((s) => {
      const t = porId[s.ticket_id] || {};
      const cor = s.estado === "estourado" ? "#f2495c" : "#ff9830";
      return `<tr class="gf-clicavel" data-abrir="${s.ticket_id}"><td>${esc(contato(t).nome)} <span class="muted">#${s.ticket_id}</span></td><td>${pill(s.urgencia)}</td>
        <td>${esc(nomeEquipe(t.equipe))}</td><td style="color:${cor}">${esc(ROTULO_SLA_CURTO[s.estado] || s.estado)}</td>
        <td><div class="gf-trilho"><div class="gf-barra" style="width:${Math.min(100, s.consumido_pct)}%;background:${cor}"></div></div>
          <small>${Math.round(s.consumido_pct)}%</small></td></tr>`;
    }).join("")}</tbody></table>${lista.length > 8 ? `<div class="gf-sub">e mais ${lista.length - 8}</div>` : ""}`;
}

function renderRecorrencia() {
  if (!estado.resumo) return;
  const tickets = noPeriodo(estado.tickets, "received_at");
  const total = tickets.length;
  const r = estado.resumo;
  // motivos de contato no período
  const porAssunto = {};
  tickets.forEach((t) => { porAssunto[t.assunto || ""] = (porAssunto[t.assunto || ""] || 0) + 1; });
  const motivos = Object.entries(porAssunto).sort((a, b) => b[1] - a[1]).map(([k, n]) => ({ chave: k, rotulo: nomeAssunto(k), n }));
  // clientes que voltaram (mais de um contato no período: atendimentos ou mensagens)
  const porCliente = {};
  tickets.forEach((t) => {
    const k = (t.cliente || `#${t.ticket_id}`).toLowerCase();
    const c = porCliente[k] || (porCliente[k] = { cliente: t, atendimentos: 0, mensagens: 0, motivos: new Set() });
    c.atendimentos += 1; c.mensagens += Number(t.total_mensagens || 1); if (t.assunto) c.motivos.add(nomeAssunto(t.assunto));
  });
  const recorrentes = Object.values(porCliente).filter((c) => c.atendimentos > 1 || c.mensagens > 2)
    .sort((a, b) => b.atendimentos - a.atendimentos || b.mensagens - a.mensagens);
  // incidentes no período
  const incid = noPeriodo(estado.incidentes || [], "incident_opened_at");
  // precisão medida (revisões) e confiança média da IA
  const p = r.precisao || {};
  const dims = [["assunto", "Assunto"], ["urgencia", "Urgência"], ["sentimento", "Sentimento"], ["equipe", "Equipe"]];
  const comIa = tickets.filter((t) => t.origem === "llm");
  const conf = dims.map(([k, rot]) => {
    const v = comIa.map((t) => Number(t["conf_" + k])).filter((x) => !Number.isNaN(x));
    return { rotulo: rot, n: v.length ? Math.round((v.reduce((a, b) => a + b, 0) / v.length) * 100) : 0 };
  });
  const precisaoMedida = p.revisados
    ? barrasGf(dims.map(([k, rot]) => { const v = Math.round(p.por_dimensao[k] ?? 0); return { rotulo: rot, n: v, cor: corLimiar(v) }; }), 0, "%")
      + `<div class="gf-sub">${p.revisados} triagens revisadas · IA ${pct(r.precisao_llm?.agregado)} · plano B ${pct(r.precisao_fallback?.agregado)}</div>`
    : `<p class="gf-vazio">Nenhuma triagem revisada ainda: a precisão aparece quando os atendentes confirmarem ou corrigirem a IA.</p>`;
  const periodoTxt = { 24: "nas últimas 24 h", 168: "nos últimos 7 dias", 720: "nos últimos 30 dias", 0: "no total" }[estado.periodo] || "";

  $("#gf-grade").innerHTML = [
    stat("Casos", total, periodoTxt),
    stat("Incidentes", incid.length, `${r.incidentes} ativo(s) agora`, incid.length ? "#f2495c" : "#73bf69"),
    stat("Precisão da triagem", p.revisados ? pct(p.agregado) : "—", p.revisados ? `${p.revisados} revisadas` : "sem revisões ainda", corLimiar(p.agregado)),
    stat("Clientes que voltaram", recorrentes.length, total ? `${Math.round((recorrentes.length / Math.max(1, Object.keys(porCliente).length)) * 100)}% dos clientes` : ""),
    painel("Principais motivos de contato", barrasGf(motivos.map((m, k) => ({ ...m, cor: CORES[k % CORES.length] })), total), "gf-largo"),
    painel("Casos ao longo do tempo", total ? serieTemporal(tickets, motivos.slice(0, 3).map((m) => m.chave).filter(Boolean)) : `<p class="gf-vazio">Sem dados no período.</p>`, "gf-largo"),
    painel("Incidentes de contato", incid.length ? `<table class="gf-tabela"><thead><tr><th>Assunto</th><th>Mensagens</th><th>Aberto</th><th>Situação</th></tr></thead><tbody>
      ${incid.map((g) => `<tr><td><i class="gf-ponto" style="background:#f2495c"></i>${esc(nomeAssunto(g.assunto_predominante))}</td><td>${g.size}</td>
        <td>${esc(hora(g.incident_opened_at))}</td><td>${esc(g.status)}</td></tr>`).join("")}</tbody></table>`
      : `<p class="gf-vazio">Nenhum incidente no período.</p>`, "gf-largo"),
    painel("Prazos (SLA) em risco", htmlPrazos(r.prazos_em_risco || []), "gf-largo"),
    painel("Precisão da triagem (revisões)", precisaoMedida),
    painel("Confiança média da IA", comIa.length ? barrasGf(conf.map((c) => ({ ...c, cor: corLimiar(c.n) })), 0, "%") + `<div class="gf-sub">${comIa.length} triagens feitas pela IA</div>`
      : `<p class="gf-vazio">Sem triagens da IA no período.</p>`),
    painel("Clientes recorrentes", recorrentes.length ? `<table class="gf-tabela"><thead><tr><th>Cliente</th><th>Atendimentos</th><th>Mensagens</th><th>Motivos</th></tr></thead><tbody>
      ${recorrentes.slice(0, 8).map((c) => `<tr><td>${esc(contato(c.cliente).nome)}</td><td>${c.atendimentos}</td><td>${c.mensagens}</td>
        <td>${esc([...c.motivos].join(", ") || "—")}</td></tr>`).join("")}</tbody></table>`
      : `<p class="gf-vazio">Nenhum cliente voltou no período.</p>`, "gf-largo"),
  ].join("");
  $("#gf-atualizado").textContent = `Atualizado ${new Date().toLocaleTimeString("pt-BR")}`;
}

// ---------------------------------------------------------------- relatórios: problemas e ocorrências (ADR-020)
async function carregarProblemas() {
  try {
    estado.problemas = await api("/problemas");
    renderProblemas();
  } catch (e) {
    $("#problema-status").textContent = `⚠ ${e.message}`;
  }
}

function renderProblemas() {
  const lista = estado.problemas || [];
  $("#lista-problemas").innerHTML = lista.length ? lista.map((p) => `
    <article class="card problema${p.status === "resolvido" ? " resolvido" : ""}" data-problema="${p.id}">
      <header class="problema-topo">
        <div><h3>${esc(p.titulo)}</h3>
          <div class="muted">${p.status === "resolvido" ? `✅ resolvido em ${esc(hora(p.resolvido_em))}` : "aberto"} · criado por ${esc(p.criado_por || "—")}</div></div>
        <div class="problema-contagem"><b>${p.total}</b><span>vez(es)</span><small>${p.clientes_distintos} cliente(s)</small></div>
      </header>
      <p class="problema-carac">${esc(p.caracteristicas)}</p>
      <table class="tabela ocorrencias"><thead><tr><th>Cliente (identificação)</th><th>Atendimento</th><th>Quando</th><th>Registrado por</th><th></th></tr></thead>
        <tbody>${p.ocorrencias.map((o) => `<tr><td>${esc(o.cliente_id)}${o.observacao ? `<div class="muted">${esc(o.observacao)}</div>` : ""}</td>
          <td>${o.ticket_id ? `#${o.ticket_id}` : "—"}</td><td>${esc(hora(o.created_at))}</td><td>${esc(o.registrado_por || "—")}</td>
          <td><button type="button" class="btn pequeno" data-remover-ocorrencia="${o.id}" title="Remover esta ocorrência">✕</button></td></tr>`).join("")
          || `<tr><td colspan="5" class="muted">Nenhuma ocorrência registrada ainda.</td></tr>`}</tbody></table>
      <form class="form-ocorrencia-rapida">
        <input name="cliente_id" maxlength="190" required placeholder="Identificação do cliente (telefone, e-mail ou protocolo)">
        <input name="ticket_id" type="number" min="1" placeholder="Nº do atendimento (opcional)">
        <button type="submit" class="btn">+ Ocorrência</button>
        <button type="button" class="btn" data-status="${p.status === "resolvido" ? "aberto" : "resolvido"}">${p.status === "resolvido" ? "↺ Reabrir" : "✓ Marcar resolvido"}</button>
      </form>
    </article>`).join("") : `<p class="card muted">Nenhum problema registrado. Crie o primeiro acima ou pelo botão "📋 Registrar problema" de um atendimento.</p>`;
}

async function acaoProblema(ev) {
  const art = ev.target.closest("[data-problema]");
  if (!art) return;
  const id = art.dataset.problema;
  try {
    const rem = ev.target.closest("[data-remover-ocorrencia]");
    if (rem) await api(`/problemas/${id}/ocorrencias/${rem.dataset.removerOcorrencia}`, { method: "DELETE" });
    const st = ev.target.closest("button[data-status]");
    if (st) await api(`/problemas/${id}`, { method: "PATCH", body: JSON.stringify({ status: st.dataset.status }) });
    if (rem || st) carregarProblemas();
  } catch (e) {
    $("#problema-status").textContent = `⚠ ${e.message}`;
  }
}

async function ocorrenciaRapida(form) {
  const id = form.closest("[data-problema]").dataset.problema;
  const d = Object.fromEntries(new FormData(form));
  try {
    await api(`/problemas/${id}/ocorrencias`, { method: "POST", body: JSON.stringify({ cliente_id: d.cliente_id, ticket_id: d.ticket_id ? Number(d.ticket_id) : null }) });
    carregarProblemas();
  } catch (e) {
    $("#problema-status").textContent = `⚠ ${e.message}`;
  }
}

async function criarProblema(form) {
  const d = Object.fromEntries(new FormData(form));
  try {
    await api("/problemas", { method: "POST", body: JSON.stringify(d) });
    form.reset();
    $("#problema-status").textContent = "✅ Problema criado. Registre as ocorrências abaixo.";
    carregarProblemas();
  } catch (e) {
    $("#problema-status").textContent = `⚠ ${e.message}`;
  }
}

// Identificação do cliente para o relatório: o telefone (WhatsApp), o usuário ou o contato; senão, o protocolo.
function identificacao(t) {
  const bruto = (t.cliente || "").trim();
  const fone = bruto.match(/\((\+?\d{8,15})\)$/);
  if (fone) return fone[1];
  return bruto.replace(/^instagram:/i, "@") || `protocolo #${t.ticket_id}`;
}

async function abrirRegistroProblema(id) {
  const t = estado.tickets.find((x) => x.ticket_id === id);
  if (!t) return;
  try { estado.problemas = await api("/problemas"); } catch { estado.problemas = estado.problemas || []; }
  const f = $("#form-ocorrencia");
  const abertos = (estado.problemas || []).filter((p) => p.status === "aberto");
  f.problema_id.innerHTML = abertos.map((p) => `<option value="${p.id}">${esc(p.titulo)} (${p.total}×)</option>`).join("")
    + `<option value="novo">+ Novo problema…</option>`;
  f.querySelector(".novo-problema").hidden = abertos.length > 0;
  if (!abertos.length) f.problema_id.value = "novo";
  f.cliente_id.value = identificacao(t);
  f.ticket_id.value = t.ticket_id;
  f.observacao.value = "";
  f.titulo.value = ""; f.caracteristicas.value = t.assunto ? `Assunto: ${t.assunto}. ${t.texto}`.slice(0, 400) : (t.texto || "").slice(0, 400);
  $("#ocorrencia-status").textContent = "";
  $("#dlg-ocorrencia").showModal();
}

async function registrarOcorrencia(f) {
  const st = $("#ocorrencia-status");
  try {
    let pid = f.problema_id.value;
    if (pid === "novo") pid = (await api("/problemas", { method: "POST", body: JSON.stringify({ titulo: f.titulo.value, caracteristicas: f.caracteristicas.value }) })).id;
    const p = await api(`/problemas/${pid}/ocorrencias`, { method: "POST", body: JSON.stringify({
      cliente_id: f.cliente_id.value, ticket_id: Number(f.ticket_id.value) || null, observacao: f.observacao.value || null }) });
    $("#dlg-ocorrencia").close();
    $("#status").textContent = `📋 Registrado em "${p.titulo}" (${p.total}× até agora).`;
    if (estado.pagina === "relatorios") carregarProblemas();
  } catch (e) {
    st.textContent = `⚠ ${e.message}`;
  }
}

// ---------------------------------------------------------------- acesso (chave de API)
function nomeAtendente() {
  return $("#atendente")?.value.trim() || "Atendente";
}

async function entrar() {
  try {
    estado.dominio = await api("/dominio");
  } catch (e) {
    return sair(e instanceof NaoAutorizado ? "Chave inválida." : `Servidor indisponível: ${e.message}`);
  }
  $("#login").hidden = true;
  $("#app").hidden = false;
  $("#plantao").checked = estado.plantao;
  renderFiltros();
  if (estado.plantao && "Notification" in window && Notification.permission === "default") Notification.requestPermission();
  const ultima = lerArmazenado(sessionStorage, "triagem.pagina");
  irPara(TITULOS[ultima] ? ultima : "atendimento");
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
  $("#atendente").value = lerArmazenado(localStorage, "triagem.atendente") || "Atendente";
  $("#atendente").addEventListener("change", (ev) => gravarArmazenado(localStorage, "triagem.atendente", ev.target.value.trim()));
  $("#sair").addEventListener("click", () => sair());
  $("#plantao").addEventListener("change", (ev) => mudarPlantao(ev.target.checked));
  $("#form-problema").addEventListener("submit", (ev) => { ev.preventDefault(); criarProblema(ev.target); });
  document.querySelectorAll(".gf-periodo button").forEach((b) => b.setAttribute("aria-pressed", String(Number(b.dataset.periodo) === estado.periodo)));
  $("#gf-grade").addEventListener("click", (ev) => {
    const linha = ev.target.closest("[data-abrir]");
    if (!linha) return;
    irPara("atendimento");
    abrirTicket(Number(linha.dataset.abrir));
  });
  $(".gf-periodo").addEventListener("click", (ev) => {
    const b = ev.target.closest("button[data-periodo]");
    if (!b) return;
    estado.periodo = Number(b.dataset.periodo);
    gravarArmazenado(localStorage, "triagem.periodo", String(estado.periodo));
    document.querySelectorAll(".gf-periodo button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    renderRecorrencia();
  });
  $("#lista-problemas").addEventListener("click", acaoProblema);
  $("#lista-problemas").addEventListener("submit", (ev) => { ev.preventDefault(); ocorrenciaRapida(ev.target); });
  const dlg = $("#dlg-ocorrencia");
  dlg.addEventListener("click", (ev) => { if (ev.target.closest("[data-fechar]")) dlg.close(); });
  $("#form-ocorrencia").problema_id.addEventListener("change", (ev) => {
    $("#form-ocorrencia .novo-problema").hidden = ev.target.value !== "novo";
  });
  $("#form-ocorrencia").addEventListener("submit", (ev) => { ev.preventDefault(); registrarOcorrencia(ev.target); });
  $(".menu").addEventListener("click", (ev) => {
    const b = ev.target.closest("button[data-pagina]");
    if (b) irPara(b.dataset.pagina);
  });

  $("#busca").addEventListener("input", renderCartoes);
  $("#filtro-equipe").value = estado.equipe;
  $("#filtro-equipe").addEventListener("change", (ev) => {
    estado.equipe = ev.target.value;
    gravarArmazenado(localStorage, "triagem.equipe", estado.equipe);
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
  detalhe.addEventListener("input", () => { estado.editando = true; });
  detalhe.addEventListener("toggle", (ev) => {
    if (ev.target.classList?.contains("triagem-faixa")) estado.triagemAberta = ev.target.open;
  }, true);
  detalhe.addEventListener("submit", (ev) => {
    if (ev.target.id === "form-triagem") {
      ev.preventDefault();
      salvarTriagem(ev.target);
    }
    if (ev.target.id === "form-chat") {
      ev.preventDefault();
      enviarChat(ev.target);
    }
  });
  // Enter envia a resposta do chat; Shift+Enter quebra a linha.
  detalhe.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter" && !ev.shiftKey && ev.target.closest("#form-chat")) {
      ev.preventDefault();
      ev.target.form.requestSubmit();
    }
  });


  if (estado.chave) entrar(); else sair();
});
