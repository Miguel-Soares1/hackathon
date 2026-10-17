"""Telas de demonstração dos canais de conversa: WhatsApp e Instagram Direct (só em desenvolvimento).

O apresentador é o ATENDENTE e a IA faz o papel do cliente (`cliente_simulado`). Ao lado da conversa, a tela mostra a
triagem da última mensagem e a resposta sugerida, como o atendente veria no painel. Para cada fala do cliente, o
servidor monta o MESMO JSON que a Meta enviaria ao webhook e passa pelo MESMO conversor do canal real
(`canais.mensagens_whatsapp` / `canais.mensagens_instagram`), então o ticket nasce exatamente como nasceria de uma
mensagem real.
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
  /* Tema de conversa estilo WhatsApp Business */
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
  .app { display:grid; grid-template-columns:minmax(320px,440px) minmax(0,1fr); gap:20px; padding:0 20px 20px; max-width:1180px; margin:0 auto; }
  .app > * { min-width:0; }

  .controles { display:flex; align-items:center; gap:8px; margin-bottom:10px; font-size:13px; color:var(--mu); flex-wrap:wrap; }
  .controles select { min-width:0; flex:1; font:inherit; color:var(--tx); background:var(--card); border:1px solid var(--bd); border-radius:8px; padding:6px 8px; }
  .btn { font:inherit; font-size:13px; font-weight:600; border:0; background:var(--acento); color:#fff; border-radius:8px; padding:7px 12px; cursor:pointer; white-space:nowrap; }
  .btn.sec { background:var(--card); color:var(--tx); border:1px solid var(--bd); font-weight:500; }
  .btn:disabled { opacity:.5; cursor:default; }

  .celular { background:var(--fundo); border:10px solid #1b1f24; border-radius:36px; height:min(720px, calc(100vh - 150px)); min-height:520px;
             display:flex; flex-direction:column; overflow:hidden; box-shadow:0 10px 40px rgba(0,0,0,.18); }
  .barra { background:var(--top); color:var(--topx); display:flex; align-items:center; gap:10px; padding:12px 14px; border-bottom:1px solid rgba(127,127,127,.18); }
  .av { width:38px; height:38px; border-radius:50%; display:grid; place-items:center; font-weight:700; font-size:14px; color:#fff; background:#8a94a6; flex:none; }
  [data-canal=instagram] .av { background:linear-gradient(135deg,#f9a03f,#c93a8f); }
  .barra b { display:block; font-size:15px; } .barra small { opacity:.75; font-size:12px; }
  .chat { flex:1; overflow:auto; padding:14px 10px; display:flex; flex-direction:column; gap:6px; }
  .dia, .sistema { align-self:center; font-size:12px; color:var(--mu); background:var(--card); padding:3px 10px; border-radius:8px; margin:2px 0 6px; opacity:.95; text-align:center; }
  .vazio { margin:auto; text-align:center; color:var(--mu); font-size:14px; padding:20px; }
  .vazio .btn { margin-top:12px; }
  .b { max-width:80%; padding:7px 10px 5px; border-radius:12px; font-size:14.5px; white-space:pre-wrap; word-wrap:break-word; animation:sobe .2s ease-out; }
  @keyframes sobe { from { transform:translateY(6px); opacity:0; } }
  .b.eu { align-self:flex-end; background:var(--eu); color:var(--eutx); border-bottom-right-radius:4px; }
  .b.ele { align-self:flex-start; background:var(--ele); color:var(--eletx); border-bottom-left-radius:4px; }
  [data-canal=instagram] .b { border-radius:20px; padding:9px 14px; }
  .b .h { display:block; text-align:right; font-size:11px; opacity:.65; margin-top:2px; }
  .b.ele .h { text-align:left; }
  .b .t.lido { color:var(--tick); opacity:1; }
  .digitando { align-self:flex-start; background:var(--ele); border-radius:12px; border-bottom-left-radius:4px; padding:10px 12px; display:flex; gap:4px; }
  [data-canal=instagram] .digitando { border-radius:20px; }
  .digitando i { width:7px; height:7px; border-radius:50%; background:var(--mu); animation:pula 1.2s infinite; }
  .digitando i:nth-child(2) { animation-delay:.15s; } .digitando i:nth-child(3) { animation-delay:.3s; }
  @keyframes pula { 0%, 60%, 100% { transform:none; opacity:.5; } 30% { transform:translateY(-4px); opacity:1; } }
  form { display:flex; gap:8px; padding:8px 10px 10px; background:var(--fundo); align-items:flex-end; }
  textarea { flex:1; resize:none; font:inherit; font-size:15px; color:var(--tx); background:var(--card); border:1px solid var(--bd); border-radius:22px; padding:10px 14px; max-height:140px; outline:none; }
  .env { width:44px; height:44px; border-radius:50%; border:0; background:var(--acento); color:#fff; display:grid; place-items:center; cursor:pointer; flex:none; }
  .env:disabled { opacity:.5; cursor:default; }
  #aviso { font-size:12px; color:var(--er); padding:0 14px 6px; background:var(--fundo); min-height:4px; }

  .ia { background:var(--card); border:1px solid var(--bd); border-radius:16px; overflow:hidden; align-self:start; }
  .ia h2 { font-size:15px; margin:0; padding:12px 16px; border-bottom:1px solid var(--bd); background:var(--side); }
  .ia .corpo { padding:14px 16px; display:flex; flex-direction:column; gap:12px; }
  .ia .s { color:var(--mu); font-size:13px; margin:0; }
  .rot { font-size:12px; color:var(--mu); text-transform:uppercase; letter-spacing:.04em; margin-bottom:4px; }
  .tags { display:flex; gap:6px; flex-wrap:wrap; }
  .chip { font-size:12.5px; padding:3px 9px; border-radius:10px; background:var(--side); }
  .chip.u-critica, .chip.u-alta, .chip.s-negativo { background:var(--ers); color:var(--er); }
  .chip.u-media { background:var(--was); color:var(--wa); }
  .chip.u-baixa, .chip.s-positivo { background:var(--oks); color:var(--ok); }
  .sugestao { border-left:3px solid var(--acento); background:var(--side); padding:10px 12px; border-radius:0 10px 10px 0; white-space:pre-wrap; font-size:14px; }
  .aguarde { color:var(--mu); font-size:14px; }
  .dot { display:inline-block; width:8px; height:8px; border-radius:50%; background:var(--acento); margin-right:6px; animation:pp 1s infinite; }
  @keyframes pp { 50% { opacity:.25; } }
  .ia a { color:var(--acento); font-size:13px; }
  @media (max-width: 860px) { .app { grid-template-columns:minmax(0,1fr); padding:0 16px 16px; } .topo { padding:12px 16px; } .celular { border-width:8px; height:600px; } }
</style>
</head>
<body>
<div class="topo">
  <h1>Simulador de canais</h1>
  <nav class="abas"><a href="/demo/whatsapp" data-c="whatsapp">WhatsApp</a><a href="/demo/instagram" data-c="instagram">Instagram</a><a href="/demo/email" data-c="email">E-mail</a></nav>
  <span class="tag-demo">AMBIENTE DE DEMONSTRAÇÃO · VOCÊ É O ATENDENTE</span>
</div>
<div class="app">
  <div>
    <div class="controles">
      <span>Situação do cliente:</span>
      <select id="cenario" aria-label="Situação do cliente"><option value="">Sorteada</option></select>
      <button class="btn" type="button" id="novo">Novo cliente</button>
    </div>
    <div class="celular">
      <div class="barra"><div class="av" id="av">?</div><div><b id="nome">Nenhum cliente</b><small id="sub">Sua Empresa · atendimento</small></div></div>
      <div class="chat" id="chat" aria-live="polite">
        <div class="vazio" id="vazio">A IA faz o papel do cliente e você responde como atendente.<br>
          <button class="btn" type="button" id="comecar">Chamar um cliente</button></div>
      </div>
      <form id="f"><textarea id="texto" rows="1" maxlength="2000" placeholder="Responder como atendente…" disabled></textarea>
        <button class="env" id="b" type="submit" aria-label="Enviar" disabled><svg width="20" height="20" viewBox="0 0 24 24" aria-hidden="true"><path d="M3 20.5 21 12 3 3.5l.01 6.6L15 12 3.01 13.9z" fill="currentColor"/></svg></button></form>
      <div id="aviso" role="status"></div>
    </div>
  </div>
  <section class="ia" aria-label="Assistente de IA">
    <h2>Assistente de IA · triagem do ticket desta conversa</h2>
    <div class="corpo" id="ia"><p class="s">Quando o cliente escrever, a IA abre o ticket e mostra aqui o assunto, a urgência, o prazo e uma resposta sugerida para começar o atendimento.</p></div>
  </section>
</div>
<script>
const CANAL = document.documentElement.dataset.canal;
const $ = (id) => document.getElementById(id);
document.querySelector('.abas a[data-c="' + CANAL + '"]').classList.add('on');
const ROT = { cobranca:'Cobrança', pagamento:'Pagamento', acesso:'Acesso', instabilidade:'Instabilidade', cancelamento:'Cancelamento',
  reclamacao:'Reclamação', duvida:'Dúvida', elogio:'Elogio', baixa:'baixa', media:'média', alta:'alta', critica:'crítica',
  positivo:'positivo', neutro:'neutro', negativo:'negativo', financeiro:'Financeiro', suporte_tecnico:'Suporte técnico',
  engenharia:'Engenharia', retencao:'Retenção', atendimento:'Atendimento' };
const r = (v) => ROT[v] || v || '—';
const prazo = (min) => min == null ? '' : min < 60 ? min + ' min' : (min / 60) + ' h';

let conversa = null; let ultimoTicket = null; let ocupado = false;

function el(tag, cls, txt) { const e = document.createElement(tag); if (cls) e.className = cls; if (txt != null) e.textContent = txt; return e; }
const hora = () => new Date().toLocaleTimeString('pt-BR', { hour:'2-digit', minute:'2-digit' });
const rolar = () => { const c = $('chat'); c.scrollTop = c.scrollHeight; };
const SUB = CANAL === 'whatsapp' ? 'online' : 'Ativo agora';

fetch('/demo/cenarios').then((x) => x.json()).then((lista) => lista.forEach((c) => {
  const o = el('option', null, c.titulo); o.value = c.chave; $('cenario').append(o); })).catch(() => {});

function bolha(de, texto) {
  $('vazio')?.remove();
  const b = el('div', 'b ' + de, texto); const h = el('span', 'h', hora() + ' ');
  if (de === 'eu') h.append(el('span', 't', '✓✓'));
  b.append(h); $('chat').append(b); rolar(); return b;
}
function sistema(texto) { $('chat').append(el('div', 'sistema', texto)); rolar(); }
function digitando(sim) {
  $('digitando')?.remove();
  if (sim) { const d = el('div', 'digitando'); d.id = 'digitando'; d.append(el('i'), el('i'), el('i')); $('chat').append(d); rolar(); }
  $('sub').textContent = sim ? 'digitando…' : (conversa ? SUB : 'Sua Empresa · atendimento');
}
function liberar(sim) { $('texto').disabled = !sim; $('b').disabled = !sim; if (sim) $('texto').focus(); }
function lidas() { document.querySelectorAll('.b.eu .t').forEach((t) => t.classList.add('lido')); }

// Painel do atendente: triagem da última mensagem do cliente e a resposta sugerida pela IA.
function painelAguardando() { const c = $('ia'); c.textContent = ''; const a = el('div', 'aguarde'); a.append(el('span', 'dot'), 'Analisando a mensagem…'); c.append(a); }
function painel(t) {
  const c = $('ia'); c.textContent = '';
  const bloco = (rot, conteudo) => { const d = el('div'); d.append(el('div', 'rot', rot), conteudo); c.append(d); };
  const tags = el('div', 'tags');
  tags.append(el('span', 'chip', r(t.assunto)), el('span', 'chip u-' + t.urgencia, 'urgência ' + r(t.urgencia)),
              el('span', 'chip s-' + t.sentimento, r(t.sentimento)), el('span', 'chip', '→ ' + r(t.equipe)));
  if (t.origem === 'fallback') tags.append(el('span', 'chip', 'plano B (regras)'));
  bloco('Ticket #' + t.ticket_id + ' · prazo da 1ª resposta: ' + prazo(t.sla.prazo_minutos), tags);
  if (t.resposta_sugerida) {
    const s = el('div', 'sugestao', t.resposta_sugerida);
    const usar = el('button', 'btn sec', 'Usar sugestão'); usar.type = 'button'; usar.style.marginTop = '8px';
    usar.addEventListener('click', () => { if (!$('texto').disabled) { $('texto').value = t.resposta_sugerida; $('texto').focus(); } });
    const d = el('div'); d.append(s, usar); bloco('Resposta sugerida (revise antes de enviar)', d);
  }
  if (t.exemplos) c.append(el('p', 's', '🧠 A IA aprendeu com tickets revisados parecidos: #' + t.exemplos.split(',').join(', #')));
  const link = el('a', null, 'Abrir o painel do atendimento ↗'); link.href = '/'; link.target = '_blank'; link.rel = 'noopener'; c.append(link);
}
async function acompanhar(ticket, n) {
  if (ticket !== ultimoTicket || !conversa) return;
  try {
    const t = await (await fetch('/demo/conversas/' + conversa + '/tickets/' + ticket)).json();
    if (t.status && t.status !== 'pendente') return painel(t);
  } catch (_) {}
  if (n < 40) setTimeout(() => acompanhar(ticket, n + 1), 1000);
}

function chegou(m) {
  digitando(false); lidas(); bolha('ele', m.texto);
  if (m.ticket_id) { ultimoTicket = m.ticket_id; painelAguardando(); acompanhar(m.ticket_id, 0); }
  if (m.encerrou) { sistema('O cliente encerrou a conversa.'); liberar(false); $('novo').focus(); }
  else liberar(true);
}

async function novoCliente() {
  if (ocupado) return; ocupado = true; $('aviso').textContent = '';
  conversa = null; ultimoTicket = null; liberar(false);
  const c = $('chat'); c.textContent = ''; c.append(el('div', 'dia', 'Hoje'));
  $('nome').textContent = 'Novo cliente…'; $('av').textContent = '…';
  $('ia').textContent = ''; $('ia').append(el('p', 's', 'Esperando o cliente escrever…'));
  digitando(true);
  try {
    const resp = await fetch('/demo/' + CANAL + '/conversas', { method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ cenario: $('cenario').value || null }) });
    const d = await resp.json();
    if (resp.status !== 201) throw new Error(d.detail || 'falha');
    conversa = d.conversa;
    $('nome').textContent = d.cliente.nome;
    $('av').textContent = d.cliente.nome.replace('@', '').slice(0, 2).toUpperCase();
    sistema('Situação do cliente (IA): ' + d.cenario);
    chegou(d.mensagem);
  } catch (e) { digitando(false); $('aviso').textContent = 'Não foi possível chamar um cliente: ' + (e.message || 'API fora do ar?'); }
  finally { ocupado = false; }
}
$('novo').addEventListener('click', novoCliente);
$('comecar').addEventListener('click', novoCliente);

$('texto').addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); $('f').requestSubmit(); } });
$('f').addEventListener('submit', async (e) => {
  e.preventDefault();
  const texto = $('texto').value.trim(); $('aviso').textContent = '';
  if (!texto || !conversa || ocupado) return;
  ocupado = true; bolha('eu', texto); $('texto').value = ''; liberar(false);
  setTimeout(() => { if (ocupado) digitando(true); }, 700);
  try {
    const resp = await fetch('/demo/conversas/' + conversa + '/respostas', { method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ texto }) });
    const d = await resp.json();
    if (resp.status !== 200) throw new Error(d.detail || 'falha');
    ocupado = false; chegou(d.mensagem);
  } catch (e) { ocupado = false; digitando(false); liberar(true); $('aviso').textContent = 'Não foi possível enviar: ' + (e.message || 'API fora do ar?'); }
});
</script>
</body>
</html>
"""

PAGINAS = {
    "whatsapp": _PAGINA.replace("__CANAL__", "whatsapp").replace("__TITULO__", "WhatsApp"),
    "instagram": _PAGINA.replace("__CANAL__", "instagram").replace("__TITULO__", "Instagram Direct"),
}
