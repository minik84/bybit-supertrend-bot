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
API_KEY = "CxQFjz7JivQbTnihTP"  # ZMIEŃ NA SWÓJ KLUCZ
API_SECRET = "zfliLpcpjbb2LeQLNjvQx8Twlm41ctR4ZUGq"  # ZMIEŃ NA SWÓJ SECRET
BASE_URL = "https://api.bybit.com"

# ==============================================================================
# ZMIANA: Główny przełącznik trybu symulacji
# True = Działanie 'na sucho', tylko logi, bez realnych zleceń.
# False = Prawdziwy handel na giełdzie.
# ==============================================================================
DRY_RUN = False # ZMIEŃ NA FALSE DO PRAWDZIWEGO HANDLU
# ==============================================================================

# === KONFIGURACJA STRATEGII ===
BOT_CONFIGS = [
    {
        "symbol": "BTCUSDT",
        "leverage": "10",
        "tp_ratio": 2.0,
        "range_interval": "240",
        "trade_interval": "5",
        "use_break_even": True,
        "use_smart_sl": False,
        "sl_buffer_percentage": 0.075, 
        
        # --- Inteligentne Zaokrąglanie Ryzyka ---
        "risk_percentage": 0.5,
        "max_risk_tolerance_percentage": 1,
    },
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
                response = self.session.get(url, headers=headers, params=params)
                
            response.raise_for_status()
            data = response.json()
            
            # Kod 110043 (Set order stop loss/take profit failed, stop loss/take profit not modify) nie jest błędem krytycznym
            if data.get("retCode") != 0 and data.get("retCode") != 110043:
                print(colored(f"Błąd API Bybit ({endpoint}): {data.get('retMsg')} (retCode: {data.get('retCode')})", "red"), flush=True)
                return None
            return data
        except requests.exceptions.HTTPError as http_err:
            # Specjalnie loguj błędy 404, aby je widzieć
            if http_err.response.status_code == 404:
                print(colored(f"BŁĄD 404 (Not Found): Sprawdź endpoint API. URL: {url}", "red", attrs=['bold']), flush=True)
            else:
                print(colored(f"Błąd HTTP: {http_err}", "red"), flush=True)
            return None
        except requests.exceptions.RequestException as e:
            print(colored(f"Błąd połączenia: {e}", "red"), flush=True)
            return None
        except Exception as e:
            print(colored(f"Błąd przetwarzania żądania: {e}", "red"), flush=True)
            return None

    def get_klines(self, symbol, interval, limit=200, start=None):
        endpoint = "/v5/market/kline"
        params = {"category": "linear", "symbol": symbol, "interval": interval, "limit": limit}
        if start: params['start'] = start
        
        try:
            response = requests.get(self.base_url + endpoint, params=params)
            response.raise_for_status()
            data = response.json()
            if data.get("retCode") == 0 and data.get("result", {}).get("list"):
                klines = data["result"]["list"]
                klines.reverse()
                return klines
            else:
                print(colored(f"Błąd pobierania klines (retCode!=0): {data.get('retMsg')}", "red"), flush=True)
                return []
        except Exception as e:
            print(colored(f"Krytyczny błąd pobierania klines: {e}", "red"), flush=True)
            return []
            
    def get_current_price(self, symbol):
        endpoint = "/v5/market/tickers"
        params = {"category": "linear", "symbol": symbol}
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
        if DRY_RUN: return None
        
        endpoint = "/v5/position/list"
        params = {"category": "linear", "symbol": symbol}
        data = self._send_request("GET", endpoint, params)
        
        if data and data.get("result", {}).get("list"):
            # Znajdź pozycję, która jest otwarta (ma size > 0)
            for pos in data["result"]["list"]:
                # Sprawdzamy 'size' i 'side', aby upewnić się, że to aktywna pozycja
                if pos['symbol'] == symbol and float(pos.get("size", 0)) > 0 and pos.get("side") != "None":
                    return {
                        "size": float(pos["size"]), 
                        "entry_price": float(pos["avgPrice"]), 
                        "side": pos["side"]
                    }
        return None
        
    def modify_position_sl(self, symbol, stop_loss):
        """Modyfikuje Stop Loss dla otwartej pozycji (na potrzeby Break-Even)."""
        if DRY_RUN: 
            print(colored(f"[{symbol}] SYMULACJA: Modyfikacja Stop Lossa na: {stop_loss}", "blue"), flush=True)
            return True
        
        # ==============================================================================
        # POPRAWKA BŁĘDU 404: Używamy endpointu '/v5/position/trading-stop'
        # ==============================================================================
        endpoint = "/v5/position/trading-stop"
        # ==============================================================================
        
        params = {
            "category": "linear", 
            "symbol": symbol, 
            "stopLoss": str(stop_loss),
            "tpslMode": "Full", # Użyj "Full" dla pełnej pozycji
            "positionIdx": 0 # Dla trybu One-Way
        }
        print(colored(f"[{symbol}] MODYFIKACJA SL: Ustawianie Stop Lossa na: {stop_loss}", "blue"), flush=True)
        data = self._send_request("POST", endpoint, params)
        
        # Sprawdź, czy API zwróciło sukces (0) lub błąd "not modify" (110043), który też jest OK
        if data and (data.get('retCode') == 0 or data.get('retCode') == 110043):
            return True
        elif data:
            print(colored(f"[{symbol}] BŁĄD MODYFIKACJI SL: {data.get('retMsg')}", "red"), flush=True)
            return False
        else:
            # Błąd 404 lub inny błąd połączenia został już zalogowany przez _send_request
            return False

    def get_instrument_info(self, symbol):
        endpoint = "/v5/market/instruments-info"
        params = {"category": "linear", "symbol": symbol}
        
        data = self._send_request("GET", endpoint, params) 
        
        if data and data.get("retCode") == 0 and data.get("result", {}).get("list"):
            info = data["result"]["list"][0]
            lot_size_filter = info.get("lotSizeFilter", {})
            price_filter = info.get("priceFilter", {})
            
            return {
                "minOrderQty": float(lot_size_filter.get("minOrderQty", 0.001)), 
                "qtyStep": float(lot_size_filter.get("qtyStep", 0.001)),
                "tickSize": float(price_filter.get("tickSize", 0.01))
            }
        
        print(colored(f"[{symbol}] KRYTYCZNY BŁĄD: Nie można pobrać informacji o instrumencie.", "red"), flush=True)
        return None

    def get_wallet_balance(self, coin="USDT"):
        global virtual_balance
        if DRY_RUN: 
            return virtual_balance
        
        endpoint = "/v5/account/wallet-balance"
        params = {"accountType": "UNIFIED"}
        data = self._send_request("GET", endpoint, params)
        
        if data and data.get("result") and data["result"].get("list"):
            if not data["result"]["list"]:
                print(colored("Nie można pobrać salda (pusta lista).", "red"), flush=True)
                return 0

            for c in data["result"]["list"][0]["coin"]:
                if c["coin"] == coin: 
                    return float(c["walletBalance"])
        
        print(colored(f"Nie znaleziono salda dla {coin}. Zwracam 0.", "yellow"), flush=True)
        return 0

    def place_order_with_sl_tp(self, symbol, side, qty, stop_loss, take_profit, entry_price_for_sim):
        side_colored = colored(side.upper(), "green" if side == "Buy" else "red")
        
        if DRY_RUN:
            print(colored(f"\n[{symbol}] SYMULACJA ZLECENIA {side_colored}:", "yellow", attrs=['bold']), flush=True)
            print(colored(f"  - Cena wejścia (symulowana): {entry_price_for_sim}", "yellow"), flush=True)
            print(colored(f"  - Ilość: {qty} {symbol[:-4]}", "yellow"), flush=True)
            print(colored(f"  - Stop Loss: {stop_loss}", "yellow"), flush=True)
            print(colored(f"  - Take Profit: {take_profit}", "yellow"), flush=True)
            return True

        print(colored(f"\n[{symbol}] SKŁADANIE ZLECENIA {side_colored}:", "yellow", attrs=['bold']), flush=True)
        print(colored(f"  - Ilość: {qty} {symbol[:-4]}", "yellow"), flush=True)
        print(colored(f"  - Stop Loss: {stop_loss}", "yellow"), flush=True)
        print(colored(f"  - Take Profit: {take_profit}", "yellow"), flush=True)
        
        endpoint = "/v5/order/create"
        params = {
            "category": "linear", 
            "symbol": symbol, 
            "side": side, 
            "orderType": "Market", 
            "qty": str(qty), 
            "stopLoss": str(stop_loss), 
            "takeProfit": str(take_profit),
            "tpslMode": "Full", # Ustawia SL/TP dla całej pozycji
            "positionIdx": 0 # Dla trybu One-Way
        }
        data = self._send_request("POST", endpoint, params)
        return data is not None

# --- Funkcje Pomocnicze ---

def get_precision_from_step(step):
    step_str = f"{step:.10f}"
    if '.' in step_str:
        return len(step_str.split('.')[-1].rstrip('0'))
    return 0

def round_to_tick(value, tick_size):
    return round(value / tick_size) * tick_size

# --- Logika Strategii ---

virtual_balance = 180.0

def find_smart_sl_level(klines_5min, direction, extreme_price):
    relevant_klines = klines_5min[-40:]
    
    if direction == "DOWN":
        for i in range(len(relevant_klines) - 2, 0, -1):
            prev_low, curr_low, next_low = float(relevant_klines[i-1][3]), float(relevant_klines[i][3]), float(relevant_klines[i+1][3])
            if curr_low < prev_low and curr_low < next_low:
                if curr_low > extreme_price:
                    print(colored(f"[{threading.current_thread().name}] (Smart SL) Znaleziono Swing Low: {curr_low}", "cyan"), flush=True)
                    return curr_low
                    
    elif direction == "UP":
        for i in range(len(relevant_klines) - 2, 0, -1):
            prev_high, curr_high, next_high = float(relevant_klines[i-1][2]), float(relevant_klines[i][2]), float(relevant_klines[i+1][2])
            if curr_high > prev_high and curr_high > next_high:
                if curr_high < extreme_price:
                    print(colored(f"[{threading.current_thread().name}] (Smart SL) Znaleziono Swing High: {curr_high}", "cyan"), flush=True)
                    return curr_high
                    
    print(colored(f"[{threading.current_thread().name}] (Smart SL) Nie znaleziono struktury, używam ekstremum: {extreme_price}", "cyan"), flush=True)
    return extreme_price

def run_strategy(config):
    global virtual_balance
    
    client = BybitClient(API_KEY, API_SECRET)
    symbol = config['symbol']
    thread_name = threading.current_thread().name
    
    if DRY_RUN:
        print(colored(f"[{thread_name}] Bot uruchomiony w trybie SYMULACJI (PAPER TRADING)", "magenta", attrs=['bold']), flush=True)
    else:
        print(colored(f"[{thread_name}] Bot '{symbol} Range Reversal' uruchomiony!", "green", attrs=['bold']), flush=True)
    
    range_high, range_low, last_range_day, state = None, None, None, "AWAITING_RANGE"
    breakout_direction, breakout_extreme_price = None, None
    trade_info = {}
    
    try:
        ny_timezone = pytz.timezone("America/New_York")
    except pytz.UnknownTimeZoneError:
        print(colored("BŁĄD: Nie można załadować strefy czasowej 'America/New_York'.", "red"), flush=True)
        return

    instrument_rules = client.get_instrument_info(symbol)
    if not instrument_rules:
        print(colored(f"[{thread_name}] KRYTYCZNY BŁĄD: Nie można pobrać zasad instrumentu. Zatrzymywanie wątku.", "red"), flush=True)
        return
    
    print(f"[{thread_name}] Zasady instrumentu: tickSize={instrument_rules['tickSize']}, qtyStep={instrument_rules['qtyStep']}", flush=True)

    while True:
        try:
            now_utc = datetime.datetime.now(pytz.utc)
            now_ny = now_utc.astimezone(ny_timezone)
            
            # --- 1. Ustalanie Zakresu Dnia (Range) ---
            if (now_ny.day != last_range_day or range_high is None) and not trade_info:
                
                if now_ny.hour < 4:
                    if state != "AWAITING_RANGE":
                        print(f"[{thread_name}] Czekam na 04:00 NY, aby ustalić nowy zakres... (teraz: {now_ny.strftime('%H:%M')})", flush=True)
                        state = "AWAITING_RANGE"
                    time.sleep(60)
                    continue

                print(f"[{thread_name}] Pobieranie nowego zakresu na dzień {now_ny.strftime('%Y-%m-%d')}...", flush=True)
                
                start_of_ny_day = now_ny.replace(hour=0, minute=0, second=0, microsecond=0)
                start_of_ny_day_utc_ms = int(start_of_ny_day.timestamp() * 1000)
                
                range_klines = client.get_klines(symbol, config['range_interval'], limit=1, start=start_of_ny_day_utc_ms)
                
                if range_klines:
                    range_high, range_low = float(range_klines[0][2]), float(range_klines[0][3])
                    last_range_day = now_ny.day
                    state = "AWAITING_BREAKOUT"
                    print(colored(f"[{thread_name}] Nowy zakres ustalony: HIGH={range_high}, LOW={range_low}", "cyan"), flush=True)
                else:
                    print(colored(f"[{thread_name}] Nie udało się pobrać świecy zakresu. Spróbuję ponownie za 60s.", "red"), flush=True)
                    time.sleep(60)
                    continue
            
            # --- 2. Zarządzanie Otwartą Pozycją (Realną lub Symulowaną) ---
            
            if not DRY_RUN: 
                if trade_info:
                    position_data = client.get_position_info(symbol)
                    if not position_data:
                        print(colored(f"[{thread_name}] Realna pozycja została zamknięta (SL/TP). Czekam na nowy sygnał.", "green"), flush=True)
                        trade_info = {}
                        state = "AWAITING_BREAKOUT"
                else:
                    position_data = client.get_position_info(symbol)
                    if position_data:
                        print(colored(f"[{thread_name}] Wykryto istniejącą pozycję po restarcie. Bot przejmuje zarządzanie (tylko BE).", "blue"), flush=True)
                        trade_info = {
                            "side": position_data["side"], 
                            "entry_price": position_data["entry_price"], 
                            "sl_moved_to_be": True # Zakładamy, że już jest zarządzana
                        }
                        state = "IN_POSITION"

            if trade_info:
                if state != "IN_POSITION": state = "IN_POSITION"
                
                current_price = client.get_current_price(symbol)
                if not current_price:
                    time.sleep(5)
                    continue

                if DRY_RUN:
                    is_closed = False
                    result_R = 0
                    
                    if trade_info["side"] == "Buy":
                        if current_price <= trade_info["stop_loss"]:
                            is_closed = True
                            sl_dist = trade_info["entry_price"] - trade_info["initial_sl"]
                            loss_dist = trade_info["entry_price"] - trade_info["stop_loss"]
                            result_R = -(loss_dist / sl_dist) if sl_dist > 0 else 0
                            print(colored(f"[{thread_name}] SYMULACJA: Stop Loss trafiony.", "red"), flush=True)
                        elif current_price >= trade_info["take_profit"]:
                            is_closed = True
                            result_R = config['tp_ratio']
                            print(colored(f"[{thread_name}] SYMULACJA: Take Profit zrealizowany.", "green"), flush=True)
                            
                    elif trade_info["side"] == "Sell":
                        if current_price >= trade_info["stop_loss"]:
                            is_closed = True
                            sl_dist = trade_info["initial_sl"] - trade_info["entry_price"]
                            loss_dist = trade_info["stop_loss"] - trade_info["entry_price"]
                            result_R = -(loss_dist / sl_dist) if sl_dist > 0 else 0
                            print(colored(f"[{thread_name}] SYMULACJA: Stop Loss trafiony.", "red"), flush=True)
                        elif current_price <= trade_info["take_profit"]:
                            is_closed = True
                            result_R = config['tp_ratio']
                            print(colored(f"[{thread_name}] SYMULACJA: Take Profit zrealizowany.", "green"), flush=True)
                    
                    if is_closed:
                        # Znajdź bazowe ryzyko dla logowania
                        base_risk_perc = config.get('risk_percentage', 1.0)
                        risk_amount_usd = virtual_balance * (base_risk_perc / 100)
                        
                        # Oblicz realny zysk/stratę na podstawie R
                        profit_usd = risk_amount_usd * result_R
                        virtual_balance += profit_usd
                        
                        print(colored(f"[{thread_name}] SYMULACJA: Wynik transakcji: {result_R:.2f}R ({profit_usd:+.2f} USDT)", "yellow"), flush=True)
                        print(colored(f"[{thread_name}] SYMULACJA: Nowe saldo: {virtual_balance:.2f} USDT", "yellow"), flush=True)
                        
                        trade_info = {}
                        state = "AWAITING_BREAKOUT"
                        continue

                if config['use_break_even'] and not trade_info.get("sl_moved_to_be"):
                    side = trade_info["side"]
                    be_target = trade_info["be_target"]
                    entry_price = trade_info["entry_price"]
                    
                    if (side == "Buy" and current_price >= be_target) or (side == "Sell" and current_price <= be_target):
                        
                        if client.modify_position_sl(symbol, entry_price): 
                            trade_info["sl_moved_to_be"] = True
                            if DRY_RUN:
                                trade_info["stop_loss"] = entry_price
                            print(colored(f"[{thread_name}] OSIĄGNIĘTO 1R: SL przesunięty na Break-Even ({entry_price}).", "cyan"), flush=True)
                        else:
                            # Błąd został już zalogowany przez modify_position_sl
                            print(colored(f"[{thread_name}] BŁĄD: Nie udało się przesunąć SL na Break-Even. Spróbuję ponownie.", "red"), flush=True)
                
                time.sleep(5)
                continue

            # --- 3. Skanowanie w Poszukiwaniu Sygnału ---
            if state in ["AWAITING_BREAKOUT", "AWAITING_REENTRY"]:
                if range_high is None or range_low is None:
                    time.sleep(10)
                    continue
                    
                klines_trade = client.get_klines(symbol, config['trade_interval'], limit=50) 
                
                if len(klines_trade) < 20:
                    print(f"[{thread_name}] Zbieram dane świec 5m...", flush=True)
                    time.sleep(10)
                    continue

                last_closed_candle = klines_trade[-2]
                candle_high, candle_low, candle_close = float(last_closed_candle[2]), float(last_closed_candle[3]), float(last_closed_candle[4])
                
                if state == "AWAITING_BREAKOUT":
                    if candle_close > range_high:
                        print(f"[{thread_name}] Wykryto wybicie GÓRĄ. Czekam na powrót do zakresu.", flush=True)
                        state, breakout_direction, breakout_extreme_price = "AWAITING_REENTRY", "UP", candle_high
                    elif candle_close < range_low:
                        print(f"[{thread_name}] Wykryto wybicie DOŁEM. Czekam na powrót do zakresu.", flush=True)
                        state, breakout_direction, breakout_extreme_price = "AWAITING_REENTRY", "DOWN", candle_low
                
                elif state == "AWAITING_REENTRY":
                    if breakout_direction == "UP" and candle_high > breakout_extreme_price:
                        breakout_extreme_price = candle_high
                    elif breakout_direction == "DOWN" and candle_low < breakout_extreme_price:
                        breakout_extreme_price = candle_low

                    if (breakout_direction == "UP" and candle_close < range_high) or (breakout_direction == "DOWN" and candle_close > range_low):
                        
                        side = "Sell" if breakout_direction == "UP" else "Buy"
                        entry_price = candle_close 
                        
                        stop_loss_base = breakout_extreme_price
                        
                        if config['use_smart_sl']:
                            stop_loss = find_smart_sl_level(klines_trade, breakout_direction, stop_loss_base)
                        else:
                            stop_loss = stop_loss_base
                            print(colored(f"[{thread_name}] Używam standardowego SL (ekstremum wybicia): {stop_loss}", "cyan"), flush=True)
                        
                        if config.get('sl_buffer_percentage', 0.0) > 0:
                            buffer_amount = stop_loss * (config['sl_buffer_percentage'] / 100.0)
                            if side == "Buy":
                                stop_loss -= buffer_amount
                                print(colored(f"[{thread_name}] Dodano bufor {buffer_amount:.4f}. Nowy SL: {stop_loss}", "cyan"), flush=True)
                            else: # side == "Sell"
                                stop_loss += buffer_amount
                                print(colored(f"[{thread_name}] Dodano bufor {buffer_amount:.4f}. Nowy SL: {stop_loss}", "cyan"), flush=True)

                        tick_size = instrument_rules['tickSize']
                        qty_step = instrument_rules['qtyStep']
                        
                        stop_loss = round_to_tick(stop_loss, tick_size)
                        
                        if (side == "Buy" and entry_price <= stop_loss) or (side == "Sell" and entry_price >= stop_loss):
                            print(colored(f"[{thread_name}] Błąd logiki: Cena wejścia ({entry_price}) jest gorsza niż SL ({stop_loss}). Anulowanie.", "red"), flush=True)
                            state = "AWAITING_BREAKOUT"
                            continue

                        stop_loss_distance_points = abs(entry_price - stop_loss)
                        if stop_loss_distance_points == 0:
                            print(colored(f"[{thread_name}] Błąd: Dystans SL = 0. Anulowanie wejścia.", "red"), flush=True)
                            state = "AWAITING_BREAKOUT"
                            continue
                            
                        tp_distance = stop_loss_distance_points * config['tp_ratio']
                        take_profit = entry_price - tp_distance if side == "Sell" else entry_price + tp_distance
                        take_profit = round_to_tick(take_profit, tick_size)

                        balance = client.get_wallet_balance()
                        if balance <= 0:
                            print(colored(f"[{thread_name}] Brak środków na koncie (Saldo: {balance}). Czekam.", "red"), flush=True)
                            time.sleep(300)
                            continue
                        
                        # --- Logika Inteligentnego Zaokrąglania ---
                        
                        base_risk_perc = config.get('risk_percentage', 1.0)
                        base_risk_amount_usd = balance * (base_risk_perc / 100)
                        qty_by_risk = base_risk_amount_usd / stop_loss_distance_points
                        
                        leverage = float(config['leverage'])
                        max_qty_by_balance = (balance * leverage * 0.95) / entry_price
                        final_qty_ideal = min(qty_by_risk, max_qty_by_balance)

                        floor_qty = math.floor(final_qty_ideal / qty_step) * qty_step
                        ceiling_qty = math.ceil(final_qty_ideal / qty_step) * qty_step

                        max_risk_tolerance_perc = config.get('max_risk_tolerance_percentage', base_risk_perc)
                        max_risk_allowed_usd = balance * (max_risk_tolerance_perc / 100)
                        
                        risk_of_ceiling_qty_usd = ceiling_qty * stop_loss_distance_points
                        
                        adjusted_qty = 0.0
                        
                        if ceiling_qty <= 0:
                             adjusted_qty = floor_qty
                        
                        elif risk_of_ceiling_qty_usd <= max_risk_allowed_usd:
                            adjusted_qty = ceiling_qty
                            print(colored(f"[{thread_name}] Zaokrąglono ilość W GÓRĘ do {ceiling_qty} (Ryzyko: {risk_of_ceiling_qty_usd:.2f} USD <= Max: {max_risk_allowed_usd:.2f} USD)", "cyan"), flush=True)
                        else:
                            adjusted_qty = floor_qty
                            risk_of_floor_qty_usd = floor_qty * stop_loss_distance_points
                            print(colored(f"[{thread_name}] Zaokrąglono ilość W DÓŁ do {floor_qty} (Ryzyko: {risk_of_floor_qty_usd:.2f} USD)", "yellow"), flush=True)
                        
                        # --- Koniec Logiki ---
                        
                        if adjusted_qty >= instrument_rules['minOrderQty']:
                            final_qty_str = f"{adjusted_qty:.{get_precision_from_step(qty_step)}f}"
                            
                            if client.place_order_with_sl_tp(symbol, side, final_qty_str, stop_loss, take_profit, entry_price):
                                
                                be_target = entry_price + stop_loss_distance_points if side == "Buy" else entry_price - stop_loss_distance_points
                                be_target = round_to_tick(be_target, tick_size)
                                
                                trade_info = {
                                    "side": side, 
                                    "entry_price": entry_price,
                                    "stop_loss": stop_loss,
                                    "initial_sl": stop_loss,
                                    "take_profit": take_profit, 
                                    "quantity": adjusted_qty, 
                                    "be_target": be_target, 
                                    "sl_moved_to_be": False
                                }
                                state = "IN_POSITION"
                            else:
                                print(colored(f"[{thread_name}] Nie udało się złożyć zlecenia (Błąd API?). Resetowanie.", "red"), flush=True)
                                state = "AWAITING_BREAKOUT"
                        else:
                            print(colored(f"[{thread_name}] Obliczona ilość ({adjusted_qty}) jest mniejsza niż minimalna ({instrument_rules['minOrderQty']}). Anulowanie wejścia.", "yellow"), flush=True)
                            state = "AWAITING_BREAKOUT"

            if not trade_info:
                if state in ["AWAITING_BREAKOUT", "AWAITING_REENTRY"]:
                    time.sleep(10)
                else:
                    time.sleep(30) 

        except Exception as e:
            print(colored(f"\n[{thread_name}] KRYTYCZNY BŁĄD w głównej pętli: {e}", "red", attrs=['bold']), flush=True)
            import traceback
            traceback.print_exc()
            time.sleep(60)

# --- Uruchomienie Bota ---

if __name__ == "__main__":
    if "TWOJ_API_KEY" in API_KEY or "TWOJ_API_SECRET" in API_SECRET:
        print(colored("BŁĄD: Proszę ustawić prawdziwe wartości API_KEY i API_SECRET w pliku!", "red"), flush=True)
        print(colored("Bot będzie działał tylko w trybie DRY_RUN (Symulacja).", "magenta"), flush=True)
        DRY_RUN = True
    
    if DRY_RUN:
        print(colored(f"Uruchamianie w trybie SYMULACJI. Saldo startowe: {virtual_balance} USDT", "magenta", attrs=['bold']), flush=True)
    else:
         print(colored(f"Uruchamianie w trybie REALNYM. Upewnij się, że masz środki na koncie UNIFIED.", "green", attrs=['bold']), flush=True)

    threads = []
    for i, config in enumerate(BOT_CONFIGS):
        thread = threading.Thread(target=run_strategy, args=(config,), name=f"{config['symbol']}-Bot")
        threads.append(thread)
        thread.start()
        time.sleep(2)

    for thread in threads:
        thread.join()
