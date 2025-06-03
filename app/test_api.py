import json
from max.client_v3 import ClientV3

def test_api_connection():
    print("開始測試MAX API連線...")
    
    # 載入API金鑰
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
            api_key = config.get('max_api_key', '')
            api_secret = config.get('max_secret_key', '')
            print(f"已載入API金鑰，長度: {len(api_key)}")
    except Exception as e:
        print(f"載入config.json失敗: {e}")
        return

    client = ClientV3(api_key, api_secret)

    # 測試公開API
    print("\n1. 測試公開API (get_market_summary)...")
    try:
        markets = client.get_market_summary()
        print("✓ 公開API測試成功")
        print(f"市場數量: {len(markets)}")
    except Exception as e:
        print(f"✗ 公開API測試失敗: {e}")

    # 測試私有API
    print("\n2. 測試私有API (get_account_balance)...")
    try:
        balance = client.get_account_balance()
        print("✓ 私有API測試成功")
        print("帳戶餘額:")
        for account in balance:
            if float(account['balance']) > 0:
                print(f"- {account['currency'].upper()}: {account['balance']}")
    except Exception as e:
        print(f"✗ 私有API測試失敗: {e}")
        print("請檢查API金鑰是否正確，以及是否有正確的權限")

if __name__ == '__main__':
    test_api_connection()
