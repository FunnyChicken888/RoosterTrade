$(document).ready(function() {
    // 載入可交易幣種
    loadAvailableMarkets();

    // 表單驗證
    $('form').submit(function(e) {
        const investment = parseFloat($('#investment_amount').val());
        const maxPosition = parseFloat($('#max_position').val());
        const takeProfit = parseFloat($('#take_profit').val());
        const autoTradePercent = parseFloat($('#auto_trade_percent').val());

        let errors = [];

        if (maxPosition > investment) {
            errors.push('加倉金額上限不能大於投資金額');
        }

        if (takeProfit <= investment) {
            errors.push('停利金額必須大於投資金額');
        }

        if (autoTradePercent <= 0 || autoTradePercent > 100) {
            errors.push('自動交易百分比必須在 0-100 之間');
        }

        if (errors.length > 0) {
            e.preventDefault();
            alert(errors.join('\n'));
            return false;
        }
    });

    // 動態更新建議值
    $('#investment_amount').on('change', function() {
        const investment = parseFloat($(this).val());
        if (!isNaN(investment)) {
            // 設定建議的加倉上限（投資金額的20%）
            if ($('#max_position').val() === '') {
                $('#max_position').val(Math.round(investment * 0.2));
            }
            
            // 設定建議的停利金額（投資金額的150%）
            if ($('#take_profit').val() === '') {
                $('#take_profit').val(Math.round(investment * 1.5));
            }
            
            // 設定建議的自動交易百分比（5%）
            if ($('#auto_trade_percent').val() === '') {
                $('#auto_trade_percent').val('5.0');
            }
        }
    });

    // 數值輸入欄位格式化
    $('.form-control[type="number"]').on('blur', function() {
        const value = parseFloat($(this).val());
        if (!isNaN(value)) {
            if ($(this).attr('id') === 'auto_trade_percent') {
                $(this).val(value.toFixed(1));
            } else {
                $(this).val(Math.round(value));
            }
        }
    });
});

// 載入可交易幣種
function loadAvailableMarkets() {
    const coinSelect = $('#coin_type');
    const currentValue = coinSelect.data('current-value') || '';
    
    // 顯示載入狀態
    coinSelect.html('<option value="">正在載入幣種...</option>');
    
    $.ajax({
        url: '/api/markets',
        method: 'GET',
        timeout: 10000,
        success: function(response) {
            if (response.success && response.markets) {
                // 清空選項
                coinSelect.empty();
                coinSelect.append('<option value="">請選擇幣種</option>');
                
                // 添加幣種選項
                response.markets.forEach(function(market) {
                    const isSelected = market.symbol === currentValue ? 'selected' : '';
                    coinSelect.append(
                        `<option value="${market.symbol}" ${isSelected}>${market.display_name}</option>`
                    );
                });
                
                console.log(`成功載入 ${response.markets.length} 個可交易幣種`);
                
                // 隱藏載入提示
                $('.form-text').show();
            } else {
                handleMarketLoadError('API回應格式錯誤');
            }
        },
        error: function(xhr, status, error) {
            let errorMessage = '載入幣種失敗';
            if (status === 'timeout') {
                errorMessage = '載入超時，請檢查網絡連接';
            } else if (xhr.responseJSON && xhr.responseJSON.error) {
                errorMessage = xhr.responseJSON.error;
            }
            handleMarketLoadError(errorMessage);
        }
    });
}

// 處理市場載入錯誤
function handleMarketLoadError(errorMessage) {
    const coinSelect = $('#coin_type');
    
    // 提供備用選項
    coinSelect.html(`
        <option value="">請選擇幣種</option>
        <option value="BTC">Bitcoin (BTC)</option>
        <option value="ETH">Ethereum (ETH)</option>
        <option value="USDT">Tether (USDT)</option>
    `);
    
    // 顯示錯誤訊息
    $('.form-text').html(`
        <small class="text-danger">
            <i class="fas fa-exclamation-triangle"></i>
            ${errorMessage}，已載入常用幣種選項
        </small>
    `);
    
    console.error('載入市場數據失敗:', errorMessage);
}

// 設置當前選中的幣種（用於編輯模式）
function setCurrentCoinType(coinType) {
    $('#coin_type').data('current-value', coinType);
}
