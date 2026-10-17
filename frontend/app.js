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
const TITULOS = { dashboard: "Dashboard", atendimento: "Atendimento", incidentes: "Incidentes", correcoes: "Correções",
  nova: "Simular mensagem", admin: "Administração", conta: "Minha conta" };
const DIMS = ["assunto", "urgencia", "sentimento", "equipe"];
const nomeIdioma = (c) => (estado.dominio?.idiomas?.[c] ? `${estado.dominio.idiomas[c]} (${c})` : c || "—");

const estado = {
  // Sessão do usuário (ADR-018): "manter conectado" guarda no localStorage (30 dias); senão só nesta aba.
  token: lerArmazenado(localStorage, "triagem.sessao") || lerArmazenado(sessionStorage, "triagem.sessao"),
  usuario: null,
  dominio: null,
  tickets: [],
  resumo: null,
  pagina: "dashboard",
  lista: "espera",
  selecionado: null,
  editando: false, // não redesenhar o detalhe enquanto o atendente digita
  triagemAberta: false,
  timer: null,
  anexos: [], // mídias a enviar em "Simular mensagem": { tipo, mime, dados_base64, nome, url }
  gravador: null,
  midiaUrls: {}, // id da mídia -> URL local (blob) já baixada, para não baixar a cada atualização
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
    if (!estado.editando && !tocandoAudio()) renderDetalhe();
    else if (estado.selecionado) carregarConversa(estado.selecionado); // a conversa continua atualizando
    renderIncidentes(incidentes);
    if (estado.pagina === "correcoes") renderCorrecoes(await api("/correcoes"));
    $("#status").textContent = `Atualizado às ${new Date().toLocaleTimeString("pt-BR")}`;
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
    <div class="msg">${iconesMidia(t)}${esc(ultimo.length > 110 ? ultimo.slice(0, 110) + "…" : ultimo)}</div>
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
    ${renderMidias(t)}
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
      <div class="corpo">${classificado ? triagem(t)
        : `<p class="muted">⏳ A IA ainda está ${t.midias?.length ? "lendo as mídias e " : ""}classificando este atendimento.</p>`}</div>
    </details>`;
  carregarConversa(t.ticket_id);
  carregarMidias(t);
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
    if (e instanceof NaoAutorizado) return sair("Sua sessão expirou. Entre de novo.");
    alertaStatus(e.message);
  }
}

async function enviarChat(form) {
  const id = estado.selecionado;
  const texto = form.texto.value.trim();
  if (!texto) return;
  try {
    await api(`/tickets/${id}/mensagens`, { method: "POST", body: JSON.stringify({ texto }) }); // assina quem está logado
    form.texto.value = "";
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

// <img>/<audio> não mandam o header de autorização: baixa com a sessão e mostra a partir de uma URL local (blob).
async function carregarMidias(t) {
  for (const m of t.midias || []) {
    try {
      if (!estado.midiaUrls[m.id]) {
        const resp = await fetch(`/tickets/${t.ticket_id}/midias/${m.id}`, { headers: { Authorization: `Bearer ${estado.token}` } });
        if (!resp.ok) throw new Error(`erro ${resp.status}`);
        estado.midiaUrls[m.id] = URL.createObjectURL(await resp.blob());
      }
      const alvo = document.querySelector(`[data-midia="${m.id}"]`);
      if (!alvo) continue; // o atendente trocou de ticket enquanto baixava
      const url = estado.midiaUrls[m.id];
      alvo.innerHTML = m.tipo === "audio" ? `<audio controls preload="metadata" src="${url}"></audio>`
        : `<a href="${url}" target="_blank" rel="noopener"><img src="${url}" alt="Foto enviada pelo cliente"></a>`;
    } catch (e) {
      const alvo = document.querySelector(`[data-midia="${m.id}"] .muted`);
      if (alvo) alvo.textContent = `não foi possível carregar (${e.message})`;
    }
  }
}

// ---------------------------------------------------------------- anexos de "Simular mensagem"
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
  const st = $("#nova-status");
  const mime = blob.type || "";
  const tipo = mime.startsWith("image/") ? "imagem" : mime.startsWith("audio/") ? "audio" : null;
  if (!tipo) return void (st.textContent = `⚠ ${nome}: envie uma foto (JPG, PNG, WebP) ou um áudio.`);
  if (estado.anexos.length >= MAX_ANEXOS) return void (st.textContent = `⚠ No máximo ${MAX_ANEXOS} anexos por mensagem.`);
  if (blob.size > MAX_MB * 1024 * 1024) return void (st.textContent = `⚠ ${nome}: maior que ${MAX_MB} MB.`);
  estado.anexos.push({ tipo, mime, nome, dados_base64: await lerBase64(blob), url: URL.createObjectURL(blob) });
  st.textContent = "";
  renderAnexos();
}

function renderAnexos() {
  $("#lista-anexos").innerHTML = estado.anexos.map((a, i) => `<li class="anexo">
    ${a.tipo === "audio" ? `<audio controls src="${a.url}"></audio>` : `<img src="${a.url}" alt="">`}
    <span class="muted">${esc(a.nome)}</span>
    <button type="button" class="btn" data-remover="${i}" aria-label="Remover ${esc(a.nome)}">Remover</button>
  </li>`).join("");
}

function limparAnexos() {
  estado.anexos.forEach((a) => URL.revokeObjectURL(a.url));
  estado.anexos = [];
  renderAnexos();
}

async function alternarGravacao() {
  const botao = $("#gravar");
  const st = $("#nova-status");
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
    botao.setAttribute("aria-pressed", "false");
    botao.textContent = "🎙 Gravar áudio";
    const blob = new Blob(pedacos, { type: gravador.mimeType || "audio/webm" });
    adicionarAnexo(blob, `gravação ${new Date().toLocaleTimeString("pt-BR")}`);
  };
  gravador.start();
  estado.gravador = gravador;
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
  if (estado.gravador) return void (st.textContent = "⚠ Pare a gravação antes de enviar.");
  if (dados.texto.trim().length < 3 && !estado.anexos.length) {
    return void (st.textContent = "⚠ Escreva uma mensagem (3+ caracteres) ou anexe uma foto ou áudio.");
  }
  dados.midias = estado.anexos.map(({ tipo, mime, dados_base64 }) => ({ tipo, mime, dados_base64 }));
  st.textContent = "Enviando…";
  try {
    const r = await api("/webhook/mensagens", { method: "POST", body: JSON.stringify(dados) });
    st.textContent = `✅ Ticket #${r.ticket_id} recebido. Veja em Atendimento → Em espera em instantes.`;
    form.texto.value = "";
    limparAnexos();
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
  if (pagina === "admin") carregarUsuarios();
}

function abrirTicket(id) {
  estado.selecionado = id;
  estado.editando = false;
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
  $("#menu-admin").hidden = u.papel !== "admin";
  $("#login").hidden = true;
  $("#app").hidden = false;
  const ultima = lerArmazenado(sessionStorage, "triagem.pagina") || "dashboard";
  irPara(ultima === "admin" && u.papel !== "admin" ? "dashboard" : ultima);
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

// ---------------------------------------------------------------- administração e minha conta
async function carregarUsuarios() {
  try {
    renderUsuarios(await api("/usuarios"));
  } catch (e) {
    $("#admin-status").textContent = `⚠ ${e.message}`;
  }
}

function renderUsuarios(lista) {
  $("#tabela-usuarios").innerHTML = `<thead><tr><th>Nome</th><th>Usuário</th><th>Papel</th><th>Situação</th><th>Último acesso</th><th>Ações</th></tr></thead>
    <tbody>${lista.map((u) => `<tr data-usuario="${u.id}" class="${u.ativo ? "" : "inativo"}">
      <td><input name="nome" value="${esc(u.nome)}" maxlength="120" aria-label="Nome de ${esc(u.usuario)}"></td>
      <td>${esc(u.usuario)}${u.id === estado.usuario?.id ? ' <span class="muted">(você)</span>' : ""}</td>
      <td><select name="papel" aria-label="Papel de ${esc(u.usuario)}">
        <option value="atendente" ${u.papel === "atendente" ? "selected" : ""}>Atendente</option>
        <option value="admin" ${u.papel === "admin" ? "selected" : ""}>Administrador</option></select></td>
      <td>${u.ativo ? "✅ ativo" : "⛔ desativado"}</td>
      <td>${esc(hora(u.ultimo_login) || "nunca")}</td>
      <td><div class="acoes-usuario">
        <button type="button" class="btn" data-acao-usuario="salvar">Salvar</button>
        <button type="button" class="btn" data-acao-usuario="${u.ativo ? "desativar" : "reativar"}">${u.ativo ? "Desativar" : "Reativar"}</button>
        <input name="senha" type="password" placeholder="nova senha" minlength="8" maxlength="200" autocomplete="new-password" aria-label="Nova senha de ${esc(u.usuario)}">
        <button type="button" class="btn" data-acao-usuario="senha">Redefinir senha</button>
      </div></td></tr>`).join("")}</tbody>`;
}

async function acaoUsuario(botao) {
  const tr = botao.closest("tr[data-usuario]");
  const id = tr.dataset.usuario;
  const acao = botao.dataset.acaoUsuario;
  const st = $("#admin-status");
  const corpo = acao === "salvar" ? { nome: tr.querySelector("[name=nome]").value.trim(), papel: tr.querySelector("[name=papel]").value }
    : acao === "desativar" ? { ativo: false } : acao === "reativar" ? { ativo: true } : { senha: tr.querySelector("[name=senha]").value };
  if (acao === "senha" && (corpo.senha || "").length < 8) { st.textContent = "⚠ A nova senha precisa ter pelo menos 8 caracteres."; return; }
  try {
    const u = await api(`/usuarios/${id}`, { method: "PATCH", body: JSON.stringify(corpo) });
    st.textContent = { salvar: `✅ ${u.nome} atualizado.`, desativar: `✅ ${u.nome} desativado (sessões encerradas).`,
      reativar: `✅ ${u.nome} reativado.`, senha: `✅ Senha de ${u.nome} redefinida (sessões encerradas).` }[acao];
    if (u.id === estado.usuario.id) return entrar(); // mudou o próprio nome
    carregarUsuarios();
  } catch (e) {
    if (e instanceof NaoAutorizado) return sair("Sua sessão expirou. Entre de novo.");
    st.textContent = `⚠ ${e.message}`;
  }
}

async function criarUsuario(form) {
  const st = $("#admin-status");
  try {
    const u = await api("/usuarios", { method: "POST", body: JSON.stringify(Object.fromEntries(new FormData(form))) });
    form.reset();
    st.textContent = `✅ Usuário ${u.usuario} criado. Passe a senha inicial para ${u.nome}; ela pode ser trocada em Minha conta.`;
    carregarUsuarios();
  } catch (e) {
    st.textContent = `⚠ ${e.message}`;
  }
}

async function trocarSenha(form) {
  const st = $("#senha-status");
  const d = Object.fromEntries(new FormData(form));
  if (d.nova_senha !== d.nova_senha2) { st.textContent = "⚠ As novas senhas não conferem."; return; }
  try {
    await api("/auth/senha", { method: "POST", body: JSON.stringify({ senha_atual: d.senha_atual, nova_senha: d.nova_senha }) });
    form.reset();
    st.textContent = "✅ Senha alterada.";
  } catch (e) {
    st.textContent = `⚠ ${e.message}`;
  }
}

// ---------------------------------------------------------------- eventos
document.addEventListener("DOMContentLoaded", () => {
  $("#form-login").addEventListener("submit", (ev) => { ev.preventDefault(); fazerLogin(); });
  $("#form-primeiro").addEventListener("submit", (ev) => { ev.preventDefault(); criarPrimeiroAdmin(ev.target); });
  $("#form-usuario").addEventListener("submit", (ev) => { ev.preventDefault(); criarUsuario(ev.target); });
  $("#form-senha").addEventListener("submit", (ev) => { ev.preventDefault(); trocarSenha(ev.target); });
  $("#tabela-usuarios").addEventListener("click", (ev) => {
    const b = ev.target.closest("button[data-acao-usuario]");
    if (b) acaoUsuario(b);
  });
  $("#sair").addEventListener("click", () => sair());
  $("#intervalo").addEventListener("change", agendar);
  $("#todos-grupos").addEventListener("change", carregar);
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
  $("#anexar").addEventListener("click", () => $("#arquivo").click());
  $("#arquivo").addEventListener("change", async (ev) => {
    for (const f of ev.target.files) {
      // Este botão é só para imagens; áudio entra pelo botão de gravar.
      if (!(f.type || "").startsWith("image/")) {
        $("#nova-status").textContent = `⚠ ${f.name}: anexe apenas imagens (JPG, PNG, WebP).`;
        continue;
      }
      await adicionarAnexo(f, f.name);
    }
    ev.target.value = ""; // permite escolher o mesmo arquivo de novo
  });
  $("#gravar").addEventListener("click", alternarGravacao);
  $("#lista-anexos").addEventListener("click", (ev) => {
    const b = ev.target.closest("button[data-remover]");
    if (!b) return;
    const [a] = estado.anexos.splice(Number(b.dataset.remover), 1);
    URL.revokeObjectURL(a.url);
    renderAnexos();
  });

  if (estado.token) entrar(); else sair();
});
