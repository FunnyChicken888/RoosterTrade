$(document).ready(function() {
    // 初始化日期範圍選擇器
    $('#date-range').daterangepicker({
        startDate: moment().subtract(30, 'days'),
        endDate: moment(),
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
            applyLabel: '確定',
            cancelLabel: '取消',
            customRangeLabel: '自訂範圍',
            daysOfWeek: ['日', '一', '二', '三', '四', '五', '六'],
            monthNames: ['一月', '二月', '三月', '四月', '五月', '六月',
                        '七月', '八月', '九月', '十月', '十一月', '十二月']
        }
    });

    // 初始化DataTables
    const table = $('#history-table').DataTable({
        order: [[0, 'desc']], // 預設按時間降序排序
        pageLength: 25,
        language: {
            "processing": "處理中...",
            "loadingRecords": "載入中...",
            "lengthMenu": "顯示 _MENU_ 項結果",
            "zeroRecords": "沒有符合的結果",
            "info": "顯示第 _START_ 至 _END_ 項結果，共 _TOTAL_ 項",
            "infoEmpty": "顯示第 0 至 0 項結果，共 0 項",
            "infoFiltered": "(從 _MAX_ 項結果中過濾)",
            "search": "搜尋:",
            "paginate": {
                "first": "第一頁",
                "previous": "上一頁",
                "next": "下一頁",
                "last": "最後一頁"
            }
        }
    });

    // 從API獲取交易記錄
    function fetchTradingHistory(strategyName = '') {
        const url = strategyName ? 
            `/api/trading_history?strategy_name=${encodeURIComponent(strategyName)}` : 
            '/api/trading_history';
        
        $.get(url)
            .done(function(response) {
                if (response.success) {
                    updateTable(response.records);
                    updateStatsFromAPI(response.stats);
                } else {
                    console.error('獲取交易記錄失敗:', response.error);
                }
            })
            .fail(function(jqXHR, textStatus, errorThrown) {
                console.error('API請求失敗:', textStatus, errorThrown);
            });
    }

    // 更新表格數據
    function updateTable(records) {
        table.clear();
        records.forEach(function(record) {
            table.row.add([
                record.trade_time,
                record.strategy_name,
                record.coin_type,
                record.action === 'buy' ? '<span class="badge bg-success">買入</span>' : '<span class="badge bg-danger">賣出</span>',
                record.price.toFixed(2),
                record.volume.toFixed(8),
                (record.price * record.volume).toFixed(2)
            ]);
        });
        table.draw();
    }

    // 從API更新統計數據
    function updateStatsFromAPI(stats) {
        $('.card-title:contains("總交易次數")').next('h4').text(stats.total_trades);
        $('.card-title:contains("總交易金額")').next('h4').text(stats.total_amount.toFixed(2) + ' TWD');
        $('.card-title:contains("平均交易金額")').next('h4').text(stats.avg_amount.toFixed(2) + ' TWD');
        
        const netProfitElement = $('.card-title:contains("淨收益")').next('h4');
        netProfitElement.text(stats.net_profit.toFixed(2) + ' TWD')
            .removeClass('text-success text-danger')
            .addClass(stats.net_profit >= 0 ? 'text-success' : 'text-danger');
    }

    // 策略篩選功能
    $('#strategy-filter').on('change', function() {
        const strategy = $(this).val();
        fetchTradingHistory(strategy);
    });

    // 日期範圍篩選
    $('#date-range').on('apply.daterangepicker', function(ev, picker) {
        const startDate = picker.startDate.format('YYYY-MM-DD');
        const endDate = picker.endDate.format('YYYY-MM-DD');
        
        // 自定義搜尋函數
        $.fn.dataTable.ext.search.push(
            function(settings, data, dataIndex) {
                const date = moment(data[0], 'YYYY-MM-DD HH:mm:ss');
                const start = moment(startDate);
                const end = moment(endDate).endOf('day');
                return date.isBetween(start, end, null, '[]');
            }
        );
        
        table.draw();
        
        // 清除自定義搜尋函數
        $.fn.dataTable.ext.search.pop();
    });

    // 頁面載入時獲取初始數據
    fetchTradingHistory();
});
