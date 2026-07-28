(function () {
  "use strict";

  var POLL_MS = 30000;
  var timer = null;

  function $(id) { return document.getElementById(id); }
  function fmt(n, d) { return Number(n).toLocaleString("en-US", { minimumFractionDigits: d || 0, maximumFractionDigits: d || 0 }); }
  function signed(n, d) { return (n >= 0 ? "+" : "") + fmt(n, d); }

  var LEVEL_TEXT = { OK: "正常", INFO: "留意", WARN: "警告", CRIT: "危急", ERR: "取數失敗" };
  var LEVEL_CLASS = { OK: "lvl-ok", INFO: "lvl-info", WARN: "lvl-warn", CRIT: "lvl-crit", ERR: "lvl-err" };

  function badge(level) {
    var t = LEVEL_TEXT[level] || level || "—";
    return '<span class="arb-pill ' + (LEVEL_CLASS[level] || "") + '">' + t + "</span>";
  }

  function bufferCell(p) {
    if (p.level === "ERR") return '<span class="neg">—</span>';
    if (p.liq_buffer_pct === null || p.liq_buffer_pct === undefined) {
      return '<span style="color:#999;">未設強平價</span>';
    }
    var v = p.liq_buffer_pct;
    var cls = v <= 4 ? "neg" : v <= 8 ? "warn" : "pos";
    return '<span class="' + cls + '">' + signed(v, 1) + "%</span>";
  }

  function fundingCell(p) {
    if (p.level === "ERR") return "—";
    var v = p.funding_apr;
    // 你實收年化：負=你付（不利），正=你收
    var cls = v < 0 ? "neg" : v >= 50 ? "warn" : "pos";
    return '<span class="' + cls + '">' + signed(v, 1) + "%</span>";
  }

  function moveCell(p) {
    if (p.level === "ERR") return "—";
    var v = p.adverse_move_pct;
    var cls = v >= 3 ? "neg" : v >= 1.5 ? "warn" : "";
    return '<span class="' + cls + '">' + signed(v, 1) + "%</span>";
  }

  function render(data) {
    var overall = $("arb-overall");
    overall.className = "arb-pill " + (LEVEL_CLASS[data.worst_level] || "");
    overall.textContent = "整體：" + (LEVEL_TEXT[data.worst_level] || data.worst_level);

    var rows = (data.positions || []).map(function (p) {
      if (p.level === "ERR") {
        return "<tr>" +
          "<td>" + p.label + "</td>" +
          "<td class=\"mono\">" + p.exchange + " / " + p.symbol + "</td>" +
          "<td>" + (p.side === "short" ? "空" : "多") + "</td>" +
          '<td class="mono text-end neg" colspan="4">取行情失敗：' + (p.error || "") + "</td>" +
          "<td>" + badge("ERR") + "</td>" +
          "</tr>";
      }
      return "<tr>" +
        "<td>" + p.label + "</td>" +
        '<td class="mono">' + p.exchange + " / " + p.symbol + "</td>" +
        "<td>" + (p.side === "short" ? "空" : "多") + "</td>" +
        '<td class="mono text-end">' + fmt(p.mark, 2) + "</td>" +
        '<td class="mono text-end">' + bufferCell(p) + "</td>" +
        '<td class="mono text-end">' + fundingCell(p) + "</td>" +
        '<td class="mono text-end">' + moveCell(p) + "</td>" +
        "<td>" + badge(p.level) + "</td>" +
        "</tr>";
    }).join("");
    $("arb-table").querySelector("tbody").innerHTML = rows ||
      '<tr><td colspan="8" style="color:#999;">設定檔沒有部位，請編輯 config/arb_monitor.json</td></tr>';

    // 彙整所有 alert 訊息
    var alerts = [];
    (data.positions || []).forEach(function (p) {
      (p.alerts || []).forEach(function (a) { alerts.push(a); });
    });
    var panel = $("arb-alerts-panel");
    if (alerts.length) {
      panel.style.display = "block";
      $("arb-alerts").innerHTML = alerts.map(function (a) {
        return '<li class="' + (LEVEL_CLASS[a.level] || "") + '">' +
          "[" + (LEVEL_TEXT[a.level] || a.level) + "] " + a.msg + "</li>";
      }).join("");
    } else {
      panel.style.display = "none";
    }

    var when = new Date((data.generated_at || 0) * 1000);
    $("arb-status").textContent = "最後更新 " + when.toLocaleTimeString() +
      "　·　急拉視窗 " + data.window_min + " 分鐘　·　每 " + (POLL_MS / 1000) + " 秒自動刷新";
  }

  function load() {
    $("arb-status").textContent = "讀取中…";
    fetch("/api/arb_status")
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (!data.success) {
          $("arb-status").innerHTML = '<span class="neg">' + (data.error || "讀取失敗") + "</span>";
          return;
        }
        render(data);
      })
      .catch(function (e) {
        $("arb-status").innerHTML = '<span class="neg">請求失敗：' + e + "</span>";
      });
  }

  document.addEventListener("DOMContentLoaded", function () {
    $("arb-refresh").addEventListener("click", load);
    load();
    timer = setInterval(load, POLL_MS);
    window.addEventListener("beforeunload", function () { if (timer) clearInterval(timer); });
  });
})();
