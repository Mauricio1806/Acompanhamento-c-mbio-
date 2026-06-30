// Monitor de Cambio EUR/BRL Salvador - frontend
(() => {
  const DATA_LATEST = './data/latest.json';
  const DATA_HISTORY = './data/history.json';
  const DATA_RANKING = './data/ranking.json';

  const state = {
    latest: null,
    history: null,
    ranking: null,
    sortKey: 'custo_efetivo',
    sortDir: 'asc',
    filtroBairro: '',
    filtroTipo: '',
    volume: 5000,
    threshold: parseFloat(localStorage.getItem('threshold_eur_brl')) || null,
    chartPeriod: 30,
    chart: null,
  };

  // ---------- util ----------
  const $ = (sel) => document.querySelector(sel);
  const fmtBRL = (v) => v == null ? '—' : 'R$ ' + v.toFixed(4);
  const fmtBRL2 = (v) => v == null ? '—' : v.toLocaleString('pt-BR', {style: 'currency', currency: 'BRL'});
  const fmtPct = (v) => v == null ? '—' : v.toFixed(2) + '%';
  const fmtDate = (iso) => {
    if (!iso) return '';
    try { return new Date(iso).toLocaleString('pt-BR'); } catch { return iso; }
  };

  async function fetchJSON(url) {
    try {
      const r = await fetch(url + '?ts=' + Date.now());
      if (!r.ok) throw new Error(r.status);
      return await r.json();
    } catch (e) {
      console.warn('Falha ao carregar', url, e);
      return null;
    }
  }

  // ---------- render ----------
  function renderHeader() {
    const meta = state.latest?.meta;
    if (!meta) {
      $('#last-update').textContent = 'Dados ainda não disponíveis.';
      return;
    }
    $('#last-update').textContent = `Última atualização: ${fmtDate(meta.timestamp)} • ${meta.total_casas} casa(s)`;
  }

  function renderRefs() {
    const cotacoes = state.latest?.cotacoes || [];
    const ptax = cotacoes.find(c => c.ptax_venda)?.ptax_venda;
    const menor30 = state.latest?.meta?.menor_custo_30_dias;
    $('#ref-ptax').textContent = fmtBRL(ptax);

    // wise nao vem direto em latest.cotacoes; pega via wise_rate se presente
    const wise = cotacoes.find(c => c.observacao && c.observacao.includes('wise'))?.wise_rate
              || cotacoes[0]?.wise_rate;
    $('#ref-wise').textContent = fmtBRL(wise);

    $('#ref-menor30').textContent = fmtBRL(menor30);
  }

  function renderTop3() {
    const c = $('#top3-cards');
    c.innerHTML = '';
    const ranking = state.ranking?.ranking?.top3 || [];
    if (!ranking.length) {
      c.innerHTML = '<p class="muted">Sem dados para ranking ainda.</p>';
      return;
    }
    ranking.forEach((r) => {
      const div = document.createElement('div');
      div.className = `top3-card pos-${r.posicao}`;
      div.innerHTML = `
        <div class="top3-pos">${r.posicao}º LUGAR</div>
        <div class="top3-nome">${r.nome}</div>
        <div class="top3-valor">${fmtBRL(r.custo_efetivo)}</div>
        <div class="top3-meta">Venda: ${fmtBRL(r.valor_venda)} • Spread PTAX: ${fmtPct(r.spread_ptax)}</div>
      `;
      c.appendChild(div);
    });
  }

  function renderVolumeCards() {
    const c = $('#volume-cards');
    c.innerHTML = '';
    const vol = state.volume;
    $('#volume-label').textContent = `(${vol.toLocaleString('pt-BR')} EUR)`;

    // Usa o ranking ja calculado se for um dos volumes-padrao, senao calcula on-the-fly
    let items = state.ranking?.ranking?.por_volume?.[String(vol)];
    if (!items) {
      const cotacoes = state.latest?.cotacoes || [];
      const validas = cotacoes.filter(x => x.custo_efetivo > 0).sort((a, b) => a.custo_efetivo - b.custo_efetivo);
      const pior = validas.length ? validas[validas.length - 1].custo_efetivo : null;
      items = validas.map(x => ({
        casa_slug: x.casa_slug,
        nome: x.nome,
        custo_efetivo: x.custo_efetivo,
        custo_total: x.custo_efetivo * vol,
        economia_vs_pior: pior ? (pior - x.custo_efetivo) * vol : 0,
      }));
    }

    items.slice(0, 5).forEach(it => {
      const div = document.createElement('div');
      div.className = 'vol-card';
      div.innerHTML = `
        <div class="vol-nome">${it.nome}</div>
        <div class="vol-total">${fmtBRL2(it.custo_total)}</div>
        <div class="vol-economia">${it.economia_vs_pior > 0 ? '↓ economia ' + fmtBRL2(it.economia_vs_pior) : '—'}</div>
      `;
      c.appendChild(div);
    });

    if (!items.length) {
      c.innerHTML = '<p class="muted">Sem dados de volume ainda.</p>';
    }
  }

  function preencherFiltros() {
    const bairros = new Set();
    (state.latest?.cotacoes || []).forEach(c => c.bairro && bairros.add(c.bairro));
    const sel = $('#filtro-bairro');
    const cur = sel.value;
    sel.innerHTML = '<option value="">Todos</option>';
    [...bairros].sort().forEach(b => {
      const o = document.createElement('option');
      o.value = b; o.textContent = b;
      sel.appendChild(o);
    });
    sel.value = cur;
  }

  function filtrarELocalmente(cotacoes) {
    return cotacoes.filter(c => {
      if (state.filtroBairro && c.bairro !== state.filtroBairro) return false;
      if (state.filtroTipo && c.tipo !== state.filtroTipo) return false;
      return true;
    });
  }

  function sortCotacoes(cotacoes) {
    const k = state.sortKey;
    const dir = state.sortDir === 'asc' ? 1 : -1;
    return [...cotacoes].sort((a, b) => {
      const va = a[k]; const vb = b[k];
      if (va == null && vb == null) return 0;
      if (va == null) return 1;
      if (vb == null) return -1;
      if (typeof va === 'number') return (va - vb) * dir;
      return String(va).localeCompare(String(vb)) * dir;
    });
  }

  function renderTabela() {
    const tbody = $('#tabela-body');
    tbody.innerHTML = '';
    let cotacoes = filtrarELocalmente(state.latest?.cotacoes || []);
    cotacoes = sortCotacoes(cotacoes);

    if (!cotacoes.length) {
      $('#empty-msg').hidden = false;
      return;
    }
    $('#empty-msg').hidden = true;

    cotacoes.forEach(c => {
      const tr = document.createElement('tr');
      const isBest = c.e_menor_30_dias;
      const isAlert = c.observacao && c.observacao.includes('ALERTA');
      const isBelowThreshold = state.threshold && c.custo_efetivo < state.threshold;

      if (isBest || isBelowThreshold) tr.classList.add('row-best');
      else if (isAlert) tr.classList.add('row-alert');

      const variacao = c.variacao_dia_anterior_pct;
      const varHtml = variacao == null ? '—'
        : `<span class="${variacao > 0 ? 'var-up' : 'var-down'}">${variacao > 0 ? '↑' : '↓'} ${Math.abs(variacao).toFixed(2)}%</span>`;

      tr.innerHTML = `
        <td>${c.nome || c.casa_slug}
          ${isBest ? '<span class="tag best">↓ 30d</span>' : ''}
          ${isAlert ? '<span class="tag alert">!</span>' : ''}
        </td>
        <td>${c.bairro || '—'}</td>
        <td>${c.horario || '—'}</td>
        <td class="num">${fmtBRL(c.valor_venda_especie)}</td>
        <td class="num">${fmtPct(c.spread_ptax_pct)}</td>
        <td class="num"><strong>${fmtBRL(c.custo_efetivo)}</strong></td>
        <td class="num">${varHtml}</td>
        <td>${c.google_maps ? `<a class="btn-map" href="${c.google_maps}" target="_blank" rel="noopener">🗺️ Mapa</a>` : '—'}</td>
      `;
      tbody.appendChild(tr);
    });
  }

  // ---------- chart ----------
  function renderChart() {
    const canvas = $('#chart-historico');
    const ctx = canvas.getContext('2d');
    if (state.chart) state.chart.destroy();

    const serie = state.history?.serie_temporal || [];
    if (!serie.length) {
      ctx.font = '14px sans-serif';
      ctx.fillStyle = '#666';
      ctx.fillText('Histórico será exibido após mais coletas.', 20, 40);
      return;
    }

    // limitar pelo periodo escolhido
    const ultimosN = serie.slice(-state.chartPeriod);
    const labels = ultimosN.map(d => d.data);

    // descobrir casas presentes
    const casasMap = new Map();
    ultimosN.forEach(d => {
      Object.entries(d.casas || {}).forEach(([slug, info]) => {
        if (!casasMap.has(slug)) casasMap.set(slug, { nome: info.nome, valores: [] });
      });
    });

    casasMap.forEach((c, slug) => {
      c.valores = ultimosN.map(d => d.casas?.[slug]?.custo_efetivo ?? null);
    });

    const colors = ['#1e5a7a', '#2e8c5a', '#c0392b', '#f5b800', '#9b59b6', '#1abc9c', '#e67e22', '#34495e'];
    const datasets = [...casasMap.entries()].map(([slug, c], i) => ({
      label: c.nome,
      data: c.valores,
      borderColor: colors[i % colors.length],
      backgroundColor: colors[i % colors.length] + '20',
      tension: 0.2,
      spanGaps: true,
    }));

    state.chart = new Chart(ctx, {
      type: 'line',
      data: { labels, datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: { position: 'bottom', labels: { boxWidth: 12, font: { size: 11 } } },
        },
        scales: {
          y: { ticks: { callback: v => 'R$ ' + Number(v).toFixed(2) } },
        },
      },
    });
  }

  // ---------- eventos ----------
  function bindEvents() {
    $('#btn-recalcular').addEventListener('click', () => {
      state.volume = Math.max(100, parseInt($('#volume-input').value || '5000', 10));
      renderVolumeCards();
    });
    $('#btn-threshold').addEventListener('click', () => {
      const v = parseFloat($('#threshold-input').value);
      state.threshold = Number.isFinite(v) ? v : null;
      if (state.threshold != null) localStorage.setItem('threshold_eur_brl', state.threshold);
      else localStorage.removeItem('threshold_eur_brl');
      renderTabela();
    });
    $('#filtro-bairro').addEventListener('change', e => { state.filtroBairro = e.target.value; renderTabela(); });
    $('#filtro-tipo').addEventListener('change', e => { state.filtroTipo = e.target.value; renderTabela(); });

    document.querySelectorAll('th[data-sort]').forEach(th => {
      th.addEventListener('click', () => {
        const k = th.dataset.sort;
        if (state.sortKey === k) state.sortDir = state.sortDir === 'asc' ? 'desc' : 'asc';
        else { state.sortKey = k; state.sortDir = 'asc'; }
        renderTabela();
      });
    });

    document.querySelectorAll('.chart-controls button').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.chart-controls button').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        state.chartPeriod = parseInt(btn.dataset.period, 10);
        renderChart();
      });
    });

    if (state.threshold != null) $('#threshold-input').value = state.threshold;
    $('#volume-input').value = state.volume;
  }

  // ---------- bootstrap ----------
  async function init() {
    bindEvents();
    [state.latest, state.history, state.ranking] = await Promise.all([
      fetchJSON(DATA_LATEST),
      fetchJSON(DATA_HISTORY),
      fetchJSON(DATA_RANKING),
    ]);

    renderHeader();
    renderRefs();
    preencherFiltros();
    renderTop3();
    renderVolumeCards();
    renderTabela();
    renderChart();
  }

  document.addEventListener('DOMContentLoaded', init);
})();
