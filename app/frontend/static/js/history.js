$(document).ready(function () {
    const fmt = (n) => Number(n).toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 });
    const fmtSigned = (n) => (n > 0 ? '+' : '') + fmt(n);

    // 日期範圍狀態（給 DataTables 自訂篩選用）
    let dateStart = null;
    let dateEnd = null;

    // 初始化日期範圍選擇器
    $('#date-range').daterangepicker({
        autoUpdateInput: false,
        ranges: {
            '今天': [moment(), moment()],
            '昨天': [moment().subtract(1, 'days'), moment().subtract(1, 'days')],
            '過去7天': [moment().subtract(6, 'days'), moment()],
            '過去30天': [moment().subtract(29, 'days'), moment()],
            '本月': [moment().startOf('month'), moment().endOf('month')],
            '上月': [moment().subtract(1, 'month').startOf('month'), moment().subtract(1, 'month').endOf('month')]
        },
        locale: {
            format: 'YYYY/MM/DD',
            applyLabel: '確定', cancelLabel: '清除', customRangeLabel: '自訂範圍',
            daysOfWeek: ['日', '一', '二', '三', '四', '五', '六'],
            monthNames: ['一月', '二月', '三月', '四月', '五月', '六月', '七月', '八月', '九月', '十月', '十一月', '十二月']
        }
    });

    // DataTables 自訂日期篩選（只註冊一次，依 dateStart/dateEnd 動態判斷）
    $.fn.dataTable.ext.search.push(function (settings, data) {
        if (!dateStart || !dateEnd) return true;
        const d = moment(data[0]);           // 第 0 欄是 ISO 時間，moment 可直接解析
        if (!d.isValid()) return true;
        return d.isBetween(dateStart, dateEnd, null, '[]');
    });

    // 初始化 DataTables
    const table = $('#history-table').DataTable({
        order: [[0, 'desc']],
        pageLength: 25,
        language: {
            processing: '處理中...', loadingRecords: '載入中...', lengthMenu: '顯示 _MENU_ 項',
            zeroRecords: '沒有符合的結果', info: '第 _START_ 至 _END_ 項，共 _TOTAL_ 項',
            infoEmpty: '共 0 項', infoFiltered: '(從 _MAX_ 項中過濾)', search: '搜尋:',
            paginate: { first: '第一頁', previous: '上一頁', next: '下一頁', last: '最後一頁' }
        }
    });

    $('#date-range').on('apply.daterangepicker', function (ev, picker) {
        dateStart = picker.startDate.startOf('day');
        dateEnd = picker.endDate.endOf('day');
        $(this).val(picker.startDate.format('YYYY/MM/DD') + ' - ' + picker.endDate.format('YYYY/MM/DD'));
        table.draw();
    });
    $('#date-range').on('cancel.daterangepicker', function () {
        dateStart = dateEnd = null;
        $(this).val('');
        table.draw();
    });

    function updateTable(records) {
        table.clear();
        records.forEach(function (r) {
            const badge = r.action === 'buy'
                ? '<span class="trade-badge buy">買入</span>'
                : '<span class="trade-badge sell">賣出</span>';
            const chip = `<span class="coin-chip coin-${(r.coin_type || '').toLowerCase()}">${r.coin_type || ''}</span>`;
            table.row.add([
                r.trade_time,
                r.strategy_name,
                chip,
                badge,
                Number(r.price).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
                Number(r.volume).toFixed(8),
                Number(r.price * r.volume).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
            ]);
        });
        table.draw();
    }

    function setSigned(el, val) {
        el.text(fmtSigned(val) + ' TWD').removeClass('pos neg').addClass(val > 0 ? 'pos' : val < 0 ? 'neg' : '');
    }

    function updateStats(s) {
        $('#stat-total-trades').text(s.total_trades);
        $('#stat-total-amount').html(fmt(s.total_amount) + ' <span class="unit">TWD</span>');
        $('#stat-avg-amount').html(fmt(s.avg_amount) + ' <span class="unit">TWD</span>');
        $('#stat-position').html(fmt(s.current_position_value) + ' <span class="unit">TWD</span>');
        setSigned($('#stat-realized'), s.realized_profit);
        setSigned($('#stat-net'), s.net_profit);
    }

    function fetchTradingHistory(strategyName = '') {
        const url = strategyName
            ? `/api/trading_history?strategy_name=${encodeURIComponent(strategyName)}`
            : '/api/trading_history';
        $.get(url)
            .done(function (resp) {
                if (resp.success) {
                    updateTable(resp.records);
                    updateStats(resp.stats);
                } else {
                    console.error('獲取交易記錄失敗:', resp.error);
                }
            })
            .fail(function (x, status, err) { console.error('API請求失敗:', status, err); });
    }

    $('#strategy-filter').on('change', function () {
        fetchTradingHistory($(this).val());
    });

    fetchTradingHistory();
});
