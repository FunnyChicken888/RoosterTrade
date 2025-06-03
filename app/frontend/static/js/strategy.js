$(document).ready(function() {
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
