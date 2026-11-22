/* Momentum2 — вытащить все flag{...} из style.css и других статик */
(async () => {
  const list = [
    '/static/style.css', '/static/app.js', '/', '/profile', '/trade', '/login',
    '/static/style.css?v=1', '/robots.txt', '/sitemap.xml', '/.well-known/security.txt',
    '/favicon.ico', '/static/fonts.css', '/static/theme.css', '/static/main.css',
  ];
  const seen = new Set();
  for (const p of list) {
    try {
      const r = await fetch(p, { credentials: 'include' });
      const t = await r.text();
      const flags = [...new Set(t.match(/flag\{[^}]{0,200}\}/g) || [])];
      const notes = [...new Set(t.match(/\/\*[\s\S]{0,300}?\*\//g) || [])].slice(0, 3);
      console.log('%c' + p.padEnd(26) + '%c' + r.status + '  ' + t.length + ' b' +
        (flags.length ? '  ' + flags.join(' ') : ''),
        'color:#0a0;font-weight:bold', 'color:inherit');
      flags.forEach(f => seen.add(f));
      if (p === '/static/style.css' && t.length) {
        console.log('--- первые 1200 символов style.css ---');
        console.log(t.slice(0, 1200));
        console.log('--- конец файла ---');
        console.log(t.slice(-800));
      }
    } catch (e) { console.log(p, 'ERR', e.message); }
  }
  console.log('%cВСЕ ФЛАГИ: ' + (seen.size ? [...seen].join('  ') : 'не найдено'),
    'color:#0a0;font-size:15px;font-weight:bold');
})();
