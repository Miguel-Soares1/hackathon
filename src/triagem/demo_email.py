"""Tela de demonstração do canal e-mail (só em desenvolvimento).

Simula a caixa do atendimento: a IA faz o papel do cliente (`cliente_simulado`) e escreve os e-mails; o
apresentador, como atendente, responde. Cada e-mail do cliente vira um e-mail de verdade (RFC 5322) e passa pelo MESMO
conversor do leitor IMAP (`canais.email_para_mensagem`), então o ticket nasce exatamente como nasceria de um e-mail
real: canal `email`, cliente = remetente, texto = assunto + corpo.
"""
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from typing import Optional

from . import canais


def montar_email(de_email: str, de_nome: Optional[str], para: str, assunto: str, corpo: str) -> bytes:
    msg = EmailMessage()
    msg["From"] = formataddr((de_nome or "", de_email)) if de_nome else de_email
    msg["To"] = para
    msg["Subject"] = assunto
    msg["Date"] = formatdate(localtime=False, usegmt=True)
    msg["Message-ID"] = make_msgid(domain="demo.local")
    msg.set_content(corpo)
    return msg.as_bytes()


def email_demo_para_mensagem(de_email: str, de_nome: Optional[str], para: str, assunto: str, corpo: str) -> Optional[dict]:
    """Mesmo caminho do IMAP: e-mail bruto -> mensagem do pipeline (ou None se seria ignorado)."""
    return canais.email_para_mensagem(montar_email(de_email, de_nome, para, assunto, corpo))


PAGINA_DEMO_EMAIL = r"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Correio · demonstração</title>
<style>
  :root { --bg:#eef2f7; --side:#e3e9f2; --card:#fff; --tx:#16202e; --mu:#5e6b7e; --bd:#d6dde8; --pr:#0b57d0;
          --prs:#d3e3fd; --ok:#137333; --oks:#e6f4ea; --wa:#b06000; --was:#fef7e0; --er:#c5221f; --ers:#fce8e6; color-scheme: light dark; }
  @media (prefers-color-scheme: dark) { :root { --bg:#111722; --side:#161e2c; --card:#1b2433; --tx:#e6ebf3; --mu:#98a4b8;
          --bd:#2b3648; --pr:#8ab4f8; --prs:#26385a; --ok:#81c995; --oks:#1e3527; --wa:#fdd663; --was:#3a3220; --er:#f28b82; --ers:#3d2322; } }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--tx); font:15px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; }
  header { display:flex; align-items:center; gap:12px; padding:10px 16px; flex-wrap:wrap; }
  .logo { display:flex; align-items:center; gap:8px; font-size:20px; font-weight:600; }
  .logo svg { width:28px; height:28px; }
  .logo small { font-size:13px; font-weight:400; color:var(--mu); }
  .abas { display:flex; gap:4px; background:var(--card); border:1px solid var(--bd); border-radius:20px; padding:3px; margin-left:16px; }
  .abas a { padding:5px 14px; border-radius:16px; color:var(--mu); text-decoration:none; font-size:13px; font-weight:600; }
  .abas a.on { background:var(--pr); color:#fff; }
  .tag-demo { margin-left:auto; font-size:12px; font-weight:600; color:var(--wa); background:var(--was); padding:4px 10px; border-radius:12px; }
  .app { display:grid; grid-template-columns:270px minmax(0,1fr) 340px; gap:12px; padding:0 12px 12px; height:calc(100vh - 60px); }
  .app > * { min-width:0; }
  .app > nav { display:flex; flex-direction:column; gap:8px; min-height:0; }
  .chamar { display:flex; flex-direction:column; gap:6px; background:var(--card); border:1px solid var(--bd); border-radius:16px; padding:12px; }
  .chamar label { font-size:12px; color:var(--mu); }
  .chamar select { font:inherit; font-size:14px; color:var(--tx); background:var(--bg); border:1px solid var(--bd); border-radius:8px; padding:6px; }
  .btn { font:inherit; font-size:14px; font-weight:600; border:0; background:var(--pr); color:#fff; border-radius:18px; padding:8px 16px; cursor:pointer; }
  .btn.sec { background:var(--card); color:var(--tx); border:1px solid var(--bd); font-weight:500; font-size:13px; }
  .btn:disabled { opacity:.5; cursor:default; }
  .pasta { font-size:13px; font-weight:600; color:var(--mu); padding:4px 6px 0; display:flex; justify-content:space-between; }
  .caixa { overflow:auto; display:flex; flex-direction:column; gap:4px; }
  .fio { background:var(--card); border:1px solid var(--bd); border-radius:12px; padding:8px 10px; cursor:pointer; }
  .fio.on { outline:2px solid var(--pr); }
  .fio.novo b { font-weight:800; } .fio.novo { background:var(--prs); }
  .fio .l1 { display:flex; justify-content:space-between; gap:6px; font-size:12px; color:var(--mu); }
  .fio b { display:block; font-size:14px; font-weight:600; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .fio .prev { font-size:12.5px; color:var(--mu); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .vazio { color:var(--mu); padding:20px 12px; font-size:14px; text-align:center; }
  .painel { background:var(--card); border-radius:16px; display:flex; flex-direction:column; overflow:hidden; border:1px solid var(--bd); min-height:0; }
  .painel h2 { font-size:15px; margin:0; padding:12px 16px; border-bottom:1px solid var(--bd); background:var(--side); font-weight:600;
               overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .leitura { flex:1; overflow:auto; padding:12px 16px; display:flex; flex-direction:column; gap:10px; }
  .msg { border:1px solid var(--bd); border-radius:12px; padding:10px 14px; }
  .msg.eu { background:var(--side); }
  .msg .de { display:flex; justify-content:space-between; gap:8px; font-size:13px; color:var(--mu); margin-bottom:6px; }
  .msg .de b { color:var(--tx); }
  .msg .tx { white-space:pre-wrap; font-size:14.5px; }
  .sistema { align-self:center; font-size:12px; color:var(--mu); background:var(--side); padding:3px 10px; border-radius:8px; }
  .escrevendo { color:var(--mu); font-size:13px; }
  .resposta { border-top:1px solid var(--bd); padding:10px 16px 12px; display:flex; flex-direction:column; gap:8px; }
  .resposta textarea { font:inherit; font-size:14.5px; color:var(--tx); background:var(--card); border:1px solid var(--bd); border-radius:10px;
                       padding:10px; min-height:110px; resize:vertical; outline:none; }
  .resposta .linha { display:flex; gap:8px; align-items:center; flex-wrap:wrap; }
  #aviso { font-size:13px; color:var(--er); }
  .ia .corpo { padding:14px 16px; display:flex; flex-direction:column; gap:12px; overflow:auto; }
  .ia .s { color:var(--mu); font-size:13px; margin:0; }
  .rot { font-size:12px; color:var(--mu); text-transform:uppercase; letter-spacing:.04em; margin-bottom:4px; }
  .tags { display:flex; gap:6px; flex-wrap:wrap; }
  .chip { font-size:12.5px; padding:3px 9px; border-radius:10px; background:var(--side); }
  .chip.u-critica, .chip.u-alta, .chip.s-negativo { background:var(--ers); color:var(--er); }
  .chip.u-media { background:var(--was); color:var(--wa); }
  .chip.u-baixa, .chip.s-positivo { background:var(--oks); color:var(--ok); }
  .sugestao { border-left:3px solid var(--pr); background:var(--side); padding:10px 12px; border-radius:0 10px 10px 0; white-space:pre-wrap; font-size:14px; }
  .dot { display:inline-block; width:8px; height:8px; border-radius:50%; background:var(--pr); margin-right:6px; animation:pp 1s infinite; }
  @keyframes pp { 50% { opacity:.25; } }
  .ia a { color:var(--pr); font-size:13px; }
  @media (max-width: 1100px) { .app { grid-template-columns:minmax(0,1fr); height:auto; } .painel { min-height:360px; } .caixa { max-height:260px; } }
</style>
</head>
<body>
<header>
  <div class="logo"><svg viewBox="0 0 24 24" aria-hidden="true"><rect x="2" y="4" width="20" height="16" rx="3" fill="#0b57d0"/><path d="M3.5 6.5 12 13l8.5-6.5" stroke="#fff" stroke-width="2" fill="none"/></svg>Correio <small>atendimento@suaempresa.com.br</small></div>
  <nav class="abas" aria-label="Canais"><a href="/demo/whatsapp">WhatsApp</a><a href="/demo/instagram">Instagram</a><a href="/demo/email" class="on">E-mail</a></nav>
  <span class="tag-demo">AMBIENTE DE DEMONSTRAÇÃO · VOCÊ É O ATENDENTE</span>
</header>
<div class="app">
  <nav aria-label="Caixa de entrada">
    <div class="chamar">
      <label for="cenario">Situação do cliente (a IA escreve o e-mail)</label>
      <select id="cenario"><option value="">Sorteada</option></select>
      <button class="btn" type="button" id="novo">Receber e-mail de cliente</button>
    </div>
    <div class="pasta"><span>Caixa de entrada</span><span id="qtd"></span></div>
    <div class="caixa" id="caixa"><div class="vazio" id="caixa-vazia">Nenhum e-mail ainda.</div></div>
  </nav>

  <section class="painel" aria-label="Conversa">
    <h2 id="titulo">Selecione um e-mail</h2>
    <div class="leitura" id="leitura"><div class="vazio">Clique em <b>Receber e-mail de cliente</b>: a IA faz o papel do cliente e você responde como atendente.</div></div>
    <form class="resposta" id="f">
      <textarea id="corpo" maxlength="2000" placeholder="Responder ao cliente…" disabled></textarea>
      <div class="linha"><button class="btn" id="b" type="submit" disabled>Enviar resposta</button><span id="aviso" role="status"></span></div>
    </form>
  </section>

  <section class="painel ia" aria-label="Assistente de IA">
    <h2>Assistente de IA</h2>
    <div class="corpo" id="ia"><p class="s">Abra um e-mail: a IA mostra o assunto, a urgência, o prazo e uma resposta sugerida.</p></div>
  </section>
</div>
<script>
const $ = (id) => document.getElementById(id);
const ROT = { cobranca:'Cobrança', pagamento:'Pagamento', acesso:'Acesso', instabilidade:'Instabilidade', cancelamento:'Cancelamento',
  reclamacao:'Reclamação', duvida:'Dúvida', elogio:'Elogio', baixa:'baixa', media:'média', alta:'alta', critica:'crítica',
  positivo:'positivo', neutro:'neutro', negativo:'negativo', financeiro:'Financeiro', suporte_tecnico:'Suporte técnico',
  engenharia:'Engenharia', retencao:'Retenção', atendimento:'Atendimento' };
const r = (v) => ROT[v] || v || '—';
const prazo = (min) => min == null ? '' : min < 60 ? min + ' min' : (min / 60) + ' h';
function el(tag, cls, txt) { const e = document.createElement(tag); if (cls) e.className = cls; if (txt != null) e.textContent = txt; return e; }
const hora = () => new Date().toLocaleTimeString('pt-BR', { hour:'2-digit', minute:'2-digit' });

fetch('/demo/cenarios').then((x) => x.json()).then((lista) => lista.forEach((c) => {
  const o = el('option', null, c.titulo); o.value = c.chave; $('cenario').append(o); })).catch(() => {});

// Cada fio é uma conversa com um cliente simulado: { conversa, cliente, assunto, mensagens, encerrada, ticket, triagem, novo, esperando }
const fios = []; let aberto = null;

function desenharCaixa() {
  const c = $('caixa'); c.textContent = '';
  if (!fios.length) c.append(el('div', 'vazio', 'Nenhum e-mail ainda.'));
  fios.forEach((f) => {
    const ultima = f.mensagens[f.mensagens.length - 1];
    const it = el('div', 'fio' + (f.novo ? ' novo' : '') + (f === aberto ? ' on' : ''));
    const l1 = el('div', 'l1'); l1.append(el('span', null, f.cliente.nome), el('span', null, ultima ? ultima.hora : ''));
    it.append(l1, el('b', null, f.assunto), el('div', 'prev', f.esperando ? 'escrevendo…' : (ultima ? ultima.texto.replace(/\s+/g, ' ') : '')));
    it.addEventListener('click', () => abrir(f)); c.append(it);
  });
  const n = fios.filter((f) => f.novo).length; $('qtd').textContent = n ? n + ' não lido' + (n > 1 ? 's' : '') : '';
}

function abrir(f) {
  aberto = f; f.novo = false; $('aviso').textContent = '';
  $('titulo').textContent = f.assunto + ' — ' + f.cliente.nome;
  const l = $('leitura'); l.textContent = '';
  f.mensagens.forEach((m) => {
    const d = el('div', 'msg' + (m.de === 'eu' ? ' eu' : ''));
    const de = el('div', 'de'); const quem = el('span');
    quem.append(el('b', null, m.de === 'eu' ? 'Você (atendimento)' : f.cliente.nome), ' ' + (m.de === 'eu' ? '' : '<' + f.cliente.contato + '>'));
    de.append(quem, el('span', null, m.hora)); d.append(de, el('div', 'tx', m.texto)); l.append(d);
  });
  if (f.esperando) l.append(el('div', 'escrevendo', f.cliente.nome + ' está escrevendo uma resposta…'));
  if (f.encerrada) l.append(el('div', 'sistema', 'O cliente encerrou a conversa.'));
  l.scrollTop = l.scrollHeight;
  const pode = !f.encerrada && !f.esperando;
  $('corpo').disabled = !pode; $('b').disabled = !pode;
  painel(f); desenharCaixa();
}

function painel(f) {
  const c = $('ia'); c.textContent = '';
  if (!f.ticket) { c.append(el('p', 's', 'Esperando o cliente escrever…')); return; }
  const t = f.triagem;
  if (!t) { const a = el('div', 's'); a.append(el('span', 'dot'), 'Analisando o e-mail…'); c.append(a); return; }
  const bloco = (rot, conteudo) => { const d = el('div'); d.append(el('div', 'rot', rot), conteudo); c.append(d); };
  const tags = el('div', 'tags');
  tags.append(el('span', 'chip', r(t.assunto)), el('span', 'chip u-' + t.urgencia, 'urgência ' + r(t.urgencia)),
              el('span', 'chip s-' + t.sentimento, r(t.sentimento)), el('span', 'chip', '→ ' + r(t.equipe)));
  if (t.origem === 'fallback') tags.append(el('span', 'chip', 'plano B (regras)'));
  bloco('Ticket #' + t.ticket_id + ' · prazo da 1ª resposta: ' + prazo(t.sla.prazo_minutos), tags);
  if (t.resposta_sugerida) {
    const usar = el('button', 'btn sec', 'Usar sugestão'); usar.type = 'button'; usar.style.marginTop = '8px';
    usar.addEventListener('click', () => { if (!$('corpo').disabled) { $('corpo').value = t.resposta_sugerida; $('corpo').focus(); } });
    const d = el('div'); d.append(el('div', 'sugestao', t.resposta_sugerida), usar); bloco('Resposta sugerida (revise antes de enviar)', d);
  }
  if (t.exemplos) c.append(el('p', 's', '🧠 A IA aprendeu com tickets revisados parecidos: #' + t.exemplos.split(',').join(', #')));
  const link = el('a', null, 'Abrir o painel do atendimento ↗'); link.href = '/'; link.target = '_blank'; link.rel = 'noopener'; c.append(link);
}

async function acompanhar(f, ticket, n) {
  if (f.ticket !== ticket) return;
  try {
    const t = await (await fetch('/demo/conversas/' + f.conversa + '/tickets/' + ticket)).json();
    if (t.status && t.status !== 'pendente') { f.triagem = t; if (f === aberto) painel(f); return; }
  } catch (_) {}
  if (n < 40) setTimeout(() => acompanhar(f, ticket, n + 1), 1000);
}

function chegou(f, m) {
  f.esperando = false; f.mensagens.push({ de:'cliente', texto:m.texto, hora:hora() }); f.encerrada = m.encerrou;
  if (m.ticket_id) { f.ticket = m.ticket_id; f.triagem = null; acompanhar(f, m.ticket_id, 0); }
  if (f !== aberto) f.novo = true;
  // o fio com a mensagem mais nova sobe para o topo da caixa
  fios.splice(fios.indexOf(f), 1); fios.unshift(f);
  if (f === aberto) abrir(f); else desenharCaixa();
}

$('novo').addEventListener('click', async () => {
  $('novo').disabled = true; $('aviso').textContent = '';
  try {
    const resp = await fetch('/demo/email/conversas', { method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ cenario: $('cenario').value || null }) });
    const d = await resp.json();
    if (resp.status !== 201) throw new Error(d.detail || 'falha');
    const f = { conversa:d.conversa, cliente:d.cliente, assunto:d.mensagem.assunto || d.cenario, mensagens:[], encerrada:false,
                ticket:null, triagem:null, novo:true, esperando:false };
    fios.unshift(f); chegou(f, d.mensagem); if (!aberto) abrir(f);
  } catch (e) { $('aviso').textContent = 'Não foi possível receber um e-mail: ' + (e.message || 'API fora do ar?'); }
  finally { $('novo').disabled = false; }
});

$('f').addEventListener('submit', async (e) => {
  e.preventDefault();
  const f = aberto; const texto = $('corpo').value.trim(); $('aviso').textContent = '';
  if (!f || !texto || f.esperando || f.encerrada) return;
  f.mensagens.push({ de:'eu', texto, hora:hora() }); f.esperando = true; $('corpo').value = ''; abrir(f);
  try {
    const resp = await fetch('/demo/conversas/' + f.conversa + '/respostas', { method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ texto }) });
    const d = await resp.json();
    if (resp.status !== 200) throw new Error(d.detail || 'falha');
    chegou(f, d.mensagem);
  } catch (e) { f.esperando = false; if (f === aberto) abrir(f); $('aviso').textContent = 'Não foi possível enviar: ' + (e.message || 'API fora do ar?'); }
});
</script>
</body>
</html>
"""
