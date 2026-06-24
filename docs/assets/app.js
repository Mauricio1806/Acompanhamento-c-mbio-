/**
 * Monitor de Câmbio EUR/BRL - Salvador, BA
 * Dashboard interativo com dados de docs/data/*.json
 */

let latestData = null;
let historyData = null;
let rankingData = null;
let chartInstance = null;
let currentSortCol = -1;
let currentSortAsc = true;

// Carregar dados ao iniciar
document.addEventListener('DOMContentLoaded', async () => {
    loadThreshold();
    await loadAllData();
    renderAll();
});

async function loadAllData() {
    try {
        const [latestResp, historyResp, rankingResp] = await Promise.allSettled([
            fetch('data/latest.json').then(r => r.ok ? r.json() : null),
            fetch('data/history.json').then(r => r.ok ? r.json() : null),
            fetch('data/ranking.json').then(r => r.ok ? r.json() : null)
        ]);

        latestData = latestResp.status === 'fulfilled' ? latestResp.value : null;
        historyData = historyResp.status === 'fulfilled' ? historyResp.value : null;
        rankingData = rankingResp.status === 'fulfilled' ? rankingResp.value : null;
    } catch (e) {
        console.error('Erro ao carregar dados:', e);
    }
}

function renderAll() {
    if (!latestData || !latestData.cotacoes || latestData.cotacoes.length === 0) {
        showNoData();
        return;
    }
    renderLastUpdate();
    renderTop3();
    renderTable();
    populateFilters();
    renderChart(30);
}

function showNoData() {
    document.querySelector('.top3-section').innerHTML = `
        <div class="no-data">
            <div class="emoji">📭</div>
            <p>Nenhuma cotação disponível ainda.</p>
            <p>Os dados serão atualizados automaticamente às 10h e 16h.</p>
        </div>
    `;
}

function renderLastUpdate() {
    const el = document.getElementById('last-update');
    if (latestData?.meta) {
        const m = latestData.meta;
        el.textContent = `Última atualização: ${m.data_coleta} às ${m.hora_atualizacao} | ${m.total_casas} casas monitoradas`;
    }
}

function renderTop3() {
    const container = document.getElementById('top3-cards');
    if (!rankingData?.ranking?.top3?.length) {
        container.innerHTML = '<p class="no-data">Ranking será exibido após a primeira coleta.</p>';
        return;
    }

    const medals = ['🥇', '🥈', '🥉'];
    const volumes = [5000, 10000, 20000];
    const menor30d = latestData?.meta?.menor_custo_30_dias;

    container.innerHTML = rankingData.ranking.top3.map((item, i) => {
        const isMenor = menor30d && item.custo_efetivo <= menor30d;
        const volumeHtml = volumes.map(v => {
            const vData = item.diferenca_por_volume?.[String(v)];
            if (!vData) return '';
            return `<div>
                <span>EUR ${v.toLocaleString('pt-BR')}</span>
                <span>R$ ${vData.custo_total_brl?.toLocaleString('pt-BR', {minimumFractionDigits: 2})}</span>
            </div>`;
        }).join('');

        return `
            <div class="top3-card rank-${i + 1}">
                <div class="medal">${medals[i]}</div>
                <div class="casa-nome">${item.nome || item.casa_slug}</div>
                <div class="custo-efetivo">
                    R$ ${item.custo_efetivo?.toFixed(4)}
                    ${isMenor ? '<span class="badge-menor">Menor em 30 dias!</span>' : ''}
                </div>
                <div class="detalhe">Venda: R$ ${item.valor_venda?.toFixed(4) || '—'}</div>
                <div class="detalhe">Spread PTAX: ${item.spread_ptax?.toFixed(2) || '—'}%</div>
                <div class="volumes">${volumeHtml}</div>
            </div>
        `;
    }).join('');
}

function renderTable() {
    const tbody = document.getElementById('tabela-body');
    const threshold = parseFloat(localStorage.getItem('threshold_eur_brl')) || null;

    tbody.innerHTML = latestData.cotacoes.map(c => {
        const isThreshold = threshold && c.custo_efetivo && c.custo_efetivo < threshold;
        const varClass = c.variacao_dia_anterior_rs > 0 ? 'variacao-positiva' :
                         c.variacao_dia_anterior_rs < 0 ? 'variacao-negativa' : '';
        const varText = c.variacao_dia_anterior_rs !== null ?
            `${c.variacao_dia_anterior_rs > 0 ? '+' : ''}${c.variacao_dia_anterior_rs?.toFixed(4)} (${c.variacao_dia_anterior_pct?.toFixed(2)}%)` : '—';

        const pagamentos = (c.formas_pagamento || []).map(p => {
            if (p === 'Pix') return '<span class="icon-pix" title="Pix">💠</span>';
            return '';
        }).join('');

        const whatsappBtn = c.whatsapp ?
            `<a href="https://wa.me/${c.whatsapp}" class="btn-whatsapp" target="_blank">📱</a>` : '';

        const mapsBtn = c.google_maps ?
            `<a href="${c.google_maps}" class="btn-maps" target="_blank">📍Maps</a>` : '';

        return `
            <tr class="${isThreshold ? 'destaque-threshold' : ''}" 
                data-bairro="${c.bairro || ''}" data-tipo="${c.tipo || ''}">
                <td>
                    <strong>${c.nome}</strong>
                    ${pagamentos}
                    ${c.estoque_disponivel ? '' : '<span class="badge-alerta">Sem estoque</span>'}
                    <br><small>${c.endereco || ''}</small>
                    ${c.telefone ? `<br><small>📞 ${c.telefone}</small>` : ''}
                </td>
                <td>${c.bairro || '—'}</td>
                <td><small>${c.horario || '—'}</small></td>
                <td class="num"><strong>${c.valor_venda_especie?.toFixed(4) || '—'}</strong></td>
                <td class="num">${c.spread_ptax_pct?.toFixed(2) || '—'}%</td>
                <td class="num">${c.spread_wise_pct?.toFixed(2) || '—'}%</td>
                <td class="num"><strong>${c.custo_efetivo?.toFixed(4) || '—'}</strong></td>
                <td class="num ${varClass}">${varText}</td>
                <td>${mapsBtn} ${whatsappBtn}</td>
            </tr>
        `;
    }).join('');
}

function populateFilters() {
    const bairros = [...new Set(latestData.cotacoes.map(c => c.bairro).filter(Boolean))];
    const select = document.getElementById('filtro-bairro');
    select.innerHTML = '<option value="">Todos</option>' +
        bairros.map(b => `<option value="${b}">${b}</option>`).join('');
}

function filtrarTabela() {
    const bairro = document.getElementById('filtro-bairro').value;
    const tipo = document.getElementById('filtro-tipo').value;
    const rows = document.querySelectorAll('#tabela-body tr');

    rows.forEach(row => {
        const matchBairro = !bairro || row.dataset.bairro === bairro;
        const matchTipo = !tipo || row.dataset.tipo === tipo;
        row.style.display = matchBairro && matchTipo ? '' : 'none';
    });
}

function sortTable(colIndex) {
    if (currentSortCol === colIndex) {
        currentSortAsc = !currentSortAsc;
    } else {
        currentSortCol = colIndex;
        currentSortAsc = true;
    }

    const tbody = document.getElementById('tabela-body');
    const rows = Array.from(tbody.querySelectorAll('tr'));

    rows.sort((a, b) => {
        let aVal = a.cells[colIndex]?.textContent?.trim() || '';
        let bVal = b.cells[colIndex]?.textContent?.trim() || '';

        // Tentar como número
        const aNum = parseFloat(aVal.replace(/[^0-9.,-]/g, '').replace(',', '.'));
        const bNum = parseFloat(bVal.replace(/[^0-9.,-]/g, '').replace(',', '.'));

        if (!isNaN(aNum) && !isNaN(bNum)) {
            return currentSortAsc ? aNum - bNum : bNum - aNum;
        }
        return currentSortAsc ? aVal.localeCompare(bVal, 'pt-BR') : bVal.localeCompare(aVal, 'pt-BR');
    });

    rows.forEach(row => tbody.appendChild(row));
}

function recalcularRanking() {
    const volume = parseInt(document.getElementById('volume-input').value) || 5000;
    // Reordenar cotações e recalcular custo total para o volume
    if (!latestData?.cotacoes) return;

    const sorted = [...latestData.cotacoes]
        .filter(c => c.custo_efetivo)
        .sort((a, b) => a.custo_efetivo - b.custo_efetivo);

    const top3Container = document.getElementById('top3-cards');
    const medals = ['🥇', '🥈', '🥉'];
    const pior = sorted[sorted.length - 1];

    top3Container.innerHTML = sorted.slice(0, 3).map((item, i) => {
        const custoTotal = (item.custo_efetivo * volume).toFixed(2);
        const economia = pior ? ((pior.custo_efetivo - item.custo_efetivo) * volume).toFixed(2) : '0.00';

        return `
            <div class="top3-card rank-${i + 1}">
                <div class="medal">${medals[i]}</div>
                <div class="casa-nome">${item.nome}</div>
                <div class="custo-efetivo">R$ ${item.custo_efetivo?.toFixed(4)}</div>
                <div class="detalhe">Venda: R$ ${item.valor_venda_especie?.toFixed(4) || '—'}</div>
                <div class="volumes">
                    <div>
                        <span>EUR ${volume.toLocaleString('pt-BR')}</span>
                        <span>R$ ${parseFloat(custoTotal).toLocaleString('pt-BR', {minimumFractionDigits: 2})}</span>
                    </div>
                    <div>
                        <span>Economia vs pior:</span>
                        <span style="color: var(--success)">R$ ${parseFloat(economia).toLocaleString('pt-BR', {minimumFractionDigits: 2})}</span>
                    </div>
                </div>
            </div>
        `;
    }).join('');
}

function loadThreshold() {
    const saved = localStorage.getItem('threshold_eur_brl');
    if (saved) {
        document.getElementById('threshold-input').value = saved;
    }
}

function aplicarThreshold() {
    const val = document.getElementById('threshold-input').value;
    if (val) {
        localStorage.setItem('threshold_eur_brl', val);
    } else {
        localStorage.removeItem('threshold_eur_brl');
    }
    renderTable();
}

function renderChart(dias) {
    // Update button states
    document.querySelectorAll('.chart-controls button').forEach(btn => {
        btn.classList.toggle('active', btn.textContent.includes(dias));
    });

    if (!historyData?.serie_temporal?.length) {
        const ctx = document.getElementById('chart-historico').getContext('2d');
        if (chartInstance) chartInstance.destroy();
        ctx.font = '16px sans-serif';
        ctx.fillStyle = '#7f8c8d';
        ctx.textAlign = 'center';
        ctx.fillText('Dados históricos serão exibidos após coletas suficientes.', ctx.canvas.width / 2, ctx.canvas.height / 2);
        return;
    }

    const cutoff = new Date();
    cutoff.setDate(cutoff.getDate() - dias);
    const filtered = historyData.serie_temporal.filter(d => new Date(d.data) >= cutoff);

    const labels = filtered.map(d => d.data);

    // Coletar todas as casas únicas
    const casaSet = new Set();
    filtered.forEach(d => Object.keys(d.casas || {}).forEach(s => casaSet.add(s)));
    const casas = [...casaSet];

    const colors = [
        '#e74c3c', '#3498db', '#2ecc71', '#f39c12', '#9b59b6',
        '#1abc9c', '#e67e22', '#34495e', '#16a085', '#c0392b',
        '#2980b9', '#27ae60', '#8e44ad', '#d35400'
    ];

    const datasets = casas.map((slug, i) => ({
        label: slug,
        data: filtered.map(d => d.casas?.[slug]?.custo_efetivo || null),
        borderColor: colors[i % colors.length],
        backgroundColor: colors[i % colors.length] + '20',
        tension: 0.3,
        pointRadius: 2,
        borderWidth: 2,
        spanGaps: true
    }));

    // Add PTAX line
    const ptaxData = filtered.map(d => d.ptax);
    if (ptaxData.some(v => v != null)) {
        datasets.unshift({
            label: 'PTAX (ref)',
            data: ptaxData,
            borderColor: '#2c3e50',
            borderDash: [5, 5],
            borderWidth: 2,
            pointRadius: 0,
            spanGaps: true
        });
    }

    const ctx = document.getElementById('chart-historico').getContext('2d');
    if (chartInstance) chartInstance.destroy();

    chartInstance = new Chart(ctx, {
        type: 'line',
        data: { labels, datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: { boxWidth: 12, font: { size: 11 } }
                },
                tooltip: {
                    callbacks: {
                        label: ctx => `${ctx.dataset.label}: R$ ${ctx.parsed.y?.toFixed(4) || '—'}`
                    }
                }
            },
            scales: {
                y: {
                    title: { display: true, text: 'R$ / EUR' },
                    ticks: { callback: v => 'R$ ' + v.toFixed(2) }
                },
                x: {
                    ticks: { maxTicksLimit: 15 }
                }
            }
        }
    });
}

function setChartPeriod(dias) {
    renderChart(dias);
}
