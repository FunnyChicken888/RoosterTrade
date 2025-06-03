#!/usr/bin/env python3

import base64
import hashlib
import hmac
import json
import time
import requests
from urllib.parse import urlencode

class ClientV3(object):
    def __init__(self, key, secret, timeout=30):
        self._api_key = key
        self._api_secret = secret
        self._api_timeout = timeout
        self._api_url = "https://max-api.maicoin.com"

    def _make_request(self, path, method='GET', params=None):
        """發送API請求"""
        # 1. 準備參數
        request_params = {
            'nonce': int(time.time() * 1000)
        }
        if params:
            request_params.update(params)

        # 2. 構建簽名內容
        params_to_sign = {**request_params, 'path': path}
        json_str = json.dumps(params_to_sign)

        # 3. 生成payload
        payload = base64.b64encode(json_str.encode()).decode()

        # 4. 計算簽名
        signature = hmac.new(
            self._api_secret.encode(),
            payload.encode(),
            hashlib.sha256
        ).hexdigest()

        # 5. 設置請求頭
        headers = {
            'X-MAX-ACCESSKEY': self._api_key,
            'X-MAX-PAYLOAD': payload,
            'X-MAX-SIGNATURE': signature,
            'Content-Type': 'application/json'
        }

        # 6. 發送請求
        url = f"{self._api_url}{path}"
        try:
            if method == 'GET':
                url += f"?{urlencode(request_params)}"
                response = requests.get(url, headers=headers, timeout=self._api_timeout)
            else:
                response = requests.request(
                    method=method,
                    url=url,
                    headers=headers,
                    data=json.dumps(request_params),
                    timeout=self._api_timeout
                )
            
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            # 嘗試印出response內容
            if e.response is not None:
                try:
                    error_text = e.response.text
                except Exception:
                    error_text = '無法取得response內容'
                raise Exception(f"API請求失敗: {str(e)}，回應內容: {error_text}")
            else:
                raise Exception(f"API請求失敗: {str(e)}")

    # 市場行情API
    def get_market_summary(self):
        """獲取所有市場的概要信息"""
        return self._make_request('/api/v3/markets')

    def get_trades(self, market, limit=1):
        """獲取市場最新成交記錄"""
        params = {
            'market': market.lower(),
            'limit': limit
        }
        return self._make_request('/api/v3/trades', params=params)

    # 交易API
    def create_order(self, market, side, volume, price=None, order_type='market', wallet_type='spot'):
        """創建訂單
        Args:
            market: 交易對，如 'btctwd'
            side: 買賣方向，'buy' 或 'sell'
            volume: 交易數量
            price: 限價單價格，市價單可為None
            order_type: 訂單類型，'market' 或 'limit'
            wallet_type: 錢包類型，'spot'(現貨) 或 'margin'(槓桿) 或 'futures'(期貨)
        """
        # 格式化volume為最多16位小數
        formatted_volume = "{:.16f}".format(float(volume))
        # 移除末尾的0
        formatted_volume = formatted_volume.rstrip('0').rstrip('.')
        
        params = {
            'market': market.lower(),
            'side': side.lower(),
            'volume': formatted_volume,
            'ord_type': order_type.lower()
        }
        if price is not None:
            params['price'] = str(price)

        return self._make_request(f'/api/v3/wallet/{wallet_type}/order', 'POST', params)

    def cancel_order(self, order_id, wallet_type='spot'):
        """取消訂單"""
        return self._make_request(f'/api/v3/wallet/{wallet_type}/orders/{order_id}/cancel', 'POST')

    def get_order(self, order_id, wallet_type='spot'):
        """獲取訂單信息"""
        return self._make_request(f'/api/v3/wallet/{wallet_type}/orders/{order_id}')

    def get_orders(self, market, state='wait', wallet_type='spot'):
        """獲取訂單列表"""
        params = {
            'market': market.lower(),
            'state': state
        }
        return self._make_request(f'/api/v3/wallet/{wallet_type}/orders', params=params)

    # 帳戶API
    def get_account_balance(self, wallet_type='spot'):
        """獲取帳戶餘額"""
        return self._make_request(f'/api/v3/wallet/{wallet_type}/accounts')

    def get_my_trades(self, market, limit=50):
        """獲取個人成交歷史"""
        params = {
            'market': market.lower(),
            'limit': limit
        }
        return self._make_request('/api/v3/trades/my', params=params)
