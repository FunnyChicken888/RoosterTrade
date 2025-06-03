$(document).ready(function() {
    // API連線檢查
    $('#checkApiBtn').click(function() {
        const $btn = $(this);
        const $status = $('#apiStatus');
        
        // 禁用按鈕，顯示載入狀態
        $btn.prop('disabled', true).text('檢查中...');
        
        // 發送API請求
        $.get('/api/check_connection')
            .done(function(response) {
                $status.removeClass('d-none alert-danger alert-success')
                    .addClass(response.success ? 'alert-success' : 'alert-danger')
                    .text(response.message)
                    .show();
            })
            .fail(function(jqXHR) {
                $status.removeClass('d-none alert-success')
                    .addClass('alert-danger')
                    .text('檢查API連線時發生錯誤')
                    .show();
            })
            .always(function() {
                // 恢復按鈕狀態
                $btn.prop('disabled', false).text('檢查API連線');
            });
    });

    // 處理策略刪除
    $('.delete-strategy').click(function() {
        const strategyName = $(this).data('strategy');
        if (confirm(`確定要刪除策略 "${strategyName}" 嗎？`)) {
            $.ajax({
                url: `/strategy/delete/${strategyName}`,
                method: 'POST',
                success: function(response) {
                    if (response.success) {
                        location.reload();
                    } else {
                        alert('刪除策略失敗：' + (response.error || '未知錯誤'));
                    }
                },
                error: function() {
                    alert('刪除策略時發生錯誤，請稍後再試。');
                }
            });
        }
    });

    // 更新交易次數顯示顏色
    function updateTradeCountStyle() {
        $('.today-trade-count').each(function() {
            const [current, limit] = $(this).text().split('/');
            if (parseInt(current) >= parseInt(limit) - 1) {
                $(this).addClass('trade-count-warning');
            } else {
                $(this).removeClass('trade-count-warning');
            }
        });
    }

    // 自動更新功能
    function updateStrategyInfo() {
        $.get('/api/strategies', function(data) {
            data.forEach(function(strategy) {
                const container = $(`.real-time-info[data-strategy="${strategy.config.strategy_name}"]`);
                
                // 更新基本資訊
                container.find('.current-balance').text(strategy.current_balance.toFixed(4));
                container.find('.current-price').text(strategy.current_price.toFixed(2));
                container.find('.current-value').text(strategy.current_value.toFixed(2));
                
                // 更新觸發價格
                container.find('.buy-price').text(strategy.buy_trigger_price.toFixed(2));
                container.find('.sell-price').text(strategy.sell_trigger_price.toFixed(2));
                
                // 更新交易次數
                container.find('.today-trade-count').text(
                    `${strategy.today_trade_count}/${strategy.config.daily_trade_limit}`
                );
                container.find('.trade-count').text(strategy.trade_count);
                
                // 更新套利金額
                const netProfitElement = container.find('.net-profit');
                netProfitElement.text(strategy.net_profit.toFixed(2));
                netProfitElement
                    .removeClass('positive negative')
                    .addClass(strategy.net_profit > 0 ? 'positive' : strategy.net_profit < 0 ? 'negative' : '');
                
                // 更新交易次數顯示樣式
                updateTradeCountStyle();
                
                // 更新觸發價格的顯示樣式
                const currentPrice = strategy.current_price;
                const buyPrice = strategy.buy_trigger_price;
                const sellPrice = strategy.sell_trigger_price;
                
                // 根據當前價格相對於觸發價格的位置更新樣式
                container.find('.buy-trigger')
                    .toggleClass('near-trigger', currentPrice <= buyPrice * 1.01);
                container.find('.sell-trigger')
                    .toggleClass('near-trigger', currentPrice >= sellPrice * 0.99);
            });
        });
    }

    // 每分鐘執行一次策略檢查
    setInterval(executeStrategies, 60000);
    setInterval(updateStrategyInfo, 60000);
    
    // 頁面載入時立即執行一次
    executeStrategies();
    updateStrategyInfo();
    updateTradeCountStyle();
});

// 執行策略檢查
function executeStrategies() {
    $.ajax({
        url: '/api/execute_strategies',
        method: 'POST',
        success: function(response) {
            if (response.success) {
                const results = response.results;
                if (results && results.length > 0) {
                    results.forEach(result => {
                        const actionText = result.action === 'take_profit' ? '停利' : '交易';
                        console.log(`${result.strategy_name}: ${actionText} - ${result.message}`);
                    });
                }
            } else {
                console.error('執行策略失敗：', response.error);
            }
        },
        error: function() {
            console.error('執行策略時發生錯誤');
        }
    });
}
