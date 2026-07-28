# 資金費率套利風控監控器 — 計畫書

> 狀態:**部分已實作、暫停待執行**。核心引擎與資料源已完成並通過測試;
> 設定檔、執行器、Telegram 接線、端到端實跑尚未做。詳見下方「進度」。

## 1. 目標與範圍
為「現貨多 + 永續/期貨空」的套利空腿做**風控示警**。**只示警、絕不自動下單**;
超過門檻就發 Telegram 提醒,平倉/減倉/加保證金由本人手動執行。

本期監控三項風險(已與需求確認):
1. **保證金緩衝 / 距離強平** — 標記價離強平價還剩多少 %。
2. **資金費率異常** — 翻成「你付費」或對手方過熱(異常高)。
3. **價格急拉 / 尬空** — 短時間內價格往不利方向急衝。

**不在本期**:兩腿基差/匯率監控、自動減倉、自動平衡(列為後續)。

## 2. 架構與檔案

| 檔案 | 角色 | 狀態 |
|---|---|---|
| `app/backend/arb_monitor/risk_engine.py` | 純函式風險判斷(三項指標 → 示警清單) | ✅ 已完成 |
| `app/backend/arb_monitor/feeds.py` | 幣安 / BingX 公開行情(標記價、資金費率、24h 區間,免金鑰) | ✅ 已完成 |
| `app/backend/arb_monitor/monitor.py` | orchestration:滾動價格視窗、示警去重/冷卻、可插拔 notify | ✅ 已完成 |
| `scripts/test_arb_risk.py` | 風控引擎單元測試 | ✅ 已完成(12 項全過) |
| `config/arb_monitor.json` | 部位與門檻設定(範本見 §4) | ⬜ 待做 |
| `scripts/run_arb_monitor.py` | CLI 迴圈:每 N 秒跑一輪、接 Telegram | ⬜ 待做 |
| 端到端實跑驗證(公開行情 + Telegram 實發) | — | ⬜ 待做 |

公開端點皆已實測可用(免金鑰):
- 幣安:`fapi.binance.com/fapi/v1/premiumIndex`、`/ticker/24hr`、`/openInterest`(黃金 = `PAXGUSDT`)
- BingX:`open-api.bingx.com/openApi/swap/v2/quote/premiumIndex`、`/ticker`(代號如 `BTC-USDT`)

## 3. 風險指標定義(已實作於 risk_engine.py)
- **距離強平 %**:空單 `(liq − mark)/mark×100`;`≤8%→WARN`、`≤4%→CRIT`、`≤0→已觸及`。
- **資金費率**:年化 = `rate ×(24/間隔h)×365`。空單:`rate>0` 你收、`rate<0` 你付。
  你付費年化 `≥5% → WARN`;你收 `≥50%/年 → INFO`(對手方過熱,慎防劇烈回歸/尬空)。
- **急拉/尬空**:15 分鐘滾動視窗內,空單自近期低點漲幅 `≥3% → CRIT`(多單則看急跌)。
- 門檻全可在 `config/arb_monitor.json` 覆寫;以上為預設(`risk_engine.DEFAULT_THRESHOLDS`)。

## 4. 設定檔範本(待建立 `config/arb_monitor.json`)
```json
{
  "poll_seconds": 30,
  "window_min": 15,
  "cooldown_min": 30,
  "thresholds": {
    "liq_buffer_warn": 8.0, "liq_buffer_crit": 4.0,
    "funding_pay_apr": 5.0, "funding_high_apr": 50.0, "squeeze_pct": 3.0
  },
  "positions": [
    {"label": "幣安PAXG空", "exchange": "binance", "symbol": "PAXGUSDT", "side": "short", "liq_price": 4400.0},
    {"label": "BingX白銀空", "exchange": "bingx", "symbol": "XAG-USDT", "side": "short", "liq_price": 0}
  ]
}
```
> `liq_price` 先由你從交易所 UI 手填(尚未接金鑰自動同步);`0` 表示暫不檢查該腿的距離強平。

## 5. 待做的執行器(scripts/run_arb_monitor.py 規格)
1. 讀 `config/arb_monitor.json`(部位 + 門檻 + 輪詢秒數)。
2. 讀 `config/config.json` 的 Telegram 金鑰;有則用 `make_telegram_notify`,無則印 console。
3. 建 `ArbMonitor(positions, thresholds, notify, window_min, cooldown_min)`。
4. 迴圈:每 `poll_seconds` 呼叫 `run_cycle()`;先 console dry-run 觀察,門檻調準後再開 Telegram。

## 6. 執行步驟(之後照做)
1. 建立 `config/arb_monitor.json`,填入你的空腿(代號、`side`、`liq_price`)與門檻。
2. 確認 `config/config.json` 內 Telegram 金鑰已填(要收推播的話)。
3. `cd app && ../.venv/bin/python ../scripts/run_arb_monitor.py`(或整合進現有輪詢)。
4. 先看 console 輸出確認示警合理,再切到 Telegram。

## 7. 注意事項 / 限制
- **只示警**:程式不會、也不應自動下單(安全原則)。下單一律由本人手動。
- **強平價手填**:未接 API 金鑰前,`liq_price`/保證金率靠你從交易所 UI 填;接金鑰後可自動同步。
- **金屬代號依掛牌**:幣安黃金 = `PAXGUSDT`;白銀幣安未必有,BingX 金屬永續較多,請確認實際代號。
- **更大的結構性風險**(見先前討論,本監控未涵蓋):兩腿基差不收斂(永續不到期)、黃金存摺的
  USD/TWD 匯率裸險、跨場保證金時間差(空腿要追繳但多腿資金調不過來)。這些建議另列監控。
- 資金費率會翻負;`funding_high` 的 INFO 是「過熱訊號」,高 funding 對空方是收入但也是尬空前兆。

## 8. 後續可選(未來再議)
- **示警 + 自動減倉**:危急線時自動減空腿/加保證金到安全(需 API 金鑰 + 硬性風控上限)。
- **跨所 funding 價差**、**兩腿基差 + 匯率**監控。
- **Web 狀態頁**:把各部位的緩衝/funding/急拉狀態做成 RoosterTrade 內的儀表板。
