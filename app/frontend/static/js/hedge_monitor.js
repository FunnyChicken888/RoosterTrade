const money = new Intl.NumberFormat('zh-TW', { maximumFractionDigits: 2 });
const number = new Intl.NumberFormat('zh-TW', { maximumFractionDigits: 6 });

function pnlClass(value) {
    return value > 0 ? 'positive' : value < 0 ? 'negative' : '';
}

function pct(value) {
    return value == null ? '—' : `${money.format(value * 100)}%`;
}

function showError(message) {
    const box = document.getElementById('page-error');
    box.textContent = message;
    box.classList.remove('d-none');
}

function renderPortfolio(result) {
    const p = result.portfolio;
    const m = result.metrics;
    const warnings = result.warnings.map(item => `<li>${item}</li>`).join('');
    const fundingRate = p.funding_rate == null ? '—' : `${number.format(p.funding_rate * 100)}%`;
    return `
        <div class="col-xl-6 mb-4">
            <article class="card h-100 hedge-card">
                <div class="card-body">
                    <div class="d-flex justify-content-between align-items-start">
                        <div><h5>${p.name}</h5><span class="text-muted">${p.spot_symbol} / ${p.perp_symbol}</span></div>
                        <span class="badge bg-dark">避險率 ${money.format(m.hedge_ratio * 100)}%</span>
                    </div>
                    ${warnings ? `<div class="alert alert-warning mt-3 mb-0"><ul class="mb-0">${warnings}</ul></div>` : ''}
                    <div class="row g-2 mt-2">
                        <div class="col-6"><div class="metric"><span>台股部位</span><strong>${number.format(p.spot_quantity)} 股</strong></div></div>
                        <div class="col-6"><div class="metric"><span>空單等值</span><strong>${number.format(m.short_equivalent_shares)} 股</strong></div></div>
                        <div class="col-6"><div class="metric"><span>現貨損益</span><strong class="${pnlClass(m.spot_pnl_twd)}">${money.format(m.spot_pnl_twd)} TWD</strong></div></div>
                        <div class="col-6"><div class="metric"><span>永續損益</span><strong class="${pnlClass(m.perp_pnl_twd)}">${money.format(m.perp_pnl_twd)} TWD</strong></div></div>
                        <div class="col-6"><div class="metric"><span>資金費</span><strong class="${pnlClass(m.funding_twd)}">${money.format(m.funding_twd)} TWD</strong></div></div>
                        <div class="col-6"><div class="metric"><span>目前資金費率</span><strong>${fundingRate}</strong></div></div>
                        <div class="col-6"><div class="metric"><span>永續溢價率</span><strong>${money.format(m.premium_rate * 100)}%</strong></div></div>
                        <div class="col-6"><div class="metric"><span>淨曝險</span><strong>${number.format(m.net_exposure_shares)} 股</strong></div></div>
                    </div>
                    <div class="total-pnl mt-3">
                        <span>台幣總損益</span>
                        <strong class="${pnlClass(m.total_pnl_twd)}">${money.format(m.total_pnl_twd)} TWD</strong>
                    </div>
                    <div class="small text-muted mt-2">資料源：永豐 ${result.source_status.sinopac}、BingX ${result.source_status.bingx}、USDT/TWD ${result.source_status.fx}</div>
                </div>
            </article>
        </div>`;
}

const ALERT_STYLE = {
    CRIT: { badge: 'bg-danger', row: 'border-danger' },
    WARN: { badge: 'bg-warning text-dark', row: 'border-warning' },
    INFO: { badge: 'bg-info text-dark', row: 'border-info' },
};

function topLevel(alerts) {
    if (alerts.some(a => a.level === 'CRIT')) return 'CRIT';
    if (alerts.some(a => a.level === 'WARN')) return 'WARN';
    if (alerts.some(a => a.level === 'INFO')) return 'INFO';
    return null;
}

const EXCHANGE_BADGE = { bingx: 'bg-primary', binance: 'bg-warning text-dark' };
const EXCHANGE_LABEL = { bingx: 'BingX', binance: '幣安' };

function renderBingxPosition(p) {
    const sideBadge = p.side === 'short'
        ? '<span class="badge bg-danger">空腿 SHORT</span>'
        : '<span class="badge bg-success">多腿 LONG</span>';
    const exBadge = `<span class="badge ${EXCHANGE_BADGE[p.exchange] || 'bg-secondary'} me-1">${p.exchange_label || p.exchange}</span>`;
    const level = topLevel(p.alerts);
    const border = level ? ALERT_STYLE[level].row : '';
    const alertHtml = p.alerts.length
        ? `<div class="mt-2">${p.alerts.map(a =>
              `<div class="small"><span class="badge ${ALERT_STYLE[a.level].badge} me-1">${a.level}</span>${a.msg}</div>`
          ).join('')}</div>`
        : '<div class="small text-success mt-2"><i class="fas fa-check me-1"></i>無風控示警</div>';
    const funding = p.funding_rate == null ? '—' : `${number.format(p.funding_rate * 100)}%`;
    return `
        <article class="border ${border} rounded p-3 mb-2">
            <div class="d-flex justify-content-between align-items-start flex-wrap gap-2">
                <div>${exBadge}<strong>${p.symbol}</strong> ${sideBadge}
                    ${p.leverage ? `<span class="badge bg-dark ms-1">${p.leverage}x</span>` : ''}</div>
                <strong class="${pnlClass(p.unrealized_profit)}">${money.format(p.unrealized_profit)} USDT</strong>
            </div>
            <div class="row g-2 mt-1 small">
                <div class="col-6 col-md-3"><span class="text-muted">部位量</span><br>${number.format(p.position_amt)}</div>
                <div class="col-6 col-md-3"><span class="text-muted">均價</span><br>${money.format(p.entry_price)}</div>
                <div class="col-6 col-md-3"><span class="text-muted">標記價</span><br>${money.format(p.mark_price)}</div>
                <div class="col-6 col-md-3"><span class="text-muted">強平價</span><br>${money.format(p.liquidation_price)}</div>
                <div class="col-6 col-md-3"><span class="text-muted">保證金</span><br>${money.format(p.margin)} USDT</div>
                <div class="col-6 col-md-3"><span class="text-muted">資金費率</span><br>${funding}</div>
            </div>
            ${alertHtml}
        </article>`;
}

async function loadBingxPositions() {
    const box = document.getElementById('bingx-positions');
    box.innerHTML = '<div class="text-muted small">讀取中…</div>';
    try {
        const response = await fetch('/api/hedge-connections/positions');
        const data = await response.json();
        if (!data.success) {
            box.innerHTML = `<div class="alert alert-warning mb-0">${data.error}</div>`;
            return;
        }
        const conn = data.connections || {};
        const unconfigured = Object.keys(conn)
            .filter(k => conn[k] === 'unconfigured')
            .map(k => EXCHANGE_LABEL[k] || k);
        const notices = [];
        if (unconfigured.length) {
            notices.push(`<div class="alert alert-secondary mb-2 small">尚未設定 API Key：${unconfigured.join('、')}（設定後即可自動抓取該所部位）</div>`);
        }
        (data.errors || []).forEach(msg =>
            notices.push(`<div class="alert alert-warning mb-2 small">${msg}</div>`));
        box.innerHTML = notices.join('') + (data.positions.length
            ? data.positions.map(renderBingxPosition).join('')
            : '<div class="alert alert-info mb-0">目前沒有未平倉合約部位。</div>');
        bingxPositions = data.positions;
        syncUsdPairing();
    } catch (error) {
        box.innerHTML = `<div class="alert alert-danger mb-0">讀取失敗：${error.message}</div>`;
    }
}

/* ── 手動多腿 × BingX 空腿（USD 對比，伺服器持久化）─────────────── */
let bingxPositions = [];
let usdLegs = [];

function pairKey(p) {
    return `${p.exchange}|${p.symbol}`;
}

function populatePairOptions() {
    const select = document.getElementById('pair-symbol');
    const prev = select.value;
    const keys = bingxPositions.map(pairKey);
    select.innerHTML = bingxPositions.length
        ? bingxPositions.map(p =>
            `<option value="${pairKey(p)}">[${p.exchange_label || p.exchange}] ${p.symbol}（${p.side === 'short' ? '空' : '多'}）</option>`
          ).join('')
        : '<option value="">（尚未讀取到合約部位）</option>';
    if (keys.includes(prev)) select.value = prev;
    updateBaselineHint();
}

function selectedPairPosition() {
    const value = document.getElementById('pair-symbol').value;
    return bingxPositions.find(p => pairKey(p) === value);
}

function updateBaselineHint() {
    const hint = document.getElementById('baseline-hint');
    if (!hint) return;
    const pos = selectedPairPosition();
    if (!pos) {
        hint.textContent = '交易所參考值：選擇空腿後顯示';
        return;
    }
    const realised = pos.realised_profit == null
        ? '此交易所未提供已實現（請自行填入）'
        : `已實現 <strong>${money.format(pos.realised_profit)}</strong>`;
    hint.innerHTML = `${pos.exchange_label} 參考：${realised}、未實現 ${money.format(pos.unrealized_profit)} USDT`;
}

function renderComparison(leg) {
    const m = leg.metrics || {};
    const s = m.short;
    const exLabel = EXCHANGE_LABEL[leg.pair_exchange] || leg.pair_exchange || 'BingX';
    let shortBlock = `<div class="alert alert-warning mb-0 small">目前抓不到 ${exLabel} 部位「${leg.pair_symbol}」（可能已平倉或未設定該所 API Key）。空腿以手動基準已實現計。</div>`;
    if (s) {
        shortBlock = `
            <div class="row g-2 small">
                <div class="col-6"><span class="text-muted">空腿即時未實現</span><br><span class="${pnlClass(s.unrealized_profit)}">${money.format(s.unrealized_profit)} USDT</span></div>
                <div class="col-6"><span class="text-muted">等值曝險 ×${number.format(leg.delta_factor)}</span><br>${money.format(s.short_exposure)} USD</div>
                <div class="col-6"><span class="text-muted">避險率</span><br>${m.hedge_ratio == null ? '—' : money.format(m.hedge_ratio * 100) + '%'}</div>
                <div class="col-6"><span class="text-muted">${s.exchange_label} 自動已實現（參考）</span><br>${s.realised_profit_auto == null ? '未提供' : money.format(s.realised_profit_auto) + ' USDT'}</div>
            </div>`;
    }
    const netExposure = m.net_exposure;
    return `
        <div class="col-xl-6 mb-3">
            <article class="border rounded p-3 h-100">
                <div class="d-flex justify-content-between align-items-start">
                    <div>
                        <strong>${leg.label}</strong>
                        <span class="badge bg-success ms-1">多腿 ${leg.broker || '手動'}</span>
                        <div class="small text-muted">${number.format(leg.quantity)} @ ${money.format(leg.avg_price)} → ${money.format(leg.current_price)} USD ｜ 配對 <span class="badge ${EXCHANGE_BADGE[leg.pair_exchange] || 'bg-secondary'}">${exLabel}</span> ${leg.pair_symbol}</div>
                        ${leg.entry_date ? `<div class="small text-muted"><i class="fas fa-calendar-day me-1"></i>購入 ${leg.entry_date}｜持有 ${m.days_held == null ? '—' : m.days_held} 天</div>` : ''}
                        ${leg.note ? `<div class="small text-muted"><i class="fas fa-note-sticky me-1"></i>${leg.note}</div>` : ''}
                    </div>
                    <div class="d-flex gap-1">
                        <button class="btn btn-sm btn-outline-secondary" data-edit-leg="${leg.id}">更新價</button>
                        <button class="btn btn-sm btn-outline-primary" data-snap-leg="${leg.id}">記錄快照</button>
                        <button class="btn btn-sm btn-outline-danger" data-del-leg="${leg.id}">刪除</button>
                    </div>
                </div>
                <div class="row g-2 mt-1 small">
                    <div class="col-6"><span class="text-muted">多腿市值</span><br>${money.format(m.long_value)} USD</div>
                    <div class="col-6"><span class="text-muted">多腿損益</span><br><span class="${pnlClass(m.long_pnl)}">${money.format(m.long_pnl)} USD</span></div>
                    <div class="col-6"><span class="text-muted">空腿基準已實現</span><br>${money.format(m.baseline_realized_usd)} USD</div>
                    <div class="col-6"><span class="text-muted">空腿真實累計</span><br><span class="${pnlClass(m.short_true_total)}">${money.format(m.short_true_total)} USD</span></div>
                </div>
                <hr class="my-2">
                ${shortBlock}
                <div class="row g-2 mt-2">
                    <div class="col-md-4">
                        <div class="stat-card p-2">
                            <div class="small text-muted">淨美元曝險</div>
                            <strong class="${netExposure > 0 ? 'positive' : netExposure < 0 ? 'negative' : ''}">${netExposure == null ? '—' : money.format(netExposure) + ' USD'}</strong>
                            <div class="small text-muted">${netExposure == null ? '' : (netExposure >= 0 ? '偏多（多腿較大）' : '偏空（空腿較大）')}</div>
                        </div>
                    </div>
                    <div class="col-md-4">
                        <div class="stat-card p-2">
                            <div class="small text-muted">合併真實損益（多+空）</div>
                            <strong class="${pnlClass(m.combined_pnl)}">${money.format(m.combined_pnl)} USD</strong>
                            <div class="small text-muted">期間報酬 ${pct(m.period_return)}</div>
                        </div>
                    </div>
                    <div class="col-md-4">
                        <div class="stat-card p-2">
                            <div class="small text-muted">年化報酬率</div>
                            <strong class="${m.annualized_return == null ? '' : pnlClass(m.annualized_return)}">${pct(m.annualized_return)}</strong>
                            <div class="small text-muted">${m.days_held == null ? '需填購入時間' : '基準：多腿成本 ' + money.format(m.cost_basis)}</div>
                        </div>
                    </div>
                </div>
                <div class="small text-muted mt-2" data-snap-info="${leg.id}"></div>
            </article>
        </div>`;
}

function renderComparisons() {
    const box = document.getElementById('usd-comparisons');
    box.innerHTML = usdLegs.length
        ? usdLegs.map(renderComparison).join('')
        : '<div class="col-12"><div class="alert alert-info mb-0">尚未新增手動多腿。填入上方欄位即可與 BingX 空腿做美元對比並存到伺服器。</div></div>';
    box.querySelectorAll('[data-del-leg]').forEach(btn =>
        btn.addEventListener('click', () => deleteLeg(btn.dataset.delLeg)));
    box.querySelectorAll('[data-snap-leg]').forEach(btn =>
        btn.addEventListener('click', () => snapshotLeg(btn.dataset.snapLeg, btn)));
    box.querySelectorAll('[data-edit-leg]').forEach(btn =>
        btn.addEventListener('click', () => editLeg(btn.dataset.editLeg)));
}

async function loadUsdLegs() {
    try {
        const res = await fetch('/api/usd-hedge-legs');
        const data = await res.json();
        if (!data.success) throw new Error(data.error);
        usdLegs = data.legs;
        renderComparisons();
    } catch (e) {
        document.getElementById('usd-comparisons').innerHTML =
            `<div class="col-12"><div class="alert alert-danger mb-0">讀取多腿紀錄失敗：${e.message}</div></div>`;
    }
}

async function deleteLeg(id) {
    if (!confirm('確定刪除這筆多腿對比（含其快照紀錄）？')) return;
    await fetch(`/api/usd-hedge-legs/${id}`, { method: 'DELETE' });
    loadUsdLegs();
}

async function editLeg(id) {
    const leg = usdLegs.find(l => String(l.id) === String(id));
    if (!leg) return;
    const cp = prompt('更新多腿現價（USD）：', leg.current_price);
    if (cp === null) return;
    const base = prompt('更新空腿基準已實現（USD）：', leg.baseline_realized_usd);
    if (base === null) return;
    const ed = prompt('購入時間（YYYY-MM-DD，供年化報酬計算）：', leg.entry_date || '');
    if (ed === null) return;
    await fetch(`/api/usd-hedge-legs/${id}`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            current_price: parseFloat(cp),
            baseline_realized_usd: parseFloat(base),
            entry_date: ed.trim(),
        }),
    });
    loadUsdLegs();
}

async function snapshotLeg(id, btn) {
    btn.disabled = true;
    try {
        const res = await fetch(`/api/usd-hedge-legs/${id}/snapshot`, { method: 'POST' });
        const data = await res.json();
        if (!data.success) throw new Error(data.error);
        await showSnapshotInfo(id);
    } catch (e) {
        alert('記錄快照失敗：' + e.message);
    } finally {
        btn.disabled = false;
    }
}

async function showSnapshotInfo(id) {
    const el = document.querySelector(`[data-snap-info="${id}"]`);
    if (!el) return;
    const res = await fetch(`/api/usd-hedge-legs/${id}/snapshots?limit=5`);
    const data = await res.json();
    if (!data.success || !data.snapshots.length) { el.textContent = '尚無快照紀錄'; return; }
    const latest = data.snapshots[0];
    const when = new Date(latest.captured_at).toLocaleString('zh-TW');
    el.innerHTML = `<i class="fas fa-clock-rotate-left me-1"></i>已存 ${data.snapshots.length} 筆快照｜最近 ${when}：合併 ${money.format(latest.metrics.combined_pnl)} USD`;
}

function syncUsdPairing() {
    populatePairOptions();
    loadUsdLegs();   // 伺服器端會用即時 BingX 部位重算 metrics
}

document.getElementById('pair-symbol').addEventListener('change', updateBaselineHint);

document.getElementById('usd-leg-form').addEventListener('submit', async event => {
    event.preventDefault();
    const payload = Object.fromEntries(new FormData(event.target).entries());
    // 下拉選單的值是 "exchange|symbol"，拆成兩個欄位送出
    const [pairExchange, pairSymbol] = String(payload.pair_symbol || '').split('|');
    if (!pairSymbol) {
        showError('請先選擇要配對的合約空腿（需先讀取到交易所部位）');
        return;
    }
    payload.pair_exchange = pairExchange;
    payload.pair_symbol = pairSymbol;
    try {
        const res = await fetch('/api/usd-hedge-legs', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const data = await res.json();
        if (!data.success) throw new Error(data.error);
        event.target.reset();
        document.querySelector('input[name="broker"]').value = 'Firstrade';
        document.querySelector('input[name="delta_factor"]').value = '1';
        populatePairOptions();
        loadUsdLegs();
    } catch (e) {
        showError('新增多腿失敗：' + e.message);
    }
});

async function loadPortfolios(refresh = false) {
    document.getElementById('page-error').classList.add('d-none');
    const response = await fetch(`/api/hedge-portfolios?refresh=${refresh ? 1 : 0}`);
    const data = await response.json();
    if (!data.success) throw new Error(data.error);
    document.getElementById('connection-status').textContent =
        `永豐 API：${data.connections.sinopac_configured ? '已設定' : '未設定（使用手動資料）'} ｜ ` +
        `BingX API：${data.connections.bingx_configured ? '已設定' : '未設定（公開行情／手動部位）'}`;
    document.getElementById('portfolio-list').innerHTML = data.portfolios.length
        ? data.portfolios.map(renderPortfolio).join('')
        : '<div class="col-12"><div class="alert alert-info">尚未建立避險組合。</div></div>';
}

document.getElementById('portfolio-form').addEventListener('submit', async event => {
    event.preventDefault();
    try {
        const payload = Object.fromEntries(new FormData(event.target).entries());
        const response = await fetch('/api/hedge-portfolios', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const data = await response.json();
        if (!data.success) throw new Error(data.error);
        await loadPortfolios(false);
    } catch (error) {
        showError(error.message);
    }
});

document.getElementById('refresh-live').addEventListener('click', async event => {
    event.currentTarget.disabled = true;
    event.currentTarget.textContent = '同步中…';
    try { await loadPortfolios(true); }
    catch (error) { showError(error.message); }
    finally {
        event.currentTarget.disabled = false;
        event.currentTarget.textContent = '同步帳戶與行情';
    }
});

document.getElementById('test-bingx').addEventListener('click', async event => {
    const button = event.currentTarget;
    button.disabled = true;
    button.textContent = '測試中…';
    try {
        const results = await Promise.all(['bingx', 'binance'].map(async ex => {
            try {
                const res = await fetch(`/api/hedge-connections/${ex}`);
                const data = await res.json();
                if (!data.success) {
                    return `${EXCHANGE_LABEL[ex]}：${data.configured === false ? '未設定 API Key' : '連線失敗（' + data.error + '）'}`;
                }
                const balance = data.balance.equity || data.balance.balance || '—';
                return `${EXCHANGE_LABEL[ex]}：正常，權益 ${balance}，部位 ${data.open_position_count} 筆`;
            } catch (e) {
                return `${EXCHANGE_LABEL[ex]}：連線失敗（${e.message}）`;
            }
        }));
        const box = document.getElementById('connection-status');
        box.innerHTML = results.join('<br>');
        box.className = 'alert alert-secondary';
    } finally {
        button.disabled = false;
        button.textContent = '測試交易所連線';
    }
});

document.getElementById('refresh-bingx-positions').addEventListener('click', async event => {
    event.currentTarget.disabled = true;
    try { await loadBingxPositions(); }
    finally { event.currentTarget.disabled = false; }
});

loadUsdLegs();                // 從伺服器讀取已存的手動多腿對比
loadPortfolios(false).catch(error => showError(error.message));
loadBingxPositions();         // 抓到 BingX 部位後會自動配對重算
