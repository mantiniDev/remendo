/* Remendo — site estático. Lê os JSONs de /dados (gerados pelo pipeline). Sem dependências. */
(() => {
'use strict';
const PAGE = document.body.dataset.page;
const app = document.getElementById('app');
const qs = new URLSearchParams(location.search);
const REPO = 'https://github.com/mantiniDev/remendo';

/* ---------- utilidades ---------- */
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const NF = d => new Intl.NumberFormat('pt-BR', { minimumFractionDigits: d, maximumFractionDigits: d });
const nf0 = NF(0), nf1 = NF(1), nf2 = NF(2);
const brl = v => 'R$ ' + nf2.format(v || 0);
const short = v => {
  const a = Math.abs(v || 0), s = (v || 0) < 0 ? '-' : '';
  if (a >= 1e9) return `${s}R$ ${nf1.format(a / 1e9)} bi`;
  if (a >= 1e6) return `${s}R$ ${nf1.format(a / 1e6)} mi`;
  if (a >= 1e3) return `${s}R$ ${nf0.format(a / 1e3)} mil`;
  return brl(v);
};
const money = v => `<span title="${esc(brl(v))}">${esc(short(v))}</span>`;
const pct = v => (v == null ? '—' : nf1.format(v) + '%');
const dt = s => (s ? `${s.slice(8, 10)}/${s.slice(5, 7)}/${s.slice(0, 4)}` : '—');
const norm = s => String(s ?? '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
const sum = (a, k) => a.reduce((t, x) => t + (x[k] || 0), 0);
const cache = {};
const J = n => (cache[n] ??= fetch('dados/' + n).then(r => { if (!r.ok) throw new Error(`${n}: HTTP ${r.status}`); return r.json(); }));
const CAT = { individual: 'Individual', bancada: 'Bancada estadual', comissao: 'Comissão', relator: 'Relator', outra: 'Outra' };
const CATCOR = { individual: '#2B4C7E', bancada: '#E8743B', comissao: '#E3B341', relator: '#5E5648', outra: '#B9AE9B' };
const STAT = { paga: 'Paga', parcial: 'Paga em parte', parada: 'Parada', empenhada: 'Só empenhada', sem_empenho: 'Sem empenho' };
const tag = s => `<span class="tag ${esc(s)}">${esc(STAT[s] || s)}</span>`;
const modal = t => (/Especia/i.test(t || '') ? 'Transferência especial' : /Finalidade/i.test(t || '') ? 'Finalidade definida' : '');
const lnkEm = e => `emenda.html?c=${encodeURIComponent(e.codigo)}&ano=${e.ano}`;
const lnkPa = (id, ano) => `parlamentar.html?id=${encodeURIComponent(id)}&ano=${ano}`;
const autorHtml = e => e.parlamentar_id
  ? `<a href="${lnkPa(e.parlamentar_id, e.ano)}">${esc(e.parlamentar_nome || e.autor_nome)}</a>`
  : esc(e.autor_nome) + (e.categoria !== 'individual' ? ` <span class="mu sm">(${esc(CAT[e.categoria] || '')})</span>` : '');
const bar = p => `<div class="bar" role="img" aria-label="${esc(pct(p))} pago"><i style="width:${Math.max(0, Math.min(100, p || 0))}%"></i></div>`;
const wait = () => { app.innerHTML = '<p class="mu m">Carregando…</p>'; };
const emendasAno = a => J(`emendas_${a}.json`);

/* ---------- ano selecionado ---------- */
function getAno(anos) {
  const q = +qs.get('ano');
  if (anos.includes(q)) return q;
  let s = 0;
  try { s = +localStorage.getItem('remendo.ano'); } catch (e) { /* sem storage */ }
  return anos.includes(s) ? s : anos[0];
}
function setAno(a) {
  try { localStorage.setItem('remendo.ano', a); } catch (e) { /* ok */ }
  const p = new URLSearchParams(location.search); p.set('ano', a);
  location.search = p.toString();
}

/* ---------- topo e rodapé ---------- */
const NAV = [['index.html', 'Início', 'home'], ['parlamentares.html', 'Parlamentares', 'parlamentares'], ['emendas.html', 'Emendas', 'emendas'],
  ['rankings.html', 'Rankings', 'rankings'], ['areas.html', 'Áreas', 'areas'], ['partidos.html', 'Partidos', 'partidos'], ['mapa.html', 'Mapa', 'mapa'], ['metodologia.html', 'Metodologia', 'metodologia']];
function shell(anos, ano, meta) {
  const nav = NAV.map(([h, t, k]) => `<a href="${h}?ano=${ano}"${k === PAGE || (k === 'parlamentares' && PAGE === 'parlamentar') || (k === 'emendas' && PAGE === 'emenda') ? ' aria-current="page"' : ''}>${t}</a>`).join('');
  document.getElementById('top').innerHTML = `<div class="w top"><a class="logo" href="index.html?ano=${ano}" aria-label="Remendo, início">remendo</a>
    <nav class="nv" aria-label="Principal">${nav}</nav>
    <label class="ys">Ano <select id="ysel">${anos.map(a => `<option${a === ano ? ' selected' : ''}>${a}</option>`).join('')}</select></label></div>`;
  document.getElementById('ysel').onchange = e => setAno(e.target.value);
  const quando = new Date(meta.atualizado_em).toLocaleString('pt-BR', { timeZone: 'America/Sao_Paulo', dateStyle: 'short', timeStyle: 'short' });
  document.getElementById('ftr').innerHTML = `<div class="w"><div class="fr"><span>remendo.com.br · dados abertos, sem partido</span>
    <span><a href="metodologia.html?ano=${ano}">Metodologia</a> · <a href="dados-abertos.html?ano=${ano}">Dados abertos</a> · <a href="${REPO}/issues/new" rel="noopener">Corrigir um dado</a></span></div>
    <p class="m sm" style="margin-top:10px">Atualizado em ${esc(quando)} · Fontes: ${meta.fontes.map(esc).join('; ')}.</p></div>`;
  if (meta.carga_parcial) {
    document.getElementById('aviso').innerHTML = `<div class="w"><div class="banner" role="status"><b>Carga em andamento.</b> Ainda faltam os documentos de ${nf0.format(meta.emendas_sem_documentos)} emendas: as datas e a situação “parada” podem estar incompletas. Os valores já estão completos.</div></div>`;
  }
}

/* ---------- tabela ordenável e paginada ---------- */
function dataTable(host, cols, rows, o = {}) {
  let sk = o.sort ?? Math.max(0, cols.findIndex(c => c.num)); let asc = o.dir === 'asc'; let page = 0; const size = o.size || 50;
  const draw = () => {
    const c = cols[sk];
    const sorted = [...rows].sort((a, b) => {
      const x = c.val(a), y = c.val(b);
      const r = (typeof x === 'string' || typeof y === 'string') ? String(x ?? '').localeCompare(String(y ?? ''), 'pt-BR') : (x ?? -Infinity) - (y ?? -Infinity);
      return asc ? r : -r;
    });
    const pages = Math.max(1, Math.ceil(sorted.length / size)); page = Math.min(page, pages - 1);
    const slice = sorted.slice(page * size, (page + 1) * size);
    host.innerHTML = `<div class="tw"><table><thead><tr>${cols.map((k, i) => `<th scope="col" class="${k.num ? 'n' : ''}" aria-sort="${i === sk ? (asc ? 'ascending' : 'descending') : 'none'}"><button type="button" data-s="${i}">${esc(k.label)}${i === sk ? (asc ? ' ↑' : ' ↓') : ''}</button></th>`).join('')}</tr></thead>
      <tbody>${slice.map(r => `<tr>${cols.map(k => `<td class="${k.num ? 'n' : ''}" data-l="${esc(k.label)}">${k.html(r)}</td>`).join('')}</tr>`).join('') || `<tr><td colspan="${cols.length}">${o.empty || 'Nada encontrado com esses filtros.'}</td></tr>`}</tbody></table></div>
      ${pages > 1 ? `<div class="pg"><button type="button" data-p="-1"${page === 0 ? ' disabled' : ''}>← Anterior</button><span>Página ${page + 1} de ${pages} · ${nf0.format(sorted.length)} linhas</span><button type="button" data-p="1"${page >= pages - 1 ? ' disabled' : ''}>Próxima →</button></div>` : `<p class="cnt">${nf0.format(sorted.length)} linhas</p>`}`;
  };
  host.onclick = e => {
    const b = e.target.closest('button'); if (!b || !host.contains(b)) return;
    if (b.dataset.s != null) { const i = +b.dataset.s; if (i === sk) asc = !asc; else { sk = i; asc = !!cols[i].asc; } page = 0; } else if (b.dataset.p) { page += +b.dataset.p; } else return;
    draw();
  };
  draw();
  return { set(r) { rows = r; page = 0; draw(); } };
}

/* ---------- colunas reutilizáveis ---------- */
const colsEmendas = [
  { label: 'Emenda', html: e => `<a href="${lnkEm(e)}" class="m">${esc(e.codigo)}</a>`, val: e => e.codigo },
  { label: 'Autor', html: autorHtml, val: e => e.autor_nome },
  { label: 'Tipo', html: e => `${esc(CAT[e.categoria] || '')}${modal(e.tipo) ? `<br><span class="mu sm">${modal(e.tipo)}</span>` : ''}`, val: e => e.categoria },
  { label: 'Destino', html: e => esc(e.localidade || '—'), val: e => e.localidade || '' },
  { label: 'Área', html: e => esc(e.funcao || '—'), val: e => e.funcao || '' },
  { label: 'Empenhado', html: e => money(e.empenhado), val: e => e.empenhado, num: true },
  { label: 'Pago', html: e => money(e.pago), val: e => e.pago, num: true },
  { label: '% pago', html: e => pct(e.pct_pago), val: e => e.pct_pago, num: true },
  { label: 'Situação', html: e => tag(e.status), val: e => e.status }
];
const kpi = (l, v, s) => `<div class="p"><div class="kl">${l}</div><div class="kv">${v}</div><div class="ks">${s || ''}</div></div>`;
const rowLi = (a, sub, v) => `<div class="row"><span>${a}${sub ? `<small>${sub}</small>` : ''}</span><span class="v">${v}</span></div>`;
const anoParcial = ano => (ano >= new Date().getFullYear() ? `<p class="nota">${ano} ainda está em andamento: parte do dinheiro empenhado deve ser paga até o fim do ano (e dos anos seguintes, como restos a pagar). Compare com cuidado.</p>` : '');

/* ================= PÁGINAS ================= */
const pages = {};

/* ---- Início ---- */
pages.home = async ({ resumo, ano }) => {
  const [cats, E, P, areas] = await Promise.all([J('categorias.json'), emendasAno(ano), J('parlamentares.json'), J('areas.json')]);
  const r = resumo.find(x => x.ano === ano);
  const c = cats.filter(x => x.ano === ano).sort((a, b) => b.empenhado - a.empenhado);
  const col = c.filter(x => x.categoria !== 'individual');
  const maiores = E.filter(e => e.nao_pago > 0).sort((a, b) => b.nao_pago - a.nao_pago).slice(0, 5);
  const paradas = E.filter(e => e.status === 'parada').sort((a, b) => b.empenhado - a.empenhado).slice(0, 5);
  const pa = P.filter(p => p.ano === ano && p.nao_pago > 0).sort((a, b) => b.nao_pago - a.nao_pago).slice(0, 5);
  const top = areas.filter(a => a.ano === ano).sort((a, b) => b.empenhado - a.empenhado).slice(0, 8);
  const maxA = Math.max(...top.map(a => a.empenhado), 1);
  app.innerHTML = `
  <section class="hero w" style="margin-top:0">
    <h1>Siga o fio de cada emenda.</h1>
    <p class="lede">Quanto os parlamentares destinaram, quanto virou empenho e quanto foi pago — com dados oficiais e link para a fonte. Os fatos ficam aqui; a conclusão é sua.</p>
    <form class="sf" action="parlamentares.html" role="search"><input type="search" name="q" aria-label="Buscar parlamentar" placeholder="Buscar parlamentar pelo nome"><input type="hidden" name="ano" value="${ano}"><button class="bt" type="submit">Buscar</button></form>
  </section>
  <div class="w">
  ${anoParcial(ano)}
  <section style="margin-top:28px"><div class="g">
    ${kpi(`Empenhado em ${ano}`, money(r.empenhado), `${nf0.format(r.n)} emendas`)}
    ${kpi('Liquidado', money(r.liquidado), `${pct(100 * r.liquidado / r.empenhado)} do empenhado · só o exercício`)}
    ${kpi('Pago', money(r.pago), `${pct(r.pct_pago)} do empenhado · inclui restos a pagar`)}
    ${kpi('Ainda não pago', money(r.nao_pago), 'empenhado menos pago')}</div></section>
  <section><h2>De quem vem o dinheiro</h2>
    <div class="stack" role="img" aria-label="Composição do empenhado por tipo de emenda">${c.map(x => `<i style="width:${x.pct_do_total}%;background:${CATCOR[x.categoria] || '#999'}" title="${esc(CAT[x.categoria])}: ${pct(x.pct_do_total)}"></i>`).join('')}</div>
    <div class="lg">${c.map(x => `<span style="--c:${CATCOR[x.categoria] || '#999'}"><b>${esc(CAT[x.categoria])}</b> ${pct(x.pct_do_total)} · ${esc(short(x.empenhado))} · ${pct(x.pct_pago)} pago</span>`).join('')}</div>
    <p style="margin-top:12px">${col.length ? `<b>${pct(sum(col, 'pct_do_total'))}</b> do valor de ${ano} vem de emendas de bancada e de comissão, que não têm um parlamentar individual como autor.` : ''} <a href="metodologia.html?ano=${ano}#tipos">Entenda os tipos</a>.</p></section>
  <section><h2>A linha da emenda</h2>
    <div class="steps">
      <div class="st na"><b>1. Indicação</b><div class="v">—</div><p>O valor que o parlamentar indicou não consta na base pública usada aqui. Mostramos a partir do empenho.</p></div>
      <div class="st"><b>2. Empenho</b><div class="v">${money(r.empenhado)}</div><p>O governo reserva o dinheiro no orçamento para aquela despesa.</p></div>
      <div class="st"><b>3. Liquidação</b><div class="v">${money(r.liquidado)}</div><p>Confirma-se que o serviço ou a obra foi entregue.</p></div>
      <div class="st fim"><b>4. Pagamento</b><div class="v">${money(r.pago)}</div><p>O dinheiro sai do caixa e chega ao destino.</p></div></div></section>
  <section><h2>Destaques de ${ano}</h2><div class="g">
    <div class="p"><h3>Maiores valores ainda não pagos</h3>${maiores.map(e => rowLi(`<a href="${lnkEm(e)}">${esc(e.autor_nome)}</a>`, esc(e.localidade || ''), money(e.nao_pago))).join('') || '<p class="mu">Nada a mostrar.</p>'}</div>
    <div class="p"><h3>Emendas paradas ${tag('parada')}</h3>${paradas.map(e => rowLi(`<a href="${lnkEm(e)}">${esc(e.autor_nome)}</a>`, `${esc(e.localidade || '')} · última movimentação ${dt(e.ultima_mov)}`, money(e.empenhado))).join('') || '<p class="mu">Nenhuma emenda parada encontrada neste ano (isso depende de os documentos já terem sido carregados).</p>'}</div>
    <div class="p"><h3>Parlamentares com mais valor a pagar</h3>${pa.map(p => rowLi(`<a href="${lnkPa(p.id, ano)}">${esc(p.nome)}</a>`, `${esc(p.partido || '')} · ${esc(p.uf || '')} · ${pct(p.pct_pago)} pago`, money(p.nao_pago))).join('')}<p class="sm mu" style="margin-top:8px">Pagar depende do Executivo: valor pendente não é, por si só, falha do parlamentar.</p></div></div></section>
  <section><h2>Para onde foi o dinheiro</h2><div class="p">
    ${top.map(a => `<div class="row ar" style="align-items:center"><span style="flex:0 0 190px"><a href="emendas.html?funcao=${encodeURIComponent(a.funcao)}&ano=${ano}">${esc(a.funcao)}</a></span><span style="flex:1"><div class="bar"><i style="width:${100 * a.empenhado / maxA}%"></i></div></span><span class="v">${money(a.empenhado)}</span></div>`).join('')}
    <p style="margin:12px 0 0"><a href="areas.html?ano=${ano}">Ver todas as áreas →</a> · <a href="mapa.html?ano=${ano}">Ver no mapa →</a></p></div></section>
  </div>`;
};

/* ---- Parlamentares ---- */
pages.parlamentares = async ({ ano }) => {
  const P = (await J('parlamentares.json')).filter(p => p.ano === ano);
  const partidos = [...new Set(P.map(p => p.partido).filter(Boolean))].sort();
  const ufs = [...new Set(P.map(p => p.uf).filter(Boolean))].sort();
  app.innerHTML = `<div class="w"><h1 style="font-size:clamp(30px,5vw,48px)">Parlamentares</h1>
  <p class="mu">Deputados e senadores com emendas individuais em ${ano}. Emendas de bancada e de comissão não entram aqui (veja <a href="rankings.html?ano=${ano}">Rankings</a>).</p>
  <form class="fl" id="f"><label>Nome<input type="search" id="q" value="${esc(qs.get('q') || '')}" placeholder="Buscar pelo nome"></label>
   <label>Casa<select id="casa"><option value="">Todas</option><option>Câmara</option><option>Senado</option></select></label>
   <label>Partido<select id="pt"><option value="">Todos</option>${partidos.map(x => `<option>${esc(x)}</option>`).join('')}</select></label>
   <label>UF<select id="uf"><option value="">Todas</option>${ufs.map(x => `<option>${esc(x)}</option>`).join('')}</select></label></form>
  <div id="t"></div></div>`;
  const cols = [
    { label: 'Parlamentar', html: p => `<a href="${lnkPa(p.id, ano)}">${esc(p.nome)}</a>`, val: p => p.nome },
    { label: 'Partido', html: p => esc(p.partido || '—'), val: p => p.partido || '' },
    { label: 'UF', html: p => esc(p.uf || '—'), val: p => p.uf || '' },
    { label: 'Casa', html: p => esc(p.casa), val: p => p.casa },
    { label: 'Emendas', html: p => nf0.format(p.n), val: p => p.n, num: true },
    { label: 'Empenhado', html: p => money(p.empenhado), val: p => p.empenhado, num: true },
    { label: 'Pago', html: p => money(p.pago), val: p => p.pago, num: true },
    { label: '% pago', html: p => `${pct(p.pct_pago)}${bar(p.pct_pago)}`, val: p => p.pct_pago, num: true }];
  const tb = dataTable(document.getElementById('t'), cols, P, { sort: 5 });
  const f = () => {
    const q = norm(document.getElementById('q').value), c = document.getElementById('casa').value, pt = document.getElementById('pt').value, u = document.getElementById('uf').value;
    tb.set(P.filter(p => (!q || norm(p.nome).includes(q)) && (!c || p.casa === c) && (!pt || p.partido === pt) && (!u || p.uf === u)));
  };
  document.getElementById('f').addEventListener('input', f); document.getElementById('f').addEventListener('submit', e => e.preventDefault());
  f();
};

/* ---- Parlamentar ---- */
pages.parlamentar = async ({ ano, anos }) => {
  const id = qs.get('id'); const P = (await J('parlamentares.json')).filter(p => p.id === id);
  if (!P.length) { app.innerHTML = '<div class="w"><div class="box">Parlamentar não encontrado. <a href="parlamentares.html">Voltar à lista</a>.</div></div>'; return; }
  const p = P.find(x => x.ano === ano) || P.sort((a, b) => b.ano - a.ano)[0];
  const E = (await emendasAno(p.ano)).filter(e => e.parlamentar_id === id);
  const paradas = E.filter(e => e.status === 'parada').length;
  document.title = `${p.nome} — Remendo`;
  app.innerHTML = `<div class="w"><p class="sm"><a href="parlamentares.html?ano=${p.ano}">← Parlamentares</a></p>
  <h1 style="font-size:clamp(30px,5vw,48px)">${esc(p.nome)}</h1>
  <p class="mu m">${esc(p.casa)} · ${esc(p.partido || 'sem partido informado')} · ${esc(p.uf || '—')}</p>
  ${anoParcial(p.ano)}
  <section style="margin-top:20px"><div class="g">
   ${kpi(`Empenhado em ${p.ano}`, money(p.empenhado), `${nf0.format(p.n)} emendas`)}
   ${kpi('Pago', money(p.pago), `${pct(p.pct_pago)} do empenhado`)}
   ${kpi('Ainda não pago', money(p.nao_pago), 'empenhado menos pago')}
   ${kpi('Emendas paradas', nf0.format(paradas), 'sem pagamento há mais de 180 dias')}</div></section>
  <section><h2>Ano a ano</h2><div class="tw"><table><thead><tr><th>Ano</th><th class="n">Emendas</th><th class="n">Empenhado</th><th class="n">Pago</th><th class="n">% pago</th></tr></thead><tbody>
   ${[...P].sort((a, b) => b.ano - a.ano).map(x => `<tr><td data-l="Ano"><a href="parlamentar.html?id=${encodeURIComponent(id)}&ano=${x.ano}">${x.ano}</a></td><td class="n" data-l="Emendas">${nf0.format(x.n)}</td><td class="n" data-l="Empenhado">${money(x.empenhado)}</td><td class="n" data-l="Pago">${money(x.pago)}</td><td class="n" data-l="% pago">${pct(x.pct_pago)}</td></tr>`).join('')}</tbody></table></div></section>
  <section><h2>Emendas de ${p.ano}</h2><div id="t"></div></section></div>`;
  dataTable(document.getElementById('t'), colsEmendas.filter(c => c.label !== 'Autor'), E, { sort: 4 });
};

/* ---- Emendas ---- */
pages.emendas = async ({ ano }) => {
  const E = await emendasAno(ano);
  const fun = [...new Set(E.map(e => e.funcao).filter(Boolean))].sort();
  const sel = (id, label, opts, val) => `<label>${label}<select id="${id}"><option value="">Todos</option>${opts.map(([v, t]) => `<option value="${esc(v)}"${v === val ? ' selected' : ''}>${esc(t)}</option>`).join('')}</select></label>`;
  app.innerHTML = `<div class="w"><h1 style="font-size:clamp(30px,5vw,48px)">Emendas de ${ano}</h1>${anoParcial(ano)}
  <form class="fl" id="f"><label>Buscar<input type="search" id="q" value="${esc(qs.get('q') || '')}" placeholder="Autor, destino ou código"></label>
   ${sel('cat', 'Tipo', Object.entries(CAT).filter(([k]) => E.some(e => e.categoria === k)), qs.get('cat'))}
   ${sel('st', 'Situação', Object.entries(STAT).filter(([k]) => E.some(e => e.status === k)), qs.get('st'))}
   ${sel('fn', 'Área', fun.map(x => [x, x]), qs.get('funcao'))}
   ${sel('uf', 'UF do autor', [...new Set(E.map(e => e.uf).filter(Boolean))].sort().map(x => [x, x]), qs.get('uf'))}</form>
  <p id="res" class="m sm"></p><div id="t"></div></div>`;
  const tb = dataTable(document.getElementById('t'), colsEmendas, E, { sort: 5 });
  const f = () => {
    const q = norm(document.getElementById('q').value), v = id => document.getElementById(id).value;
    const r = E.filter(e => (!q || norm(`${e.autor_nome} ${e.localidade} ${e.codigo} ${e.funcao}`).includes(q)) && (!v('cat') || e.categoria === v('cat')) && (!v('st') || e.status === v('st')) && (!v('fn') || e.funcao === v('fn')) && (!v('uf') || e.uf === v('uf')));
    document.getElementById('res').textContent = `${nf0.format(r.length)} emendas · empenhado ${short(sum(r, 'empenhado'))} · pago ${short(sum(r, 'pago'))}`;
    tb.set(r);
  };
  document.getElementById('f').addEventListener('input', f); document.getElementById('f').addEventListener('submit', e => e.preventDefault());
  f();
};

/* ---- Emenda ---- */
pages.emenda = async ({ ano }) => {
  const cod = qs.get('c'); const a = +qs.get('ano') || ano;
  const e = (await emendasAno(a)).find(x => x.codigo === cod);
  if (!e) { app.innerHTML = '<div class="w"><div class="box">Emenda não encontrada. <a href="emendas.html">Voltar à lista</a>.</div></div>'; return; }
  document.title = `Emenda ${e.codigo} — Remendo`;
  const irmas = (await emendasAno(a)).filter(x => x.codigo.split('~')[0] === e.codigo.split('~')[0] && x.codigo !== e.codigo);
  const exp = { paga: 'O valor pago alcançou (ou superou) o valor empenhado.', parcial: 'Parte do valor empenhado já foi paga.', parada: 'Nada foi pago e a última movimentação tem mais de 180 dias.', empenhada: 'O dinheiro foi reservado, mas ainda não há pagamento.', sem_empenho: 'Ainda não há empenho.' }[e.status] || '';
  const passo = (t, v, d, cls) => `<div class="st ${cls || ''}"><b>${t}</b><div class="v">${money(v)}</div><p>${d ? `Última movimentação: ${dt(d)}` : 'Data não disponível'}</p></div>`;
  app.innerHTML = `<div class="w"><p class="sm"><a href="emendas.html?ano=${a}">← Emendas de ${a}</a></p>
  <h1 style="font-size:clamp(28px,4.5vw,44px)">Emenda ${esc(e.numero || '')} · ${esc(e.autor_nome)}</h1>
  <p class="mu m">Código ${esc(e.codigo)} · ${esc(CAT[e.categoria] || '')}${modal(e.tipo) ? ' · ' + modal(e.tipo) : ''}</p>
  <p>${tag(e.status)} <span class="mu">${esc(exp)}</span></p>
  <section><h2>A linha desta emenda</h2><div class="steps">
    <div class="st na"><b>1. Indicação</b><div class="v">—</div><p>Valor indicado não disponível na base pública.</p></div>
    ${passo('2. Empenho', e.empenhado, e.data_empenho)}${passo('3. Liquidação', e.liquidado, e.data_liquidacao)}${passo('4. Pagamento', e.pago, e.data_pagamento, 'fim')}</div>
    <p style="margin-top:14px">${bar(e.pct_pago)} <span class="m sm">${pct(e.pct_pago)} do empenhado foi pago${e.resto_pago ? ` · inclui ${esc(brl(e.resto_pago))} pagos de restos a pagar` : ''}${e.nao_pago ? ` · faltam ${esc(brl(e.nao_pago))}` : ''}</span></p></section>
  <section><h2>Detalhes</h2><div class="p"><dl class="dd">
    <dt>Autor</dt><dd>${autorHtml(e)}${e.partido ? ` · ${esc(e.partido)}-${esc(e.uf || '')}` : ''}</dd>
    <dt>Destino</dt><dd>${esc(e.localidade || '—')}</dd>
    <dt>Área</dt><dd>${esc(e.funcao || '—')}${e.subfuncao ? ` · ${esc(e.subfuncao)}` : ''}</dd>
    <dt>Tipo</dt><dd>${esc(e.tipo || '')}</dd>
    <dt>Ano</dt><dd>${e.ano}</dd>
    <dt>Documentos</dt><dd>${e.n_documentos ? `${nf0.format(e.n_documentos)} documentos de empenho, liquidação e pagamento no Portal` : 'ainda não carregados'}</dd></dl>
    <p class="sm mu" style="margin:14px 0 0">Fonte oficial: <a href="https://portaldatransparencia.gov.br/emendas" rel="noopener">Portal da Transparência</a> — procure pelo código <span class="m">${esc(e.codigo.split('~')[0])}</span>. Viu algo errado? <a href="${REPO}/issues/new" rel="noopener">Corrigir um dado</a>.</p></div></section>
  ${irmas.length ? `<section><h2>Outras linhas com o mesmo código</h2><p class="mu">A fonte divide uma mesma emenda em mais de uma linha (por exemplo, uma parte “transferência especial” e outra “finalidade definida”).</p><div id="t"></div></section>` : ''}</div>`;
  if (irmas.length) dataTable(document.getElementById('t'), colsEmendas, irmas, { sort: 5 });
};

/* ---- Rankings ---- */
pages.rankings = async ({ ano }) => {
  const R = await J('rankings.json'); const tab = qs.get('t') || 'menos'; const casa = qs.get('casa') || 'camara';
  const link = (t, c) => `rankings.html?ano=${ano}&t=${t}&casa=${c}`;
  const abas = [['menos', 'Menor taxa de pagamento'], ['valor', 'Mais valor a pagar'], ['coletivas', 'Bancadas e comissões'], ['paradas', 'Emendas paradas']];
  const casas = tab === 'menos' || tab === 'valor';
  const pessoa = [
    { label: 'Parlamentar', html: r => `<a href="${lnkPa(r.parlamentar_id, ano)}">${esc(r.autor_nome)}</a>`, val: r => r.autor_nome },
    { label: 'Partido-UF', html: r => `${esc(r.partido || '—')}-${esc(r.uf || '')}`, val: r => r.partido || '' },
    { label: 'Emendas', html: r => nf0.format(r.n), val: r => r.n, num: true },
    { label: 'Empenhado', html: r => money(r.empenhado), val: r => r.empenhado, num: true },
    { label: 'Pago', html: r => money(r.pago), val: r => r.pago, num: true },
    { label: 'Não pago', html: r => money(r.nao_pago), val: r => r.nao_pago, num: true },
    { label: '% pago', html: r => `${pct(r.pct_pago)}${bar(r.pct_pago)}`, val: r => r.pct_pago, num: true }];
  let rows, cols, sort, dir = 'desc', nota = '';
  if (tab === 'menos') { rows = R['menos_executam_' + casa]; cols = pessoa; sort = 6; dir = 'asc'; nota = 'Só entram parlamentares com pelo menos R$ 5 milhões empenhados no ano.'; }
  else if (tab === 'valor') { rows = R['maior_nao_pago_' + casa]; cols = pessoa; sort = 5; }
  else if (tab === 'coletivas') {
    rows = R.coletivas_menos_executam; sort = 5; dir = 'asc'; nota = 'Bancadas estaduais, comissões e relator não têm um parlamentar individual como autor.';
    cols = [{ label: 'Autor', html: r => esc(r.autor_nome), val: r => r.autor_nome }, { label: 'Tipo', html: r => esc(CAT[r.categoria] || ''), val: r => r.categoria },
      { label: 'Emendas', html: r => nf0.format(r.n), val: r => r.n, num: true }, { label: 'Empenhado', html: r => money(r.empenhado), val: r => r.empenhado, num: true },
      { label: 'Pago', html: r => money(r.pago), val: r => r.pago, num: true }, { label: '% pago', html: r => `${pct(r.pct_pago)}${bar(r.pct_pago)}`, val: r => r.pct_pago, num: true },
      { label: 'Não pago', html: r => money(r.nao_pago), val: r => r.nao_pago, num: true }]; sort = 5;
  } else {
    rows = R.paradas; sort = 6; cols = [colsEmendas[0], colsEmendas[1], colsEmendas[3], colsEmendas[4], { label: 'Empenhado', html: e => money(e.empenhado), val: e => e.empenhado, num: true },
      { label: 'Última movimentação', html: e => dt(e.ultima_mov), val: e => e.ultima_mov || '' }]; sort = 4;
    rows = rows.map(r => ({ ...r, autor_nome: r.autor_nome, status: 'parada' }));
  }
  rows = rows.filter(r => r.ano === ano);
  app.innerHTML = `<div class="w"><h1 style="font-size:clamp(30px,5vw,48px)">Rankings de ${ano}</h1>
  <p class="nota"><b>Leia com cuidado.</b> Quem paga a emenda é o Executivo; um valor pendente não significa, sozinho, falha do parlamentar. Emendas recentes ainda estão em execução. Os rankings mostram dados, não culpa.</p>
  <div class="tabs" role="group" aria-label="Ranking">${abas.map(([k, t]) => `<button type="button" aria-pressed="${k === tab}" data-t="${k}">${t}</button>`).join('')}</div>
  ${casas ? `<div class="tabs" role="group" aria-label="Casa"><button type="button" aria-pressed="${casa === 'camara'}" data-c="camara">Câmara</button><button type="button" aria-pressed="${casa === 'senado'}" data-c="senado">Senado</button></div>` : ''}
  ${nota ? `<p class="sm mu">${nota}</p>` : ''}${tab === 'paradas' && !rows.length ? '<p class="nota">Nenhuma emenda parada neste ano. A situação “parada” depende dos documentos de movimentação, que ainda podem estar sendo carregados.</p>' : ''}
  <div id="t"></div></div>`;
  app.querySelectorAll('[data-t]').forEach(b => b.onclick = () => { location.href = link(b.dataset.t, casa); });
  app.querySelectorAll('[data-c]').forEach(b => b.onclick = () => { location.href = link(tab, b.dataset.c); });
  dataTable(document.getElementById('t'), cols, rows, { sort, dir, size: 50 });
};

/* ---- Áreas ---- */
pages.areas = async ({ ano }) => {
  const A = (await J('areas.json')).filter(a => a.ano === ano).sort((a, b) => b.empenhado - a.empenhado); const max = Math.max(...A.map(a => a.empenhado), 1);
  app.innerHTML = `<div class="w"><h1 style="font-size:clamp(30px,5vw,48px)">Por área, em ${ano}</h1>${anoParcial(ano)}
  <p class="mu">Em que o dinheiro das emendas foi empenhado, segundo a função orçamentária. “Encargos especiais” inclui as transferências especiais (o “Pix das emendas”).</p>
  <div id="t"></div></div>`;
  dataTable(document.getElementById('t'), [
    { label: 'Área', html: a => `<a href="emendas.html?funcao=${encodeURIComponent(a.funcao)}&ano=${ano}">${esc(a.funcao)}</a>`, val: a => a.funcao },
    { label: 'Emendas', html: a => nf0.format(a.n), val: a => a.n, num: true },
    { label: 'Empenhado', html: a => `${money(a.empenhado)}<div class="bar"><i style="width:${100 * a.empenhado / max}%"></i></div>`, val: a => a.empenhado, num: true },
    { label: 'Pago', html: a => money(a.pago), val: a => a.pago, num: true },
    { label: '% pago', html: a => `${pct(a.pct_pago)}${bar(a.pct_pago)}`, val: a => a.pct_pago, num: true },
    { label: 'Não pago', html: a => money(a.nao_pago), val: a => a.nao_pago, num: true }], A, { sort: 2, size: 60 });
};

/* ---- Partidos ---- */
pages.partidos = async ({ ano }) => {
  const P = (await J('partidos.json')).filter(p => p.ano === ano);
  app.innerHTML = `<div class="w"><h1 style="font-size:clamp(30px,5vw,48px)">Partidos, em ${ano}</h1>${anoParcial(ano)}
  <p class="nota">Somam só emendas <b>individuais</b> vinculadas a um parlamentar, pelo partido <b>atual</b> dele. Não inclui bancadas e comissões. O tamanho da bancada pesa: compare a coluna “% pago”, não o valor total.</p><div id="t"></div></div>`;
  dataTable(document.getElementById('t'), [
    { label: 'Partido', html: p => esc(p.partido), val: p => p.partido },
    { label: 'Parlamentares', html: p => nf0.format(p.parlamentares), val: p => p.parlamentares, num: true },
    { label: 'Emendas', html: p => nf0.format(p.n), val: p => p.n, num: true },
    { label: 'Empenhado', html: p => money(p.empenhado), val: p => p.empenhado, num: true },
    { label: 'Pago', html: p => money(p.pago), val: p => p.pago, num: true },
    { label: '% pago', html: p => `${pct(p.pct_pago)}${bar(p.pct_pago)}`, val: p => p.pct_pago, num: true },
    { label: 'Empenhado por parlamentar', html: p => money(p.empenhado / p.parlamentares), val: p => p.empenhado / p.parlamentares, num: true }], P, { sort: 3, size: 60 });
};

/* ---- Mapa ---- */
const GRID = { RR: [3, 0], AP: [5, 0], AM: [2, 1], PA: [4, 1], MA: [5, 1], CE: [6, 1], RN: [7, 1], AC: [1, 2], RO: [2, 2], MT: [3, 2], TO: [4, 2], PI: [5, 2], PE: [6, 2], PB: [7, 2],
  MS: [3, 3], GO: [4, 3], BA: [5, 3], SE: [6, 3], AL: [7, 3], PR: [3, 4], DF: [4, 4], MG: [5, 4], ES: [6, 4], SC: [3, 5], SP: [4, 5], RJ: [5, 5], RS: [3, 6] };
pages.mapa = async ({ ano }) => {
  const U = (await J('ufs.json')).filter(u => u.ano === ano);
  const base = qs.get('base') === 'destino' ? 'destino' : 'autor'; const met = qs.get('m') === 'pct' ? 'pct' : 'valor'; const sel = qs.get('uf');
  const D = U.filter(u => u.base === base), nd = D.find(u => u.uf === 'ND'), M = Object.fromEntries(D.filter(u => u.uf !== 'ND').map(u => [u.uf, u]));
  const val = u => (met === 'pct' ? u.pct_pago : u.empenhado);
  const vs = Object.values(M).map(val), lo = met === 'pct' ? Math.min(...vs) : 0, hi = Math.max(...vs, 1);
  const mix = t => { const a = [0xEA, 0xDF, 0xCB], b = [0x2B, 0x4C, 0x7E]; return a.map((x, i) => Math.round(x + (b[i] - x) * t)); };
  const L = c => (0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]);
  const tiles = Object.entries(GRID).map(([uf, [x, y]]) => {
    const u = M[uf]; const t = u ? (val(u) - lo) / ((hi - lo) || 1) : 0; const c = mix(t);
    return `<button type="button" data-uf="${uf}" aria-pressed="${sel === uf}" style="grid-column:${x + 1};grid-row:${y + 1};background:rgb(${c});color:${L(c) < 150 ? '#fff' : '#1F1F1F'}" aria-label="${uf}: ${u ? esc(short(u.empenhado)) + ', ' + pct(u.pct_pago) + ' pago' : 'sem dados'}"><b>${uf}</b><span>${u ? (met === 'pct' ? pct(u.pct_pago) : esc(short(u.empenhado).replace('R$ ', ''))) : '—'}</span></button>`;
  }).join('');
  const link = (o) => { const p = new URLSearchParams({ ano, base, m: met, ...(sel ? { uf: sel } : {}), ...o }); return 'mapa.html?' + p; };
  const u = sel && M[sel];
  app.innerHTML = `<div class="w"><h1 style="font-size:clamp(30px,5vw,48px)">Mapa de ${ano}</h1>${anoParcial(ano)}
  <p class="mu">Mapa esquemático: cada quadrado é um estado, sem tamanhos proporcionais.</p>
  <div class="tabs" role="group" aria-label="Base do mapa"><button type="button" aria-pressed="${base === 'autor'}" data-go="${esc(link({ base: 'autor' }))}">UF do parlamentar</button><button type="button" aria-pressed="${base === 'destino'}" data-go="${esc(link({ base: 'destino' }))}">UF do destino do gasto</button></div>
  <div class="tabs" role="group" aria-label="Medida"><button type="button" aria-pressed="${met === 'valor'}" data-go="${esc(link({ m: 'valor' }))}">Valor empenhado</button><button type="button" aria-pressed="${met === 'pct'}" data-go="${esc(link({ m: 'pct' }))}">% pago</button></div>
  <div class="mapa-wrap"><div><div class="mp" role="group" aria-label="Estados">${tiles}</div>
   <p class="sm m" style="margin-top:14px">${met === 'pct' ? `${pct(lo)}` : 'menos'} <span class="ramp" style="display:inline-block;width:160px;vertical-align:middle"></span> ${met === 'pct' ? pct(hi) : 'mais'}</p></div>
   <div>${u ? `<div class="p"><h2 style="margin-bottom:6px">${esc(sel)}</h2><p class="m">${money(u.empenhado)} empenhados<br>${money(u.pago)} pagos (${pct(u.pct_pago)})<br>${nf0.format(u.n)} emendas</p>${base === 'autor' ? `<p><a href="emendas.html?uf=${sel}&ano=${ano}">Ver as emendas dos parlamentares de ${esc(sel)} →</a></p>` : ''}</div>` : '<div class="box">Clique em um estado para ver os números.</div>'}
   ${nd ? `<div class="box" style="margin-top:14px"><b>Sem UF definida: ${money(nd.empenhado)}</b> (${pct(100 * nd.empenhado / (sum(Object.values(M), 'empenhado') + nd.empenhado))} do total)<p class="sm mu" style="margin:6px 0 0">${base === 'destino' ? 'Gastos com destino “Nacional” ou “Múltiplo”, sem um estado informado.' : 'Emendas de comissão e do relator, ou de autores ainda sem vínculo.'}</p></div>` : ''}</div></div></div>`;
  app.querySelectorAll('[data-go]').forEach(b => b.onclick = () => { location.href = b.dataset.go; });
  app.querySelectorAll('[data-uf]').forEach(b => b.onclick = () => { location.href = link({ uf: b.dataset.uf }); });
};

/* ---- Metodologia ---- */
pages.metodologia = async ({ meta, resumo, ano }) => {
  const v = (meta.vinculo_individuais || []).find(x => x.ano === ano);
  app.innerHTML = `<div class="w prose"><h1 style="font-size:clamp(30px,5vw,48px)">Metodologia</h1>
  <p class="lede">O Remendo junta dados públicos e oficiais, sem opinião. Aqui está exatamente o que contamos e o que não contamos.</p>
  <h2>De onde vêm os dados</h2><ul><li><b>Emendas e documentos:</b> Portal da Transparência (CGU), consulta de emendas parlamentares.</li><li><b>Parlamentares:</b> API de Dados Abertos da Câmara dos Deputados e Dados Abertos do Senado Federal.</li></ul>
  <p>Os dados são atualizados todos os dias. A data da última atualização está no rodapé.</p>
  <h2>As etapas</h2><ul><li><b>Empenho:</b> o governo reserva o valor no orçamento.</li><li><b>Liquidação:</b> verifica-se que o serviço ou bem foi entregue.</li><li><b>Pagamento:</b> o dinheiro é efetivamente pago.</li></ul>
  <p><b>A indicação não aparece.</b> O valor que o parlamentar indicou originalmente fica em outro sistema (SIOP) e não está na base que usamos. Por isso o Remendo parte do empenho. Pretendemos integrar a indicação no futuro.</p>
  <h2>Como calculamos “pago”</h2>
  <p>“Pago” é o valor pago no ano <b>mais</b> os pagamentos de <i>restos a pagar</i> daquela emenda (valor empenhado em um ano e pago em anos seguintes). Sem isso, emendas antigas pareceriam não pagas. Já o “liquidado” que a fonte informa refere-se ao exercício; por isso, em alguns agrupamentos o pago pode superar o liquidado. Quando o pago passa do empenhado, o percentual é limitado a 100%.</p>
  <h2 id="tipos">Tipos de emenda</h2>
  <ul><li><b>Individual:</b> de um deputado ou senador. Divide-se em <i>finalidade definida</i> (o recurso tem destino e objeto indicados) e <i>transferência especial</i> (o “Pix das emendas”, que vai direto ao caixa do ente beneficiado).</li>
  <li><b>Bancada estadual:</b> proposta pelo conjunto dos parlamentares de um estado.</li><li><b>Comissão:</b> proposta por comissões permanentes do Congresso.</li><li><b>Relator:</b> do relator-geral do orçamento.</li></ul>
  <p>Bancadas e comissões não têm um parlamentar individual como autor e por isso não entram nas páginas por parlamentar nem por partido.</p>
  <h2>Situação da emenda</h2><ul><li><b>Paga:</b> o valor pago alcançou o empenhado.</li><li><b>Paga em parte:</b> há pagamento, mas menor que o empenhado.</li><li><b>Parada:</b> nada foi pago e o último documento tem mais de 180 dias. Depende de os documentos já terem sido carregados.</li><li><b>Só empenhada:</b> reservada, sem pagamento, com movimentação recente ou sem documentos.</li></ul>
  <p>O corte de 180 dias é uma escolha nossa, para dar um critério claro.</p>
  <h2>Vínculo com o parlamentar</h2>
  <p>A fonte informa o nome do autor, não um identificador. Vinculamos por nome (apelido ou nome civil), ignorando acentos, pontos e títulos. Se houver mais de um candidato, não vinculamos.${v ? ` Em ${ano}, <b>${pct(v.pct_valor_vinculado)}</b> do valor das emendas individuais está vinculado a um parlamentar.` : ''}</p>
  <h2>Partidos</h2><p>O partido é o <b>atual</b> do parlamentar, não necessariamente o da época da emenda.</p>
  <h2>Limites que você precisa conhecer</h2><ul><li>O ano corrente está em andamento: o percentual pago ainda vai subir.</li><li>Uma mesma emenda pode vir dividida em mais de uma linha; mantemos cada linha.</li><li>Pagamento depende do Executivo. Valor pendente não é, por si só, falha do parlamentar.</li><li>${meta.carga_parcial ? `Agora: faltam os documentos de ${nf0.format(meta.emendas_sem_documentos)} emendas.` : 'Todos os documentos disponíveis foram carregados.'}</li></ul>
  <h2>Errou algum dado?</h2><p><a href="${REPO}/issues/new" rel="noopener">Abra um aviso</a> com o código da emenda e o que está errado. O código-fonte também está no <a href="${REPO}" rel="noopener">GitHub</a>.</p></div>`;
};

/* ---- Dados abertos ---- */
pages.dados = async ({ anos, ano }) => {
  const arq = (f, d) => `<tr><td data-l="Arquivo"><a href="dados/${f}" download class="m">${f}</a></td><td data-l="O que é">${d}</td></tr>`;
  app.innerHTML = `<div class="w"><h1 style="font-size:clamp(30px,5vw,48px)">Dados abertos</h1>
  <p class="mu">Os mesmos arquivos que alimentam o site. Pode usar, cruzar e republicar: cite “Remendo (remendo.com.br), com dados do Portal da Transparência”. Valores em reais.</p>
  <div class="tw"><table><thead><tr><th>Arquivo</th><th>O que é</th></tr></thead><tbody>
  ${anos.map(a => arq(`emendas_${a}.csv`, `Todas as emendas de ${a}, uma por linha (planilha).`) + arq(`emendas_${a}.json`, `As mesmas emendas de ${a} em JSON.`)).join('')}
  ${arq('resumo.json', 'Totais por ano.')}${arq('categorias.json', 'Totais por tipo de emenda (individual, bancada, comissão…).')}${arq('areas.json', 'Totais por área (função orçamentária).')}${arq('partidos.json', 'Totais por partido (emendas individuais).')}${arq('parlamentares.json', 'Totais por parlamentar e ano.')}${arq('ufs.json', 'Totais por estado (do parlamentar e do destino).')}${arq('rankings.json', 'Listas usadas na página Rankings.')}${arq('nao_vinculados.json', 'Autores que não foram ligados a um parlamentar.')}${arq('meta.json', 'Data da atualização e situação da carga.')}</tbody></table></div>
  <section><h2>Campos das emendas</h2><dl class="dd">
   <dt>codigo</dt><dd>código da emenda no Portal (um “~2” indica outra linha do mesmo código)</dd><dt>ano, numero</dt><dd>ano e número da emenda</dd>
   <dt>tipo, categoria</dt><dd>tipo original e agrupamento (individual, bancada, comissão, relator)</dd><dt>autor_nome, parlamentar_id</dt><dd>autor e identificador (C- = Câmara, S- = Senado)</dd>
   <dt>partido, uf</dt><dd>do parlamentar</dd><dt>localidade, funcao, subfuncao</dt><dd>destino e área</dd>
   <dt>empenhado, liquidado, pago, resto_pago</dt><dd>valores em reais; pago inclui restos a pagar pagos</dd><dt>pct_pago, nao_pago</dt><dd>derivados</dd>
   <dt>status, ultima_mov</dt><dd>situação e data do último documento</dd><dt>data_empenho, data_liquidacao, data_pagamento</dt><dd>datas dos documentos</dd></dl></section></div>`;
};

/* ---------- início ---------- */
(async () => {
  try {
    const [resumo, meta] = await Promise.all([J('resumo.json'), J('meta.json')]);
    const anos = resumo.map(r => r.ano).sort((a, b) => b - a);
    const ano = getAno(anos);
    shell(anos, ano, meta);
    await pages[PAGE]({ resumo, meta, anos, ano });
  } catch (err) {
    console.error(err);
    app.innerHTML = `<div class="w"><div class="box err"><h2>Não foi possível carregar os dados</h2><p class="m sm">${esc(err.message)}</p><p>Se você abriu o arquivo direto do computador, o navegador bloqueia a leitura dos dados. Use o endereço publicado ou rode um servidor local (<span class="m">python -m http.server</span>).</p></div></div>`;
  }
})();
})();
