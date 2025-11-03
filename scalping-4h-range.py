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
        "leverage": "10",           # Dźwignia (używana jako limit max. pozycji)
        "risk_percentage": 0.5,     # Ryzyko na transakcję (np. 1.0 = 1% kapitału)
        "tp_ratio": 2.0,            # Stosunek Take Profit do Stop Loss (np. 2.0 = 1:2 R:R)
        "range_interval": "240",    # Interwał do wyznaczania zakresu (4h)
        "trade_interval": "5",      # Interwał do szukania sygnału wejścia (5 min)
        
        # --- USTAWIENIA ZARZĄDZANIA POZYCJĄ ---
        
        # Przesuń SL na cenę wejścia (Break-Even) po osiągnięciu 1R
        "use_break_even": True,     
        
        # Użyj "hybrydowego" SL opartego o strukturę rynku (lepsze R:R)
        "use_smart_sl": True,
    },
    # Możesz dodać tu inne pary, np. ETHUSDT, z tymi samymi ustawieniami
    # {
    #     "symbol": "ETHUSDT",
    #     "leverage": "10",
    #     "risk_percentage": 1.0,
    #     "tp_ratio": 2.0,
    #     "range_interval": "240",
    #     "trade_interval": "5",
    #     "use_break_even": True,
    #     "use_smart_sl": True,
    # },
]
# ==============================================================================

class BybitClient:
    """
    Klient API Bybit v5 do obsługi zleceń i danych rynkowych.
    """
    def __init__(self, api_key, api_secret):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = BASE_URL
        self.session = requests.Session()

    def _send_request(self, method, endpoint, params=None):
        """Wysyła podpisane żądanie do API."""
        url = self.base_url + endpoint
        timestamp = str(int(time.time() * 1000))
        recv_window = "10000"
        if params is None: params = {}

        if method == "POST":
            # Prawidłowe formatowanie JSON dla POST
            payload_str = json.dumps(params, separators=(',', ':'))
        else:
            # Prawidłowe formatowanie dla GET
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
                
            response.raise_for_status() # Zgłoś błąd HTTP
            data = response.json()
            
            if data.get("retCode") != 0:
                print(colored(f"Błąd API Bybit ({endpoint}): {data.get('retMsg')} (retCode: {data.get('retCode')})", "red"), flush=True)
                return None
            return data
        except requests.exceptions.RequestException as e:
            print(colored(f"Błąd połączenia: {e}", "red"), flush=True)
            return None
        except Exception as e:
            print(colored(f"Błąd przetwarzania żądania: {e}", "red"), flush=True)
            return None

    def get_klines(self, symbol, interval, limit=200, start=None):
        """Pobiera dane Klines (świece) z publicznego endpointu."""
        endpoint = "/v5/market/kline"
        params = {"category": "linear", "symbol": symbol, "interval": interval, "limit": limit}
        if start: params['start'] = start
        
        try:
            # Używamy zwykłego requestu (bez podpisu) dla publicznych danych
            response = requests.get(self.base_url + endpoint, params=params)
            response.raise_for_status()
            data = response.json()
            if data.get("retCode") == 0 and data.get("result", {}).get("list"):
                klines = data["result"]["list"]
                klines.reverse() # Sortuj od najstarszej do najnowszej
                return klines
            else:
                print(colored(f"Błąd pobierania klines (retCode!=0): {data.get('retMsg')}", "red"), flush=True)
                return []
        except Exception as e:
            print(colored(f"Krytyczny błąd pobierania klines: {e}", "red"), flush=True)
            return []
            
    def get_current_price(self, symbol):
        """Pobiera ostatnią cenę dla symbolu."""
        endpoint = "/v5/market/tickers"
        params = {"category": "linear", "symbol": symbol}
        try:
            response = requests.get(self.base_url + endpoint, params=params)
            response.raise_for_status()
            data = response.json()
            if data.get("retCode") == 0 and data.get("result", {}).get("list"):
                return float(data["result"]["list"][0]["lastPrice"])
        except Exception:
            return None # Cichy błąd, bot spróbuje ponownie
        return None

    def get_position_info(self, symbol):
        """Pobiera informacje o otwartej pozycji."""
        if DRY_RUN: return None # W trybie symulacji nie ma realnych pozycji
        
        endpoint = "/v5/position/list"
        params = {"category": "linear", "symbol": symbol}
        data = self._send_request("GET", endpoint, params)
        
        if data and data.get("result", {}).get("list"):
            for pos in data["result"]["list"]:
                # Sprawdź, czy pozycja faktycznie istnieje (rozmiar > 0)
                if pos['symbol'] == symbol and float(pos.get("size", 0)) > 0:
                    return {
                        "size": float(pos["size"]), 
                        "entry_price": float(pos["avgPrice"]), 
                        "side": pos["side"]
                    }
        return None
        
    def modify_position_sl(self, symbol, stop_loss):
        """Modyfikuje Stop Loss dla otwartej pozycji (na potrzeby Break-Even)."""
        if DRY_RUN: 
            # W trybie symulacji tylko logujemy
            print(colored(f"[{symbol}] SYMULACJA: Modyfikacja Stop Lossa na: {stop_loss}", "blue"), flush=True)
            return True # Symulujemy sukces
            
        endpoint = "/v5/position/set-trading-stop"
        params = {
            "category": "linear", 
            "symbol": symbol, 
            "stopLoss": str(stop_loss)
        }
        print(colored(f"[{symbol}] MODYFIKACJA SL: Ustawianie Stop Lossa na: {stop_loss}", "blue"), flush=True)
        data = self._send_request("POST", endpoint, params)
        return data is not None

    def get_instrument_info(self, symbol):
        """Pobiera zasady handlowe dla instrumentu (precyzja, min. ilość)."""
        endpoint = "/v5/market/instruments-info"
        params = {"category": "linear", "symbol": symbol}
        
        # Używamy _send_request, bo to kluczowe dane
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
        """Pobiera saldo portfela."""
        if DRY_RUN: 
            # W trybie symulacji użyj wirtualnego salda 1000 USDT (lub ile chcesz)
            # Można też użyć salda startowego z symulacji
            global virtual_balance
            return virtual_balance
        
        endpoint = "/v5/account/wallet-balance"
        params = {"accountType": "UNIFIED"} # Lub "CONTRACT", jeśli nie masz konta UTA
        data = self._send_request("GET", endpoint, params)
        
        if data and data.get("result") and data["result"].get("list"):
            # Sprawdź, czy lista nie jest pusta
            if not data["result"]["list"]:
                print(colored("Nie można pobrać salda (pusta lista).", "red"), flush=True)
                return 0

            # Przejdź przez wszystkie coiny na koncie
            for c in data["result"]["list"][0]["coin"]:
                if c["coin"] == coin: 
                    return float(c["walletBalance"])
        
        print(colored(f"Nie znaleziono salda dla {coin}. Zwracam 0.", "yellow"), flush=True)
        return 0

    def place_order_with_sl_tp(self, symbol, side, qty, stop_loss, take_profit, entry_price_for_sim):
        """Składa zlecenie rynkowe wraz z SL i TP."""
        side_colored = colored(side.upper(), "green" if side == "Buy" else "red")
        
        if DRY_RUN:
            print(colored(f"\n[{symbol}] SYMULACJA ZLECENIA {side_colored}:", "yellow", attrs=['bold']), flush=True)
            print(colored(f"  - Cena wejścia (symulowana): {entry_price_for_sim}", "yellow"), flush=True)
            print(colored(f"  - Ilość: {qty} {symbol[:-4]}", "yellow"), flush=True)
            print(colored(f"  - Stop Loss: {stop_loss}", "yellow"), flush=True)
            print(colored(f"  - Take Profit: {take_profit}", "yellow"), flush=True)
            return True # Symulujemy złożenie zlecenia

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
            "tpslMode": "Full" # Upewnij się, że SL/TP dotyczy całej pozycji
        }
        data = self._send_request("POST", endpoint, params)
        return data is not None

# --- Funkcje Pomocnicze ---

def get_precision_from_step(step):
    """Zwraca liczbę miejsc po przecinku na podstawie kroku (np. 0.001 -> 3)"""
    step_str = f"{step:.10f}" # Konwertuj na string z dużą precyzją
    if '.' in step_str:
        return len(step_str.split('.')[-1].rstrip('0'))
    return 0

def round_to_tick(value, tick_size):
    """Zaokrągla wartość do najbliższego kroku tickSize (dla cen)."""
    return round(value / tick_size) * tick_size

# --- Logika Strategii ---

virtual_balance = 180.0 # Saldo startowe dla trybu DRY_RUN

def find_smart_sl_level(klines_5min, direction, extreme_price):
    """
    ULEPSZONA FUNKCJA: Próbuje znaleźć bliższy punkt struktury (swing high/low) dla SL.
    Skanuje 40 ostatnich świec 5-minutowych.
    """
    relevant_klines = klines_5min[-40:] # Skanuj 40 ostatnich świec 5m
    
    if direction == "DOWN": # Szukamy SL dla pozycji BUY (wybicie było w dół)
        # Szukamy lokalnego dołka (swing low), który jest POWYŻEJ absolutnego minimum (extreme_price)
        for i in range(len(relevant_klines) - 2, 0, -1):
            # [timestamp, open, high, low, close, volume, turnover]
            prev_low, curr_low, next_low = float(relevant_klines[i-1][3]), float(relevant_klines[i][3]), float(relevant_klines[i+1][3])
            
            # Czy to jest swing low (niższy niż sąsiedzi)?
            if curr_low < prev_low and curr_low < next_low:
                # Czy jest powyżej absolutnego minimum? (daje lepsze R:R)
                if curr_low > extreme_price:
                    print(colored(f"[{threading.current_thread().name}] Znaleziono Smart SL (Swing Low): {curr_low}", "cyan"), flush=True)
                    return curr_low
                    
    elif direction == "UP": # Szukamy SL dla pozycji SELL (wybicie było w górę)
        # Szukamy lokalnego szczytu (swing high), który jest PONIŻEJ absolutnego maksimum (extreme_price)
        for i in range(len(relevant_klines) - 2, 0, -1):
            prev_high, curr_high, next_high = float(relevant_klines[i-1][2]), float(relevant_klines[i][2]), float(relevant_klines[i+1][2])
            
            # Czy to jest swing high (wyższy niż sąsiedzi)?
            if curr_high > prev_high and curr_high > next_high:
                # Czy jest poniżej absolutnego maksimum? (daje lepsze R:R)
                if curr_high < extreme_price:
                    print(colored(f"[{threading.current_thread().name}] Znaleziono Smart SL (Swing High): {curr_high}", "cyan"), flush=True)
                    return curr_high
                    
    # Jeśli nie znaleziono odpowiedniej struktury, zwróć bezpieczne ekstremum
    print(colored(f"[{threading.current_thread().name}] Nie znaleziono Smart SL, używam standardowego ekstremum: {extreme_price}", "cyan"), flush=True)
    return extreme_price

def run_strategy(config):
    """
    Główna pętla bota dla pojedynczej pary walutowej.
    """
    global virtual_balance # Użyj globalnego salda dla DRY_RUN
    
    client = BybitClient(API_KEY, API_SECRET)
    symbol = config['symbol']
    thread_name = threading.current_thread().name
    
    if DRY_RUN:
        print(colored(f"[{thread_name}] Bot uruchomiony w trybie SYMULACJI (PAPER TRADING)", "magenta", attrs=['bold']), flush=True)
    else:
        print(colored(f"[{thread_name}] Bot '{symbol} Range Reversal' uruchomiony!", "green", attrs=['bold']), flush=True)
    
    # Zmienne stanu i zarządzania pozycją
    range_high, range_low, last_range_day, state = None, None, None, "AWAITING_RANGE"
    breakout_direction, breakout_extreme_price = None, None
    trade_info = {} # Przechowuje dane symulowanej lub realnej pozycji
    
    # Kluczowe: Ustawienie strefy czasowej Nowego Jorku
    try:
        ny_timezone = pytz.timezone("America/New_York")
    except pytz.UnknownTimeZoneError:
        print(colored("BŁĄD: Nie można załadować strefy czasowej 'America/New_York'. Upewnij się, że biblioteka pytz jest zainstalowana.", "red"), flush=True)
        return

    instrument_rules = client.get_instrument_info(symbol)
    if not instrument_rules:
        print(colored(f"[{thread_name}] KRYTYCZNY BŁĄD: Nie można pobrać zasad instrumentu. Zatrzymywanie wątku.", "red"), flush=True)
        return
    
    print(f"[{thread_name}] Zasady instrumentu: tickSize={instrument_rules['tickSize']}, qtyStep={instrument_rules['qtyStep']}", flush=True)

    while True:
        try:
            # Zawsze pobieraj aktualny czas UTC
            now_utc = datetime.datetime.now(pytz.utc)
            # Konwertuj na czas nowojorski
            now_ny = now_utc.astimezone(ny_timezone)
            
            # --- 1. Ustalanie Zakresu Dnia (Range) ---
            # Sprawdź, czy dzień się zmienił LUB czy zakres nie jest jeszcze ustawiony
            # ORAZ czy nie jesteśmy w trakcie transakcji
            if (now_ny.day != last_range_day or range_high is None) and not trade_info:
                
                # Czekaj na pełne uformowanie się pierwszej świecy 4H (00:00 - 04:00 NY)
                if now_ny.hour < 4:
                    if state != "AWAITING_RANGE":
                        print(f"[{thread_name}] Czekam na 04:00 NY, aby ustalić nowy zakres... (teraz: {now_ny.strftime('%H:%M')})", flush=True)
                        state = "AWAITING_RANGE"
                    time.sleep(60)
                    continue

                # Godzina 04:00+ NY, pobierz świecę 00:00
                print(f"[{thread_name}] Pobieranie nowego zakresu na dzień {now_ny.strftime('%Y-%m-%d')}...", flush=True)
                
                # Oblicz dokładny czas startu świecy 00:00 NYT w milisekundach UTC
                start_of_ny_day = now_ny.replace(hour=0, minute=0, second=0, microsecond=0)
                start_of_ny_day_utc_ms = int(start_of_ny_day.timestamp() * 1000)
                
                # Pobierz dokładnie jedną świecę 4H (240 min)
                range_klines = client.get_klines(symbol, config['range_interval'], limit=1, start=start_of_ny_day_utc_ms)
                
                if range_klines:
                    # [timestamp, open, high, low, close, volume, turnover]
                    range_high, range_low = float(range_klines[0][2]), float(range_klines[0][3])
                    last_range_day = now_ny.day
                    state = "AWAITING_BREAKOUT" # Gotowy do szukania wybicia
                    print(colored(f"[{thread_name}] Nowy zakres ustalony: HIGH={range_high}, LOW={range_low}", "cyan"), flush=True)
                else:
                    print(colored(f"[{thread_name}] Nie udało się pobrać świecy zakresu. Spróbuję ponownie za 60s.", "red"), flush=True)
                    time.sleep(60)
                    continue
            
            # --- 2. Zarządzanie Otwartą Pozycją (Realną lub Symulowaną) ---
            
            # Logika dla realnego handlu (sprawdzanie, czy pozycja została zamknięta)
            if not DRY_RUN: 
                # Jeśli bot myśli, że jest w pozycji...
                if trade_info:
                    position_data = client.get_position_info(symbol)
                    # ...a giełda mówi, że pozycji nie ma (bo SL/TP ją zamknął)
                    if not position_data:
                        print(colored(f"[{thread_name}] Realna pozycja została zamknięta (SL/TP). Czekam na nowy sygnał.", "green"), flush=True)
                        trade_info = {}
                        state = "AWAITING_BREAKOUT"
                # Jeśli bot myśli, że nie ma pozycji...
                else:
                    position_data = client.get_position_info(symbol)
                    # ...a giełda mówi, że pozycja jest (np. po restarcie bota)
                    if position_data:
                        print(colored(f"[{thread_name}] Wykryto istniejącą pozycję po restarcie. Bot przejmuje zarządzanie (tylko BE).", "blue"), flush=True)
                        trade_info = {
                            "side": position_data["side"], 
                            "entry_price": position_data["entry_price"], 
                            "sl_moved_to_be": True # Ustaw na True, aby bot nie próbował ustawić BE
                        }
                        state = "IN_POSITION"


            # Główna pętla zarządzania pozycją (DRY_RUN i REAL)
            if trade_info:
                if state != "IN_POSITION": state = "IN_POSITION"
                
                current_price = client.get_current_price(symbol)
                if not current_price:
                    time.sleep(5) # Szybsze sprawdzanie, gdy cena jest niedostępna
                    continue

                # --- 2a. Logika symulacji SL/TP (tylko w DRY_RUN) ---
                if DRY_RUN:
                    is_closed = False
                    result_R = 0
                    
                    if trade_info["side"] == "Buy":
                        if current_price <= trade_info["stop_loss"]:
                            is_closed = True
                            result_R = (trade_info["stop_loss"] - trade_info["entry_price"]) / (trade_info["entry_price"] - trade_info["initial_sl"])
                            print(colored(f"[{thread_name}] SYMULACJA: Stop Loss trafiony.", "red"), flush=True)
                        elif current_price >= trade_info["take_profit"]:
                            is_closed = True
                            result_R = config['tp_ratio']
                            print(colored(f"[{thread_name}] SYMULACJA: Take Profit zrealizowany.", "green"), flush=True)
                            
                    elif trade_info["side"] == "Sell":
                        if current_price >= trade_info["stop_loss"]:
                            is_closed = True
                            result_R = (trade_info["entry_price"] - trade_info["stop_loss"]) / (trade_info["initial_sl"] - trade_info["entry_price"])
                            print(colored(f"[{thread_name}] SYMULACJA: Stop Loss trafiony.", "red"), flush=True)
                        elif current_price <= trade_info["take_profit"]:
                            is_closed = True
                            result_R = config['tp_ratio']
                            print(colored(f"[{thread_name}] SYMULACJA: Take Profit zrealizowany.", "green"), flush=True)
                    
                    if is_closed:
                        # Aktualizuj wirtualne saldo
                        risk_amount_usd = virtual_balance * (config['risk_percentage'] / 100)
                        profit_usd = risk_amount_usd * result_R
                        virtual_balance += profit_usd
                        
                        print(colored(f"[{thread_name}] SYMULACJA: Wynik transakcji: {result_R:.2f}R ({profit_usd:+.2f} USDT)", "yellow"), flush=True)
                        print(colored(f"[{thread_name}] SYMULACJA: Nowe saldo: {virtual_balance:.2f} USDT", "yellow"), flush=True)
                        
                        trade_info = {}
                        state = "AWAITING_BREAKOUT"
                        continue

                # --- 2b. Logika Break-Even (działa w obu trybach) ---
                if config['use_break_even'] and not trade_info.get("sl_moved_to_be"):
                    side = trade_info["side"]
                    be_target = trade_info["be_target"]
                    entry_price = trade_info["entry_price"]
                    
                    if (side == "Buy" and current_price >= be_target) or (side == "Sell" and current_price <= be_target):
                        
                        # Przesuń SL (realnie lub symulacyjnie)
                        if client.modify_position_sl(symbol, entry_price): 
                            trade_info["sl_moved_to_be"] = True
                            if DRY_RUN: # W trybie symulacji musimy zaktualizować SL
                                trade_info["stop_loss"] = entry_price
                            print(colored(f"[{thread_name}] OSIĄGNIĘTO 1R: SL przesunięty na Break-Even ({entry_price}).", "cyan"), flush=True)
                        else:
                            print(colored(f"[{thread_name}] BŁĄD: Nie udało się przesunąć SL na Break-Even.", "red"), flush=True)
                
                time.sleep(5) # W trybie pozycji sprawdzamy cenę częściej
                continue

            # --- 3. Skanowanie w Poszukiwaniu Sygnału (jeśli nie ma pozycji i jest zakres) ---
            if state in ["AWAITING_BREAKOUT", "AWAITING_REENTRY"]:
                if range_high is None or range_low is None:
                    time.sleep(10) # Czekaj, jeśli zakres jeszcze nieustalony
                    continue
                    
                # Pobierz 50 ostatnich świec 5-minutowych dla analizy Smart SL
                klines_trade = client.get_klines(symbol, config['trade_interval'], limit=50) 
                
                if len(klines_trade) < 20: # Wymagaj minimum 20 świec
                    print(f"[{thread_name}] Zbieram dane świec 5m...", flush=True)
                    time.sleep(10)
                    continue

                last_closed_candle = klines_trade[-2] # Analizuj tylko zamknięte świece
                candle_high, candle_low, candle_close = float(last_closed_candle[2]), float(last_closed_candle[3]), float(last_closed_candle[4])
                
                # --- 3a. Czekanie na wybicie z zakresu ---
                if state == "AWAITING_BREAKOUT":
                    if candle_close > range_high:
                        print(f"[{thread_name}] Wykryto wybicie GÓRĄ. Czekam na powrót do zakresu.", flush=True)
                        state, breakout_direction, breakout_extreme_price = "AWAITING_REENTRY", "UP", candle_high
                    elif candle_close < range_low:
                        print(f"[{thread_name}] Wykryto wybicie DOŁEM. Czekam na powrót do zakresu.", flush=True)
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
                        # Dla DRY_RUN używamy ceny zamknięcia jako wejścia
                        # Dla REAL, giełda weźmie cenę rynkową
                        entry_price = candle_close 
                        
                        # === LOGIKA USTALANIA STOP LOSSA (Standard vs Smart) ===
                        stop_loss_standard = breakout_extreme_price
                        
                        if config['use_smart_sl']:
                            # To jest Twoje "podejście hybrydowe"
                            stop_loss = find_smart_sl_level(klines_trade, breakout_direction, stop_loss_standard)
                        else:
                            stop_loss = stop_loss_standard
                        # ======================================================

                        # Pobierz zasady precyzji
                        tick_size = instrument_rules['tickSize']
                        qty_step = instrument_rules['qtyStep']
                        
                        # Zaokrąglij SL
                        stop_loss = round_to_tick(stop_loss, tick_size)
                        
                        # Zabezpieczenie przed handlem w złą stronę (SL musi być za ceną wejścia)
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

                        # Obliczanie wielkości pozycji
                        balance = client.get_wallet_balance()
                        if balance <= 0:
                            print(colored(f"[{thread_name}] Brak środków na koncie (Saldo: {balance}). Czekam.", "red"), flush=True)
                            time.sleep(300) # Czekaj 5 minut
                            continue

                        risk_amount_usd = balance * (config['risk_percentage'] / 100)
                        
                        qty_by_risk = risk_amount_usd / stop_loss_distance_points
                        
                        # Sprawdź maksymalną ilość dozwoloną przez dźwignię i saldo
                        leverage = float(config['leverage'])
                        max_qty_by_balance = (balance * leverage * 0.95) / entry_price # 0.95 jako bufor bezpieczeństwa
                        
                        final_qty = min(qty_by_risk, max_qty_by_balance)
                        
                        # Dostosuj do zasad instrumentu (qtyStep)
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
                                    "entry_price": entry_price, # Symulowana cena wejścia
                                    "stop_loss": stop_loss,     # Aktualny SL (zmieni się na BE)
                                    "initial_sl": stop_loss,    # Oryginalny SL (do obliczeń R)
                                    "take_profit": take_profit, 
                                    "quantity": adjusted_qty, 
                                    "be_target": be_target, 
                                    "sl_moved_to_be": False
                                }
                                state = "IN_POSITION" # Zmień stan
                            else:
                                print(colored(f"[{thread_name}] Nie udało się złożyć zlecenia (Błąd API?). Resetowanie.", "red"), flush=True)
                                state = "AWAITING_BREAKOUT" # Zresetuj stan
                        else:
                            print(colored(f"[{thread_name}] Obliczona ilość ({adjusted_qty}) jest mniejsza niż minimalna ({instrument_rules['minOrderQty']}). Anulowanie wejścia.", "yellow"), flush=True)
                            state = "AWAITING_BREAKOUT"

            # Spowalnia pętlę, gdy nie ma sygnału ani pozycji
            if not trade_info:
                # Czekaj 10 sekund, jeśli czekamy na sygnał
                if state in ["AWAITING_BREAKOUT", "AWAITING_REENTRY"]:
                    time.sleep(10)
                else:
                    # Czekaj dłużej, jeśli czekamy na zakres
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
        DRY_RUN = True # Wymuś DRY_RUN, jeśli klucze są domyślne
    
    if DRY_RUN:
        print(colored(f"Uruchamianie w trybie SYMULACJI. Saldo startowe: {virtual_balance} USDT", "magenta", attrs=['bold']), flush=True)
    else:
         print(colored(f"Uruchamianie w trybie REALNYM. Upewnij się, że masz środki na koncie UNIFIED.", "green", attrs=['bold']), flush=True)

    threads = []
    for i, config in enumerate(BOT_CONFIGS):
        thread = threading.Thread(target=run_strategy, args=(config,), name=f"{config['symbol']}-Bot")
        threads.append(thread)
        thread.start()
        time.sleep(2) # Odstęp 2 sekundy między uruchamianiem wątków (limit API)

    for thread in threads:
        thread.join()
