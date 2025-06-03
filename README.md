# RoosterTrade - 加密貨幣自動交易系統

RoosterTrade是一個基於Python的加密貨幣自動交易系統，支持多策略管理和自動執行交易。

## 功能特點

- 多策略管理：支持同時運行多個交易策略(目前只有一種交易策略)
- 實時監控：即時顯示當前價格、持倉和收益情況
- 自動交易：根據設定的觸發價格自動執行買賣操作
- 風險控制：支持每日交易次數限制和停利機制
- Telegram通知：重要交易信息即時推送

## 目錄結構

```
RoosterTrade/
├── backend/                # 後端程式碼
│   ├── models/            # 數據模型
│   ├── strategies/        # 交易策略
│   └── utils/             # 工具函數
├── frontend/              # 前端程式碼
│   ├── static/           # 靜態資源
│   └── templates/        # HTML模板
├── config/               # 配置文件
│   └── strategies/      # 策略配置
├── records/             # 交易記錄
└── run.py              # 主程序入口
```

## 安裝配置

1. 克隆代碼庫：
```bash
git clone https://github.com/yourusername/RoosterTrade.git
cd RoosterTrade
```

2. 安裝依賴：
```bash
pip install -r requirements.txt
```

3. 配置策略：
- 在`config/strategies/`目錄下創建策略配置文件
- 可以參考`example.json`的格式進行配置

策略配置示例：
```json
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
```

## 運行系統

```bash
python run.py
```

系統啟動後，可以通過瀏覽器訪問：
- 主頁面：http://localhost:5000
- 交易歷史：http://localhost:5000/history

## 注意事項

1. 請妥善保管您的API密鑰和其他敏感信息
2. 建議在實盤交易前，先進行充分的測試
3. 請定期備份您的交易記錄
4. 系統運行時會自動創建必要的目錄結構

## 隱私和安全

- 所有的策略配置文件（`config/strategies/*.json`）都已被加入.gitignore
- 交易記錄目錄（`records/`）也已被忽略
- 請不要將包含敏感信息的文件提交到版本控制系統

## 貢獻指南

歡迎提交Issue和Pull Request來幫助改進這個項目。

## 授權協議

本項目採用MIT授權協議。
