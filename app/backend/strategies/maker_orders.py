"""Maker 掛單引擎。

取代原本「輪詢→市價 taker」的做法：因為定值再平衡策略是確定性的，
任一持倉下的觸發價與成交量都能事先算死，所以直接把限價單預掛在 band 邊緣
等成交（賺 maker、省 taker、成交價更精準）。

兩個階段：
  - building（建倉中）：只掛一張建倉買單，直到持倉市值達目標投資金額。
    建倉掛價有兩種模式：target=固定目標開倉價、chase=追買一(買一+1tick)。
  - trading（交易中）：建滿後才開始雙邊再平衡掛單。

每個 poll cycle 呼叫一次 sync()：
  1. reconcile()：查掛單狀態，偵測（含部分）成交並記錄，清掉已結束的單。
  2. 依階段：_manage_build()(建倉) 或 _place_targets()(再平衡)。

狀態（掛單 id、phase、開倉均價）持久化到 records/maker_orders_<策略>.json，
重啟後可對帳，避免重複掛單或留下孤兒單。
"""
import os
import json
import datetime
import logging

from ..utils.paths import records_dir

# 價量比對容差：價格 1bp、量 0.1% 以內視為「已是目標掛單」，不重掛，避免每輪 churn。
_PRICE_TOL = 1e-4
_VOL_TOL = 1e-3

# MAX maker 費率（預掛限價單成交走 maker）
MAKER_FEE_RATE = 0.0005


class MakerOrderManager:
    def __init__(self, client, config, trading_record, notifier=None, logger=None):
        self.client = client
        self.config = config
        self.trading_record = trading_record
        self.notifier = notifier
        self.logger = logger or logging.getLogger(f"maker.{config.strategy_name}")
        self.market = f"{config.coin_type.lower()}twd"
        self._state_file = os.path.join(
            records_dir(), f"maker_orders_{config.strategy_name}.json"
        )
        # tracked: {order_id(str): {"side","price","volume","recorded"}}
        # phase: "building"(建倉中) | "trading"(交易中)；open_price: 開倉均價
        self.tracked, phase, self.open_price = self._load_state()
        if phase is None:
            # 遷移舊資料：已有持倉視為交易中，否則建倉中
            phase = "trading" if self.trading_record.get_current_balance() > 1e-12 else "building"
        self.phase = phase

    # ---------- 持久化 ----------
    def _load_state(self):
        try:
            with open(self._state_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}, None, 0.0
        if isinstance(data, dict) and "tracked" in data:
            return (data.get("tracked", {}), data.get("phase"),
                    float(data.get("open_price", 0) or 0))
        # 舊格式：整個 dict 即 tracked
        return (data if isinstance(data, dict) else {}), None, 0.0

    def _save_state(self):
        with open(self._state_file, "w", encoding="utf-8") as f:
            json.dump({"tracked": self.tracked, "phase": self.phase,
                       "open_price": self.open_price}, f, ensure_ascii=False, indent=2)

    # ---------- 工具 ----------
    def _current_price(self):
        trades = self.client.get_trades(self.market, limit=1)
        if not trades:
            raise ValueError(f"無法取得 {self.market} 現價")
        return float(trades[0]["price"])

    def _round_price(self, p):
        # 避免觸發交易所 tick size 限制：高價市場取整數，低價市場保留 4 位小數。
        return float(round(p)) if p >= 1000 else float(round(p, 4))

    def _tick(self):
        try:
            return float(self.client.tick_size(self.market))
        except Exception:
            return 0.0

    def _align(self, price):
        """把價格對齊到最小跳動單位（tick）；取不到 tick 時退回 _round_price。"""
        t = self._tick()
        return round(price / t) * t if t and t > 0 else self._round_price(price)

    def _record_fill(self, side, price, volume):
        fee = price * volume * MAKER_FEE_RATE
        self.trading_record.add_trade_record(
            datetime.datetime.now().isoformat(), price, volume, side,
            confirmed=False, fee=fee,
        )
        msg = f"Maker 成交 {side} {volume:.8f} {self.config.coin_type} @ {price:,.2f}"
        self.logger.info(msg)
        if self.notifier:
            try:
                self.notifier.send_trade_result(self.config.strategy_name, True, msg)
            except Exception as e:
                self.logger.warning(f"成交通知失敗: {e}")

    # ---------- 主流程 ----------
    def sync(self):
        """單一 poll cycle：對帳成交 + 依階段建倉或再平衡。回傳本輪訊息（無則 None）。"""
        try:
            filled_msgs = self._reconcile()
            if self.phase == "building":
                built = self._manage_build()   # 建倉階段：只掛建倉買單，建滿才轉交易
                if built:
                    filled_msgs.append(built)
            else:
                self._place_targets()          # 交易階段：雙邊再平衡掛單
            self._save_state()
            return "；".join(filled_msgs) if filled_msgs else None
        except Exception as e:
            self.logger.error(f"maker sync 發生錯誤: {e}")
            return None

    # ---------- 建倉階段 ----------
    def _manage_build(self):
        """建倉階段：維持一張建倉買單，直到持倉市值達目標投資金額才轉入交易階段。"""
        V = self.config.investment_amount
        price = self._current_price()
        balance = self.trading_record.get_current_balance()
        value = balance * price

        if value >= V * 0.999:
            # 全數建倉完成 → 撤掉殘單、記錄開倉均價、進入交易階段
            self._cancel_all()
            net_inv = self.trading_record.get_net_investment()
            self.open_price = net_inv / balance if balance > 1e-12 else price
            self.phase = "trading"
            msg = f"全數建倉完成，開倉均價 {self.open_price:,.2f}，開始自動再平衡"
            self.logger.info(msg)
            if self.notifier:
                try:
                    self.notifier.send_trade_result(self.config.strategy_name, True, msg)
                except Exception as e:
                    self.logger.warning(f"建倉完成通知失敗: {e}")
            self._place_targets()              # 立即掛出再平衡單
            return msg

        # 尚未建滿：維持一張建倉買單（量 = 補到目標市值所需）
        build_price = self._compute_build_price(price)
        qty = (V - value) / build_price
        self._ensure_single_buy(build_price, qty)
        return None

    def _compute_build_price(self, price):
        """建倉掛價：chase=買一+1tick(會變taker則改買一)；target=目標開倉價(或市價)。"""
        if self.config.build_mode == "chase":
            try:
                depth = self.client.get_depth(self.market, limit=1)
                best_bid = float(depth["bids"][0][0])
                best_ask = float(depth["asks"][0][0])
                tick = self._tick() or 0.0
                p = best_bid + tick
                if tick > 0 and p >= best_ask:
                    # 買一+1tick 會吃到賣單變 taker → 改用買一價維持 maker
                    p = best_bid
                return self._align(p)
            except Exception as e:
                self.logger.warning(f"取得委託簿失敗，改用市價建倉: {e}")
                return self._align(price)
        # 固定目標開倉價（0 = 用當前市價）
        tp = self.config.target_open_price
        return self._align(tp if tp and tp > 0 else price)

    def _ensure_single_buy(self, price, qty):
        """確保只有一張建倉買單在指定價/量；參數變了就撤掉重掛。"""
        if qty <= 0:
            return
        keep = None
        for oid, info in list(self.tracked.items()):
            if info["side"] == "buy" and keep is None:
                keep = oid
            else:
                self._cancel(oid)              # 多餘的單（理論上不會有）
        if keep is not None:
            info = self.tracked[keep]
            same_price = abs(float(info["price"]) - price) / price < _PRICE_TOL
            same_vol = abs(float(info["volume"]) - qty) / max(qty, 1e-9) < _VOL_TOL
            if same_price and same_vol:
                return
            self._cancel(keep)
        self._place("buy", price, qty)

    def _reconcile(self):
        """查每張 tracked 單，記錄新成交（含部分），移除已結束的單。"""
        messages = []
        for oid in list(self.tracked.keys()):
            info = self.tracked[oid]
            try:
                o = self.client.get_order(int(oid))
            except Exception as e:
                self.logger.warning(f"查訂單 {oid} 失敗，下輪重試: {e}")
                continue

            state = o.get("state")
            executed = float(o.get("executed_volume") or 0)
            fill_price = float(o.get("avg_price") or 0) or float(info["price"])

            newly = executed - float(info.get("recorded", 0))
            if newly > 1e-12:
                self._record_fill(info["side"], fill_price, newly)
                info["recorded"] = executed
                messages.append(
                    f"{info['side']} {newly:.8f}@{fill_price:,.0f}"
                )

            remaining = o.get("remaining_volume")
            finished = state in ("done", "cancel", "convert") or (
                remaining is not None and float(remaining) <= 1e-12
            )
            if finished:
                del self.tracked[oid]
        return messages

    def _desired_orders(self):
        """依當前持倉算出應掛的單：{side: (price, volume)}。"""
        f = self.config.auto_trade_percent / 100.0
        V = self.config.investment_amount
        balance = self.trading_record.get_current_balance()
        net_inv = self.trading_record.get_net_investment()
        desired = {}

        # 交易階段一定已有持倉（建倉由 building 階段負責）；無持倉則不掛單
        if balance <= 1e-12:
            return desired

        p_buy = self._align(V * (1 - f) / balance)
        p_sell = self._align(V * (1 + f) / balance)
        q_buy = balance * f / (1 - f)
        q_sell = balance * f / (1 + f)

        # 加碼上限：淨投資達 V+max_position 就不再掛買單（只留賣單）
        if net_inv < V + self.config.max_position:
            desired["buy"] = (p_buy, q_buy)
        desired["sell"] = (p_sell, q_sell)
        return desired

    def _place_targets(self):
        # 每日次數上限：達標即撤掉所有掛單、今日不再掛，待明日重啟
        if self.trading_record.get_today_trade_count() >= self.config.daily_trade_limit:
            if self.tracked:
                self.logger.info("已達每日交易次數上限，撤銷所有掛單")
                self._cancel_all()
            return

        desired = self._desired_orders()
        by_side = {info["side"]: oid for oid, info in self.tracked.items()}

        for side, (price, volume) in desired.items():
            if volume <= 0:
                continue
            existing = by_side.get(side)
            if existing is not None:
                info = self.tracked[existing]
                same_price = abs(float(info["price"]) - price) / price < _PRICE_TOL
                same_vol = abs(float(info["volume"]) - volume) / max(volume, 1e-9) < _VOL_TOL
                if same_price and same_vol:
                    continue  # 目標掛單已存在，不動
                self._cancel(existing)  # 參數變了，撤掉重掛
            self._place(side, price, volume)

        # 撤掉「目標已不需要」的那一邊（例如達加碼上限後的買單）
        for side, oid in list(by_side.items()):
            if side not in desired and oid in self.tracked:
                self._cancel(oid)

    def _place(self, side, price, volume):
        o = self.client.create_order(
            market=self.market, side=side, volume=volume,
            price=price, order_type="limit",
        )
        oid = str(o["id"])
        self.tracked[oid] = {
            "side": side, "price": float(price),
            "volume": float(volume), "recorded": 0.0,
        }
        self.logger.info(f"掛 {side} 限價單 {volume:.8f} @ {price:,.2f} (id={oid})")

    def _cancel(self, oid):
        try:
            self.client.cancel_order(int(oid))
        except Exception as e:
            self.logger.warning(f"撤單 {oid} 失敗: {e}")
        self.tracked.pop(oid, None)

    def _cancel_all(self):
        for oid in list(self.tracked.keys()):
            self._cancel(oid)
