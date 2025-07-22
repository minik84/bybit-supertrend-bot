import time
import hmac
import hashlib
import requests
import json
import datetime
from termcolor import colored

# === KONFIGURACJA ===
# --- Wklej swój klucz API i Sekret ---
API_KEY = "pk3pm3ytYQfYq8Kbku"
API_SECRET = "0gLWHahoJ546CbTqozDVYHPiwwaKGIiljToR"
# ------------------------------------

# === USTAWIENIA STRATEGII ===
BASE_URL = "https://api.bybit.com"
SYMBOL = "WIFUSDT"
LEVERAGE = "10"
INTERVAL = "5" 

# --- USTAWIENIA WSKAŹNIKA SUPERTREND ---
ATR_PERIOD = 10
FACTOR = 3.0

# --- USTAWIENIA ZARZĄDZANIA KAPITAŁEM ---
RISK_PERCENTAGE = 5 

# === KLASA DO OBSŁUGI API BYBIT ===
class BybitClient:
    def __init__(self, api_key, api_secret):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = BASE_URL
        self.session = requests.Session()

    def _send_request(self, method, endpoint, params=None):
        """Wysyła zapytanie do API Bybit z sygnaturą HMAC."""
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

            if data.get("retCode") != 0:
                if data.get("retCode") in [110025, 110043]: return data
                print(colored(f"Błąd API Bybit: {data.get('retMsg')} (retCode: {data.get('retCode')})", "red"), flush=True)
                return None
            return data
        except Exception as e:
            print(colored(f"Błąd połączenia lub zapytania: {e}", "red"), flush=True)
            return None

    def get_klines(self, symbol, interval, limit=200):
        """Pobiera dane historyczne dla danego interwału."""
        endpoint = "/v5/market/kline"
        params = {"category": "linear", "symbol": symbol, "interval": interval, "limit": limit}
        try:
            response = requests.get(self.base_url + endpoint, params=params)
            response.raise_for_status()
            data = response.json()
            if data.get("retCode") == 0: return data["result"]["list"]
            return []
        except Exception: return []

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
            return side, size
        return "None", 0

    def place_order(self, symbol, side, qty, reduce_only=False):
        endpoint = "/v5/order/create"
        params = {"category": "linear", "symbol": symbol, "side": side, "orderType": "Market", "qty": str(qty), "reduceOnly": reduce_only}
        print(colored(f"--- Składanie zlecenia: {params}", "yellow"), flush=True)
        return self._send_request("POST", endpoint, params)

    def set_leverage(self, symbol, leverage):
        endpoint = "/v5/position/set-leverage"
        params = {"category": "linear", "symbol": symbol, "buyLeverage": leverage, "sellLeverage": leverage}
        print(colored(f"--- Ustawianie dźwigni na {leverage}x dla {symbol}...", "cyan"), flush=True)
        return self._send_request("POST", endpoint, params)

# === LOGIKA TRADINGOWA ===
def calculate_supertrend_kivanc(data, period, factor):
    """Oblicza wskaźnik Supertrend zgodnie z logiką Kivanc Ozbilgic."""
    highs = [float(d[2]) for d in data]
    lows = [float(d[3]) for d in data]
    closes = [float(d[4]) for d in data]
    
    src = [(h + l) / 2 for h, l in zip(highs, lows)]

    true_ranges = [0.0] * len(closes)
    for i in range(1, len(closes)):
        true_ranges[i] = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))

    atr = [0.0] * len(closes)
    if len(closes) > period:
        atr[period] = sum(true_ranges[1:period+1]) / period
        for i in range(period + 1, len(closes)):
            atr[i] = (atr[i-1] * (period - 1) + true_ranges[i]) / period

    if not any(atr) or len(atr) < period: return 0

    up, dn, trend = ([0.0] * len(data) for _ in range(3))
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
    
    return trend[-1]

def execute_trade(client, symbol, side):
    """Pobiera dane, oblicza wielkość i składa zlecenie."""
    balance = client.get_wallet_balance()
    price = client.get_last_price(symbol)
    if balance > 0 and price > 0:
        notional_value = balance * float(LEVERAGE)
        max_qty = notional_value / price
        qty = int(round(max_qty * (RISK_PERCENTAGE / 100)))
        
        print(colored(f"Kapitał: {balance:.2f} USDT. Obliczona ilość do otwarcia: {qty} {SYMBOL}", "cyan"), flush=True)
        if qty > 0:
            return client.place_order(symbol, side, qty)
    return None

# === GŁÓWNA PĘTLA BOTA ===
def run_bot():
    client = BybitClient(API_KEY, API_SECRET)
    print(colored("Bot Supertrend (Logika Kivanc) uruchomiony!", "green"), flush=True)
    print(f"Interwał: {INTERVAL}m, Ryzyko: {RISK_PERCENTAGE}%", flush=True)

    last_signal, leverage_set = None, False
    while True:
        try:
            if not leverage_set:
                result = client.set_leverage(SYMBOL, LEVERAGE)
                if result and (result.get('retCode') == 0 or result.get('retCode') in [110025, 110043]):
                    print(colored("Dźwignia zweryfikowana/ustawiona pomyślnie.", "green"), flush=True)
                    leverage_set = True
                else:
                    print(colored("Nie udało się ustawić dźwigni. Próba za 10s...", "red"), flush=True)
                    time.sleep(10)
                    continue
            
            klines = client.get_klines(SYMBOL, INTERVAL, limit=ATR_PERIOD + 50)
            if not klines or len(klines) < ATR_PERIOD + 1:
                time.sleep(60)
                continue
            
            klines.reverse() 
            
            signal_direction = calculate_supertrend_kivanc(klines, ATR_PERIOD, FACTOR)
            current_signal = "Buy" if signal_direction == 1 else "Sell"

            if last_signal is None:
                last_signal = current_signal
                print(colored(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Inicjalizacja. Główny sygnał to {current_signal}. Oczekuję na pierwszą zmianę trendu...", "blue"), flush=True)
            else:
                position_side, position_size = client.get_position(SYMBOL)
                status_color = "green" if current_signal == "Buy" else "red"
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Ostatni sygnał: {last_signal} | Aktualny: {colored(current_signal, status_color)} | Pozycja: {colored(position_side, 'cyan')}, Rozmiar: {colored(position_size, 'cyan')}", flush=True)
                
                if current_signal != last_signal:
                    print(colored(f"Wykryto zmianę głównego trendu z {last_signal} na {current_signal}!", "magenta"), flush=True)
                    
                    if position_size > 0:
                        close_side = "Buy" if position_side == "Sell" else "Sell"
                        client.place_order(SYMBOL, close_side, position_size, reduce_only=True)
                        print(colored("Pozycja zamknięta. Czekam 5s na przetworzenie.", "yellow"), flush=True)
                        time.sleep(5)
                    
                    execute_trade(client, SYMBOL, current_signal)
                    last_signal = current_signal

            now = datetime.datetime.now(datetime.timezone.utc)
            interval_minutes = int(INTERVAL)
            minutes_to_next_interval = interval_minutes - (now.minute % interval_minutes)
            seconds_to_wait = (minutes_to_next_interval * 60) - now.second + 5
            if seconds_to_wait > interval_minutes * 60: seconds_to_wait -= interval_minutes * 60
            print(colored(f"--- Czekam {int(seconds_to_wait)}s do następnej świecy {INTERVAL}m ---\n", "blue"), flush=True)
            time.sleep(seconds_to_wait)
        except Exception as e:
            print(colored(f"Błąd w głównej pętli: {e}", "red"), flush=True)
            time.sleep(60)

# === START BOTA ===
if __name__ == "__main__":
    while True:
        try:
            if API_KEY == "TWOJ_API_KEY" or API_SECRET == "TWOJ_API_SECRET":
                print(colored("BŁĄD: Proszę ustawić API_KEY i API_SECRET w pliku!", "red"), flush=True)
                break
            run_bot()
        except Exception as e:
            print(colored(f"KRYTYCZNY BŁĄD! Restartowanie bota za 60 sekund. Błąd: {e}", "red"), flush=True)
            import traceback
            traceback.print_exc()
            time.sleep(60)
