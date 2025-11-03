import time
import hmac
import hashlib
import requests
import json
import datetime
import math
from termcolor import colored
import pytz
import threading

# === KONFIGURACJA GŁÓWNA ===
API_KEY = "pk3pm3ytYQfYq8Kbku"
API_SECRET = "0gLWHahoJ546CbTqozDVYHPiwwaKGIiljToR"
BASE_URL = "https://api.bybit.com"

# ==============================================================================
# ZMIANA: Główny przełącznik trybu symulacji
# True = Działanie 'na sucho', tylko logi, bez realnych zleceń.
# False = Prawdziwy handel na giełdzie.
# ==============================================================================
DRY_RUN = True
# ==============================================================================

# === KONFIGURACJA STRATEGII ===
BOT_CONFIGS = [
   {
        "symbol": "BTCUSDT",
        "leverage": "10",
        "risk_percentage": 0.5,
        "tp_ratio": 2.0,
        "range_interval": "240",
        "trade_interval": "5",
        "use_break_even": False,     # NOWA FUNKCJA: Przesuń SL na cenę wejścia przy 1:1 R:R
        "use_smart_sl": False,      # NOWA FUNKCJA: Użyj ciaśniejszego SL opartego o strukturę rynku
    },
]
# ==============================================================================

class BybitClient:
    # ... (większość klasy BybitClient pozostaje bez zmian)
    def __init__(self, api_key, api_secret):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = BASE_URL
        self.session = requests.Session()

    def _send_request(self, method, endpoint, params=None):
        url = self.base_url + endpoint
        timestamp = str(int(time.time() * 1000))
        recv_window = "10000"
        if params is None: params = {}

        if method == "POST":
            payload_str = json.dumps(params, separators=(',', ':'))
        else:
            payload_str = "&".join([f"{k}={v}" for k, v in sorted(params.items())])

        to_sign = timestamp + self.api_key + recv_window + payload_str
        signature = hmac.new(self.api_secret.encode('utf-8'), to_sign.encode('utf-8'), hashlib.sha256).hexdigest()
        headers = {'X-BAPI-API-KEY': self.api_key, 'X-BAPI-SIGN': signature, 'X-BAPI-TIMESTAMP': timestamp, 'X-BAPI-RECV-WINDOW': recv_window, 'Content-Type': 'application/json'}

        try:
            response = self.session.request(method, url, headers=headers, data=payload_str if method == "POST" else None, params=params if method != "POST" else None)
            response.raise_for_status()
            data = response.json()
            if data.get("retCode") != 0:
                print(colored(f"Błąd API Bybit: {data.get('retMsg')} (retCode: {data.get('retCode')})", "red"), flush=True)
                return None
            return data
        except Exception as e:
            print(colored(f"Błąd połączenia: {e}", "red"), flush=True)
            return None

    def get_klines(self, symbol, interval, limit=200, start=None):
        endpoint = "/v5/market/kline"
        params = {"category": "linear", "symbol": symbol, "interval": interval, "limit": limit}
        if start: params['start'] = start
        try:
            response = requests.get(self.base_url + endpoint, params=params)
            response.raise_for_status()
            data = response.json()
            if data.get("retCode") == 0:
                klines = data["result"]["list"]
                klines.reverse()
                return klines
            return []
        except Exception as e:
            print(colored(f"Błąd pobierania klines: {e}", "red"), flush=True)
            return []
            
    def get_current_price(self, symbol):
        endpoint = "/v5/market/tickers"
        params = {"category": "linear", "symbol": symbol}
        # Używamy zwykłego requestu, aby nie zaśmiecać logów błędami API przy starcie bota
        try:
            response = requests.get(self.base_url + endpoint, params=params)
            response.raise_for_status()
            data = response.json()
            if data.get("retCode") == 0 and data.get("result", {}).get("list"):
                return float(data["result"]["list"][0]["lastPrice"])
        except Exception:
            return None
        return None

    def get_position_info(self, symbol):
        if DRY_RUN: return None # W trybie symulacji nie sprawdzamy realnych pozycji
        endpoint = "/v5/position/list"
        params = {"category": "linear", "symbol": symbol}
        data = self._send_request("GET", endpoint, params)
        if data and data.get("result", {}).get("list"):
            for pos in data["result"]["list"]:
                if pos['symbol'] == symbol and float(pos.get("size", 0)) > 0:
                    return {"size": float(pos["size"]), "entry_price": float(pos["avgPrice"]), "side": pos["side"]}
        return None
        
    def modify_position_sl(self, symbol, stop_loss):
        if DRY_RUN: return True # W trybie symulacji symulujemy sukces
        endpoint = "/v5/position/set-trading-stop"
        params = {"category": "linear", "symbol": symbol, "stopLoss": str(stop_loss)}
        print(colored(f"[{symbol}] Modyfikacja Stop Lossa na: {stop_loss}", "blue"), flush=True)
        return self._send_request("POST", endpoint, params)

    def get_instrument_info(self, symbol):
        endpoint = "/v5/market/instruments-info"
        params = {"category": "linear", "symbol": symbol}
        data = self._send_request("GET", endpoint, params)
        if data and data.get("retCode") == 0 and data["result"]["list"]:
            info = data["result"]["list"][0]["lotSizeFilter"]
            return {"minOrderQty": float(info["minOrderQty"]), "qtyStep": float(info["qtyStep"])}
        return None

    def get_wallet_balance(self, coin="USDT"):
        endpoint = "/v5/account/wallet-balance"
        params = {"accountType": "UNIFIED"}
        data = self._send_request("GET", endpoint, params)
        if data and data.get("result") and data["result"]["list"]:
            for c in data["result"]["list"][0]["coin"]:
                if c["coin"] == coin: return float(c["walletBalance"])
        return 0

    def place_order_with_sl_tp(self, symbol, side, qty, stop_loss, take_profit):
        side_colored = colored(side.upper(), "green" if side == "Buy" else "red")
        if DRY_RUN:
            print(colored(f"\n[{symbol}] SYMULACJA ZLECENIA {side_colored}:", "yellow", attrs=['bold']), flush=True)
            print(colored(f"  - Ilość: {qty} {symbol[:-4]}", "yellow"), flush=True)
            return True # Symulujemy złożenie zlecenia

        print(colored(f"\n[{symbol}] Składanie zlecenia {side_colored}:", "yellow", attrs=['bold']), flush=True)
        print(colored(f"  - Ilość: {qty} {symbol[:-4]}", "yellow"), flush=True)
        print(colored(f"  - Stop Loss: {stop_loss}", "yellow"), flush=True)
        print(colored(f"  - Take Profit: {take_profit}", "yellow"), flush=True)
        endpoint = "/v5/order/create"
        params = {"category": "linear", "symbol": symbol, "side": side, "orderType": "Market", "qty": str(qty), "stopLoss": str(stop_loss), "takeProfit": str(take_profit)}
        return self._send_request("POST", endpoint, params)

def get_precision(step):
    return len(str(step).split('.')[1]) if '.' in str(step) else 0

def find_smart_sl_level(klines, direction, extreme_price):
    # Ta funkcja pozostaje bez zmian
    relevant_klines = klines[-10:]
    if direction == "DOWN":
        for i in range(len(relevant_klines) - 2, 0, -1):
            prev_low, curr_low, next_low = float(relevant_klines[i-1][3]), float(relevant_klines[i][3]), float(relevant_klines[i+1][3])
            if curr_low < prev_low and curr_low < next_low and curr_low > extreme_price:
                return curr_low
    elif direction == "UP":
        for i in range(len(relevant_klines) - 2, 0, -1):
            prev_high, curr_high, next_high = float(relevant_klines[i-1][2]), float(relevant_klines[i][2]), float(relevant_klines[i+1][2])
            if curr_high > prev_high and curr_high > next_high and curr_high < extreme_price:
                return curr_high
    return extreme_price

def run_strategy(config):
    client = BybitClient(API_KEY, API_SECRET)
    symbol = config['symbol']
    
    if DRY_RUN:
        print(colored(f"[{symbol}] Bot uruchomiony w trybie SYMULACJI (PAPER TRADING)", "magenta", attrs=['bold']), flush=True)
    else:
        print(colored(f"[{symbol}] Bot '4h Range Reversal' uruchomiony!", "green", attrs=['bold']), flush=True)
    
    # Zmienne stanu i zarządzania pozycją
    range_high, range_low, last_range_day, state = None, None, None, "AWAITING_RANGE"
    breakout_direction, breakout_extreme_price = None, None
    trade_info = {}
    ny_timezone = pytz.timezone("America/New_York")

    while True:
        try:
            now_utc = datetime.datetime.now(pytz.utc)
            now_ny = now_utc.astimezone(ny_timezone)
            
            # --- Ustalanie zakresu ---
            if now_ny.day != last_range_day:
                if now_ny.hour < 4:
                    time.sleep(60)
                    continue

                start_of_ny_day_utc_ms = int(now_ny.replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)
                range_klines = client.get_klines(symbol, config['range_interval'], limit=1, start=start_of_ny_day_utc_ms)
                
                if range_klines:
                    range_high, range_low = float(range_klines[0][2]), float(range_klines[0][3])
                    last_range_day = now_ny.day
                    if not trade_info: state = "AWAITING_BREAKOUT"
                else:
                    time.sleep(60)
                    continue

            # --- Zarządzanie Otwartą Pozycją (Realną lub Symulowaną) ---
            if not DRY_RUN: # Logika dla realnego handlu
                position_data = client.get_position_info(symbol)
                if not position_data and trade_info: # Jeśli pozycja została zamknięta
                    trade_info = {}
                    state = "AWAITING_BREAKOUT"
                elif position_data and not trade_info: # Jeśli bot został zrestartowany
                    trade_info = {"sl_moved_to_be": True}

            if trade_info:
                current_price = client.get_current_price(symbol)
                if not current_price:
                    time.sleep(5)
                    continue

                # Logika symulacji SL/TP
                if DRY_RUN:
                    is_closed = False
                    result = 0
                    if trade_info["side"] == "Buy":
                        if current_price <= trade_info["stop_loss"]:
                            is_closed = True
                            result = (trade_info["stop_loss"] - trade_info["entry_price"]) * trade_info["quantity"]
                            print(colored(f"[{symbol}] SYMULACJA: Stop Loss trafiony. Wynik: {result:.2f} USDT", "red"), flush=True)
                        elif current_price >= trade_info["take_profit"]:
                            is_closed = True
                            result = (trade_info["take_profit"] - trade_info["entry_price"]) * trade_info["quantity"]
                            print(colored(f"[{symbol}] SYMULACJA: Take Profit zrealizowany. Wynik: {result:.2f} USDT", "green"), flush=True)
                    elif trade_info["side"] == "Sell":
                        if current_price >= trade_info["stop_loss"]:
                            is_closed = True
                            result = (trade_info["entry_price"] - trade_info["stop_loss"]) * trade_info["quantity"]
                            print(colored(f"[{symbol}] SYMULACJA: Stop Loss trafiony. Wynik: {result:.2f} USDT", "red"), flush=True)
                        elif current_price <= trade_info["take_profit"]:
                            is_closed = True
                            result = (trade_info["entry_price"] - trade_info["take_profit"]) * trade_info["quantity"]
                            print(colored(f"[{symbol}] SYMULACJA: Take Profit zrealizowany. Wynik: {result:.2f} USDT", "green"), flush=True)
                    
                    if is_closed:
                        trade_info = {}
                        state = "AWAITING_BREAKOUT"
                        continue

                # Logika Break-Even (działa w obu trybach)
                if config['use_break_even'] and not trade_info.get("sl_moved_to_be"):
                    side, be_target, entry_price = trade_info["side"], trade_info["be_target"], trade_info["entry_price"]
                    if (side == "Buy" and current_price >= be_target) or (side == "Sell" and current_price <= be_target):
                        client.modify_position_sl(symbol, entry_price) # W trybie DRY_RUN ta funkcja nic nie robi
                        trade_info["sl_moved_to_be"] = True
                        print(colored(f"[{symbol}] SYMULACJA: Osiągnięto cel 1R. SL przesunięty na Break-Even ({entry_price}).", "cyan"), flush=True)
                
                time.sleep(5) # W trybie pozycji sprawdzamy cenę częściej
                continue

            # --- Skanowanie w Poszukiwaniu Sygnału ---
            if state in ["AWAITING_BREAKOUT", "AWAITING_REENTRY"]:
                klines_trade = client.get_klines(symbol, config['trade_interval'], limit=20)
                if len(klines_trade) < 20:
                    time.sleep(10)
                    continue

                last_closed_candle = klines_trade[-2]
                candle_high, candle_low, candle_close = float(last_closed_candle[2]), float(last_closed_candle[3]), float(last_closed_candle[4])
                
                if state == "AWAITING_BREAKOUT":
                    if candle_close > range_high:
                        state, breakout_direction, breakout_extreme_price = "AWAITING_REENTRY", "UP", candle_high
                    elif candle_close < range_low:
                        state, breakout_direction, breakout_extreme_price = "AWAITING_REENTRY", "DOWN", candle_low
                
                elif state == "AWAITING_REENTRY":
                    if breakout_direction == "UP" and candle_high > breakout_extreme_price:
                        breakout_extreme_price = candle_high
                    elif breakout_direction == "DOWN" and candle_low < breakout_extreme_price:
                        breakout_extreme_price = candle_low

                    if (breakout_direction == "UP" and candle_close < range_high) or (breakout_direction == "DOWN" and candle_close > range_low):
                        instrument_rules = client.get_instrument_info(symbol) # Pobierz aktualne info
                        if not instrument_rules: continue

                        side = "Sell" if breakout_direction == "UP" else "Buy"
                        entry_price = candle_close
                        stop_loss = breakout_extreme_price
                        
                        if config['use_smart_sl']:
                            stop_loss = find_smart_sl_level(klines_trade, breakout_direction, breakout_extreme_price)
                        
                        take_profit = entry_price - (abs(entry_price - stop_loss) * config['tp_ratio']) if side == "Sell" else entry_price + (abs(entry_price - stop_loss) * config['tp_ratio'])
                        
                        balance = 10000 if DRY_RUN else client.get_wallet_balance() # W trybie symulacji użyj wirtualnego salda
                        risk_amount = balance * (config['risk_percentage'] / 100)
                        stop_loss_distance = abs(entry_price - stop_loss)
                        
                        if stop_loss_distance == 0:
                            state = "AWAITING_BREAKOUT"
                            continue
                        
                        qty_by_risk = risk_amount / stop_loss_distance
                        leverage = float(config['leverage'])
                        max_qty_by_balance = (balance * leverage * 0.95) / entry_price
                        final_qty = min(qty_by_risk, max_qty_by_balance)
                        
                        qty_precision = get_precision(instrument_rules['qtyStep'])
                        adjusted_qty = math.floor(final_qty / instrument_rules['qtyStep']) * instrument_rules['qtyStep']
                        
                        if adjusted_qty >= instrument_rules['minOrderQty']:
                            final_qty_str = f"{adjusted_qty:.{qty_precision}f}"
                            if client.place_order_with_sl_tp(symbol, side, final_qty_str, round(stop_loss, 4), round(take_profit, 4)):
                                be_target = entry_price + stop_loss_distance if side == "Buy" else entry_price - stop_loss_distance
                                trade_info = {"side": side, "entry_price": entry_price, "stop_loss": stop_loss, "take_profit": take_profit, "quantity": adjusted_qty, "be_target": be_target, "sl_moved_to_be": False}
                        else:
                            state = "AWAITING_BREAKOUT"
            time.sleep(10) # Spowalnia pętlę, gdy nie ma sygnału

        except Exception as e:
            print(colored(f"\n[{symbol}] KRYTYCZNY BŁĄD w głównej pętli: {e}", "red", attrs=['bold']), flush=True)
            time.sleep(60)

if __name__ == "__main__":
    if "TWOJ_API_KEY" in API_KEY or "TWOJ_API_SECRET" in API_SECRET:
        print(colored("BŁĄD: Proszę ustawić prawdziwe wartości API_KEY i API_SECRET w pliku!", "red"), flush=True)
    else:
        for config in BOT_CONFIGS:
            thread = threading.Thread(target=run_strategy, args=(config,))
            thread.start()
