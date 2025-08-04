import time
import hmac
import hashlib
import requests
import json
import datetime
import threading
from termcolor import colored

# === KONFIGURACJA ===
# Pamiętaj, aby zastąpić te wartości swoimi kluczami API!
API_KEY = "pk3pm3ytYQfYq8Kbku" 
API_SECRET = "0gLWHahoJ546CbTqozDVYHPiwwaKGIiljToR"
BASE_URL = "https://api.bybit.com"
LEVERAGE = "10"

# ==============================================================================
# === KONFIGURACJA BOTÓW ===
# ==============================================================================
BOT_CONFIGS = [
    {
        "symbol": "WIFUSDT",
        "interval": "15",
        "atr_period": 10,
        "factor": 3.0,
        "risk_percentage": 5
    }
    # Możesz dodać więcej konfiguracji dla innych par
    # {
    #     "symbol": "BTCUSDT",
    #     "interval": "15",
    #     "atr_period": 10,
    #     "factor": 3.0,
    #     "risk_percentage": 5
    # }
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

            # Ignoruj błędy informujące o braku zmian (dźwignia) lub braku pozycji do zamknięcia.
            if data.get("retCode") != 0 and data.get("retCode") not in [110025, 110043]:
                print(colored(f"Błąd API Bybit: {data.get('retMsg')} (retCode: {data.get('retCode')})", "red"), flush=True)
                return None
            return data
        except Exception as e:
            print(colored(f"Błąd połączenia: {e}", "red"), flush=True)
            return None

    def get_klines(self, symbol, interval, limit=200):
        endpoint = "/v5/market/kline"
        params = {"category": "linear", "symbol": symbol, "interval": interval, "limit": limit}
        try:
            # Użycie publicznego endpointu nie wymaga autoryzacji
            response = requests.get(self.base_url + endpoint, params=params)
            response.raise_for_status()
            data = response.json()
            if data.get("retCode") == 0: return data["result"]["list"]
            return []
        except Exception as e:
            print(colored(f"Błąd pobierania klines: {e}", "red"), flush=True)
            return []

    def get_wallet_balance(self):
        endpoint = "/v5/account/wallet-balance"
        params = {"accountType": "UNIFIED"}
        data = self._send_request("GET", endpoint, params)
        if data and data.get("result") and data["result"].get("list"):
            for coin in data["result"]["list"][0]["coin"]:
                if coin["coin"] == "USDT": return float(coin["walletBalance"])
        return 0

    def get_last_price(self, symbol):
        endpoint = "/v5/market/tickers"
        params = {"category": "linear", "symbol": symbol}
        try:
            response = requests.get(self.base_url + endpoint, params=params)
            response.raise_for_status()
            data = response.json()
            if data.get("retCode") == 0 and data["result"]["list"]: return float(data["result"]["list"][0]["lastPrice"])
            return 0
        except Exception: return 0

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
def calculate_supertrend_kivanc(data, period, factor):
    highs = [float(d[2]) for d in data]
    lows = [float(d[3]) for d in data]
    closes = [float(d[4]) for d in data]
    
    src = [(h + l) / 2 for h, l in zip(highs, lows)]

    true_ranges = [max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1])) for i in range(1, len(closes))]
    true_ranges.insert(0, 0) # Pierwszy TR jest zazwyczaj ignorowany lub równy H-L

    atr = [0.0] * len(closes)
    if len(closes) > period:
        atr[period] = sum(true_ranges[1:period+1]) / period
        for i in range(period + 1, len(closes)):
            atr[i] = (atr[i-1] * (period - 1) + true_ranges[i]) / period

    if not any(atr) or len(atr) < period: return 0

    up, dn = ([0.0] * len(data) for _ in range(2))
    trend = [1] * len(data) # Domyślny trend to wzrostowy

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
    
    return trend[-1]

def execute_trade(client, config):
    balance = client.get_wallet_balance()
    price = client.get_last_price(config['symbol'])
    if balance > 0 and price > 0:
        margin_to_risk = balance * (config['risk_percentage'] / 100)
        notional_value = margin_to_risk * float(LEVERAGE)
        qty = round(notional_value / price, 3) # Zaokrąglenie do 3 miejsc po przecinku, dostosuj w razie potrzeby

        print(colored(f"[{config['symbol']}] Kapitał: {balance:.2f} USDT. Ryzykowany margin: {margin_to_risk:.2f} USDT. Notional: {notional_value:.2f} USDT. Obliczona ilość: {qty}", "cyan"), flush=True)
        if qty > 0:
            return client.place_order(config['symbol'], config['current_signal'], qty)
    return None

# === GŁÓWNA PĘTLA BOTA (DLA JEDNEJ PARY) ===
def run_strategy_for_pair(config):
    client = BybitClient(API_KEY, API_SECRET)
    symbol = config['symbol']
    interval = config['interval']
    
    print(colored(f"[{symbol}] Bot Supertrend (Stop & Reverse) uruchomiony!", "green"), flush=True)
    print(f"[{symbol}] Interwał: {interval}m, Ryzyko: {config['risk_percentage']}%", flush=True)

    last_signal, leverage_set = None, False

    while True:
        try:
            if not leverage_set:
                result = client.set_leverage(symbol, LEVERAGE)
                if result and (result.get('retCode') == 0 or result.get('retCode') in [110025, 110043]):
                    leverage_set = True
                    print(colored(f"[{symbol}] Dźwignia ustawiona pomyślnie.", "green"), flush=True)
                else:
                    time.sleep(10); continue
            
            # --- KLUCZOWA ZMIANA: POBIERANIE I FILTROWANIE ŚWIEC ---
            klines_raw = client.get_klines(symbol, interval, limit=300)
            # Potrzebujemy co najmniej okresu ATR + 2 świece do obliczeń
            if not klines_raw or len(klines_raw) < config['atr_period'] + 2:
                print(colored(f"[{symbol}] Oczekuję na wystarczającą ilość danych historycznych...", "yellow"), flush=True)
                time.sleep(60); continue

            # API zwraca dane z najnowszą, NIEZAMKNIĘTĄ świecą na indeksie [0].
            # Używamy wszystkich świec OPRÓCZ tej bieżącej, aby sygnał był stabilny.
            klines_closed = klines_raw[1:]
            klines_closed.reverse() # Odwracamy listę, by najstarsza świeca była pierwsza

            # Obliczenia wykonujemy tylko na zamkniętych świecach
            signal_direction = calculate_supertrend_kivanc(klines_closed, config['atr_period'], config['factor'])
            current_signal = "Buy" if signal_direction == 1 else "Sell"
            config['current_signal'] = current_signal
            
            # --- KONIEC KLUCZOWEJ ZMIANY ---

            position_side, position_size, _ = client.get_position(symbol)
            status_color = "green" if current_signal == "Buy" else "red"
            print(f"[{symbol}][{time.strftime('%H:%M:%S')}] Poprzedni sygnał: {last_signal} | Aktualny sygnał: {colored(current_signal, status_color)} | Otwarta pozycja: {colored(position_side, 'cyan')} ({position_size})", flush=True)
            
            # Jeśli `last_signal` nie jest jeszcze ustawiony (pierwsze uruchomienie), tylko go zapisujemy
            if last_signal is None:
                last_signal = current_signal
                print(colored(f"[{symbol}] Inicjalizacja. Pierwszy odczytany sygnał: {current_signal}. Oczekiwanie na zmianę.", "blue"), flush=True)
            # Jeśli sygnał się zmienił, wykonujemy transakcję
            elif current_signal != last_signal:
                print(colored(f"[{symbol}] ZMIANA TRENDU z {last_signal} na {current_signal}!", "magenta", attrs=['bold']), flush=True)
                
                # 1. Zamknij istniejącą pozycję, jeśli istnieje (logika Stop and Reverse)
                if position_size > 0:
                    # Strona zlecenia zamykającego jest przeciwna do strony pozycji
                    close_side = "Buy" if position_side == "Sell" else "Sell"
                    client.place_order(symbol, close_side, position_size, reduce_only=True)
                    print(colored(f"[{symbol}] Pozycja ({position_side}) zamknięta. Czekam 5s przed otwarciem nowej...", "yellow"), flush=True)
                    time.sleep(5)
                
                # 2. Otwórz nową pozycję zgodnie z nowym sygnałem
                execute_trade(client, config)
            
            # Aktualizujemy ostatni sygnał
            last_signal = current_signal

            # Oczekiwanie na kolejną świecę
            now = datetime.datetime.now(datetime.timezone.utc)
            interval_minutes = int(interval)
            minutes_to_next_interval = interval_minutes - (now.minute % interval_minutes)
            seconds_to_wait = (minutes_to_next_interval * 60) - now.second + 5 # +5s buforu
            print(colored(f"--- [{symbol}] Czekam {int(seconds_to_wait)}s do nast. świecy {interval}m ---\n", "blue"), flush=True)
            time.sleep(seconds_to_wait)

        except Exception as e:
            print(colored(f"[{symbol}] KRYTYCZNY BŁĄD w głównej pętli: {e}", "red", attrs=['bold']), flush=True)
            time.sleep(60)

# === START BOTA ===
if __name__ == "__main__":
    if "pk3pm3ytYQfYq8Kbku" in API_KEY or "0gLWHahoJ546CbTqozDVYHPiwwaKGIiljToR" in API_SECRET:
        print(colored("BŁĄD: Proszę ustawić prawdziwe wartości API_KEY i API_SECRET w pliku!", "red"), flush=True)
    else:
        threads = []
        for config in BOT_CONFIGS:
            thread = threading.Thread(target=run_strategy_for_pair, args=(config,))
            threads.append(thread)
            thread.start()
            print(f"Uruchomiono wątek dla {config['symbol']}")
            time.sleep(3) # Krótka przerwa między uruchamianiem kolejnych wątków

        for thread in threads:
            thread.join()
