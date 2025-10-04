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
# === KONFIGURACJA STRATEGII 4H RANGE REVERSAL ===
# ==============================================================================
BOT_CONFIGS = [
    {
        "symbol": "BTCUSDT",
        "leverage": "10",
        "risk_percentage": 0.5,
        "tp_ratio": 2.0,
        "range_interval": "240", # Interwał do wyznaczania zakresu (4h)
        "trade_interval": "5"    # Interwał do wyszukiwania sygnałów (5m)
    },
    # Aby dodać kolejną parę, skopiuj powyższy blok i zmień "symbol", np.:
    # {
    #     "symbol": "ETHUSDT",
    #     "leverage": "10",
    #     "risk_percentage": 0.5,
    #     "tp_ratio": 2.0,
    #     "range_interval": "240",
    #     "trade_interval": "5"
    # },
]
# ==============================================================================

class BybitClient:
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

        headers = {
            'X-BAPI-API-KEY': self.api_key,
            'X-BAPI-SIGN': signature,
            'X-BAPI-TIMESTAMP': timestamp,
            'X-BAPI-RECV-WINDOW': recv_window,
            'Content-Type': 'application/json'
        }

        try:
            if method == "POST":
                response = self.session.post(url, headers=headers, data=payload_str)
            else:
                del headers['Content-Type']
                response = self.session.get(url, headers=headers, params=params)
            
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
        if start:
            params['start'] = start
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

    def get_instrument_info(self, symbol):
        endpoint = "/v5/market/instruments-info"
        params = {"category": "linear", "symbol": symbol}
        data = self._send_request("GET", endpoint, params)
        if data and data.get("retCode") == 0 and data["result"]["list"]:
            info = data["result"]["list"][0]["lotSizeFilter"]
            return {
                "minOrderQty": float(info["minOrderQty"]),
                "qtyStep": float(info["qtyStep"])
            }
        return None

    def get_wallet_balance(self, coin="USDT"):
        endpoint = "/v5/account/wallet-balance"
        params = {"accountType": "UNIFIED"}
        data = self._send_request("GET", endpoint, params)
        if data and data.get("result") and data["result"]["list"]:
            for c in data["result"]["list"][0]["coin"]:
                if c["coin"] == coin: return float(c["walletBalance"])
        return 0

    def get_position_size(self, symbol):
        endpoint = "/v5/position/list"
        params = {"category": "linear", "symbol": symbol}
        data = self._send_request("GET", endpoint, params)
        if data and data.get("result") and data["result"]["list"]:
            for pos in data["result"]["list"]:
                if pos['symbol'] == symbol:
                    return float(pos.get("size", 0))
        return 0
    
    def place_order_with_sl_tp(self, symbol, side, qty, stop_loss, take_profit):
        endpoint = "/v5/order/create"
        params = {
            "category": "linear", 
            "symbol": symbol, 
            "side": side, 
            "orderType": "Market", 
            "qty": str(qty),
            "stopLoss": str(stop_loss),
            "takeProfit": str(take_profit)
        }
        side_colored = colored(side.upper(), "green" if side == "Buy" else "red")
        print(colored(f"\n[{symbol}] Składanie zlecenia {side_colored}:", "yellow", attrs=['bold']))
        print(colored(f"  - Ilość: {qty} {symbol[:-4]}", "yellow"))
        print(colored(f"  - Stop Loss: {stop_loss}", "yellow"))
        print(colored(f"  - Take Profit: {take_profit}", "yellow"))
        return self._send_request("POST", endpoint, params)

def get_precision(step):
    if '.' in str(step):
        return len(str(step).split('.')[1])
    return 0

def run_strategy(config):
    client = BybitClient(API_KEY, API_SECRET)
    symbol = config['symbol']
    
    print(colored(f"[{symbol}] Bot '4h Range Reversal' uruchomiony!", "green", attrs=['bold']))
    print(colored(f"[{symbol}] Interwał handlowy: {config['trade_interval']}m | Czas: Nowy Jork (EST/EDT)", "blue"))
    
    instrument_rules = client.get_instrument_info(symbol)
    if not instrument_rules:
        print(colored(f"[{symbol}] Nie udało się pobrać reguł handlowych. Zatrzymuję wątek.", "red"))
        return
    
    qty_precision = get_precision(instrument_rules['qtyStep'])

    range_high, range_low, last_range_day = None, None, None
    state = "AWAITING_RANGE"
    breakout_direction, breakout_extreme_price = None, None
    in_position = False

    ny_timezone = pytz.timezone("America/New_York")
    
    waiting_log_sent_for_day = None
    in_position_log_sent = False
    range_fetch_failed_log_sent = False

    while True:
        try:
            now_utc = datetime.datetime.now(pytz.utc)
            now_ny = now_utc.astimezone(ny_timezone)
            
            if now_ny.day != last_range_day:
                if now_ny.hour < 4:
                    if waiting_log_sent_for_day != now_ny.day:
                        print(colored(f"[{symbol}][{now_ny.strftime('%H:%M:%S')}] Nowy dzień. Oczekiwanie na zamknięcie świecy 4h (do 04:00 NY Time)...", "yellow"))
                        waiting_log_sent_for_day = now_ny.day
                    time.sleep(60)
                    continue

                start_of_ny_day = now_ny.replace(hour=0, minute=0, second=0, microsecond=0)
                start_of_ny_day_utc_ms = int(start_of_ny_day.timestamp() * 1000)

                range_klines = client.get_klines(symbol, config['range_interval'], limit=1, start=start_of_ny_day_utc_ms)
                
                if range_klines:
                    range_fetch_failed_log_sent = False
                    range_high = float(range_klines[0][2])
                    range_low = float(range_klines[0][3])
                    last_range_day = now_ny.day
                    if not in_position:
                        state = "AWAITING_BREAKOUT"
                        breakout_direction = None
                    print(colored(f"\n[{symbol}] Zakres na dziś ustalony:", "green", attrs=['bold']))
                    print(colored(f"  - Top Range:    {range_high}", "green"))
                    print(colored(f"  - Bottom Range: {range_low}", "green"))
                else:
                    if not range_fetch_failed_log_sent:
                        print(colored(f"[{symbol}][{now_ny.strftime('%H:%M:%S')}] Nie można pobrać danych 4h z API. Ponawiam próbę co 60 sekund...", "red"))
                        range_fetch_failed_log_sent = True
                    time.sleep(60)
                    continue

            position_size = client.get_position_size(symbol)
            if position_size > 0:
                in_position = True
                if not in_position_log_sent:
                    print(colored(f"[{symbol}][{now_ny.strftime('%H:%M:%S')}] Pozycja otwarta ({position_size} {symbol}). Oczekuję na SL/TP...", "cyan"))
                    in_position_log_sent = True
                time.sleep(15)
                continue
            elif in_position and position_size == 0:
                print(colored(f"\n[{symbol}][{now_ny.strftime('%H:%M:%S')}] Pozycja zamknięta. Wznawiam skanowanie rynku.", "green", attrs=['bold']))
                in_position = False
                in_position_log_sent = False
                state = "AWAITING_BREAKOUT"
            
            if not in_position and state in ["AWAITING_BREAKOUT", "AWAITING_REENTRY"]:
                klines_trade = client.get_klines(symbol, config['trade_interval'], limit=2)
                if len(klines_trade) < 2:
                    time.sleep(10)
                    continue

                last_closed_candle = klines_trade[0]
                candle_high, candle_low, candle_close = float(last_closed_candle[2]), float(last_closed_candle[3]), float(last_closed_candle[4])
                
                if state == "AWAITING_BREAKOUT":
                    if candle_close > range_high:
                        state, breakout_direction, breakout_extreme_price = "AWAITING_REENTRY", "UP", candle_high
                        print(colored(f"\n[{symbol}][{now_ny.strftime('%H:%M:%S')}] WYBICIE GÓRĄ! Zamknięcie: {candle_close}. Oczekuję na powrót.", "magenta"))
                    elif candle_close < range_low:
                        state, breakout_direction, breakout_extreme_price = "AWAITING_REENTRY", "DOWN", candle_low
                        print(colored(f"\n[{symbol}][{now_ny.strftime('%H:%M:%S')}] WYBICIE DOŁEM! Zamknięcie: {candle_close}. Oczekuję na powrót.", "magenta"))
                
                elif state == "AWAITING_REENTRY":
                    signal_confirmed = False
                    if breakout_direction == "UP" and candle_close < range_high:
                        side, stop_loss, entry_price = "Sell", breakout_extreme_price, candle_close
                        take_profit = entry_price - (abs(entry_price - stop_loss) * config['tp_ratio'])
                        signal_confirmed = True
                        print(colored(f"\n[{symbol}][{now_ny.strftime('%H:%M:%S')}] POWRÓT DO ZAKRESU! Potwierdzony sygnał SHORT!", "red", attrs=['bold']))

                    elif breakout_direction == "DOWN" and candle_close > range_low:
                        side, stop_loss, entry_price = "Buy", breakout_extreme_price, candle_close
                        take_profit = entry_price + (abs(entry_price - stop_loss) * config['tp_ratio'])
                        signal_confirmed = True
                        print(colored(f"\n[{symbol}][{now_ny.strftime('%H:%M:%S')}] POWRÓT DO ZAKRESU! Potwierdzony sygnał LONG!", "green", attrs=['bold']))

                    if signal_confirmed:
                        balance = client.get_wallet_balance()
                        risk_amount = balance * (config['risk_percentage'] / 100)
                        stop_loss_distance = abs(entry_price - stop_loss)
                        
                        if stop_loss_distance == 0:
                            state = "AWAITING_BREAKOUT"
                            continue

                        qty = risk_amount / stop_loss_distance
                        adjusted_qty = math.floor(qty / instrument_rules['qtyStep']) * instrument_rules['qtyStep']
                        
                        if adjusted_qty >= instrument_rules['minOrderQty']:
                            final_qty_str = f"{adjusted_qty:.{qty_precision}f}"
                            client.place_order_with_sl_tp(symbol, side, final_qty_str, round(stop_loss, 4), round(take_profit, 4))
                            in_position = True
                        else:
                            state = "AWAITING_BREAKOUT"
            
            time.sleep(5)

        except Exception as e:
            print(colored(f"\n[{symbol}] KRYTYCZNY BŁĄD w głównej pętli: {e}", "red", attrs=['bold']))
            time.sleep(60)

if __name__ == "__main__":
    if "TWOJ_API_KEY" in API_KEY or "TWOJ_API_SECRET" in API_SECRET:
        print(colored("BŁĄD: Proszę ustawić prawdziwe wartości API_KEY i API_SECRET w pliku!", "red"), flush=True)
    else:
        threads = []
        for config in BOT_CONFIGS:
            thread = threading.Thread(target=run_strategy, args=(config,))
            threads.append(thread)
            thread.start()
            print(colored(f"Uruchomiono wątek dla {config['symbol']}", "yellow"))
            time.sleep(5)

        for thread in threads:
            thread.join()
