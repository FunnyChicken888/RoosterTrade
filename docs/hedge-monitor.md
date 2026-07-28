# 跨市場避險監控

第一版只讀取帳戶、行情及資金費資料，不會送出任何訂單。

## 憑證設定

推薦使用環境變數：

```text
BINGX_API_KEY=read_only_key
BINGX_SECRET_KEY=read_only_secret
SHIOAJI_API_KEY=sinopac_key
SHIOAJI_SECRET_KEY=sinopac_secret
HEDGE_POLL_INTERVAL=60
```

本機可複製 `.env.example` 為 `.env` 再填入憑證；程式啟動時會自動載入，`.env` 已被 Git 忽略。請勿把真正憑證填入 `.env.example`。

也可以把對應的小寫欄位放在 `config/config.json`。該檔案不得提交至 Git。

- BingX Key 僅開啟讀取權限，不開啟交易與提領權限。
- 永豐 API Key 開啟 Market/Data 與 Account 權限即可；此監控不需要 Trading 權限或 CA 憑證。
- 建議兩邊都設定允許連線的固定 IP。

## 使用方式

啟動服務後開啟 `/hedge-monitor`。即使尚未設定 API Key，也能手動輸入現貨與永續部位，先驗證台幣損益。每次同步會以 MAX `usdttwd` 最新成交價覆蓋手動 USDT/TWD；MAX API 異常時才沿用手動值。

背景採集器預設每 60 秒執行一次，最低間隔為 15 秒。本機執行時結果保存於 `app/data/hedge_monitor.db`；Docker 執行時透過 `./data:/app/data` 保存。Web 頁面的「同步帳戶與行情」也會立即保存一筆快照。

台積電範例預設：

- 現貨代碼：`2330`
- BingX 永續代碼：`TSMU-USDT`
- 一個 TSM ADS 對應 5 股 2330
- `contract_multiplier` 必須以 BingX 當下商品規格為準，不應只依賴預設值

## API

- `GET /api/hedge-portfolios`：使用已保存資料計算
- `GET /api/hedge-portfolios?refresh=1`：同步外部資料並保存快照
- `POST /api/hedge-portfolios`：建立組合
- `GET /api/hedge-portfolios/<id>`：取得單一組合
- `PUT /api/hedge-portfolios/<id>`：更新組合
- `GET /api/hedge-portfolios/<id>/snapshots`：取得歷史快照
- `GET /api/hedge-connections/bingx`：實際測試 BingX 唯讀連線

## 目前限制

- USDT/TWD 使用 MAX `usdttwd` 最新成交價；手動值是 API 異常時的 fallback。
- BingX 累積資金費目前取最近一批 income 紀錄，不代表完整帳戶生命週期。
- 快照已保存，但尚未提供歷史圖表與 Telegram 門檻告警。
- 台股收盤後，永續行情仍可能變動；介面數字不代表兩邊都在同一時間可成交。
