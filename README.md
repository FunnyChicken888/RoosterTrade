# RoosterTrade - 加密貨幣自動交易系統

RoosterTrade 是一個基於 Python 的加密貨幣自動交易系統，支持多策略管理和自動執行交易。系統使用 Flask 作為 Web 框架。

## 功能特點

- 🚀 多策略管理：支持同時運行多個交易策略
- 📊 實時監控：即時顯示當前價格、持倉和收益情況
- 🤖 自動交易：根據設定的觸發價格自動執行買賣操作
- ⚡ 高效能：使用 Gunicorn 作為 WSGI 服務器，支持多 worker 處理
- 🔒 風險控制：支持每日交易次數限制和停利機制
- 📱 Telegram 通知：重要交易信息即時推送

## 系統架構

```
RoosterTrade/
├── app/                   # 應用程式主目錄
│   ├── backend/          # 後端程式碼
│   │   ├── models/      # 數據模型
│   │   ├── services/    # 服務層
│   │   ├── strategies/  # 交易策略
│   │   └── utils/       # 工具函數
│   ├── frontend/        # 前端程式碼
│   │   ├── static/     # 靜態資源
│   │   └── templates/  # HTML模板
│   ├── max/            # MAX API 客戶端（含 mock_client 模擬版）
│   ├── run.py         # 開發模式入口點
│   └── wsgi.py        # WSGI 生產環境入口點
├── config/             # 配置文件目錄
│   └── strategies/    # 策略配置
└── gunicorn.conf.py  # Gunicorn 配置
```

## 快速開始

1. 克隆代碼庫並安裝依賴：
\`\`\`bash
git clone https://github.com/FunnyChicken888/RoosterTrade.git
cd RoosterTrade
python -m venv .venv
.venv\\Scripts\\python -m pip install -r requirements.txt   # Windows
# source .venv/bin/activate && pip install -r requirements.txt   # macOS / Linux
\`\`\`

2. 配置環境：
- 複製 \`config/config_example.json\` 到 \`config/config.json\`
- 填入您的 API 密鑰和 Telegram 配置（或設 \`demo_mode: true\` 用模擬資料試跑）

3. 啟動服務：
\`\`\`bash
# 開發模式（從 app 目錄執行）
cd app
python run.py            # http://localhost:5003

# 生產模式（WSGI）
gunicorn --config gunicorn.conf.py wsgi:application
\`\`\`

### DEMO 模式

沒有真實 API 金鑰也能看 UI：在 \`config/config.json\` 設 \`"demo_mode": true\`（或設環境變數 \`ROOSTER_DEMO=1\`），系統會改用模擬行情與帳戶資料，不會送出任何真實交易。未填寫金鑰時也會自動進入 DEMO 模式。

## 配置說明

### 系統配置

\`config/config.json\` 範例：
\`\`\`json
{
    "demo_mode": false,
    "telegram_bot_token": "your_telegram_bot_token",
    "telegram_chat_id": "your_telegram_chat_id",
    "max_api_key": "your_max_api_key",
    "max_secret_key": "your_max_secret_key"
}
\`\`\`
> 金鑰名稱大小寫皆可（\`config_loader\` 會自動正規化），但建議使用上方小寫格式。

### 策略配置

\`config/strategies/example.json\` 範例：
\`\`\`json
{
    "strategy_name": "策略名稱",
    "coin_type": "BTC",
    "investment_amount": 35000.0,
    "max_position": 10000.0,
    "take_profit": 100000.0,
    "auto_trade_percent": 1.0,
    "daily_trade_limit": 5,
    "confirm_amount_threshold": 0,
    "is_active": false
}
\`\`\`

## 系統訪問

服務啟動後，可以通過以下地址訪問：
- 主頁面：http://localhost:5003
- 交易歷史：http://localhost:5003/history
- 健康檢查：http://localhost:5003/api/check_connection

## 效能優化

系統使用 Gunicorn 作為 WSGI 服務器，提供以下優化：
- 多 worker 處理請求
- 自動 worker 重啟機制
- 優化的請求隊列
- 健康檢查支持

## 安全注意事項

1. 🔐 API 密鑰安全
   - 請妥善保管您的 API 密鑰
   - 不要將包含密鑰的配置文件提交到版本控制系統
   - 配置文件已被加入 .gitignore

2. 💾 數據安全
   - 定期備份交易記錄
   - 記錄目錄（records/）已被加入 .gitignore
   - 日誌文件存放在 log/ 目錄

3. 🛡️ 系統安全
   - 使用環境變量管理敏感信息
   - 建議在獨立的虛擬環境（venv）中運行
   - 定期更新依賴包版本

## 故障排除

1. 服務無法啟動
   - 確認端口 5003 未被占用
   - 確認已安裝 requirements.txt 中的依賴
   - 查看 app/log/ 下的日誌輸出

2. API 連接失敗
   - 確認配置文件格式正確
   - 驗證 API 密鑰有效性
   - 檢查網絡連接狀態

3. Telegram 通知問題
   - 確認 Bot Token 正確
   - 驗證 Chat ID 設置
   - 檢查 Bot 權限設置

## 開發指南

1. 新增交易策略
   - 在 backend/strategies/ 創建新策略類
   - 實現必要的交易邏輯
   - 在 strategy_manager.py 中註冊策略

2. 前端開發
   - 靜態文件位於 frontend/static/
   - 模板文件位於 frontend/templates/
   - 使用 Flask-Assets 管理資源

## 授權協議

本項目採用 MIT 授權協議。

## 貢獻指南

歡迎提交 Issue 和 Pull Request 來幫助改進這個項目。提交時請：
1. 確保代碼符合 PEP 8 規範
2. 添加必要的測試用例
3. 更新相關文檔
