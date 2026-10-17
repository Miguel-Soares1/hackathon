"""Tela de demonstração do canal e-mail (só em desenvolvimento).

Simula um webmail: o apresentador escreve um e-mail fictício e clica em Enviar. O servidor monta um e-mail
de verdade (RFC 5322) e passa pelo MESMO conversor do leitor IMAP (`canais.email_para_mensagem`), então o
ticket nasce exatamente como nasceria de um e-mail real: canal `email`, cliente = remetente, texto = assunto + corpo.
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
  header { display:flex; align-items:center; gap:12px; padding:10px 16px; }
  .logo { display:flex; align-items:center; gap:8px; font-size:20px; font-weight:600; }
  .logo svg { width:28px; height:28px; }
  .busca { flex:1; max-width:640px; margin-left:24px; background:var(--side); border-radius:24px; padding:10px 18px; color:var(--mu); font-size:14px; }
  .abas { display:flex; gap:4px; background:var(--card); border:1px solid var(--bd); border-radius:20px; padding:3px; }
  .abas a { padding:5px 14px; border-radius:16px; color:var(--mu); text-decoration:none; font-size:13px; font-weight:600; }
  .abas a.on { background:var(--pr); color:#fff; }
  .tag-demo { margin-left:auto; font-size:12px; font-weight:600; color:var(--wa); background:var(--was); padding:4px 10px; border-radius:12px; }
  .app { display:grid; grid-template-columns:220px 1fr 380px; gap:12px; padding:0 12px 12px; height:calc(100vh - 60px); }
  nav { padding:4px 0; }
  .escrever { display:inline-flex; align-items:center; gap:10px; background:var(--prs); color:var(--tx); border:0; border-radius:16px;
              padding:16px 22px; font:inherit; font-weight:600; cursor:pointer; margin-bottom:12px; }
  nav a { display:flex; justify-content:space-between; padding:6px 16px; border-radius:0 16px 16px 0; color:var(--tx); text-decoration:none; font-size:14px; }
  nav a.on { background:var(--prs); font-weight:600; }
  .painel { background:var(--card); border-radius:16px; display:flex; flex-direction:column; overflow:hidden; border:1px solid var(--bd); }
  .painel h2 { font-size:15px; margin:0; padding:12px 16px; border-bottom:1px solid var(--bd); background:var(--side); font-weight:600; }
  .campo { display:flex; align-items:center; border-bottom:1px solid var(--bd); padding:0 16px; }
  .campo span { color:var(--mu); font-size:14px; width:64px; flex:none; }
  .campo input { flex:1; border:0; background:transparent; color:inherit; font:inherit; padding:11px 0; outline:none; }
  textarea { flex:1; border:0; resize:none; background:transparent; color:inherit; font:inherit; padding:14px 16px; outline:none; min-height:180px; }
  .rodape { display:flex; align-items:center; gap:10px; padding:12px 16px; border-top:1px solid var(--bd); flex-wrap:wrap; }
  .enviar { background:var(--pr); color:#fff; border:0; border-radius:20px; padding:10px 26px; font:inherit; font-weight:600; cursor:pointer; }
  @media (prefers-color-scheme: dark) { .enviar { color:#0b1a33; } }
  .enviar:disabled { opacity:.55; cursor:default; }
  .modelos { display:flex; gap:6px; flex-wrap:wrap; margin-left:auto; }
  .modelos button { border:1px solid var(--bd); background:transparent; color:var(--mu); border-radius:14px; padding:5px 10px; font:inherit; font-size:12px; cursor:pointer; }
  .modelos button:hover { color:var(--tx); border-color:var(--mu); }
  #aviso { padding:0 16px 10px; font-size:13px; min-height:18px; }
  .er { color:var(--er); } .okt { color:var(--ok); }
  .lista { overflow:auto; flex:1; }
  .vazio { color:var(--mu); padding:24px 16px; font-size:14px; text-align:center; }
  .item { padding:12px 16px; border-bottom:1px solid var(--bd); animation:entra .35s ease-out; }
  @keyframes entra { from { background:var(--prs); } to { background:transparent; } }
  .item .l1 { display:flex; justify-content:space-between; gap:8px; font-size:13px; color:var(--mu); }
  .item .as { font-weight:600; margin:2px 0 6px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .prev { font-size:13px; color:var(--mu); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .item.novo { background:var(--prs); }
  .item.novo .as { font-weight:700; }
  .item { cursor:pointer; }
  .item.aberto .prev { white-space:pre-wrap; overflow:visible; color:var(--tx); font-size:14px; margin-top:6px; }
  .item .acoes { display:none; margin-top:10px; }
  .item.aberto .acoes { display:block; }
  .item .acoes button { font:inherit; font-size:13px; border:1px solid var(--bd); background:var(--card); color:var(--tx); border-radius:16px; padding:5px 14px; cursor:pointer; }
  .chegando { color:var(--mu); font-size:13px; padding:10px 16px; border-bottom:1px solid var(--bd); }
  @media (max-width: 980px) { .app { grid-template-columns:1fr; height:auto; } nav, .busca { display:none; } .painel { min-height:340px; } }
</style>
</head>
<body>
<header>
  <div class="logo"><svg viewBox="0 0 24 24" aria-hidden="true"><rect x="2" y="4" width="20" height="16" rx="3" fill="#0b57d0"/><path d="M3.5 6.5 12 13l8.5-6.5" stroke="#fff" stroke-width="2" fill="none"/></svg>Correio</div>
  <div class="busca">Pesquisar e-mails</div>
  <nav class="abas" aria-label="Canais"><a href="/demo/whatsapp">WhatsApp</a><a href="/demo/instagram">Instagram</a><a href="/demo/email" class="on">E-mail</a></nav>
  <span class="tag-demo">AMBIENTE DE DEMONSTRAÇÃO</span>
</header>
<div class="app">
  <nav>
    <button class="escrever" id="novo" type="button"><svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true"><path d="M3 17.25V21h3.75L17.8 9.94l-3.75-3.75L3 17.25zM20.7 7.04a1 1 0 0 0 0-1.41l-2.34-2.34a1 1 0 0 0-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z" fill="currentColor"/></svg>Escrever</button>
    <a href="#" data-pasta="entrada">Caixa de entrada <span id="qtd-entrada"></span></a>
    <a href="#" data-pasta="enviados" class="on">Enviados <span id="qtd">0</span></a>
    <a href="#">Rascunhos <span></span></a>
  </nav>

  <section class="painel" aria-label="Nova mensagem">
    <h2>Nova mensagem</h2>
    <form id="f" novalidate style="display:flex;flex-direction:column;flex:1">
      <label class="campo"><span>De</span><input id="nome" placeholder="Nome do cliente" maxlength="80" style="max-width:40%"><input id="de" type="email" placeholder="cliente@exemplo.com" maxlength="120"></label>
      <label class="campo"><span>Para</span><input id="para" value="atendimento@suaempresa.com.br" maxlength="120"></label>
      <label class="campo"><span>Assunto</span><input id="assunto" maxlength="200"></label>
      <textarea id="corpo" maxlength="3500" placeholder="Escreva a mensagem do cliente…"></textarea>
      <div id="aviso" role="status" aria-live="polite"></div>
      <div class="rodape">
        <button class="enviar" id="b" type="submit">Enviar</button>
        <div class="modelos" aria-label="Exemplos prontos">
          <button type="button" data-m="0">Cobrança duplicada</button>
          <button type="button" data-m="1">Pix não caiu</button>
          <button type="button" data-m="2">Conta bloqueada</button>
          <button type="button" data-m="3">Elogio</button>
        </div>
      </div>
    </form>
  </section>

  <section class="painel" aria-label="Pasta">
    <h2 id="titulo-pasta">Enviados</h2>
    <div class="lista" id="lista"></div>
  </section>
</div>
<script>
const $ = (id) => document.getElementById(id);
const PESSOAS = [["Mariana Souza","mariana.souza"],["Carlos Lima","carlos.lima"],["Ana Ribeiro","ana.ribeiro"],["João Pereira","joao.pereira"],
                 ["Beatriz Costa","bia.costa"],["Rafael Gomes","rafael.gomes"],["Luana Martins","luana.m"],["Pedro Alves","pedro.alves"]];
const MODELOS = [
  ["Cobrança duplicada", "Olá,\n\nFui cobrado duas vezes na fatura deste mês, o mesmo valor de R$ 89,90 aparece em duplicidade. Já é a segunda vez que isso acontece e estou bem insatisfeito. Quero o estorno o quanto antes.\n\nAguardo retorno."],
  ["Pix não caiu", "Bom dia,\n\nFiz um Pix ontem às 15h e até agora o dinheiro não caiu na conta de destino. Preciso desse valor hoje para pagar um boleto que vence. Por favor, me ajudem com urgência."],
  ["Não consigo entrar - conta bloqueada", "Olá, desde hoje cedo não consigo entrar no aplicativo. Aparece a mensagem de conta bloqueada e não recebo o código de verificação. O que está acontecendo?"],
  ["Parabéns pelo atendimento", "Oi! Só queria agradecer pelo atendimento de ontem, a atendente resolveu meu problema rapidinho. Muito obrigado!"],
];
let ultimo = -1;
function novaPessoa() { let i; do { i = Math.floor(Math.random() * PESSOAS.length); } while (i === ultimo); ultimo = i;
  $('nome').value = PESSOAS[i][0]; $('de').value = PESSOAS[i][1] + '@exemplo.com'; }
function limpar() { $('assunto').value = ''; $('corpo').value = ''; $('aviso').textContent = ''; novaPessoa(); $('assunto').focus(); }
document.querySelectorAll('[data-m]').forEach((b) => b.addEventListener('click', () => {
  const m = MODELOS[+b.dataset.m]; novaPessoa(); $('assunto').value = m[0]; $('corpo').value = m[1]; }));
$('novo').addEventListener('click', limpar);
novaPessoa();

function el(tag, cls, txt) { const e = document.createElement(tag); if (cls) e.className = cls; if (txt != null) e.textContent = txt; return e; }
const hora = () => new Date().toLocaleTimeString('pt-BR', { hour:'2-digit', minute:'2-digit' });
const pausa = (ms) => new Promise((r) => setTimeout(r, ms));
const EQUIPES = { financeiro:'Financeiro', suporte_tecnico:'Suporte Técnico', engenharia:'Engenharia', retencao:'Retenção', atendimento:'Atendimento' };
const REMETENTE = 'Atendimento Sua Empresa';

// O webmail é a caixa do cliente: o que ele envia vai para "Enviados" e as respostas da empresa chegam na "Caixa de entrada".
const caixa = { entrada: [], enviados: [] };
let pasta = 'enviados'; let chegando = 0;

function abrirPasta(nome) {
  pasta = nome;
  document.querySelectorAll('nav a[data-pasta]').forEach((a) => a.classList.toggle('on', a.dataset.pasta === nome));
  $('titulo-pasta').textContent = nome === 'entrada' ? 'Caixa de entrada' : 'Enviados';
  desenhar();
}
document.querySelectorAll('nav a[data-pasta]').forEach((a) => a.addEventListener('click', (e) => { e.preventDefault(); abrirPasta(a.dataset.pasta); }));

function desenhar() {
  const l = $('lista'); l.textContent = '';
  if (pasta === 'entrada' && chegando > 0) l.append(el('div', 'chegando', 'Sincronizando… novas mensagens a caminho'));
  const itens = caixa[pasta];
  if (!itens.length) l.append(el('div', 'vazio', pasta === 'entrada' ? 'Nenhuma mensagem recebida ainda.' : 'Nenhum e-mail enviado ainda.'));
  itens.forEach((m) => {
    const it = el('div', 'item' + (m.novo ? ' novo' : '') + (m.aberto ? ' aberto' : ''));
    const l1 = el('div', 'l1'); l1.append(el('span', null, pasta === 'entrada' ? m.de : 'Para: ' + m.para), el('span', null, m.hora));
    it.append(l1, el('div', 'as', m.assunto || '(sem assunto)'), el('div', 'prev', m.corpo));
    if (pasta === 'entrada' && m.responder) {
      const ac = el('div', 'acoes'); const b = el('button', null, '↩ Responder'); b.type = 'button';
      b.addEventListener('click', (e) => { e.stopPropagation(); responderEmail(m); }); ac.append(b); it.append(ac);
    }
    it.addEventListener('click', () => { m.aberto = !m.aberto; m.novo = false; desenhar(); });
    l.append(it);
  });
  const naoLidas = caixa.entrada.filter((m) => m.novo).length;
  $('qtd-entrada').textContent = naoLidas || ''; $('qtd').textContent = caixa.enviados.length;
}

function receber(m) {
  caixa.entrada.unshift({ ...m, de: REMETENTE, hora: hora(), novo: true });
  const a = $('aviso'); a.className = 'okt'; a.textContent = 'Nova mensagem na Caixa de entrada: ' + m.assunto;
  desenhar();
}

// A conversa continua no mesmo fio: "Re:" no assunto e o mesmo cliente como remetente.
function responderEmail(m) {
  $('nome').value = m.responder.nome || ''; $('de').value = m.responder.email;
  $('assunto').value = /^re:/i.test(m.responder.assunto) ? m.responder.assunto : 'Re: ' + m.responder.assunto;
  $('corpo').value = ''; $('aviso').textContent = ''; $('corpo').focus();
}

// A empresa responde como na vida real: confirmação automática com protocolo e, em seguida,
// a resposta do atendimento, escrita a partir do que o cliente escreveu.
async function acompanhar(d, dados) {
  const fio = { nome: dados.de_nome, email: dados.de_email, assunto: dados.assunto || '(sem assunto)' };
  const base = fio.assunto.replace(/^(re:\s*)+/i, '');
  const nome = (dados.de_nome || '').split(' ')[0];
  chegando += 1; desenhar();
  const inicio = Date.now();
  try {
    if (!/^re:/i.test(dados.assunto)) {
      await pausa(1500);
      receber({ assunto: '[Protocolo #' + d.ticket_id + '] Recebemos sua solicitação', responder: fio,
        corpo: 'Olá' + (nome ? ', ' + nome : '') + '!\n\nRecebemos sua mensagem sobre "' + base + '" e abrimos o protocolo #' + d.ticket_id +
               '. Um atendente vai responder por este e-mail.\n\nEsta é uma resposta automática.\n' + REMETENTE });
    }
    let r = null;
    for (let n = 0; n < 60 && !(r && r.respondida); n++) {
      try { r = await (await fetch('/demo/conversa/' + d.ticket_id + '?senha=' + encodeURIComponent(d.senha))).json(); } catch (_) {}
      if (!(r && r.respondida)) await pausa(1000);
    }
    await pausa(Math.max(0, 3000 - (Date.now() - inicio)));
    if (r && r.respondida) {
      const time = EQUIPES[r.equipe] ? '\n\nAtenciosamente,\nTime ' + EQUIPES[r.equipe] + ' · ' + REMETENTE : '\n\n' + REMETENTE;
      receber({ assunto: 'Re: ' + base + ' [Protocolo #' + d.ticket_id + ']', corpo: r.resposta + time, responder: fio });
    }
  } finally { chegando -= 1; desenhar(); }
}

$('f').addEventListener('submit', async (e) => {
  e.preventDefault();
  const a = $('aviso'); a.className = ''; a.textContent = '';
  const dados = { de_nome: $('nome').value.trim() || null, de_email: $('de').value.trim(), para: $('para').value.trim(),
                  assunto: $('assunto').value.trim(), corpo: $('corpo').value.trim() };
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(dados.de_email)) { a.className = 'er'; a.textContent = 'Informe um remetente válido.'; return; }
  if ((dados.assunto + dados.corpo).length < 10) { a.className = 'er'; a.textContent = 'Escreva o assunto e a mensagem.'; return; }
  $('b').disabled = true;
  try {
    const resp = await fetch('/demo/email', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(dados) });
    const d = await resp.json().catch(() => ({}));
    if (resp.status === 202) {
      a.className = 'okt'; a.textContent = 'Mensagem enviada.';
      caixa.enviados.unshift({ para: dados.para, assunto: dados.assunto, corpo: dados.corpo, hora: hora() });
      desenhar(); acompanhar(d, dados);
      $('assunto').value = ''; $('corpo').value = '';  // mesmo cliente: a conversa continua com ele ("Escrever" troca)
    }
    else { a.className = 'er'; a.textContent = d.detail || 'Não foi possível enviar.'; }
  } catch (_) { a.className = 'er'; a.textContent = 'API fora do ar? Confira o terminal do uvicorn.'; }
  finally { $('b').disabled = false; }
});
desenhar();
</script>
</body>
</html>
"""
