import json
import requests

def get_chat_id(bot_token: str) -> str:
    """獲取Telegram chat ID"""
    try:
        # 獲取最新的消息更新
        response = requests.get(f"https://api.telegram.org/bot{bot_token}/getUpdates")
        updates = response.json()
        
        if not updates.get('ok'):
            print("錯誤：無法獲取更新")
            print(f"錯誤信息：{updates.get('description', '未知錯誤')}")
            return None
            
        if not updates.get('result'):
            print("請先和機器人發送一條消息，然後再運行此腳本")
            return None
            
        # 獲取最新消息的chat ID
        chat_id = updates['result'][-1]['message']['chat']['id']
        print(f"已找到您的chat ID: {chat_id}")
        return chat_id
        
    except Exception as e:
        print(f"發生錯誤：{e}")
        return None

if __name__ == "__main__":
    # 從config.json讀取bot token
    with open('config.json', 'r') as f:
        config = json.load(f)
        bot_token = config.get('telegram_bot_token')
        
    if not bot_token:
        print("請先在config.json中添加您的bot token")
        print("格式：")
        print('{')
        print('    "max_api_key": "...",')
        print('    "max_secret_key": "...",')
        print('    "telegram_bot_token": "YOUR_BOT_TOKEN"')
        print('}')
    else:
        chat_id = get_chat_id(bot_token)
        if chat_id:
            print("\n請將以下內容添加到config.json：")
            print('"telegram_chat_id": "' + str(chat_id) + '"')
