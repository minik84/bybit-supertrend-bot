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
    client = BybitClient(API_KEY, API_SECRET
