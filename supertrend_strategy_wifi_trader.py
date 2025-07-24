import time
import hmac
import hashlib
import requests
import json
import datetime
import threading
from termcolor import colored

# === KONFIGURACJA ===
# --- Wklej swój klucz API i Sekret ---
API_KEY = "pk3pm3ytYQfYq8Kbku"
API_SECRET = "0gLWHahoJ546CbTqozDVYHPiwwaKGIiljToR"
# ------------------------------------
BASE_URL = "https://api.bybit.com"
LEVERAGE = "10"

# ==============================================================================
# === KONFIGURACJA BOTÓW ===
# Tutaj definiujesz ustawienia dla każdego bota, którego chcesz uruchomić.
# Możesz dodać więcej słowników do tej listy, aby uruchomić więcej botów.
# ==============================================================================
BOT_CONFIGS = [
    {
        "symbol": "WIFUSDT",
        "interval": "15",
        "atr_period": 10,
        "factor": 3.0,
        "risk_percentage": 5,
        "take_profit_percentage": 1.5
    },
    # --- PRZYKŁAD: Dodaj tutaj drugiego bota ---
    # {
    #     "symbol": "BTCUSDT",
    #     "interval": "5",
    #     "atr_period": 12,
    #     "factor": 2.5,
    #     "risk_percentage": 3,
    #     "take_profit_percentage": 1.0
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

            if data.get("retCode") != 0:
                if data.get("retCode") in [110025, 110043]: return data
                print(colored(f"Błąd API Bybit: {data.get('retMsg')} (retCode: {data.get('retCode')})", "red"), flush=True)
                return None
            return data
        except Exception as e:
            print(colored(f"Błąd połączenia lub zapytania: {e}", "red"), flush=True)
            return None

    def get_klines(self, symbol, interval, limit=200):
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
            avg_price = float(pos["avgPrice"]) if size > 0 else 0
            return side, size, avg_price
        return "None", 0, 0

    def place_order(self, symbol, side, qty, reduce_only=False):
        endpoint = "/v5/order/create"
        params = {"category": "linear", "symbol": symbol, "side": side, "orderType": "Market", "qty": str(qty), "reduceOnly": reduce_only}
        print(colored(f"--- [{symbol}] Składanie zlecenia: {params}", "yellow"), flush=True)
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

def execute_trade(client, config):
    balance = client.get_wallet_balance()
    price = client.get_last_price(config['symbol'])
    if balance > 0 and price > 0:
        notional_value = balance * float(LEVERAGE)
        max_qty = notional_value / price
        qty = int(round(max_qty * (config['risk_percentage'] / 100)))
        
        print(colored(f"[{config['symbol']}] Kapitał: {balance:.2f} USDT. Obliczona ilość: {qty} {config['symbol']}", "cyan"), flush=True)
        if qty > 0:
            return client.place_order(config['symbol'], config['current_signal'], qty)
    return None

# === GŁÓWNA PĘTLA BOTA (DLA JEDNEJ PARY) ===
def run_strategy_for_pair(config):
    client = BybitClient(API_KEY, API_SECRET)
    symbol = config['symbol']
    interval = config['interval']
    
    print(colored(f"[{symbol}] Bot Supertrend (Logika Kivanc + TP) uruchomiony!", "green"), flush=True)
    print(f"[{symbol}] Interwał: {interval}m, Ryzyko: {config['risk_percentage']}%, TP: {config['take_profit_percentage']}%", flush=True)

    last_signal, leverage_set = None, False
    while True:
        try:
            if not leverage_set:
                result = client.set_leverage(symbol, LEVERAGE)
                if result and (result.get('retCode') == 0 or result.get('retCode') in [110025, 110043]):
                    print(colored(f"[{symbol}] Dźwignia zweryfikowana/ustawiona.", "green"), flush=True)
                    leverage_set = True
                else:
                    print(colored(f"[{symbol}] Nie udało się ustawić dźwigni. Próba za 10s...", "red"), flush=True)
                    time.sleep(10)
                    continue
            
            klines = client.get_klines(symbol, interval, limit=config['atr_period'] + 50)
            if not klines or len(klines) < config['atr_period'] + 1:
                time.sleep(60)
                continue
            
            klines.reverse() 
            
            signal_direction = calculate_supertrend_kivanc(klines, config['atr_period'], config['factor'])
            current_signal = "Buy" if signal_direction == 1 else "Sell"
            config['current_signal'] = current_signal

            if last_signal is None:
                last_signal = current_signal
                print(colored(f"[{symbol}][{time.strftime('%H:%M:%S')}] Inicjalizacja. Sygnał: {current_signal}. Czekam na zmianę...", "blue"), flush=True)
            else:
                position_side, position_size, avg_entry_price = client.get_position(symbol)
                
                if position_size > 0:
                    current_price = client.get_last_price(symbol)
                    if current_price > 0 and avg_entry_price > 0:
                        pnl_percent = ((current_price - avg_entry_price) / avg_entry_price) * 100 if position_side == 'Buy' else ((avg_entry_price - current_price) / avg_entry_price) * 100
                        if pnl_percent >= config['take_profit_percentage']:
                            print(colored(f"[{symbol}] ZYSK OSIĄGNĄŁ {pnl_percent:.2f}%. Zamykanie pozycji (TP)...", "green"), flush=True)
                            close_side = "Buy" if position_side == "Sell" else "Sell"
                            client.place_order(symbol, close_side, position_size, reduce_only=True)
                            last_signal = None # Resetuj sygnał, aby czekać na nową zmianę
                            time.sleep(5)
                            continue

                status_color = "green" if current_signal == "Buy" else "red"
                print(f"[{symbol}][{time.strftime('%H:%M:%S')}] Poprzedni: {last_signal} | Aktualny: {colored(current_signal, status_color)} | Pozycja: {colored(position_side, 'cyan')}", flush=True)
                
                if current_signal != last_signal:
                    print(colored(f"[{symbol}] ZMIANA TRENDU z {last_signal} na {current_signal}!", "magenta"), flush=True)
                    
                    if position_size > 0:
                        close_side = "Buy" if position_side == "Sell" else "Sell"
                        client.place_order(symbol, close_side, position_size, reduce_only=True)
                        print(colored(f"[{symbol}] Pozycja zamknięta (Stop & Reverse). Czekam 5s...", "yellow"), flush=True)
                        time.sleep(5)
                    
                    execute_trade(client, config)
                    last_signal = current_signal

            now = datetime.datetime.now(datetime.timezone.utc)
            interval_minutes = int(interval)
            minutes_to_next_interval = interval_minutes - (now.minute % interval_minutes)
            seconds_to_wait = (minutes_to_next_interval * 60) - now.second + 5
            if seconds_to_wait > interval_minutes * 60: seconds_to_wait -= interval_minutes * 60
            print(colored(f"--- [{symbol}] Czekam {int(seconds_to_wait)}s do nast. świecy {interval}m ---\n", "blue"), flush=True)
            time.sleep(seconds_to_wait)
        except Exception as e:
            print(colored(f"[{symbol}] Błąd w pętli: {e}", "red"), flush=True); time.sleep(60)

# === START BOTA ===
if __name__ == "__main__":
    if API_KEY == "TWOJ_API_KEY" or API_SECRET == "TWOJ_API_SECRET":
        print(colored("BŁĄD: Proszę ustawić API_KEY i API_SECRET w pliku!", "red"), flush=True)
    else:
        threads = []
        for config in BOT_CONFIGS:
            thread = threading.Thread(target=run_strategy_for_pair, args=(config,))
            threads.append(thread)
            thread.start()
            print(f"Uruchomiono wątek dla {config['symbol']}")
            time.sleep(3) # Mała przerwa, aby nie zasypać API zapytaniami na starcie

        for thread in threads:
            thread.join()
