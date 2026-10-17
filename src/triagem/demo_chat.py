"""Telas de demonstração dos canais de conversa: WhatsApp e Instagram Direct (só em desenvolvimento).

O apresentador "conversa" como cliente numa tela de celular. O servidor monta o MESMO JSON que a Meta enviaria
ao webhook e passa pelo MESMO conversor do canal real (`canais.mensagens_whatsapp` / `canais.mensagens_instagram`),
então a mensagem entra na conversa do cliente exatamente como entraria uma mensagem real (ADR-016).
"""
import time
import uuid
from typing import Optional

from . import canais


def payload_whatsapp(telefone: str, nome: Optional[str], texto: str, agora: Optional[float] = None) -> dict:
    """Payload no formato do webhook da WhatsApp Cloud API (Meta)."""
    ts = str(int(agora if agora is not None else time.time()))
    return {
        "object": "whatsapp_business_account",
        "entry": [{"id": "demo", "changes": [{"field": "messages", "value": {
            "messaging_product": "whatsapp",
            "metadata": {"display_phone_number": "550000000000", "phone_number_id": "demo"},
            "contacts": [{"profile": {"name": nome or ""}, "wa_id": telefone}],
            "messages": [{"from": telefone, "id": f"wamid.DEMO{uuid.uuid4().hex}", "timestamp": ts,
                          "type": "text", "text": {"body": texto}}],
        }}]}],
    }


def payload_instagram(usuario: str, texto: str, agora: Optional[float] = None) -> dict:
    """Payload no formato do webhook de mensagens do Instagram (Meta). Na vida real `sender.id` é um IGSID numérico."""
    ms = int((agora if agora is not None else time.time()) * 1000)
    return {
        "object": "instagram",
        "entry": [{"id": "demo", "time": ms, "messaging": [{
            "sender": {"id": usuario}, "recipient": {"id": "demo"}, "timestamp": ms,
            "message": {"mid": f"m_DEMO{uuid.uuid4().hex}", "text": texto},
        }]}],
    }


def mensagem_demo(canal: str, remetente: str, nome: Optional[str], texto: str) -> Optional[dict]:
    """Mesmo caminho do webhook real: payload da Meta -> mensagem do pipeline (ou None se seria ignorada)."""
    if canal == "whatsapp":
        msgs = canais.mensagens_whatsapp(payload_whatsapp(remetente, nome, texto))
    elif canal == "instagram":
        msgs = canais.mensagens_instagram(payload_instagram(remetente, texto))
    else:
        raise ValueError(canal)
    return msgs[0] if msgs else None


_PAGINA = r"""<!doctype html>
<html lang="pt-BR" data-canal="__CANAL__">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITULO__ · demonstração</title>
<style>
  :root { --bg:#eef1f4; --card:#fff; --tx:#16202e; --mu:#5e6b7e; --bd:#dbe1e8; --side:#f1f4f7;
          --ok:#137333; --oks:#e6f4ea; --wa:#a05a00; --was:#fef3d8; --er:#c5221f; --ers:#fce8e6; color-scheme: light dark; }
  @media (prefers-color-scheme: dark) { :root { --bg:#0f141b; --card:#18202b; --tx:#e6ebf3; --mu:#98a4b8; --bd:#2a3442; --side:#1f2935;
          --ok:#81c995; --oks:#1e3527; --wa:#fdd663; --was:#3a3220; --er:#f28b82; --ers:#3d2322; } }
  /* Tema de conversa estilo WhatsApp */
  [data-canal=whatsapp] { --top:#0f6e60; --topx:#fff; --fundo:#ece5dd; --eu:#d6f8c8; --eutx:#16202e; --ele:#fff; --eletx:#16202e; --acento:#0f8f6f; --tick:#3b9ae1; }
  @media (prefers-color-scheme: dark) { [data-canal=whatsapp] { --top:#1d2b33; --fundo:#0d1418; --eu:#0f5b4b; --eutx:#e9f1ee; --ele:#1d2b33; --eletx:#e6ebf3; --acento:#22b38a; } }
  /* Tema de Direct estilo Instagram */
  [data-canal=instagram] { --top:#fff; --topx:#16202e; --fundo:#fff; --eu:linear-gradient(135deg,#6d4ce8,#c93a8f); --eutx:#fff; --ele:#efeff2; --eletx:#16202e; --acento:#6d4ce8; --tick:#8e8e93; }
  @media (prefers-color-scheme: dark) { [data-canal=instagram] { --top:#000; --topx:#f2f2f2; --fundo:#000; --ele:#26262a; --eletx:#f2f2f2; --acento:#a58bff; } }

  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--tx); font:15px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; }
  .topo { display:flex; align-items:center; gap:12px; padding:12px 20px; flex-wrap:wrap; }
  .topo h1 { font-size:18px; margin:0; }
  .abas { display:flex; gap:4px; background:var(--card); border:1px solid var(--bd); border-radius:20px; padding:3px; }
  .abas a { padding:5px 14px; border-radius:16px; color:var(--mu); text-decoration:none; font-size:13px; font-weight:600; }
  .abas a.on { background:var(--acento); color:#fff; }
  .tag-demo { margin-left:auto; font-size:12px; font-weight:600; color:var(--wa); background:var(--was); padding:4px 10px; border-radius:12px; }
  .app { padding:0 20px 20px; max-width:440px; margin:0 auto; }

  .quem { display:flex; align-items:center; gap:8px; margin-bottom:10px; font-size:13px; color:var(--mu); }
  .quem select { min-width:0; font:inherit; color:var(--tx); background:var(--card); border:1px solid var(--bd); border-radius:8px; padding:5px 8px; flex:1; }
  .auto { display:flex; align-items:center; gap:6px; margin:-4px 0 10px; font-size:13px; color:var(--mu); cursor:pointer; }
  .quem button { white-space:nowrap; font:inherit; font-size:13px; border:1px solid var(--bd); background:var(--card); color:var(--tx); border-radius:8px; padding:5px 10px; cursor:pointer; }
  .celular { background:var(--fundo); border:10px solid #1b1f24; border-radius:36px; height:min(720px, calc(100vh - 150px)); min-height:520px;
             display:flex; flex-direction:column; overflow:hidden; box-shadow:0 10px 40px rgba(0,0,0,.18); }
  .barra { background:var(--top); color:var(--topx); display:flex; align-items:center; gap:10px; padding:12px 14px; border-bottom:1px solid rgba(127,127,127,.18); }
  .av { width:38px; height:38px; border-radius:50%; display:grid; place-items:center; font-weight:700; font-size:14px; color:#fff; background:var(--acento); flex:none; }
  [data-canal=instagram] .av { background:linear-gradient(135deg,#6d4ce8,#c93a8f); }
  .barra b { display:block; font-size:15px; } .barra small { opacity:.75; font-size:12px; }
  .chat { flex:1; overflow:auto; padding:14px 10px; display:flex; flex-direction:column; gap:6px; }
  .dia { align-self:center; font-size:12px; color:var(--mu); background:var(--card); padding:3px 10px; border-radius:8px; margin-bottom:6px; opacity:.9; }
  .b { max-width:80%; padding:7px 10px 5px; border-radius:12px; font-size:14.5px; white-space:pre-wrap; word-wrap:break-word; animation:sobe .2s ease-out; }
  @keyframes sobe { from { transform:translateY(6px); opacity:0; } }
  .b.eu { align-self:flex-end; background:var(--eu); color:var(--eutx); border-bottom-right-radius:4px; }
  .b.ele { align-self:flex-start; background:var(--ele); color:var(--eletx); border-bottom-left-radius:4px; }
  [data-canal=instagram] .b { border-radius:20px; padding:9px 14px; }
  .b .h { display:block; text-align:right; font-size:11px; opacity:.65; margin-top:2px; }
  [data-canal=instagram] .b.eu .h { display:none; }
  .b.ele .h { text-align:left; }
  .b .t.lido { color:var(--tick); opacity:1; }
  .visto { align-self:flex-end; font-size:11px; color:var(--mu); margin:-2px 6px 0; }
  .digitando { align-self:flex-start; background:var(--ele); border-radius:12px; border-bottom-left-radius:4px; padding:10px 12px; display:flex; gap:4px; }
  [data-canal=instagram] .digitando { border-radius:20px; }
  .digitando i { width:7px; height:7px; border-radius:50%; background:var(--mu); animation:pula 1.2s infinite; }
  .digitando i:nth-child(2) { animation-delay:.15s; } .digitando i:nth-child(3) { animation-delay:.3s; }
  @keyframes pula { 0%, 60%, 100% { transform:none; opacity:.5; } 30% { transform:translateY(-4px); opacity:1; } }
  .chips { display:flex; gap:6px; overflow-x:auto; padding:8px 10px 0; background:var(--fundo); scrollbar-width:none; }
  .chips button { flex:none; font:inherit; font-size:12px; border:1px solid var(--bd); background:var(--card); color:var(--tx); border-radius:14px; padding:5px 10px; cursor:pointer; }
  form { display:flex; gap:8px; padding:8px 10px 10px; background:var(--fundo); align-items:flex-end; }
  textarea { flex:1; resize:none; font:inherit; font-size:15px; color:var(--tx); background:var(--card); border:1px solid var(--bd); border-radius:22px; padding:10px 14px; max-height:120px; outline:none; }
  .env { width:44px; height:44px; border-radius:50%; border:0; background:var(--acento); color:#fff; display:grid; place-items:center; cursor:pointer; flex:none; }
  .env:disabled { opacity:.5; }
  #aviso { font-size:12px; color:var(--er); padding:0 14px 6px; background:var(--fundo); min-height:4px; }

  .app > * { min-width:0; }
  @media (max-width: 820px) { .app { padding:0 16px 16px; } .topo { padding:12px 16px; } .celular { border-width:8px; } .celular { height:600px; } }
</style>
</head>
<body>
<div class="topo">
  <h1>Simulador de canais</h1>
  <nav class="abas"><a href="/demo/whatsapp" data-c="whatsapp">WhatsApp</a><a href="/demo/instagram" data-c="instagram">Instagram</a><a href="/demo/email" data-c="email">E-mail</a></nav>
  <span class="tag-demo">AMBIENTE DE DEMONSTRAÇÃO</span>
</div>
<div class="app">
  <div>
    <div class="quem"><span>Cliente:</span><select id="pessoa" aria-label="Cliente simulado"></select><button type="button" id="outro">Outro cliente</button></div>
    <label class="auto" title="Ligada: a IA responde sozinha a primeira mensagem. Desligada: só o atendente responde, pelo painel.">
      <input type="checkbox" id="auto"> Resposta automática da IA na 1ª mensagem (o atendente responde pelo painel)</label>
    <div class="celular">
      <div class="barra"><div class="av">SE</div><div><b>Sua Empresa</b><small id="sub"></small></div></div>
      <div class="chat" id="chat" aria-live="polite"><div class="dia">Hoje</div></div>
      <div class="chips" aria-label="Mensagens prontas">
        <button type="button" data-m="0">Pix não caiu</button><button type="button" data-m="1">Conta bloqueada</button>
        <button type="button" data-m="2">Cobrança duplicada</button><button type="button" data-m="3">App caindo</button>
        <button type="button" data-m="4">Cancelar</button><button type="button" data-m="5">Elogio</button>
      </div>
      <form id="f"><textarea id="texto" rows="1" maxlength="1000" placeholder="Mensagem"></textarea>
        <button class="env" id="b" type="submit" aria-label="Enviar"><svg width="20" height="20" viewBox="0 0 24 24" aria-hidden="true"><path d="M3 20.5 21 12 3 3.5l.01 6.6L15 12 3.01 13.9z" fill="currentColor"/></svg></button></form>
      <div id="aviso" role="status"></div>
    </div>
  </div>
</div>
<script>
const CANAL = document.documentElement.dataset.canal;
const $ = (id) => document.getElementById(id);
document.querySelector('.abas a[data-c="' + CANAL + '"]').classList.add('on');

const PESSOAS = CANAL === 'whatsapp'
  ? [["Mariana Souza","5511987654321"],["Carlos Lima","5521998761234"],["Ana Ribeiro","5531991234567"],["João Pereira","5511976543210"],
     ["Beatriz Costa","5541988887777"],["Rafael Gomes","5551999990000"],["Luana Martins","5561981112222"],["Pedro Alves","5571993334444"]]
  : [["@mari.souza","mari.souza"],["@carloslima_","carloslima_"],["@ana.ribeiro","ana.ribeiro"],["@joaop","joaop"],
     ["@bia.costa","bia.costa"],["@rafagomes","rafagomes"],["@luana.mrt","luana.mrt"],["@pedro.alves","pedro.alves"]];
const MODELOS = [
  "meu pix não caiu e preciso do dinheiro hoje, o que aconteceu??",
  "não consigo entrar no app, aparece conta bloqueada e não chega o código",
  "fui cobrado duas vezes no cartão esse mês, quero meu dinheiro de volta",
  "o aplicativo fica fechando sozinho toda vez que abro a tela de pagamentos",
  "quero cancelar minha conta, como faço?",
  "só passando pra agradecer, o atendimento de ontem foi excelente! 👏",
];
PESSOAS.forEach((p, i) => { const o = document.createElement('option'); o.value = i;
  o.textContent = CANAL === 'whatsapp' ? p[0] + ' · +' + p[1].replace(/^(\d{2})(\d{2})(\d{5})(\d{4})$/, '$1 $2 $3-$4') : p[0]; $('pessoa').append(o); });
const EQUIPES = { financeiro:'Financeiro', suporte_tecnico:'Suporte Técnico', engenharia:'Engenharia', retencao:'Retenção' };
const ESPERA_MAX = 60;  // segundos esperando a resposta antes de cair na mensagem padrão

// Cada cliente simulado tem a própria conversa, guardada na aba do navegador (some ao fechar a aba).
const pessoa = () => PESSOAS[+$('pessoa').value];
const chaveConversa = (p) => 'demo-' + CANAL + '-' + p[1];
function historico(k) { try { return JSON.parse(sessionStorage.getItem(k)) || []; } catch (_) { return []; } }
const memoria = {};  // se o navegador bloquear o sessionStorage, a conversa fica só na memória da página
function salvar(k, h) { memoria[k] = h.slice(-80); try { sessionStorage.setItem(k, JSON.stringify(memoria[k])); } catch (_) {} }
function ler(k) { const h = historico(k); return h.length ? h : (memoria[k] || []); }
function registrar(k, item) { const h = ler(k); h.push(item); salvar(k, h); return h.length - 1; }
function atualizar(k, i, campos) { const h = ler(k); if (h[i]) { Object.assign(h[i], campos); salvar(k, h); } }
const aguardando = {};  // conversa -> respostas ainda a caminho (mostra "digitando…")

// Ticket da conversa no servidor: as mensagens do mesmo cliente entram no mesmo ticket (ADR-016). A senha devolvida no
// envio permite ler as respostas que o atendente mandar pelo painel (só as dele, nunca a classificação).
function meta(k) { try { return JSON.parse(sessionStorage.getItem('meta-' + k)) || memoria['meta-' + k] || null; } catch (_) { return memoria['meta-' + k] || null; } }
function salvarMeta(k, m) { memoria['meta-' + k] = m; try { sessionStorage.setItem('meta-' + k, JSON.stringify(m)); } catch (_) {} }
const autoLigada = () => $('auto').checked;
try { $('auto').checked = localStorage.getItem('demo-auto') !== '0'; } catch (_) { $('auto').checked = true; }
$('auto').addEventListener('change', () => { try { localStorage.setItem('demo-auto', $('auto').checked ? '1' : '0'); } catch (_) {} });

function el(tag, cls, txt) { const e = document.createElement(tag); if (cls) e.className = cls; if (txt != null) e.textContent = txt; return e; }
const hora = () => new Date().toLocaleTimeString('pt-BR', { hour:'2-digit', minute:'2-digit' });
const rolar = () => { const c = $('chat'); c.scrollTop = c.scrollHeight; };
const SUB = CANAL === 'whatsapp' ? 'Conta comercial · online' : 'sua.empresa · Ativo agora';

function bolha(m) {
  const b = el('div', 'b ' + m.de, m.texto); const h = el('span', 'h', m.hora + ' ');
  if (m.de === 'eu') h.append(el('span', 't' + (m.estado === 'lido' ? ' lido' : ''), m.estado === 'enviado' ? '✓' : m.estado === 'erro' ? '!' : '✓✓'));
  b.append(h); return b;
}
function desenhar() {
  const k = chaveConversa(pessoa()); const c = $('chat'); c.textContent = ''; c.append(el('div', 'dia', 'Hoje'));
  const h = ler(k); h.forEach((m) => c.append(bolha(m)));
  const ultima = h[h.length - 1];
  if (CANAL === 'instagram' && ultima && ultima.de === 'eu' && ultima.estado === 'lido') c.append(el('div', 'visto', 'Visto'));
  if (aguardando[k] > 0) { const d = el('div', 'digitando'); d.append(el('i'), el('i'), el('i')); c.append(d); }
  $('sub').textContent = aguardando[k] > 0 ? 'digitando…' : SUB;
  rolar();
}
function mudou(k) { if (k === chaveConversa(pessoa())) desenhar(); }

function trocar(i) { $('pessoa').value = i; $('aviso').textContent = ''; desenhar(); }
$('pessoa').addEventListener('change', () => trocar($('pessoa').value));
$('outro').addEventListener('click', () => trocar((+$('pessoa').value + 1 + Math.floor(Math.random() * (PESSOAS.length - 1))) % PESSOAS.length));
trocar(Math.floor(Math.random() * PESSOAS.length));
document.querySelectorAll('[data-m]').forEach((b) => b.addEventListener('click', () => { $('texto').value = MODELOS[+b.dataset.m]; $('texto').focus(); }));
$('texto').addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); $('f').requestSubmit(); } });

const pausa = (ms) => new Promise((r) => setTimeout(r, ms));
const primeiroNome = (p) => CANAL === 'whatsapp' ? p[0].split(' ')[0] : p[0];
function marcarLidas(k) { const h = ler(k); h.forEach((m) => { if (m.de === 'eu' && m.estado === 'entregue') m.estado = 'lido'; }); salvar(k, h); }

// A empresa responde como numa conversa real: confirmação automática na primeira mensagem e, depois de
// "digitando…", a resposta do atendimento, escrita a partir do que o cliente disse.
async function responder(k, p, ticket, senha, primeira, comIA) {
  aguardando[k] = (aguardando[k] || 0) + 1; mudou(k);
  const inicio = Date.now();
  try {
    if (primeira) {
      await pausa(1200);
      const saudacao = CANAL === 'whatsapp'
        ? 'Olá, ' + primeiroNome(p) + '! 👋 Aqui é o atendimento da Sua Empresa. Recebemos sua mensagem, protocolo #' + ticket + '. Já vamos te responder por aqui.'
        : 'Oi, ' + primeiroNome(p) + '! Recebemos sua mensagem 💬 Protocolo #' + ticket + '. Já já te respondemos por aqui.';
      marcarLidas(k); registrar(k, { de:'ele', texto:saudacao, hora:hora() }); mudou(k);
    }
    if (!comIA) return;  // sem resposta automática: quem responde é o atendente, pelo painel
    let r = null;
    for (let n = 0; n < ESPERA_MAX && !(r && r.respondida); n++) {
      try { r = await (await fetch('/demo/conversa/' + ticket + '?senha=' + encodeURIComponent(senha))).json(); } catch (_) {}
      if (!(r && r.respondida)) await pausa(1000);
    }
    await pausa(Math.max(0, 2200 - (Date.now() - inicio)));  // ninguém responde em meio segundo
    marcarLidas(k);
    if (r && r.respondida) {
      const ultimaEquipe = [...ler(k)].reverse().find((m) => m.equipe)?.equipe;
      if (EQUIPES[r.equipe] && r.equipe !== ultimaEquipe) {
        registrar(k, { de:'ele', texto:'Encaminhei seu caso para o time ' + EQUIPES[r.equipe] + ', que cuida desse assunto.', hora:hora(), equipe:r.equipe });
        mudou(k); await pausa(900);
      }
      // No meio da conversa ninguém cumprimenta de novo: tira o "Olá!" do começo das respostas seguintes.
      const jaRespondeu = ler(k).some((m) => m.equipe);
      const texto = jaRespondeu ? r.resposta.replace(/^(olá|ola|oi|bom dia|boa tarde|boa noite)[^.!?\n]{0,40}[!.,]\s*/i, '') : r.resposta;
      registrar(k, { de:'ele', texto: texto ? texto[0].toUpperCase() + texto.slice(1) : r.resposta, hora:hora(), equipe:r.equipe });
    } else {
      registrar(k, { de:'ele', texto:'Recebemos sua mensagem e um atendente vai responder em breve. Obrigado pela paciência!', hora:hora() });
    }
  } finally { aguardando[k] -= 1; mudou(k); }
}

const urlConversa = (m) => '/demo/conversa/' + m.ticket + '?senha=' + encodeURIComponent(m.senha) + '&depois_de=' + m.ultimo;
let buscando = false;
async function buscarAtendente() {
  const k = chaveConversa(pessoa()); const m = meta(k);
  if (!m || buscando) return;
  buscando = true;
  try {
    const r = await (await fetch(urlConversa(m))).json();
    if (r.atendente && r.atendente.length) {
      marcarLidas(k);
      r.atendente.forEach((x) => registrar(k, { de:'ele', texto:x.texto, hora:hora(), atendente:true }));
    }
    if (r.ultimo_id != null && k === chaveConversa(pessoa())) salvarMeta(k, { ...m, ultimo: r.ultimo_id });
    if (r.atendente && r.atendente.length) mudou(k);
  } catch (_) {} finally { buscando = false; }
}
setInterval(buscarAtendente, 3000);

$('f').addEventListener('submit', async (e) => {
  e.preventDefault();
  const texto = $('texto').value.trim(); $('aviso').textContent = '';
  if (texto.length < 3) return;
  const p = pessoa(); const k = chaveConversa(p);
  const i = registrar(k, { de:'eu', texto, hora:hora(), estado:'enviado' }); desenhar();
  $('texto').value = ''; $('b').disabled = true;
  try {
    const resp = await fetch('/demo/' + CANAL, { method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ remetente: p[1], nome: CANAL === 'whatsapp' ? p[0] : null, texto }) });
    const d = await resp.json().catch(() => ({}));
    if (resp.status === 202) {
      atualizar(k, i, { estado:'entregue' }); mudou(k);
      const m = meta(k);
      const conhecido = m && m.ticket === d.ticket_id;
      if (!conhecido) {
        // Conversa nova nesta aba. Se o servidor anexou a um ticket antigo do cliente, não repete respostas já lidas.
        let ultimo = 0;
        if (d.status === 'anexada') { try { ultimo = (await (await fetch(urlConversa({ ticket:d.ticket_id, senha:d.senha, ultimo:0 }))).json()).ultimo_id || 0; } catch (_) {} }
        salvarMeta(k, { ticket:d.ticket_id, senha:d.senha, ultimo });
      }
      const novo = d.status === 'pendente';
      if (novo || !conhecido) responder(k, p, d.ticket_id, d.senha, true, novo && autoLigada());
    }
    else { atualizar(k, i, { estado:'erro' }); mudou(k); $('aviso').textContent = d.detail || 'Não foi possível enviar.'; }
  } catch (_) { atualizar(k, i, { estado:'erro' }); mudou(k); $('aviso').textContent = 'API fora do ar? Confira o terminal do uvicorn.'; }
  finally { $('b').disabled = false; $('texto').focus(); }
});
</script>
</body>
</html>
"""

PAGINAS = {
    "whatsapp": _PAGINA.replace("__CANAL__", "whatsapp").replace("__TITULO__", "WhatsApp"),
    "instagram": _PAGINA.replace("__CANAL__", "instagram").replace("__TITULO__", "Instagram Direct"),
}
