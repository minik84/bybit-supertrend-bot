import time
import hmac
import hashlib
import requests
import json
import datetime
import threading
import math # Dodajemy bibliotekę math do obsługi zaokrągleń w dół
from termcolor import colored

# === KONFIGURACJA ===
API_KEY = "7wNz85HfTWLEwYSNvq"  # Wstaw swój klucz
API_SECRET = "vxUMPh2UrzWb9uMRei1uZauXEeQaNFmzWP6A" # Wstaw swój secret
BASE_URL = "https://api.bybit.com"
LEVERAGE = "10" # Dźwignia pozostaje jako globalne ustawienie

# ==============================================================================
# === KONFIGURACJA BOTÓW ===
# ==============================================================================
BOT_CONFIGS = [
    {
        "symbol": "WIFUSDT",
        "interval": "1", # ZMIANA: Ustawienie interwału na 1 minutę
        "atr_period": 10,
        "factor": 4.0, # To jest Twój "ATR Multiplier"
        "risk_percentage": 1 # ZMIANA: Ustawienie ryzyka na 1%
    }
]
# ==============================================================================

# === KLASA DO OBSŁUGI API BYBIT ===
class BybitClient:
    def __init__(self, api_key, api_secret):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = BASE_URL
        self.session = requests.Session()

    def _send_request(self, method, endpoint, params=None):
        url = self.base_url + endpoint
        timestamp = str(int(time.time() * 1000))
        recv_window = "5000"
        if params is None: params = {}

        if method == "POST":
            payload_str = json.dumps(params, separators=(',', ':'))
        else:
            # Parametry dla GET muszą być posortowane alfabetycznie dla sygnatury
            sorted_params = sorted(params.items())
            payload_str = "&".join([f"{k}={v}" for k, v in sorted_params])

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
                del headers['Content-Type'] # Usuwamy Content-Type dla żądań GET
                # Przekazujemy 'params' jako słownik do 'requests.get'
                response = self.session.get(url, headers=headers, params=params) 
            
            response.raise_for_status()
            data = response.json()

            # Obsługa błędów Bybit (retCode != 0)
            if data.get("retCode") != 0 and data.get("retCode") not in [110025, 110043]:
                print(colored(f"Błąd API Bybit: {data.get('retMsg')} (retCode: {data.get('retCode')})", "red"), flush=True)
                return None
            return data
        except requests.exceptions.HTTPError as http_err:
            if http_err.response.status_code == 403:
                print(colored(f"KRYTYCZNY BŁĄD 403 (Forbidden): Sprawdź uprawnienia klucza API i brak restrykcji IP. {http_err}", "red", attrs=['bold']), flush=True)
            else:
                print(colored(f"Błąd HTTP: {http_err}", "red"), flush=True)
            return None
        except Exception as e:
            print(colored(f"Błąd połączenia: {e}", "red"), flush=True)
            return None

    # ZMIANA: Używa _send_request (podpisane żądanie)
    def get_klines(self, symbol, interval, limit=200):
        endpoint = "/v5/market/kline"
        params = {"category": "linear", "symbol": symbol, "interval": interval, "limit": limit}
        
        data = self._send_request("GET", endpoint, params)
        if data and data.get("retCode") == 0:
            return data["result"]["list"]
        
        if data:
            print(colored(f"Błąd pobierania klines (retCode: {data.get('retCode')}, retMsg: {data.get('retMsg')})", "red"), flush=True)
        return []
            
    # ZMIANA: Używa _send_request (podpisane żądanie)
    def get_instrument_info(self, symbol):
        endpoint = "/v5/market/instruments-info"
        params = {"category": "linear", "symbol": symbol}
        
        data = self._send_request("GET", endpoint, params)
        if data and data.get("retCode") == 0 and data["result"]["list"]:
            info = data["result"]["list"][0]
            return {
                "minOrderQty": float(info["lotSizeFilter"]["minOrderQty"]),
                "qtyStep": float(info["lotSizeFilter"]["qtyStep"])
            }
        
        if data:
            print(colored(f"Błąd pobierania informacji o instrumencie (retCode: {data.get('retCode')}, retMsg: {data.get('retMsg')})", "red"), flush=True)
        return None

    def get_wallet_balance(self):
        endpoint = "/v5/account/wallet-balance"
        params = {"accountType": "UNIFIED"}
        data = self._send_request("GET", endpoint, params)
        if data and data.get("result") and data["result"].get("list"):
            for coin in data["result"]["list"][0]["coin"]:
                if coin["coin"] == "USDT": return float(coin["walletBalance"])
        return 0

    # ZMIANA: Używa _send_request (podpisane żądanie)
    def get_last_price(self, symbol):
        endpoint = "/v5/market/tickers"
        params = {"category": "linear", "symbol": symbol}
        
        data = self._send_request("GET", endpoint, params)
        if data and data.get("retCode") == 0 and data["result"]["list"]:
            return float(data["result"]["list"][0]["lastPrice"])
        
        if data:
            print(colored(f"Błąd pobierania ostatniej ceny (retCode: {data.get('retCode')}, retMsg: {data.get('retMsg')})", "red"), flush=True)
        return 0

    def get_position(self, symbol):
        endpoint = "/v5/position/list"
        params = {"category": "linear", "symbol": symbol}
        data = self._send_request("GET", endpoint, params)
        if data and data.get("result") and data["result"].get("list"):
            pos = data["result"]["list"][0]
            side = pos["side"] if float(pos["size"]) > 0 else "None"
            size = float(pos["size"])
            avg_price = float(pos["avgPrice"]) if size > 0 else 0
            return side, size, avg_price
        return "None", 0, 0

    def place_order(self, symbol, side, qty, reduce_only=False):
        endpoint = "/v5/order/create"
        params = {
            "category": "linear", 
            "symbol": symbol, 
            "side": side, 
            "orderType": "Market", 
            "qty": str(qty),
            "reduceOnly": reduce_only
        }
        print(colored(f"--- [{symbol}] Zlecenie: {params}", "yellow"), flush=True)
        return self._send_request("POST", endpoint, params)

    def set_leverage(self, symbol, leverage):
        endpoint = "/v5/position/set-leverage"
        params = {"category": "linear", "symbol": symbol, "buyLeverage": leverage, "sellLeverage": leverage}
        print(colored(f"--- [{symbol}] Ustawianie dźwigni na {leverage}x...", "cyan"), flush=True)
        return self._send_request("POST", endpoint, params)

# === LOGIKA TRADINGOWA ===
# ZMIANA: Zwraca kierunek, wstęgę górną (SL dla Short), wstęgę dolną (SL dla Long)
def calculate_supertrend_kivanc(data, period, factor):
    highs = [float(d[2]) for d in data]
    lows = [float(d[3]) for d in data]
    closes = [float(d[4]) for d in data]
    
    src = [(h + l) / 2 for h, l in zip(highs, lows)]

    true_ranges = [max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1])) for i in range(1, len(closes))]
    true_ranges.insert(0, 0)

    atr = [0.0] * len(closes)
    if len(closes) > period:
        atr[period] = sum(true_ranges[1:period+1]) / period
        for i in range(period + 1, len(closes)):
            atr[i] = (atr[i-1] * (period - 1) + true_ranges[i]) / period

    if not any(atr) or len(atr) < period: 
        return 0, 0, 0 # Kierunek, Wstęga dolna, Wstęga górna

    up, dn = ([0.0] * len(data) for _ in range(2))
    trend = [1] * len(data)

    for i in range(period, len(data)):
        up_basic = src[i] - (factor * atr[i])
        dn_basic = src[i] + (factor * atr[i])
        
        up[i] = max(up_basic, up[i-1]) if closes[i-1] > up[i-1] else up_basic
        dn[i] = min(dn_basic, dn[i-1]) if closes[i-1] < dn[i-1] else dn_basic
        
        trend[i] = trend[i-1]
        if trend[i] == -1 and closes[i] > dn[i-1]:
            trend[i] = 1
        elif trend[i] == 1 and closes[i] < up[i-1]:
            trend[i] = -1
    
    # Zwraca (kierunek, dolna wstęga SL dla Long, górna wstęga SL dla Short)
    return trend[-1], up[-1], dn[-1]

# ZMIANA: Logika obliczania wielkości pozycji na podstawie SL
def execute_trade(client, config, instrument_rules, stop_loss_price):
    balance = client.get_wallet_balance()
    price = client.get_last_price(config['symbol'])
    
    if not (balance > 0 and price > 0):
        print(colored(f"[{config['symbol']}] Błąd: Brak salda ({balance}) lub ceny ({price}).", "red"), flush=True)
        return None

    min_qty = instrument_rules["minOrderQty"]
    qty_step = instrument_rules["qtyStep"]

    # 1. Oblicz maksymalną stratę w USDT
    loss_in_usdt = balance * (config['risk_percentage'] / 100)
    
    # 2. Oblicz dystans (w cenie) od aktualnej ceny do poziomu Stop Loss
    sl_distance = abs(price - stop_loss_price)

    if sl_distance == 0:
        print(colored(f"[{config['symbol']}] BŁĄD: Dystans do Stop Loss wynosi 0 (Cena={price}, SL={stop_loss_price}). Anulowanie zlecenia.", "red"), flush=True)
        return None

    # 3. Oblicz "surową" ilość
    raw_qty = loss_in_usdt / sl_distance
    
    # 4. Sprawdź, czy ilość jest powyżej minimum giełdy
    if raw_qty < min_qty:
        print(colored(f"[{config['symbol']}] BŁĄD: Obliczona ilość {raw_qty:.6f} jest mniejsza niż minimalna {min_qty}. Zwiększ kapitał lub % ryzyka.", "red"), flush=True)
        return None
        
    # 5. Dostosuj ilość do wymaganego kroku (qtyStep)
    adjusted_qty = math.floor(raw_qty / qty_step) * qty_step
    
    # Konwersja do stringa z odpowiednią precyzją
    if '.' in str(qty_step):
        precision = len(str(qty_step).split('.')[1])
    else:
        precision = 0
    final_qty_str = f"{adjusted_qty:.{precision}f}"

    print(colored(f"[{config['symbol']}] Kapitał: {balance:.2f} USDT. Ryzyko: {loss_in_usdt:.2f} USDT.", "cyan"), flush=True)
    print(colored(f"[{config['symbol']}] Cena: {price}, SL: {stop_loss_price:.4f}, Dystans SL: {sl_distance:.4f}", "cyan"), flush=True)
    print(colored(f"[{config['symbol']}] Surowa ilość: {raw_qty:.4f}. Finalna ilość: {final_qty_str}", "cyan"), flush=True)
    
    # Upewniamy się, że finalna ilość nie jest zerowa po zaokrągleniu
    if float(final_qty_str) > 0:
        return client.place_order(config['symbol'], config['current_signal'], final_qty_str)
    
    return None


# === GŁÓWNA PĘTLA BOTA (DLA JEDNEJ PARY) ===
def run_strategy_for_pair(config):
    client = BybitClient(API_KEY, API_SECRET)
    symbol = config['symbol']
    interval = config['interval']
    
    print(colored(f"[{symbol}] Bot Supertrend (Stop & Reverse) uruchomiony!", "green"), flush=True)
    print(f"[{symbol}] Interwał: {interval}m, Ryzyko: {config['risk_percentage']}%", flush=True)

    last_signal, leverage_set, rules_fetched = None, False, False
    instrument_rules = {}

    while True:
        try:
            # Jednorazowe pobranie reguł handlowych
            if not rules_fetched:
                rules = client.get_instrument_info(symbol)
                if rules:
                    instrument_rules = rules
                    rules_fetched = True
                    print(colored(f"[{symbol}] Pomyślnie pobrano reguły handlowe: {instrument_rules}", "green"), flush=True)
                else:
                    print(colored(f"[{symbol}] Nie udało się pobrać reguł handlowych. Ponowna próba za 10s.", "red"), flush=True)
                    time.sleep(10); continue
            
            # Jednorazowe ustawienie dźwigni
            if not leverage_set:
                result = client.set_leverage(symbol, LEVERAGE)
                if result and (result.get('retCode') == 0 or result.get('retCode') in [110025, 110043]):
                    leverage_set = True
                    print(colored(f"[{symbol}] Dźwignia ustawiona pomyślnie.", "green"), flush=True)
                else:
                    time.sleep(10); continue
            
            klines_raw = client.get_klines(symbol, interval, limit=300)
            if not klines_raw or len(klines_raw) < config['atr_period'] + 2:
                print(colored(f"[{symbol}] Oczekuję na wystarczającą ilość danych historycznych...", "yellow"), flush=True)
                time.sleep(60); continue

            klines_closed = klines_raw[1:]
            klines_closed.reverse()
            
            # ZMIANA: Przechwytujemy 3 wartości: kierunek, wstęgę dolną (SL dla long) i górną (SL dla short)
            signal_direction, sl_up_band, sl_dn_band = calculate_supertrend_kivanc(klines_closed, config['atr_period'], config['factor'])

            if signal_direction == 0:
                print(colored(f"[{symbol}] Błąd kalkulacji Supertrend (prawdopodobnie za mało danych). Czekam...", "yellow"), flush=True)
                time.sleep(30); continue 

            current_signal = "Buy" if signal_direction == 1 else "Sell"
            config['current_signal'] = current_signal
            
            # ZMIANA: Wybieramy odpowiedni poziom SL na podstawie sygnału
            stop_loss_price = sl_up_band if current_signal == "Buy" else sl_dn_band
            
            position_side, position_size, _ = client.get_position(symbol)
            status_color = "green" if current_signal == "Buy" else "red"
            print(f"[{symbol}][{time.strftime('%H:%M:%S')}] Poprzedni sygnał: {last_signal} | Aktualny sygnał: {colored(current_signal, status_color)} | Pozycja: {colored(position_side, 'cyan')} ({position_size})", flush=True)
            
            if last_signal is None:
                last_signal = current_signal
                print(colored(f"[{symbol}] Inicjalizacja. Pierwszy sygnał: {current_signal}. Oczekiwanie na zmianę.", "blue"), flush=True)
            
            elif current_signal != last_signal:
                print(colored(f"[{symbol}] ZMIANA TRENDU z {last_signal} na {current_signal}!", "magenta", attrs=['bold']), flush=True)
                
                # Bot zamyka pozycję tylko jeśli ją ma (obsługa ręcznego zamknięcia)
                if position_size > 0:
                    close_side = "Buy" if position_side == "Sell" else "Sell"
                    client.place_order(symbol, close_side, position_size, reduce_only=True)
                    print(colored(f"[{symbol}] Pozycja ({position_side}) zamknięta. Czekam 5s przed otwarciem nowej...", "yellow"), flush=True)
                    time.sleep(5)
                
                # Otwórz nową pozycję z obliczonym ryzykiem
                execute_trade(client, config, instrument_rules, stop_loss_price)
            
            last_signal = current_signal

            now = datetime.datetime.now(datetime.timezone.utc)
            interval_minutes = int(interval)
            minutes_to_next_interval = interval_minutes - (now.minute % interval_minutes)
            
            # ZMIANA: Bufor +2 sekundy dla interwału 1m
            seconds_to_wait = (minutes_to_next_interval * 60) - now.second + 2 
            
            print(colored(f"--- [{symbol}] Czekam {int(seconds_to_wait)}s do nast. świecy {interval}m ---\n", "blue"), flush=True)
            time.sleep(seconds_to_wait)

        except Exception as e:
            print(colored(f"[{symbol}] KRYTYCZNY BŁĄD w głównej pętli: {e}", "red", attrs=['bold']), flush=True)
            time.sleep(60)

# === START BOTA ===
if __name__ == "__main__":
    if "TWOJ_API_KEY" in API_KEY or "TWOJ_API_SECRET" in API_SECRET:
        print(colored("BŁĄD: Proszę ustawić prawdziwe wartości API_KEY i API_SECRET w pliku!", "red"), flush=True)
    else:
        threads = []
        for config in BOT_CONFIGS:
            thread = threading.Thread(target=run_strategy_for_pair, args=(config,))
            threads.append(thread)
            thread.start()
            print(f"Uruchomiono wątek dla {config['symbol']}")
            time.sleep(3) # Odstęp między uruchamianiem wątków, aby uniknąć rate limit

        for thread in threads:
            thread.join()
