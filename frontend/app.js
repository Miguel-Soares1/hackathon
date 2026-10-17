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
const TITULOS = { dashboard: "Dashboard", atendimento: "Atendimento", incidentes: "Incidentes", correcoes: "Correções", atendimentos: "Atendimentos" };
const DIMS = ["assunto", "urgencia", "sentimento", "equipe"];
const nomeIdioma = (c) => (estado.dominio?.idiomas?.[c] ? `${estado.dominio.idiomas[c]} (${c})` : c || "—");

const estado = {
  chave: lerArmazenado(sessionStorage, "triagem.chave"),
  dominio: null,
  tickets: [],
  resumo: null,
  pagina: "dashboard",
  lista: "espera",
  canal: "",
  selecionado: null,
  editando: false, // não redesenhar o detalhe enquanto o atendente digita
  triagemAberta: false,
  timer: null,
  midiaUrls: {}, // id da mídia -> URL local (blob) já baixada, para não baixar a cada atualização
  anexos: [], // imagem/áudio a enviar na resposta do chat: { tipo, mime, dados_base64, nome, url }
  gravador: null,
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
      api("/tickets?limite=1000"),
      api("/metricas"),
      api(`/incidentes?todos_os_grupos=${$("#todos-grupos").checked}`),
    ]);
    estado.tickets = tickets;
    estado.resumo = resumo;
    renderKpis();
    renderAlertas(incidentes.filter((g) => g.status === "incidente"));
    renderMetricas();
    renderCartoes();
    renderRelatorio();
    if (!estado.editando && !tocandoAudio() && !estado.anexos.length && !estado.gravador) renderDetalhe();
    else if (estado.selecionado) carregarConversa(estado.selecionado); // a conversa continua atualizando
    renderIncidentes(incidentes);
    if (estado.pagina === "correcoes") renderCorrecoes(await api("/correcoes"));
    const agora = `Atualizado às ${new Date().toLocaleTimeString("pt-BR")}`;
    $("#status").textContent = agora;
    $("#hero-hora").textContent = agora;
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
const ICONES = {
  relogio: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  balao: '<path d="M21 11.5a8.4 8.4 0 0 1-12.3 7.4L3 21l2.1-5.7A8.4 8.4 0 1 1 21 11.5z"/>',
  xis: '<circle cx="12" cy="12" r="9"/><path d="m15 9-6 6M9 9l6 6"/>',
  check: '<circle cx="12" cy="12" r="9"/><path d="m8 12.5 2.7 2.5L16 9.5"/>',
  alerta: '<path d="M10.3 3.9 2.4 18a2 2 0 0 0 1.7 3h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4M12 17h.01"/>',
  sirene: '<path d="M7 18v-6a5 5 0 0 1 10 0v6"/><path d="M5 21h14v-3H5zM12 3v2M4.2 6.2l1.4 1.4M19.8 6.2l-1.4 1.4"/>',
  medidor: '<path d="M3.5 17a9 9 0 1 1 17 0"/><path d="m12 13 4-4"/>',
  alvo: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>',
};
const icone = (n) => `<svg viewBox="0 0 24 24" aria-hidden="true">${ICONES[n]}</svg>`;

function cardInd(ic, rotulo, valor, lista) {
  const attrs = lista ? ` role="button" tabindex="0" data-ir-lista="${lista}" title="Abrir em Atendimento"` : "";
  return `<div class="card-ind${lista ? " clicavel" : ""}"${attrs}><div class="card-icone">${icone(ic)}</div>
    <div><div class="card-rotulo">${esc(rotulo)}</div><div class="card-valor">${esc(valor)}</div></div></div>`;
}

// Situação de cada cliente: em espera (falta responder), em atendimento (respondido e em aberto), cancelado, encerrado.
function situacao(t) {
  if (t.desfecho) return t.desfecho === "cancelado" ? "cancelado" : "encerrado";
  return aguardando(t) ? "espera" : "atendimento";
}

function renderKpis() {
  const n = { espera: 0, atendimento: 0, cancelado: 0, encerrado: 0 };
  estado.tickets.forEach((t) => { n[situacao(t)] += 1; });
  $("#cards-atendimento").innerHTML = [
    cardInd("relogio", "Clientes em espera", n.espera, "espera"),
    cardInd("balao", "Clientes em atendimento", n.atendimento, "atendimento"),
    cardInd("xis", "Clientes cancelados", n.cancelado, "finalizados"),
    cardInd("check", "Clientes encerrados", n.encerrado, "finalizados"),
  ].join("");
  const r = estado.resumo;
  $("#kpis").innerHTML = [
    cardInd("alerta", "Prazos em risco", r.prazos_em_risco.length),
    cardInd("sirene", "Incidentes", r.incidentes),
    cardInd("medidor", `SLI (meta ${r.sli.alvo_pct.toFixed(0)}%)`, pct(r.sli.sli_pct)),
    cardInd("alvo", `Precisão da IA (${r.precisao.revisados} rev.)`, pct(r.precisao.agregado)),
  ].join("");
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
  const base = estado.canal ? estado.tickets.filter((t) => chaveCanal(t.canal) === estado.canal) : estado.tickets;
  const todos = q
    ? base.filter((t) => [t.cliente, t.canal, t.texto, t.ultima_texto, t.assunto].join(" ").toLowerCase().includes(q))
    : base;
  const espera = todos.filter((t) => situacao(t) === "espera").sort((a, b) => (ORDEM_URGENCIA[a.urgencia] ?? 4) - (ORDEM_URGENCIA[b.urgencia] ?? 4)
    || (b.sla.consumido_pct ?? 0) - (a.sla.consumido_pct ?? 0));
  const atendimento = todos.filter((t) => situacao(t) === "atendimento");
  const finalizados = todos.filter((t) => t.desfecho);
  return { espera, atendimento, finalizados };
}

// O texto vem do cliente (não confiável): tudo passa por esc() (threat model T19).
function cartao(t) {
  const c = contato(t);
  const ultimo = t.ultima_texto || t.texto || "";
  const marcas = [];
  if (t.desfecho) marcas.push(selo(t.desfecho, t.desfecho === "cancelado" ? "u-critica" : "s-no_prazo"));
  else {
    if (t.first_response_at && aguardando(t)) marcas.push(selo("nova mensagem", "s-novo"));
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
  $("#qtd-atendimento").textContent = listas.atendimento.length;
  $("#qtd-finalizados").textContent = listas.finalizados.length;
  const badge = $("#badge-espera");
  const totalEspera = estado.tickets.filter((t) => situacao(t) === "espera").length;
  badge.hidden = !totalEspera;
  badge.textContent = totalEspera;
  const itens = (listas[estado.lista] || listas.espera).slice(0, 80);
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
    : `<button type="button" class="btn pequeno ok" data-acao="encerrar">✓ Encerrar</button><button type="button" class="btn pequeno perigo" data-acao="cancelar">✕ Cancelar</button>`;
  // Conversa (ADR-016): a primeira mensagem do cliente aparece até a conversa carregar.
  painel.innerHTML = `
    <div class="cab-chat">${avatar(t, true)}
      <div class="cab-info"><div class="nome">${esc(c.nome)}</div>
        <div class="sub">${tagCanal(t.canal)}${c.detalhe ? `<span>${esc(c.detalhe)}</span>` : ""}<span>#${t.ticket_id}</span></div></div>
      <div class="cab-acoes">${acoes}</div></div>
    <div id="conversa" class="conversa" aria-live="polite">${bolha({ direcao: "entrada", autor: t.cliente, texto: t.texto, created_at: t.received_at })}</div>
    ${renderMidias(t)}
    <form id="form-chat" class="form-chat"${t.desfecho ? " hidden" : ""}>
      ${classificado && t.resposta_sugerida ? `<button type="button" class="btn sugestao pequeno" data-acao="sugestao">💡 Usar resposta sugerida pela IA</button>` : ""}
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
    <details class="triagem" id="triagem" ${estado.triagemAberta ? "open" : ""}>
      <summary>Triagem da IA${classificado ? ` <span class="resumo-triagem">${esc(t.assunto || "")} · ${esc((t.equipe || "").replace("_", " "))}</span>` : ""}</summary>
      <div class="corpo">${classificado ? triagem(t) : `<p class="muted">⏳ A IA ainda está ${t.midias?.length ? "lendo as mídias e " : ""}classificando este atendimento.</p>`}</div>
    </details>`;
  carregarConversa(t.ticket_id);
  carregarMidias(t);
  renderAnexos();
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
    if (e instanceof NaoAutorizado) return sair("Chave inválida ou expirada.");
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
    await api(`/tickets/${id}/mensagens`, { method: "POST", body: JSON.stringify({ texto, midias, autor: $("#atendente").value.trim() || "Atendente" }) });
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

// <img>/<audio> não mandam o header X-API-Key: baixa com a chave e mostra a partir de uma URL local (blob).
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
    if (acao === "encerrar" || acao === "cancelar") {
      const desfecho = acao === "encerrar" ? "encerrado" : "cancelado";
      await api(`/tickets/${id}/encerrar`, { method: "POST", body: JSON.stringify({ desfecho }) });
    }
    if (acao === "reabrir") await api(`/tickets/${id}/reabrir`, { method: "POST" });
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
  $("#titulo").hidden = pagina === "dashboard" || pagina === "atendimentos";
  gravarArmazenado(sessionStorage, "triagem.pagina", pagina);
  if (pagina === "correcoes") api("/correcoes").then(renderCorrecoes).catch((e) => alertaStatus(e.message));
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
  renderCartoes();
  renderDetalhe();
}

// ---------------------------------------------------------------- atendimentos: relatório de controle
const ROTULO_SITUACAO = { espera: "Em Espera", atendimento: "Em Atendimento", encerrado: "Finalizado", cancelado: "Cancelado" };
const ROTULO_PERIODO = { hoje: "Hoje", 7: "Últimos 7 dias", 30: "Últimos 30 dias", tudo: "Todo o período", personalizado: "Personalizado" };
const rel = {
  status: "",
  busca: "",
  filtros: { periodo: "hoje", de: "", ate: "", canal: "", equipe: "", urgencia: "" },
  fixados: new Set((() => { try { return JSON.parse(lerArmazenado(localStorage, "triagem.fixados") || "[]"); } catch { return []; } })()),
};
const diaLocal = (iso) => {
  if (!iso) return "";
  const d = new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : iso + "Z");
  return d.toLocaleDateString("en-CA", { timeZone: "America/Sao_Paulo" }); // AAAA-MM-DD
};
const hojeLocal = () => new Date().toLocaleDateString("en-CA", { timeZone: "America/Sao_Paulo" });
const somarDias = (dia, n) => { const d = new Date(dia + "T12:00:00Z"); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10); };
const protocolo = (t) => diaLocal(t.received_at).replaceAll("-", "") + String(t.ticket_id).padStart(6, "0");
const EQUIPES = { financeiro: "Financeiro", suporte_tecnico: "Suporte técnico", engenharia: "Engenharia", retencao: "Retenção", atendimento: "Atendimento" };
const nomeEquipe = (e) => (e ? EQUIPES[e] || e.replace("_", " ").replace(/^./, (c) => c.toUpperCase()) : "A definir");

function intervalo() {
  const f = rel.filtros;
  const hoje = hojeLocal();
  if (f.periodo === "hoje") return [hoje, hoje];
  if (f.periodo === "7") return [somarDias(hoje, -6), hoje];
  if (f.periodo === "30") return [somarDias(hoje, -29), hoje];
  if (f.periodo === "personalizado") return [f.de || "0000-00-00", f.ate || "9999-99-99"];
  return null;
}

function relFiltrados() {
  const f = rel.filtros;
  const faixa = intervalo();
  const q = rel.busca.trim().toLowerCase();
  const qDig = q.replace(/\D/g, "");
  const base = estado.tickets.filter((t) => {
    if (faixa) { const d = diaLocal(t.received_at); if (d < faixa[0] || d > faixa[1]) return false; }
    if (f.canal && chaveCanal(t.canal) !== f.canal) return false;
    if (f.equipe && t.equipe !== f.equipe) return false;
    if (f.urgencia && t.urgencia !== f.urgencia) return false;
    if (q) {
      const c = contato(t);
      const texto = [c.nome, c.detalhe, t.cliente, `#${t.ticket_id}`, protocolo(t)].join(" ").toLowerCase();
      const digitos = [c.detalhe, t.cliente, protocolo(t), String(t.ticket_id)].join(" ").replace(/\D/g, "");
      if (!texto.includes(q) && !(qDig.length >= 3 && digitos.includes(qDig))) return false;
    }
    return true;
  });
  return base;
}

function linhaRel(t) {
  const c = contato(t);
  const sit = situacao(t);
  const fixado = rel.fixados.has(t.ticket_id);
  const fim = t.desfecho ? ` • ${t.desfecho === "cancelado" ? "Cancelado" : "Encerrado"}: ${esc(hora(t.encerrado_em))}` : "";
  return `<div class="rel-linha${fixado ? " fixado" : ""}" data-id="${t.ticket_id}" tabindex="0" role="button" aria-label="Abrir atendimento de ${esc(c.nome)}">
    <div class="rel-info">
      <span class="rel-nome${/[@.]/.test(c.nome) ? " sem-caixa" : ""}">${esc(c.nome)}</span>
      ${c.detalhe ? `<span class="rel-contato">${esc(c.detalhe)}</span>` : ""}
      ${tagCanal(t.canal)}
      <span class="rel-dados">Protocolo: ${esc(protocolo(t))} • Status: <b class="st st-${sit}">${esc(ROTULO_SITUACAO[sit])}</b> • Time: ${esc(nomeEquipe(t.equipe))} • Início: ${esc(hora(t.received_at))}${fim}</span>
    </div>
    <button type="button" class="btn icone fixar" data-fixar="${t.ticket_id}" aria-pressed="${fixado}" title="${fixado ? "Desafixar" : "Fixar no topo"}" aria-label="${fixado ? "Desafixar" : "Fixar no topo"}">
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 3h6l-1 6 4 3v2H6v-2l4-3zM12 14v7"/></svg></button>
  </div>`;
}

function renderRelatorio() {
  if (!estado.resumo) return;
  const base = relFiltrados();
  const cont = { "": base.length, espera: 0, atendimento: 0, encerrado: 0, cancelado: 0 };
  base.forEach((t) => { cont[situacao(t)] += 1; });
  document.querySelectorAll(".rel-abas [data-status] .n").forEach((n) => { n.textContent = cont[n.parentElement.dataset.status]; });
  const lista = (rel.status ? base.filter((t) => situacao(t) === rel.status) : base)
    .sort((a, b) => (rel.fixados.has(b.ticket_id) - rel.fixados.has(a.ticket_id)) || b.ticket_id - a.ticket_id);
  $("#rel-contagem").textContent = `Atendimentos: ${lista.length} de ${estado.tickets.length}.`;
  $("#rel-linhas").innerHTML = lista.slice(0, 300).map(linhaRel).join("")
    || `<div class="vazio">Nenhum atendimento com esses filtros.</div>`;
  renderChips();
}

function renderChips() {
  const f = rel.filtros;
  const chips = [];
  if (f.periodo !== "tudo") {
    const txt = f.periodo === "personalizado" ? `${f.de || "início"} a ${f.ate || "hoje"}` : ROTULO_PERIODO[f.periodo];
    chips.push(["periodo", `Período: ${txt}`]);
  }
  if (f.canal) chips.push(["canal", `Canal: ${CANAIS[f.canal].rotulo}`]);
  if (f.equipe) chips.push(["equipe", `Time: ${nomeEquipe(f.equipe)}`]);
  if (f.urgencia) chips.push(["urgencia", `Urgência: ${f.urgencia}`]);
  if (rel.busca) chips.push(["busca", `Busca: ${rel.busca}`]);
  $("#rel-chips").innerHTML = chips.map(([k, txt]) => `<span class="chip-filtro">${esc(txt)}<button type="button" data-tirar="${k}" aria-label="Remover filtro ${esc(txt)}">×</button></span>`).join("");
  $("#rel-qtd-filtros").textContent = chips.filter(([k]) => k !== "busca").length;
}

function exportarCsv() {
  const lista = (rel.status ? relFiltrados().filter((t) => situacao(t) === rel.status) : relFiltrados());
  const cab = ["Protocolo", "Cliente", "Contato", "Canal", "Status", "Time", "Assunto", "Urgência", "Início", "1ª resposta", "Finalizado em", "Prazo"];
  const q = (v) => `"${String(v ?? "").replaceAll('"', '""')}"`;
  const linhas = lista.map((t) => {
    const c = contato(t);
    return [protocolo(t), c.nome, c.detalhe, CANAIS[chaveCanal(t.canal)].rotulo, ROTULO_SITUACAO[situacao(t)], nomeEquipe(t.equipe),
      t.assunto || "", t.urgencia || "", hora(t.received_at), hora(t.first_response_at), hora(t.encerrado_em),
      ROTULO_SLA_CURTO[t.sla.estado] || t.sla.estado].map(q).join(";");
  });
  const blob = new Blob(["﻿" + [cab.map(q).join(";"), ...linhas].join("\r\n")], { type: "text/csv;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `atendimentos-${hojeLocal()}.csv`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

function abrirNoAtendimento(id) {
  const t = estado.tickets.find((x) => x.ticket_id === id);
  if (!t) return;
  const sit = situacao(t);
  estado.lista = sit === "espera" ? "espera" : sit === "atendimento" ? "atendimento" : "finalizados";
  estado.canal = "";
  $("#busca").value = "";
  document.querySelectorAll(".abas-lista button").forEach((x) => x.setAttribute("aria-selected", String(x.dataset.lista === estado.lista)));
  document.querySelectorAll("#filtro-canal button").forEach((x) => x.setAttribute("aria-pressed", String(x.dataset.canal === "")));
  irPara("atendimento");
  abrirTicket(id);
}

function ligarRelatorio() {
  const modal = $("#rel-modal");
  const form = $("#rel-modal-form");
  const equipes = form.equipe;
  const datas = () => { form.querySelector(".rel-datas").hidden = form.periodo.value !== "personalizado"; };
  form.periodo.addEventListener("change", datas);
  $("#rel-config").addEventListener("click", () => {
    if (equipes.options.length === 1 && estado.dominio) {
      estado.dominio.equipes.forEach((e) => equipes.add(new Option(nomeEquipe(e), e)));
    }
    Object.entries(rel.filtros).forEach(([k, v]) => { if (form[k]) form[k].value = v; });
    datas();
    modal.showModal();
  });
  $("#rel-modal-cancelar").addEventListener("click", () => modal.close());
  form.addEventListener("submit", () => {
    Object.keys(rel.filtros).forEach((k) => { if (form[k]) rel.filtros[k] = form[k].value; });
    renderRelatorio();
  });
  $("#rel-busca-form").addEventListener("submit", (ev) => { ev.preventDefault(); rel.busca = $("#rel-busca").value.trim(); renderRelatorio(); });
  $("#rel-busca").addEventListener("input", (ev) => { rel.busca = ev.target.value.trim(); renderRelatorio(); });
  $(".rel-abas").addEventListener("click", (ev) => {
    const b = ev.target.closest("button[data-status]");
    if (!b) return;
    rel.status = b.dataset.status;
    document.querySelectorAll(".rel-abas [data-status]").forEach((x) => x.setAttribute("aria-selected", String(x === b)));
    renderRelatorio();
  });
  $("#rel-limpar").addEventListener("click", () => {
    rel.filtros = { periodo: "tudo", de: "", ate: "", canal: "", equipe: "", urgencia: "" };
    rel.busca = "";
    $("#rel-busca").value = "";
    renderRelatorio();
  });
  $("#rel-chips").addEventListener("click", (ev) => {
    const b = ev.target.closest("[data-tirar]");
    if (!b) return;
    const k = b.dataset.tirar;
    if (k === "busca") { rel.busca = ""; $("#rel-busca").value = ""; }
    else if (k === "periodo") rel.filtros.periodo = "tudo";
    else rel.filtros[k] = "";
    renderRelatorio();
  });
  $("#rel-exportar").addEventListener("click", exportarCsv);
  const linhas = $("#rel-linhas");
  linhas.addEventListener("click", (ev) => {
    const pin = ev.target.closest("[data-fixar]");
    if (pin) {
      const id = Number(pin.dataset.fixar);
      if (rel.fixados.has(id)) rel.fixados.delete(id); else rel.fixados.add(id);
      gravarArmazenado(localStorage, "triagem.fixados", JSON.stringify([...rel.fixados]));
      return renderRelatorio();
    }
    const l = ev.target.closest(".rel-linha[data-id]");
    if (l) abrirNoAtendimento(Number(l.dataset.id));
  });
  linhas.addEventListener("keydown", (ev) => {
    const l = ev.target.closest(".rel-linha[data-id]");
    if (l && ev.target === l && (ev.key === "Enter" || ev.key === " ")) { ev.preventDefault(); abrirNoAtendimento(Number(l.dataset.id)); }
  });
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
  const salva = lerArmazenado(sessionStorage, "triagem.pagina");
  irPara(TITULOS[salva] ? salva : "dashboard");
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
  $("#filtro-canal").addEventListener("click", (ev) => {
    const b = ev.target.closest("button[data-canal]");
    if (!b) return;
    estado.canal = b.dataset.canal;
    document.querySelectorAll("#filtro-canal button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    renderCartoes();
  });
  const irLista = (lista) => {
    estado.lista = lista;
    document.querySelectorAll(".abas-lista button").forEach((x) => x.setAttribute("aria-selected", String(x.dataset.lista === lista)));
    renderCartoes();
    irPara("atendimento");
  };
  $("#cards-atendimento").addEventListener("click", (ev) => {
    const c = ev.target.closest("[data-ir-lista]");
    if (c) irLista(c.dataset.irLista);
  });
  $("#cards-atendimento").addEventListener("keydown", (ev) => {
    const c = ev.target.closest("[data-ir-lista]");
    if (c && (ev.key === "Enter" || ev.key === " ")) { ev.preventDefault(); irLista(c.dataset.irLista); }
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
    }
  });
  // Enter envia a resposta do chat; Shift+Enter quebra a linha.
  detalhe.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter" && !ev.shiftKey && ev.target.closest("#form-chat")) {
      ev.preventDefault();
      ev.target.form.requestSubmit();
    }
  });

  ligarRelatorio();

  if (estado.chave) entrar(); else sair();
});
