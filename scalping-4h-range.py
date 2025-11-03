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
        "risk_percentage": 0.5,     # 0.5% kapitału na transakcję
        "tp_ratio": 2.0,            # Stosunek Take Profit do Stop Loss (np. 2.0 = 1:2 R:R)
        "range_interval": "240",    # Interwał do wyznaczania zakresu (4h)
        "trade_interval": "5",      # Interwał do szukania sygnału wejścia (5 min)
        "use_break_even": True,     # Przesuń SL na cenę wejścia przy 1:1 R:R
        # ==============================================================================
        # ZMIANA: Aktywowano Twoje "Podejście Hybrydowe" (Smart SL)
        # True = Użyj bliższego SL opartego o strukturę rynku (lepsze R:R)
        # False = Użyj standardowego SL (ekstremum wybicia)
        # ==============================================================================
        "use_smart_sl": True,
        # ==============================================================================
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
            # Używamy zwykłego requestu bez podpisu dla publicznego endpointu
            response = requests.get(self.base_url + endpoint, params=params)
            response.raise_for_status()
            data = response.json()
            if data.get("retCode") == 0:
                klines = data["result"]["list"]
                klines.reverse() # Sortuj od najstarszej do najnowszej
                return klines
            return []
        except Exception as e:
            print(colored(f"Błąd pobierania klines: {e}", "red"), flush=True)
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
        if DRY_RUN: 
            print(colored(f"[{symbol}] SYMULACJA: Modyfikacja Stop Lossa na: {stop_loss}", "blue"), flush=True)
            return True # W trybie symulacji symulujemy sukces
            
        endpoint = "/v5/position/set-trading-stop"
        params = {"category": "linear", "symbol": symbol, "stopLoss": str(stop_loss)}
        print(colored(f"[{symbol}] Modyfikacja Stop Lossa na: {stop_loss}", "blue"), flush=True)
        return self._send_request("POST", endpoint, params)

    def get_instrument_info(self, symbol):
        endpoint = "/v5/market/instruments-info"
        params = {"category": "linear", "symbol": symbol}
        # Ten endpoint może być cache'owany, ale dla prostoty pobieramy go za każdym razem
        data = self._send_request("GET", endpoint, params)
        if data and data.get("retCode") == 0 and data["result"]["list"]:
            info = data["result"]["list"][0]["lotSizeFilter"]
            price_info = data["result"]["list"][0]["priceFilter"]
            return {
                "minOrderQty": float(info["minOrderQty"]), 
                "qtyStep": float(info["qtyStep"]),
                "tickSize": float(price_info["tickSize"])
            }
        print(colored(f"[{symbol}] Nie można pobrać informacji o instrumencie.", "red"), flush=True)
        return None

    def get_wallet_balance(self, coin="USDT"):
        if DRY_RUN: return 10000.0 # W trybie symulacji użyj wirtualnego salda 10,000 USDT
        
        endpoint = "/v5/account/wallet-balance"
        params = {"accountType": "UNIFIED"} # Lub "CONTRACT" jeśli używasz konta kontraktowego
        data = self._send_request("GET", endpoint, params)
        if data and data.get("result") and data["result"]["list"]:
            for c in data["result"]["list"][0]["coin"]:
                if c["coin"] == coin: return float(c["walletBalance"])
        return 0

    def place_order_with_sl_tp(self, symbol, side, qty, stop_loss, take_profit, entry_price_for_sim):
        side_colored = colored(side.upper(), "green" if side == "Buy" else "red")
        
        if DRY_RUN:
            print(colored(f"\n[{symbol}] SYMULACJA ZLECENIA {side_colored}:", "yellow", attrs=['bold']), flush=True)
            print(colored(f"  - Cena wejścia (symulowana): {entry_price_for_sim}", "yellow"), flush=True)
            print(colored(f"  - Ilość: {qty} {symbol[:-4]}", "yellow"), flush=True)
            print(colored(f"  - Stop Loss: {stop_loss}", "yellow"), flush=True)
            print(colored(f"  - Take Profit: {take_profit}", "yellow"), flush=True)
            return True # Symulujemy złożenie zlecenia

        print(colored(f"\n[{symbol}] Składanie zlecenia {side_colored}:", "yellow", attrs=['bold']), flush=True)
        print(colored(f"  - Ilość: {qty} {symbol[:-4]}", "yellow"), flush=True)
        print(colored(f"  - Stop Loss: {stop_loss}", "yellow"), flush=True)
        print(colored(f"  - Take Profit: {take_profit}", "yellow"), flush=True)
        endpoint = "/v5/order/create"
        params = {"category": "linear", "symbol": symbol, "side": side, "orderType": "Market", "qty": str(qty), "stopLoss": str(stop_loss), "takeProfit": str(take_profit)}
        return self._send_request("POST", endpoint, params)

def get_precision_from_step(step):
    """Zwraca liczbę miejsc po przecinku na podstawie kroku (np. 0.001 -> 3)"""
    if '.' in str(step):
        return len(str(step).split('.')[-1])
    return 0

def round_to_tick(value, tick_size):
    """Zaokrągla wartość do najbliższego kroku tickSize"""
    return round(value / tick_size) * tick_size

def find_smart_sl_level(klines, direction, extreme_price):
    """
    ULEPSZONA FUNKCJA: Próbuje znaleźć bliższy punkt struktury (swing high/low) dla SL.
    Skanuje więcej świec (domyślnie 40 ostatnich) dla większej niezawodności.
    """
    # ZMIANA: Skanuj 40 ostatnich świec, aby znaleźć wyraźniejszą strukturę
    relevant_klines = klines[-40:] 
    
    if direction == "DOWN": # Szukamy SL dla pozycji BUY (wybicie było w dół)
        # Szukamy lokalnego dołka (swing low), który jest POWYŻEJ absolutnego minimum (extreme_price)
        for i in range(len(relevant_klines) - 2, 0, -1):
            # [timestamp, open, high, low, close, volume, turnover]
            prev_low, curr_low, next_low = float(relevant_klines[i-1][3]), float(relevant_klines[i][3]), float(relevant_klines[i+1][3])
            # Czy to jest swing low (niższy niż sąsiedzi)?
            if curr_low < prev_low and curr_low < next_low:
                # Czy jest powyżej absolutnego minimum? (daje lepsze R:R)
                if curr_low > extreme_price:
                    print(colored(f"[INFO] Znaleziono Smart SL (Swing Low): {curr_low}", "cyan"), flush=True)
                    return curr_low
                    
    elif direction == "UP": # Szukamy SL dla pozycji SELL (wybicie było w górę)
        # Szukamy lokalnego szczytu (swing high), który jest PONIŻEJ absolutnego maksimum (extreme_price)
        for i in range(len(relevant_klines) - 2, 0, -1):
            prev_high, curr_high, next_high = float(relevant_klines[i-1][2]), float(relevant_klines[i][2]), float(relevant_klines[i+1][2])
            # Czy to jest swing high (wyższy niż sąsiedzi)?
            if curr_high > prev_high and curr_high > next_high:
                # Czy jest poniżej absolutnego maksimum? (daje lepsze R:R)
                if curr_high < extreme_price:
                    print(colored(f"[INFO] Znaleziono Smart SL (Swing High): {curr_high}", "cyan"), flush=True)
                    return curr_high
                    
    # Jeśli nie znaleziono odpowiedniej struktury, zwróć bezpieczne ekstremum
    print(colored(f"[INFO] Nie znaleziono Smart SL, używam standardowego ekstremum: {extreme_price}", "cyan"), flush=True)
    return extreme_price

def run_strategy(config):
    client = BybitClient(API_KEY, API_SECRET)
    symbol = config['symbol']
    
    if DRY_RUN:
        print(colored(f"[{symbol}] Bot uruchomiony w trybie SYMULACJI (PAPER TRADING)", "magenta", attrs=['bold']), flush=True)
    else:
        print(colored(f"[{symbol}] Bot '{symbol} Range Reversal' uruchomiony!", "green", attrs=['bold']), flush=True)
    
    # Zmienne stanu i zarządzania pozycją
    range_high, range_low, last_range_day, state = None, None, None, "AWAITING_RANGE"
    breakout_direction, breakout_extreme_price = None, None
    trade_info = {} # Przechowuje dane symulowanej lub realnej pozycji
    ny_timezone = pytz.timezone("America/New_York")
    
    instrument_rules = client.get_instrument_info(symbol)
    if not instrument_rules:
        print(colored(f"[{symbol}] KRYTYCZNY BŁĄD: Nie można pobrać zasad instrumentu. Zatrzymywanie wątku.", "red"), flush=True)
        return

    while True:
        try:
            now_utc = datetime.datetime.now(pytz.utc)
            now_ny = now_utc.astimezone(ny_timezone)
            
            # --- 1. Ustalanie Zakresu Dnia (Range) ---
            # Sprawdź, czy dzień się zmienił LUB czy zakres nie jest jeszcze ustawiony
            if now_ny.day != last_range_day and not trade_info:
                # Czekaj na pełne uformowanie się pierwszej świecy 4H (00:00 - 04:00 NY)
                if now_ny.hour < 4:
                    if state != "AWAITING_RANGE":
                        print(f"[{symbol}] Czekam na 04:00 NY, aby ustalić nowy zakres...", flush=True)
                        state = "AWAITING_RANGE"
                    time.sleep(60)
                    continue

                # Godzina 04:00+ NY, pobierz świecę 00:00
                print(f"[{symbol}] Pobieranie nowego zakresu na dzień {now_ny.strftime('%Y-%m-%d')}...", flush=True)
                start_of_ny_day_utc_ms = int(now_ny.replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)
                
                # Pobierz dokładnie jedną świecę 4H (240 min)
                range_klines = client.get_klines(symbol, config['range_interval'], limit=1, start=start_of_ny_day_utc_ms)
                
                if range_klines:
                    # [timestamp, open, high, low, close, volume, turnover]
                    range_high, range_low = float(range_klines[0][2]), float(range_klines[0][3])
                    last_range_day = now_ny.day
                    state = "AWAITING_BREAKOUT" # Gotowy do szukania wybicia
                    print(colored(f"[{symbol}] Nowy zakres ustalony: HIGH={range_high}, LOW={range_low}", "cyan"), flush=True)
                else:
                    print(colored(f"[{symbol}] Nie udało się pobrać świecy zakresu. Spróbuję ponownie za 60s.", "red"), flush=True)
                    time.sleep(60)
                    continue
            
            # --- 2. Zarządzanie Otwartą Pozycją (Realną lub Symulowaną) ---
            if not DRY_RUN: # Logika dla realnego handlu
                position_data = client.get_position_info(symbol)
                if not position_data and trade_info: # Jeśli pozycja została zamknięta (przez SL/TP)
                    print(colored(f"[{symbol}] Realna pozycja została zamknięta. Czekam na nowy sygnał.", "green"), flush=True)
                    trade_info = {}
                    state = "AWAITING_BREAKOUT"
                elif position_data and not trade_info: # Jeśli bot został zrestartowany i wykrył pozycję
                    print(colored(f"[{symbol}] Wykryto istniejącą pozycję po restarcie. Bot przejmuje zarządzanie.", "blue"), flush=True)
                    # Ustawiamy flagę BE na True, aby uniknąć modyfikacji SL, jeśli nie znamy pierwotnego planu
                    trade_info = {"side": position_data["side"], "entry_price": position_data["entry_price"], "sl_moved_to_be": True}

            if trade_info:
                current_price = client.get_current_price(symbol)
                if not current_price:
                    time.sleep(5)
                    continue

                # --- 2a. Logika symulacji SL/TP (tylko w DRY_RUN) ---
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
                        print(colored(f"[{symbol}] SYMULACJA: Koniec transakcji. Czekam na nowy sygnał.", "yellow"), flush=True)
                        continue

                # --- 2b. Logika Break-Even (działa w obu trybach) ---
                if config['use_break_even'] and not trade_info.get("sl_moved_to_be"):
                    side, be_target, entry_price = trade_info["side"], trade_info["be_target"], trade_info["entry_price"]
                    
                    if (side == "Buy" and current_price >= be_target) or (side == "Sell" and current_price <= be_target):
                        # Przesuń SL (realnie lub symulacyjnie)
                        client.modify_position_sl(symbol, entry_price) 
                        
                        trade_info["sl_moved_to_be"] = True
                        if DRY_RUN: # W trybie symulacji musimy zaktualizować SL
                            trade_info["stop_loss"] = entry_price
                        print(colored(f"[{symbol}] Osiągnięto cel 1R. SL przesunięty na Break-Even ({entry_price}).", "cyan"), flush=True)
                
                time.sleep(5) # W trybie pozycji sprawdzamy cenę częściej
                continue

            # --- 3. Skanowanie w Poszukiwaniu Sygnału (jeśli nie ma pozycji) ---
            if state in ["AWAITING_BREAKOUT", "AWAITING_REENTRY"]:
                # ZMIANA: Pobierz więcej świec dla funkcji Smart SL
                klines_trade = client.get_klines(symbol, config['trade_interval'], limit=50) 
                
                if len(klines_trade) < 20: # Wymagaj minimum 20 świec, aby uniknąć błędów
                    print(f"[{symbol}] Zbieram dane świec...", flush=True)
                    time.sleep(10)
                    continue

                last_closed_candle = klines_trade[-2] # Analizuj tylko zamknięte świece
                candle_high, candle_low, candle_close = float(last_closed_candle[2]), float(last_closed_candle[3]), float(last_closed_candle[4])
                
                # --- 3a. Czekanie na wybicie z zakresu ---
                if state == "AWAITING_BREAKOUT":
                    if candle_close > range_high:
                        print(f"[{symbol}] Wykryto wybicie GÓRĄ. Czekam na powrót do zakresu.", flush=True)
                        state, breakout_direction, breakout_extreme_price = "AWAITING_REENTRY", "UP", candle_high
                    elif candle_close < range_low:
                        print(f"[{symbol}] Wykryto wybicie DOŁEM. Czekam na powrót do zakresu.", flush=True)
                        state, breakout_direction, breakout_extreme_price = "AWAITING_REENTRY", "DOWN", candle_low
                
                # --- 3b. Czekanie na powrót do zakresu (sygnał wejścia) ---
                elif state == "AWAITING_REENTRY":
                    # Aktualizuj ekstremum ceny podczas wybicia
                    if breakout_direction == "UP" and candle_high > breakout_extreme_price:
                        breakout_extreme_price = candle_high
                    elif breakout_direction == "DOWN" and candle_low < breakout_extreme_price:
                        breakout_extreme_price = candle_low

                    # Sprawdź sygnał wejścia (powrót do zakresu)
                    if (breakout_direction == "UP" and candle_close < range_high) or (breakout_direction == "DOWN" and candle_close > range_low):
                        
                        side = "Sell" if breakout_direction == "UP" else "Buy"
                        entry_price = candle_close # Cena wejścia (symulowana, realna będzie rynkowa)
                        
                        # === LOGIKA USTALANIA STOP LOSSA (Standard vs Smart) ===
                        stop_loss_standard = breakout_extreme_price
                        
                        if config['use_smart_sl']:
                            # To jest Twoje "podejście hybrydowe"
                            stop_loss = find_smart_sl_level(klines_trade, breakout_direction, stop_loss_standard)
                        else:
                            stop_loss = stop_loss_standard
                        # ======================================================

                        # Zaokrąglij SL i TP do precyzji instrumentu
                        tick_size = instrument_rules['tickSize']
                        stop_loss = round_to_tick(stop_loss, tick_size)
                        
                        stop_loss_distance_points = abs(entry_price - stop_loss)
                        if stop_loss_distance_points == 0:
                            print(colored(f"[{symbol}] Błąd: Dystans SL = 0. Anulowanie wejścia.", "red"), flush=True)
                            state = "AWAITING_BREAKOUT"
                            continue
                            
                        tp_distance = stop_loss_distance_points * config['tp_ratio']
                        take_profit = entry_price - tp_distance if side == "Sell" else entry_price + tp_distance
                        take_profit = round_to_tick(take_profit, tick_size)

                        # Obliczanie wielkości pozycji
                        balance = client.get_wallet_balance()
                        risk_amount_usd = balance * (config['risk_percentage'] / 100)
                        
                        qty_by_risk = risk_amount_usd / stop_loss_distance_points
                        
                        # Sprawdź maksymalną ilość dozwoloną przez dźwignię i saldo
                        leverage = float(config['leverage'])
                        max_qty_by_balance = (balance * leverage * 0.95) / entry_price # 0.95 jako bufor bezpieczeństwa
                        
                        final_qty = min(qty_by_risk, max_qty_by_balance)
                        
                        # Dostosuj do zasad instrumentu (qtyStep)
                        qty_step = instrument_rules['qtyStep']
                        adjusted_qty = math.floor(final_qty / qty_step) * qty_step
                        
                        if adjusted_qty >= instrument_rules['minOrderQty']:
                            final_qty_str = f"{adjusted_qty:.{get_precision_from_step(qty_step)}f}"
                            
                            # Złóż zlecenie (realne lub symulowane)
                            if client.place_order_with_sl_tp(symbol, side, final_qty_str, stop_loss, take_profit, entry_price):
                                
                                # Cel dla Break-Even (1R)
                                be_target = entry_price + stop_loss_distance_points if side == "Buy" else entry_price - stop_loss_distance_points
                                be_target = round_to_tick(be_target, tick_size)
                                
                                # Zapisz informacje o transakcji (kluczowe dla trybu DRY_RUN)
                                trade_info = {
                                    "side": side, 
                                    "entry_price": entry_price, 
                                    "stop_loss": stop_loss, 
                                    "take_profit": take_profit, 
                                    "quantity": adjusted_qty, 
                                    "be_target": be_target, 
                                    "sl_moved_to_be": False
                                }
                                state = "IN_POSITION" # Zmień stan, aby bot przeszedł w tryb zarządzania pozycją
                            else:
                                print(colored(f"[{symbol}] Nie udało się złożyć zlecenia. Spróbuję ponownie.", "red"), flush=True)
                                state = "AWAITING_BREAKOUT" # Zresetuj stan, jeśli zlecenie się nie udało
                        else:
                            print(colored(f"[{symbol}] Obliczona ilość ({adjusted_qty}) jest mniejsza niż minimalna ({instrument_rules['minOrderQty']}). Anulowanie wejścia.", "yellow"), flush=True)
                            state = "AWAITING_BREAKOUT"

            # Spowalnia pętlę, gdy nie ma sygnału ani pozycji
            if not trade_info:
                time.sleep(10)

        except Exception as e:
            print(colored(f"\n[{symbol}] KRYTYCZNY BŁĄD w głównej pętli: {e}", "red", attrs=['bold']), flush=True)
            print("Traceback:", flush=True)
            import traceback
            traceback.print_exc()
            time.sleep(60)

if __name__ == "__main__":
    if "Twoj key" in API_KEY:
        print(colored("OSTRZEŻENIE: Używasz przykładowych kluczy API. Bot będzie działał w trybie DRY_RUN.", "magenta"), flush=True)
        print(colored("Jeśli chcesz handlować realnie, wstaw swoje klucze API i ustaw DRY_RUN = False", "magenta"), flush=True)
        DRY_RUN = True # Wymuś DRY_RUN, jeśli klucze są domyślne
    elif "TWOJ_API_KEY" in API_KEY or "TWOJ_API_SECRET" in API_SECRET:
         print(colored("BŁĄD: Proszę ustawić prawdziwe wartości API_KEY i API_SECRET w pliku!", "red"), flush=True)
    else:
        for config in BOT_CONFIGS:
            thread = threading.Thread(target=run_strategy, args=(config,))
            thread.start()
            time.sleep(2) # Odstęp między uruchamianiem wątków
