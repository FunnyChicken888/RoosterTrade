(function () {
  "use strict";

  var chart = null;
  var STOCKS = [];            // [{code, name}] 上市公司清單
  var NAME_BY_CODE = {};

  function $(id) { return document.getElementById(id); }
  function fmt(n, d) { return Number(n).toLocaleString("en-US", { minimumFractionDigits: d || 0, maximumFractionDigits: d || 0 }); }
  function signed(n, d) { return (n >= 0 ? "+" : "") + fmt(n, d); }
  function cls(n) { return n > 0 ? "pos" : n < 0 ? "neg" : ""; }

  function loadStocks() {
    fetch("/api/tw_stocks")
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d.success) return;
        STOCKS = d.stocks || [];
        NAME_BY_CODE = {};
        var html = "";
        STOCKS.forEach(function (s) {
          NAME_BY_CODE[s.code] = s.name;
          html += '<option value="' + s.code + " " + s.name + '"></option>';
        });
        $("bt-stock-list").innerHTML = html;   // 代號或公司名皆可自動完成
        updateStockName();
      })
      .catch(function () { /* 清單抓失敗不影響用代號回測 */ });
  }

  // 把輸入（代號 / "代號 公司名" / 純公司名）解析成股票代號
  function resolveCode(input) {
    input = (input || "").trim();
    var m = input.match(/^(\d{3,6})/);
    if (m) return m[1];
    var exact = STOCKS.find(function (s) { return s.name === input; });
    if (exact) return exact.code;
    var hit = STOCKS.find(function (s) { return input && s.name.indexOf(input) >= 0; });
    return hit ? hit.code : input;
  }

  function updateStockName() {
    var code = resolveCode($("bt-stock").value);
    var name = NAME_BY_CODE[code] || "";
    $("bt-stock-name").textContent = name || (code ? "查無此代號" : "");
  }

  var STOCK_PRICE = null;     // 最新收盤價（換算每筆股數用）

  function smallestBand() {
    var bands = ($("bt-bands").value || "").split(",")
      .map(function (s) { return parseFloat(s); })
      .filter(function (x) { return x > 0; });
    return bands.length ? Math.min.apply(null, bands) : 0;
  }

  // 手續費門檻：每筆 slice ≈ V×band%，需 ≥ 低消/費率 才不會卡低消
  function updateFeeHelper() {
    var discount = parseFloat($("bt-discount").value) || 0.6;
    var feeMin = parseFloat($("bt-feemin").value); if (isNaN(feeMin)) feeMin = 20;
    var V = parseFloat($("bt-invest").value) || 0;
    var f = smallestBand();
    var feeRate = 0.001425 * discount;
    var holder = $("bt-fee-helper"), note = $("bt-fee-note");
    if (!feeRate || !V || !f) {
      holder.innerHTML = "";
      note.textContent = "請先填妥折扣、目標市值與 band%。";
      return;
    }
    var Amin = feeMin / feeRate;             // 損益平衡單筆金額（fee 剛好=低消）
    var slice = V * f / 100;                 // 最小單筆交易金額（band 邊緣）
    var ok = slice >= Amin;
    var effRate = Math.max(feeRate, feeMin / slice) * 100;
    var minV = Amin / (f / 100);             // 固定最小 band → 最低投資金額
    var minBand = Amin / V * 100;            // 固定投資金額 → 最低 band

    var html =
      card("低消平衡單筆金額", fmt(Amin) + " <small>TWD</small>") +
      card("你的最小單筆 (V×" + f + "%)",
           '<span class="' + (ok ? "pos" : "neg") + '">' + fmt(slice) + (ok ? " ✓" : " ✗") + "</span>") +
      card("實際手續費率", '<span class="' + (ok ? "" : "neg") + '">' + effRate.toFixed(3) + "%</span>") +
      card("建議最低投資金額", fmt(Math.ceil(minV / 1000) * 1000) + " <small>TWD</small>") +
      card("建議最低 band", minBand.toFixed(2) + "%");
    if (STOCK_PRICE) {
      var sh = slice / STOCK_PRICE;
      html += card("每筆約股數 @" + fmt(STOCK_PRICE, 2),
                   sh >= 1 ? Math.round(sh) + " 股" : '<span class="neg">&lt;1 股 ✗</span>');
    }
    holder.innerHTML = html;

    if (ok) {
      note.innerHTML = "✓ 最小單筆 " + fmt(slice) + " ≥ 平衡點 " + fmt(Amin) +
        "，手續費走費率（" + (feeRate * 100).toFixed(4) + "%），不卡低消。";
    } else {
      note.innerHTML = "✗ 最小單筆 " + fmt(slice) + " &lt; 平衡點 " + fmt(Amin) +
        "，會卡 " + fmt(feeMin) + " 元低消，實際費率高達 " + effRate.toFixed(3) +
        "%。建議投資金額 ≥ " + fmt(Math.ceil(minV / 1000) * 1000) +
        "，或最小 band ≥ " + minBand.toFixed(2) + "%。";
      if (STOCK_PRICE && slice < STOCK_PRICE) {
        note.innerHTML += "（單筆還不到 1 股股價 " + fmt(STOCK_PRICE, 2) + "，買不到整數股。）";
      }
    }
  }

  function fetchPrice() {
    var code = resolveCode($("bt-stock").value);
    if (!code) return;
    fetch("/api/tw_price?stock_no=" + encodeURIComponent(code))
      .then(function (r) { return r.json(); })
      .then(function (d) { STOCK_PRICE = d.success ? d.price : null; updateFeeHelper(); })
      .catch(function () { STOCK_PRICE = null; updateFeeHelper(); });
  }

  function setStatus(msg, isErr) {
    var el = $("bt-status");
    el.textContent = msg || "";
    el.style.color = isErr ? "#e24b4a" : "#888";
  }

  function card(label, valueHtml) {
    return '<div class="stat-card"><div class="stat-label">' + label +
           '</div><div class="stat-value mono">' + valueHtml + "</div></div>";
  }

  function run() {
    var payload = {
      stock_no: resolveCode($("bt-stock").value),
      months: parseInt($("bt-months").value, 10) || 12,
      investment_amount: parseFloat($("bt-invest").value) || 1000000,
      max_position: parseFloat($("bt-maxpos").value) || 0,
      bands: $("bt-bands").value.trim(),
      security_type: $("bt-type").value,
      fee_discount: parseFloat($("bt-discount").value) || 0.6,
      fee_min: parseFloat($("bt-feemin").value) || 0
    };
    if (!payload.stock_no) { setStatus("請輸入股票代號", true); return; }

    var btn = $("bt-run");
    btn.disabled = true;
    setStatus("抓取行情並回測中…（首次抓取較久）");

    fetch("/api/backtest_tw", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        btn.disabled = false;
        if (!data.success) { setStatus(data.error || "回測失敗", true); return; }
        setStatus("");
        render(data);
      })
      .catch(function (e) {
        btn.disabled = false;
        setStatus("請求失敗：" + e, true);
      });
  }

  function render(data) {
    $("bt-results").style.display = "block";

    var chg = (data.price_end / data.price_start - 1) * 100;
    var bh = data.results[0].buy_hold_roi;
    $("bt-summary-title").textContent =
      data.stock_no + (data.stock_name ? " " + data.stock_name : "") +
      " · " + data.start + " ~ " + data.end + " · " + data.days + " 交易日";
    $("bt-summary-sub").textContent =
      "股價 " + fmt(data.price_start, 2) + " → " + fmt(data.price_end, 2) +
      " (" + signed(chg, 1) + "%)　買進持有 ROI " + signed(bh, 2) + "%";

    // 以損益最高的 band 當頭條
    var best = data.results.reduce(function (a, b) { return b.profit > a.profit ? b : a; });
    var taxPct = (data.costs.tax_rate * 100).toFixed(2);
    $("bt-cards").innerHTML =
      card("最佳 band", best.band + "%") +
      card("損益 (TWD)", '<span class="' + cls(best.profit) + '">' + signed(best.profit) + "</span>") +
      card("ROI", '<span class="' + cls(best.roi) + '">' + signed(best.roi, 2) + "%</span>") +
      card("買進持有 ROI", '<span class="' + cls(bh) + '">' + signed(bh, 2) + "%</span>") +
      card("累積手續費", fmt(best.total_fee)) +
      card("累積證交稅 (" + taxPct + "%)", fmt(best.total_tax));

    renderChart(data.results[0]);
    renderTable(data.results, bh);
  }

  function renderChart(r0) {
    var labels = r0.series.map(function (p) { return p.date; });
    var closes = r0.series.map(function (p) { return p.close; });

    // 把成交點標在價格線上
    var idxByDate = {};
    labels.forEach(function (d, i) { idxByDate[d] = i; });
    var radius = labels.map(function () { return 0; });
    var colors = labels.map(function () { return "rgba(0,0,0,0)"; });
    (r0.trades || []).forEach(function (t) {
      var i = idxByDate[t.date];
      if (i === undefined) return;
      radius[i] = 5;
      colors[i] = t.side === "buy" ? "#1d9e75" : "#e24b4a";
    });

    if (chart) chart.destroy();
    chart = new Chart($("bt-chart"), {
      type: "line",
      data: {
        labels: labels,
        datasets: [{
          label: "收盤價",
          data: closes,
          borderColor: "#378add",
          backgroundColor: "rgba(55,138,221,0.08)",
          borderWidth: 2,
          fill: true,
          tension: 0.15,
          pointRadius: radius,
          pointBackgroundColor: colors,
          pointBorderColor: colors
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { ticks: { maxTicksLimit: 10, autoSkip: true } },
          y: { ticks: { callback: function (v) { return fmt(v); } } }
        }
      }
    });
  }

  function renderTable(results, bh) {
    var tbody = $("bt-sweep-table").querySelector("tbody");
    tbody.innerHTML = results.map(function (r) {
      var diff = r.roi - bh;
      return "<tr>" +
        "<td>" + r.band + "%</td>" +
        '<td class="mono text-end">' + r.n_trades + "</td>" +
        '<td class="mono text-end">' + fmt(r.total_fee) + "</td>" +
        '<td class="mono text-end">' + fmt(r.total_tax) + "</td>" +
        '<td class="mono text-end">' + fmt(r.peak_invested) + "</td>" +
        '<td class="mono text-end">' + fmt(r.final_value) + "</td>" +
        '<td class="mono text-end ' + cls(r.profit) + '">' + signed(r.profit) + "</td>" +
        '<td class="mono text-end ' + cls(r.roi) + '">' + signed(r.roi, 2) + "</td>" +
        '<td class="mono text-end ' + cls(diff) + '">' + signed(diff, 2) + "</td>" +
        "</tr>";
    }).join("");
  }

  function dbStatus(msg, isErr) {
    var el = $("bt-db-status");
    if (!el) return;
    el.textContent = msg || "";
    el.style.color = isErr ? "#e24b4a" : "var(--text-mute, #888)";
  }

  function loadDbResults() {
    if (!$("bt-db-table")) return;
    var params = new URLSearchParams();
    params.set("limit", "100");
    params.set("sort_by", $("bt-db-sort").value || "roi");
    params.set("order", "desc");
    var q = $("bt-db-q").value.trim();
    var minRoi = $("bt-db-min-roi").value.trim();
    var band = $("bt-db-band").value.trim();
    if (q) params.set("q", q);
    if (minRoi) params.set("min_roi", minRoi);
    if (band) params.set("band", band);

    dbStatus("讀取資料庫排行中…");
    fetch("/api/backtest_tw_db?" + params.toString())
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (!data.success) {
          dbStatus(data.error || "資料庫讀取失敗", true);
          renderDbRows([]);
          return;
        }
        renderDbRows(data.rows || []);
        if (!data.run) {
          dbStatus("目前還沒有批次回測資料。請先執行 scripts/build_tw_backtest_db.py。");
          return;
        }
        var created = new Date((data.run.created_at || 0) * 1000).toLocaleString();
        dbStatus("run #" + data.run.id + " · " + created +
          " · 共 " + data.total + " 筆符合條件（顯示前 100 筆）");
      })
      .catch(function (e) {
        dbStatus("請求失敗：" + e, true);
        renderDbRows([]);
      });
  }

  function renderDbRows(rows) {
    var tbody = $("bt-db-table").querySelector("tbody");
    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="9" style="color:#999;">沒有符合條件的資料</td></tr>';
      return;
    }
    tbody.innerHTML = rows.map(function (r) {
      return "<tr>" +
        '<td class="mono">' + r.stock_no + "</td>" +
        "<td>" + (r.stock_name || "") + "</td>" +
        '<td class="mono text-end">' + fmt(r.band, 1) + "</td>" +
        '<td class="mono text-end ' + cls(r.roi) + '">' + signed(r.roi, 2) + "</td>" +
        '<td class="mono text-end ' + cls(r.buy_hold_roi) + '">' + signed(r.buy_hold_roi, 2) + "</td>" +
        '<td class="mono text-end ' + cls(r.vs_buy_hold) + '">' + signed(r.vs_buy_hold, 2) + "</td>" +
        '<td class="mono text-end ' + cls(r.profit) + '">' + signed(r.profit) + "</td>" +
        '<td class="mono text-end">' + fmt(r.n_trades) + "</td>" +
        '<td class="mono text-end ' + cls(r.price_change_pct) + '">' + signed(r.price_change_pct, 1) + "</td>" +
        "</tr>";
    }).join("");
  }

  document.addEventListener("DOMContentLoaded", function () {
    $("bt-run").addEventListener("click", run);
    $("bt-stock").addEventListener("input", updateStockName);
    $("bt-stock").addEventListener("change", fetchPrice);
    ["bt-discount", "bt-feemin", "bt-invest", "bt-bands"].forEach(function (id) {
      $(id).addEventListener("input", updateFeeHelper);
    });
    loadStocks();
    updateFeeHelper();
    fetchPrice();
    $("bt-db-apply").addEventListener("click", loadDbResults);
    $("bt-db-refresh").addEventListener("click", loadDbResults);
    ["bt-db-q", "bt-db-min-roi", "bt-db-band"].forEach(function (id) {
      $(id).addEventListener("keydown", function (e) {
        if (e.key === "Enter") loadDbResults();
      });
    });
    $("bt-db-sort").addEventListener("change", loadDbResults);
    loadDbResults();
  });
})();
