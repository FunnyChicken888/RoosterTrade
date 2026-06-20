$(document).ready(function () {

    // ── 連線狀態膠囊 ──
    function setConnPill(state, label) {
        const $p = $('#connStatus');
        $p.removeClass('conn-ok conn-fail conn-unknown').addClass('conn-' + state);
        $p.find('.conn-label').text(label);
    }

    function refreshConnPill() {
        $.get('/api/check_connection')
            .done((r) => setConnPill(r.success ? 'ok' : 'fail', r.success ? '已連線' : '未連線'))
            .fail(() => setConnPill('fail', '未連線'));
    }

    // 手動「檢查連線」按鈕
    $('#checkApiBtn').click(function () {
        const $btn = $(this);
        const $status = $('#apiStatus');
        $btn.prop('disabled', true).html('<i class="fas fa-spinner fa-spin me-1"></i> 檢查中...');
        $.get('/api/check_connection')
            .done(function (resp) {
                $status.removeClass('d-none alert-danger alert-success')
                    .addClass(resp.success ? 'alert-success' : 'alert-danger')
                    .html(`<i class="fas fa-${resp.success ? 'check' : 'triangle-exclamation'} me-2"></i>${resp.message}`)
                    .show();
                setConnPill(resp.success ? 'ok' : 'fail', resp.success ? '已連線' : '未連線');
            })
            .fail(function () {
                $status.removeClass('d-none alert-success').addClass('alert-danger')
                    .html('<i class="fas fa-triangle-exclamation me-2"></i>檢查 API 連線時發生錯誤').show();
                setConnPill('fail', '未連線');
            })
            .always(() => $btn.prop('disabled', false).html('<i class="fas fa-plug me-1"></i> 檢查連線'));
    });

    // ── 刪除策略 ──
    $('.delete-strategy').click(function () {
        const name = $(this).data('strategy');
        if (!confirm(`確定要刪除策略「${name}」嗎？此操作會備份並移除其交易紀錄。`)) return;
        $.ajax({
            url: `/strategy/delete/${encodeURIComponent(name)}`,
            method: 'POST',
            success: (resp) => resp.success ? location.reload() : alert('刪除策略失敗：' + (resp.error || '未知錯誤')),
            error: () => alert('刪除策略時發生錯誤，請稍後再試。')
        });
    });

    // 今日交易次數接近上限時變色
    function updateTradeCountStyle() {
        $('.today-trade-count').each(function () {
            const [cur, lim] = $(this).text().split('/').map((x) => parseInt(x, 10));
            $(this).toggleClass('trade-count-warning', cur >= lim - 1);
        });
    }

    // ── 即時資料刷新 ──
    function updateStrategyInfo() {
        $.get('/api/strategies', function (data) {
            (data || []).forEach(function (s) {
                const c = $(`.real-time-info[data-strategy="${s.config.strategy_name}"]`);
                if (!c.length) return;
                c.find('.current-balance').text(Number(s.current_balance).toFixed(4));
                c.find('.current-price').text(Number(s.current_price).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }));
                c.find('.current-value').text(Number(s.current_value).toLocaleString('en-US', { maximumFractionDigits: 0 }));
                c.find('.buy-price').text(Number(s.buy_trigger_price).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }));
                c.find('.sell-price').text(Number(s.sell_trigger_price).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }));
                c.find('.today-trade-count').text(`${s.today_trade_count}/${s.config.daily_trade_limit}`);
                c.find('.trade-count').text(s.trade_count);

                const np = c.find('.net-profit');
                np.text((s.net_profit > 0 ? '+' : '') + Number(s.net_profit).toLocaleString('en-US', { maximumFractionDigits: 0 }))
                    .removeClass('pos neg').addClass(s.net_profit > 0 ? 'pos' : s.net_profit < 0 ? 'neg' : '');

                // 觸發價接近提示
                c.find('.buy-trigger').toggleClass('near-trigger', s.current_price <= s.buy_trigger_price * 1.01);
                c.find('.sell-trigger').toggleClass('near-trigger', s.current_price >= s.sell_trigger_price * 0.99);
            });
            updateTradeCountStyle();
            $('#lastUpdate').text(new Date().toLocaleTimeString('zh-TW', { hour12: false }));
        });
    }

    // 執行所有活躍策略（伺服器端有 Lock 保證不會重複觸發）
    function executeStrategies() {
        $.ajax({
            url: '/api/execute_strategies', method: 'POST',
            success: function (resp) {
                if (resp.success && resp.results && resp.results.length) {
                    resp.results.forEach((r) => {
                        const a = r.action === 'take_profit' ? '停利' : '交易';
                        console.log(`${r.strategy_name}: ${a} - ${r.message}`);
                    });
                } else if (!resp.success) {
                    console.error('執行策略失敗：', resp.error);
                }
            },
            error: () => console.error('執行策略時發生錯誤')
        });
    }

    // 啟動：立即刷新一次，之後每 60 秒
    refreshConnPill();
    updateStrategyInfo();
    updateTradeCountStyle();
    executeStrategies();
    setInterval(refreshConnPill, 60000);
    setInterval(updateStrategyInfo, 60000);
    setInterval(executeStrategies, 60000);
});
