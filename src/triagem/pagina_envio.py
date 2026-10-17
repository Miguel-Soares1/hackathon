"""Página pública de envio de solicitações (HTML autocontido, sem dependências externas)."""

PAGINA_ENVIO = """<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Fale com a gente</title>
<style>
  :root { --bg:#f4f7fb; --card:#fff; --tx:#0f1b2d; --mu:#5d6b82; --pr:#1666d6; --bd:#dde4ee; --ok:#1e8e3e; --er:#d93025; color-scheme: light dark; }
  @media (prefers-color-scheme: dark) { :root { --bg:#0c1422; --card:#141f33; --tx:#e8eef8; --mu:#93a2bb; --pr:#5b9bff; --bd:#25324a; --ok:#5fd081; --er:#ff6b60; } }
  * { box-sizing: border-box; }
  body { margin:0; background:var(--bg); color:var(--tx); font:16px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; padding:16px; }
  main { max-width:560px; margin:24px auto; background:var(--card); border:1px solid var(--bd); border-radius:14px; padding:20px; }
  h1 { font-size:22px; margin:0 0 4px; } p.s { color:var(--mu); margin:0 0 16px; font-size:14px; }
  label { display:block; font-weight:600; margin:14px 0 6px; font-size:14px; }
  input[type=text], textarea { width:100%; font:inherit; color:inherit; background:transparent; border:1px solid var(--bd); border-radius:10px; padding:10px 12px; }
  textarea { min-height:140px; resize:vertical; }
  input:focus, textarea:focus, button:focus-visible { outline:2px solid var(--pr); outline-offset:1px; }
  button { margin-top:16px; width:100%; font:inherit; font-weight:600; color:#fff; background:var(--pr); border:0; border-radius:10px; padding:12px; cursor:pointer; }
  button:disabled { opacity:.6; cursor:default; }
  .c { text-align:right; color:var(--mu); font-size:12px; margin-top:4px; }
  #msg { margin-top:14px; font-size:15px; } .ok { color:var(--ok); } .er { color:var(--er); }
  .hp { position:absolute; left:-9999px; width:1px; height:1px; overflow:hidden; }
  small { display:block; margin-top:14px; color:var(--mu); font-size:12px; }
</style>
</head>
<body>
<main>
  <h1>Fale com a gente</h1>
  <p class="s">Descreva o seu problema ou dúvida. Nossa equipe responde o quanto antes.</p>
  <form id="f" novalidate>
    <label for="cliente">Seu nome (opcional)</label>
    <input type="text" id="cliente" name="cliente" maxlength="120" autocomplete="name">
    <label for="texto">Mensagem</label>
    <textarea id="texto" name="texto" maxlength="1000" required></textarea>
    <div class="c"><span id="n">0</span>/1000</div>
    <div class="hp" aria-hidden="true"><label for="website">Não preencha</label><input type="text" id="website" name="website" tabindex="-1" autocomplete="off"></div>
    <button id="b" type="submit">Enviar</button>
    <div id="msg" role="status" aria-live="polite"></div>
  </form>
  <small>Não envie senhas, números de cartão ou outros dados sensíveis. O texto é analisado por inteligência artificial para direcionar o atendimento.</small>
</main>
<script>
const f = document.getElementById('f'), t = document.getElementById('texto'), m = document.getElementById('msg'), b = document.getElementById('b');
t.addEventListener('input', () => { document.getElementById('n').textContent = t.value.length; });
f.addEventListener('submit', async (e) => {
  e.preventDefault();
  m.className = ''; m.textContent = '';
  if (t.value.trim().length < 10) { m.className = 'er'; m.textContent = 'Escreva pelo menos 10 caracteres.'; return; }
  b.disabled = true;
  try {
    const r = await fetch(new URL('public/mensagens', location.href), {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ texto: t.value, cliente: document.getElementById('cliente').value || null, website: document.getElementById('website').value })
    });
    const d = await r.json().catch(() => ({}));
    if (r.status === 202) { m.className = 'ok'; m.textContent = 'Recebemos sua mensagem. Protocolo: ' + (d.protocolo || '—'); f.reset(); document.getElementById('n').textContent = '0'; }
    else if (r.status === 429) { m.className = 'er'; m.textContent = 'Muitas mensagens em pouco tempo. Tente novamente em instantes.'; }
    else { m.className = 'er'; m.textContent = 'Não foi possível enviar. Confira o texto e tente novamente.'; }
  } catch (_) { m.className = 'er'; m.textContent = 'Falha de conexão. Tente novamente.'; }
  finally { b.disabled = false; }
});
</script>
</body>
</html>
"""
