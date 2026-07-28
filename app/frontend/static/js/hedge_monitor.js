const money = new Intl.NumberFormat('zh-TW', { maximumFractionDigits: 2 });
const number = new Intl.NumberFormat('zh-TW', { maximumFractionDigits: 6 });

function pnlClass(value) {
    return value > 0 ? 'positive' : value < 0 ? 'negative' : '';
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
        const response = await fetch('/api/hedge-connections/bingx');
        const data = await response.json();
        if (!data.success) throw new Error(data.error);
        const balance = data.balance.equity || data.balance.balance || '—';
        document.getElementById('connection-status').textContent =
            `${data.message} ｜帳戶權益：${balance} ｜目前部位：${data.open_position_count} 筆`;
        document.getElementById('connection-status').className = 'alert alert-success';
    } catch (error) {
        showError(`BingX 連線失敗：${error.message}`);
    } finally {
        button.disabled = false;
        button.textContent = '測試 BingX 連線';
    }
});

loadPortfolios(false).catch(error => showError(error.message));
