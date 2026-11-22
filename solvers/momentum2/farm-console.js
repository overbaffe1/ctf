/* Momentum2 — спокойный фарм в консоли браузера.
 *
 * Вставить целиком на странице задачи (/profile или /trade), затем:
 *   FARM.start()                 // 6 потоков, без паузы
 *   FARM.start({workers:4})      // 4 потока — совсем тихо
 *   FARM.start({pause:50})       // пауза 50 мс между сделками
 *   FARM.stop()                  // остановить
 *   FARM.status()                // цифры в консоль
 *
 * Плашка в правом верхнем углу показывает: время, сделки, сделок/с, баланс,
 * остаток до 250 000 и сколько ждать. На цели сам вызывает /profile/buy.
 */
(() => {
  if (window.FARM && window.FARM.__v === 3) {
    console.log('%cFARM уже загружен, версия 3', 'color:#0a0');
    return;
  }

  const TARGET = 250000;         // рублей
  const HUD_ID = 'farm-hud';
  const sleep = ms => new Promise(r => setTimeout(r, ms));

  const S = {
    __v: 3,
    running: false,
    stop: false,
    started: 0,
    trades: 0,
    wins: 0,
    errors: {},
    balance: null,        // рубли
    peak: 0,
    lastError: '',
    flags: [],
    startedTip: '',
  };

  // ---------- плашка ----------

  function hud() {
    let d = document.getElementById(HUD_ID);
    if (d) return d;
    d = document.createElement('div');
    d.id = HUD_ID;
    Object.assign(d.style, {
      position: 'fixed', top: '10px', right: '10px', zIndex: 2147483647,
      background: 'rgba(12,16,22,.93)', color: '#d8e2ee', padding: '10px 14px',
      font: '13px/1.5 ui-monospace,Consolas,monospace', borderRadius: '8px',
      border: '1px solid #2a3543', boxShadow: '0 6px 24px rgba(0,0,0,.45)',
      maxWidth: '340px', whiteSpace: 'pre', pointerEvents: 'none',
    });
    document.body.appendChild(d);
    return d;
  }

  function hhmmss(sec) {
    if (!isFinite(sec) || sec < 0) return '?';
    if (sec > 86400 * 2) return '> 2 сут';
    sec = Math.round(sec);
    const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
    return h ? `${h} ч ${String(m).padStart(2, '0')} мин` : `${m} мин ${String(s).padStart(2, '0')} с`;
  }

  function render() {
    const d = hud();
    const el = S.started ? (Date.now() - S.started) / 1000 : 0;
    const rps = el > 1 ? S.trades / el : 0;
    const bal = S.balance === null ? '?' : S.balance;
    const left = S.balance === null ? null : Math.max(0, TARGET - S.balance);
    const eta = (rps > 0.05 && left !== null) ? left / rps : null;

    let txt =
      (S.running ? '▶ ФАРМ ИДЁТ' : '■ остановлен') + '   v3\n' +
      `время      ${hhmmss(el)}\n` +
      `сделок     ${S.trades}   (${rps.toFixed(1)} в сек)\n` +
      `выигрышей  ${S.wins}\n` +
      `баланс     ${bal} ₽${S.peak ? `  (пик ${S.peak})` : ''}\n`;
    if (left !== null) txt += `осталось   ${left} ₽\n`;
    txt += `ждать      ${eta === null ? '?' : '~' + hhmmss(eta)}\n`;
    const errs = Object.entries(S.errors).sort((a, b) => b[1] - a[1]).slice(0, 2);
    if (errs.length) txt += 'ошибки     ' + errs.map(([k, v]) => `${v}× ${k}`).join('\n           ') + '\n';
    if (S.flags.length) txt += '\nФЛАГ: ' + S.flags.join(' ') + '\n';
    if (!S.running && S.startedTip) txt += '\n' + S.startedTip;

    d.textContent = txt;
  }

  // ---------- запросы ----------

  function note(obj) {
    const e = String(obj.error || obj.message || '').trim();
    if (!e) return;
    S.errors[e] = (S.errors[e] || 0) + 1;
    S.lastError = e;
    if (/недостаточно|войд|сумм|баланс/i.test(e)) S.stop = true;
  }

  async function trade() {
    const body = new URLSearchParams({
      asset: 'RUB/USD', direction: 'up', amount: '1', multiplier: '1.01',
    });
    const r = await fetch('/trade', {
      method: 'POST', credentials: 'include',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded', accept: '*/*' },
      body,
    });
    let j = null;
    try { j = await r.json(); } catch (e) { /* html или пусто */ }
    if (!j) { S.errors['не JSON: ' + r.status] = (S.errors['не JSON: ' + r.status] || 0) + 1; return; }
    if ('won' in j) {
      S.trades++;
      if (j.won) S.wins++;
      if (typeof j.balance === 'number') {
        S.balance = Math.floor(j.balance / 100);
        if (S.balance > S.peak) S.peak = S.balance;
      }
    } else {
      note(j);
    }
  }

  async function refreshBalance() {
    try {
      const r = await fetch('/profile', { credentials: 'include' });
      const t = await r.text();
      const m = t.replace(/\\u([0-9a-f]{4})/gi, (_, h) => String.fromCharCode(parseInt(h, 16)))
                 .match(/([\d][\d\s\u00a0]{0,14})\s*(?:₽|руб)/);
      if (m) {
        S.balance = parseInt(m[1].replace(/[^\d]/g, ''), 10);
        if (S.balance > S.peak) S.peak = S.balance;
      }
    } catch (e) { /* игнорируем */ }
  }

  async function buy() {
    try {
      const r = await fetch('/profile/buy', { method: 'POST', credentials: 'include' });
      const t = await r.text();
      const j = t.replace(/\\u([0-9a-f]{4})/gi, (_, h) => String.fromCharCode(parseInt(h, 16)));
      const f = j.match(/flag\{[^}]+\}/g) || [];
      S.flags = [...new Set(f)];
      console.log('%cПОКУПКА -> ' + r.status, 'color:#0a0;font-weight:bold');
      console.log(S.flags.length ? 'ФЛАГИ: ' + S.flags.join(' ') : j.replace(/<[^>]+>/g, ' ').slice(0, 300));
      if (!S.flags.length) {
        const p = await (await fetch('/profile', { credentials: 'include' })).text();
        const pf = p.match(/flag\{[^}]+\}/g) || [];
        if (pf.length) { S.flags = [...new Set(pf)]; console.log('ФЛАГИ в профиле: ' + pf.join(' ')); }
      }
    } catch (e) { console.log('buy error', e); }
  }

  // ---------- рабочие ----------

  async function worker(id, pause) {
    while (!S.stop) {
      try {
        await trade();
      } catch (e) {
        S.errors['сеть: ' + (e.message || e)] = (S.errors['сеть: ' + (e.message || e)] || 0) + 1;
        await sleep(300);
        continue;
      }
      if (S.balance !== null && S.balance >= TARGET) { S.stop = true; break; }
      if (pause) await sleep(pause);
    }
  }

  // ---------- публичный интерфейс ----------

  const FARM = {
    __v: 3,

    async start(opts = {}) {
      if (S.running) { console.log('уже идёт, сначала FARM.stop()'); return; }
      const workers = Math.max(1, Math.min(20, opts.workers || 6));
      const pause = Math.max(0, opts.pause || 0);

      Object.assign(S, {
        running: true, stop: false, started: Date.now(), trades: 0, wins: 0,
        errors: {}, flags: [], startedTip: '',
      });
      await refreshBalance();
      console.log(`%cFARM v3 старт: ${workers} потоков, пауза ${pause} мс, баланс ${S.balance} ₽`,
                  'color:#0a0;font-weight:bold');
      if ((S.balance || 0) < 1) {
        S.startedTip = '⚠ на счету нет денег — нужен аккаунт с промокодом';
        console.log('%cнет денег на ставку: активируй промокод на этом аккаунте',
                    'color:#e33;font-weight:bold');
      }

      render();
      const tick = setInterval(render, 1000);
      const bal = setInterval(refreshBalance, 10000);

      const loops = Array.from({ length: workers }, (_, i) => worker(i, pause));
      await Promise.all(loops);

      clearInterval(tick); clearInterval(bal);
      await refreshBalance();
      S.running = false;
      render();

      if (S.balance !== null && S.balance >= TARGET) {
        await buy();
        render();
      } else {
        console.log(`%cостановлено: ${S.trades} сделок, баланс ${S.balance} ₽, не хватило ${TARGET - (S.balance || 0)} ₽`,
                    'color:#e90;font-weight:bold');
        S.startedTip = 'запусти FARM.start() снова — продолжит с этого баланса';
        render();
      }
    },

    stop() {
      S.stop = true;
      console.log('FARM.stop() — завершаю текущие сделки');
    },

    status() {
      const el = S.started ? (Date.now() - S.started) / 1000 : 0;
      const rps = el > 1 ? S.trades / el : 0;
      console.table({
        идёт: S.running, секунд: Math.round(el), сделок: S.trades,
        'в секунду': +rps.toFixed(2), выигрышей: S.wins,
        баланс: S.balance, осталось: S.balance === null ? null : Math.max(0, TARGET - S.balance),
        'ждать сек': rps > 0.05 && S.balance !== null ? Math.round(Math.max(0, TARGET - S.balance) / rps) : null,
      });
      if (Object.keys(S.errors).length) console.log('ошибки:', S.errors);
      return S;
    },

    buy,
    balance: refreshBalance,
  };

  window.FARM = FARM;
  console.log('%cFARM v3 загружен. FARM.start() — начать, FARM.stop() — стоп, FARM.status() — цифры.',
              'color:#0a0;font-weight:bold');
})();
