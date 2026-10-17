"""Telas de demonstração dos canais de conversa: WhatsApp e Instagram Direct (só em desenvolvimento).

O apresentador "conversa" como cliente numa tela de celular. O servidor monta o MESMO JSON que a Meta enviaria
ao webhook e passa pelo MESMO conversor do canal real (`canais.mensagens_whatsapp` / `canais.mensagens_instagram`),
então o ticket nasce exatamente como nasceria de uma mensagem real.
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
  .b.ele .h { text-align:left; }
  .b .t.lido { color:var(--tick); opacity:1; }
  [data-canal=instagram] .b.eu .h { display:none; }
  .chips { display:flex; gap:6px; overflow-x:auto; padding:8px 10px 0; background:var(--fundo); scrollbar-width:none; }
  .chips button { flex:none; font:inherit; font-size:12px; border:1px solid var(--bd); background:var(--card); color:var(--tx); border-radius:14px; padding:5px 10px; cursor:pointer; }
  form { display:flex; gap:8px; padding:8px 10px 10px; background:var(--fundo); align-items:flex-end; }
  textarea { flex:1; resize:none; font:inherit; font-size:15px; color:var(--tx); background:var(--card); border:1px solid var(--bd); border-radius:22px; padding:10px 14px; max-height:120px; outline:none; }
  .env { width:44px; height:44px; border-radius:50%; border:0; background:var(--acento); color:#fff; display:grid; place-items:center; cursor:pointer; flex:none; }
  .env:disabled { opacity:.5; }
  #aviso { font-size:12px; color:var(--er); padding:0 14px 6px; background:var(--fundo); min-height:4px; }

  .app > * { min-width:0; }
  .no-cel { font-size:13px; font-weight:600; color:var(--acento); text-decoration:none; }
  @media (max-width: 820px) { .app { padding:0 16px 16px; } .topo { padding:12px 16px; } .celular { border-width:8px; } .celular { height:600px; } }
  /* Aberta no próprio celular: a tela inteira vira o app de conversa, sem a moldura de aparelho. */
  @media (max-width: 520px) {
    .topo { padding:8px 10px; gap:8px; } .topo h1, .tag-demo, .no-cel { display:none; } .abas { width:100%; } .abas a { flex:1; text-align:center; }
    .app { padding:0; max-width:none; } .quem { padding:0 10px; margin-bottom:6px; }
    .celular { border:0; border-radius:0; box-shadow:none; min-height:0; height:calc(100dvh - 92px); }
    textarea { font-size:16px; }  /* 16px evita o zoom automático do iPhone ao focar */
  }
</style>
</head>
<body>
<div class="topo">
  <h1>Simulador de canais</h1>
  <nav class="abas"><a href="/demo/whatsapp" data-c="whatsapp">WhatsApp</a><a href="/demo/instagram" data-c="instagram">Instagram</a><a href="/demo/email" data-c="email">E-mail</a></nav>
  <a class="no-cel" href="/demo/celular">📱 Abrir no celular</a>
  <span class="tag-demo">AMBIENTE DE DEMONSTRAÇÃO</span>
</div>
<div class="app">
  <div>
    <div class="quem"><span>Cliente:</span><select id="pessoa" aria-label="Cliente simulado"></select><button type="button" id="outro">Outro cliente</button></div>
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
$('sub').textContent = CANAL === 'whatsapp' ? 'Conta comercial · online' : 'sua.empresa · Ativo agora';

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
// Conversa de cada cliente simulado nesta aba: mensagens na tela e o ticket no servidor (ticket, senha, última vista).
const conversas = {};
const conversa = () => { const p = PESSOAS[+$('pessoa').value]; return conversas[p[1]] || (conversas[p[1]] = { msgs: [], ticket: null }); };
function trocar(i) {
  $('pessoa').value = i; const c = $('chat'); c.textContent = ''; const d = document.createElement('div'); d.className = 'dia'; d.textContent = 'Hoje'; c.append(d);
  conversa().msgs.forEach((m) => desenharBolha(m)); c.scrollTop = c.scrollHeight;
}
$('pessoa').addEventListener('change', () => trocar($('pessoa').value));
$('outro').addEventListener('click', () => trocar((+$('pessoa').value + 1 + Math.floor(Math.random() * (PESSOAS.length - 1))) % PESSOAS.length));
trocar(Math.floor(Math.random() * PESSOAS.length));
document.querySelectorAll('[data-m]').forEach((b) => b.addEventListener('click', () => { $('texto').value = MODELOS[+b.dataset.m]; $('texto').focus(); }));
$('texto').addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); $('f').requestSubmit(); } });

function el(tag, cls, txt) { const e = document.createElement(tag); if (cls) e.className = cls; if (txt != null) e.textContent = txt; return e; }
const hora = () => new Date().toLocaleTimeString('pt-BR', { hour:'2-digit', minute:'2-digit' });
const rolar = () => { const c = $('chat'); c.scrollTop = c.scrollHeight; };

function desenharBolha(m) {
  const b = el('div', 'b ' + m.de, m.texto); const h = el('span', 'h', m.hora + ' ');
  if (m.de === 'eu') { m.tick = el('span', 't' + (m.lido ? ' lido' : ''), m.estado); h.append(m.tick); }
  b.append(h); $('chat').append(b); return m;
}
function bolha(texto) {
  const m = { de: 'eu', texto, hora: hora(), estado: '✓' };
  conversa().msgs.push(m); desenharBolha(m); rolar();
  return { set textContent(v) { m.estado = v; if (m.tick) m.tick.textContent = v; } };
}

// Respostas que o atendente envia pelo painel (Atendimento) chegam aqui, como no canal real (ADR-016).
const urlConversa = (c) => '/demo/conversa/' + c.ticket + '?senha=' + encodeURIComponent(c.senha) + '&depois_de=' + c.ultimo;
async function lembrarTicket(c, d) {
  if (c.ticket === d.ticket_id) return;
  let ultimo = 0;  // cliente que já tinha conversa aberta no servidor: não repete respostas antigas
  if (d.status === 'anexada') { try { ultimo = (await (await fetch(urlConversa({ ticket: d.ticket_id, senha: d.senha, ultimo: 0 }))).json()).ultimo_id || 0; } catch (_) {} }
  Object.assign(c, { ticket: d.ticket_id, senha: d.senha, ultimo });
}
let buscando = false;
async function buscarRespostas() {
  if (buscando) return;
  buscando = true;
  try {
    for (const [contato, c] of Object.entries(conversas)) {
      if (!c.ticket) continue;
      try {
        const r = await (await fetch(urlConversa(c))).json();
        if (r.ultimo_id != null) c.ultimo = r.ultimo_id;
        if (!r.atendente || !r.atendente.length) continue;
        c.msgs.forEach((m) => { if (m.de === 'eu') { m.lido = true; m.estado = '✓✓'; } });
        r.atendente.forEach((x) => c.msgs.push({ de: 'ele', texto: x.texto, hora: hora() }));
        if (contato === PESSOAS[+$('pessoa').value][1]) trocar($('pessoa').value);
      } catch (_) {}
    }
  } finally { buscando = false; }
}
setInterval(buscarRespostas, 3000);

$('f').addEventListener('submit', async (e) => {
  e.preventDefault();
  const texto = $('texto').value.trim(); $('aviso').textContent = '';
  if (texto.length < 3) return;
  const p = PESSOAS[+$('pessoa').value];
  const tick = bolha(texto); $('texto').value = ''; $('b').disabled = true;
  try {
    const resp = await fetch('/demo/' + CANAL, { method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ remetente: p[1], nome: CANAL === 'whatsapp' ? p[0] : null, texto }) });
    const d = await resp.json().catch(() => ({}));
    if (resp.status === 202) {
      tick.textContent = '✓✓';  // entregue
      await lembrarTicket(conversas[p[1]], d);
    } else { tick.textContent = '!'; $('aviso').textContent = d.detail || 'Não foi possível enviar.'; }
  } catch (_) { tick.textContent = '!'; $('aviso').textContent = 'API fora do ar? Confira o terminal do uvicorn.'; }
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
