#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════════════════════
    BOT LEGENDX - BYBIT TRADING
    Strategia bazowana na MA + ATR + Standard Deviation
    8 poziomów Take Profit | Risk Management | Multi-Para Support
═══════════════════════════════════════════════════════════════════════════════
"""

import time
import hmac
import hashlib
import requests
import json
import datetime
import threading
import math
from termcolor import colored

# ==============================================================================
# === KONFIGURACJA API ===
# ==============================================================================
API_KEY = "CxQFjz7JivQbTnihTP"  # ZMIEŃ NA SWÓJ KLUCZ
API_SECRET = "zfliLpcpjbb2LeQLNjvQx8Twlm41ctR4ZUGq"  # ZMIEŃ NA SWÓJ SECRET
BASE_URL = "https://api.bybit.com"  # Produkcja
# BASE_URL = "https://api-testnet.bybit.com"  # Testnet (odkomentuj dla testów)

# ==============================================================================
# === KONFIGURACJA BOTÓW ===
# ==============================================================================

# ==============================================================================
# === PREDEFINIOWANE KONFIGURACJE (PRESETY) ===
# Wszystkie parametry z oryginalnej strategii Legendx PineScript
# ==============================================================================

PRESETS = {
    # ========== 30 MINUT ==========
    
    "BNBUSDT_30m": {
        "symbol": "BNBUSDT", "interval": "30", "ma_choice": "VWMA", "ma_period": 230,
        "std_period_long": 14, "std_coeff_long": 1.3, "atr_period_long": 9, "atr_coeff_long": 1.0,
        "ma_distance_perc_long": 1.0, "stop_loss_perc_long": 4.5,
        "std_period_short": 13, "std_coeff_short": 1.3, "atr_period_short": 9, "atr_coeff_short": 1.5,
        "ma_distance_perc_short": 1.3, "stop_loss_perc_short": 4.5,
        "tp_levels": [2.0, 4.0, 8.0], "risk_percentage": 1.0, "renorm_coeff": 1.0, "leverage": "20"
    },
    
    "BTCUSDT_30m": {
        "symbol": "BTCUSDT", "interval": "30", "ma_choice": "VWMA", "ma_period": 300,
        "std_period_long": 17, "std_coeff_long": 1.6, "atr_period_long": 11, "atr_coeff_long": 2.0,
        "ma_distance_perc_long": 2.1, "stop_loss_perc_long": 4.5,
        "std_period_short": 12, "std_coeff_short": 1.2, "atr_period_short": 14, "atr_coeff_short": 1.5,
        "ma_distance_perc_short": 1.0, "stop_loss_perc_short": 4.5,
        "tp_levels": [2.0, 4.0, 8.0], "risk_percentage": 1.0, "renorm_coeff": 1.0, "leverage": "20"
    },
    
    "ETHUSDT_30m": {
        "symbol": "ETHUSDT", "interval": "30", "ma_choice": "VWMA", "ma_period": 300,
        "std_period_long": 14, "std_coeff_long": 1.0, "atr_period_long": 14, "atr_coeff_long": 1.0,
        "ma_distance_perc_long": 1.0, "stop_loss_perc_long": 4.5,
        "std_period_short": 11, "std_coeff_short": 0.5, "atr_period_short": 14, "atr_coeff_short": 1.1,
        "ma_distance_perc_short": 1.4, "stop_loss_perc_short": 4.5,
        "tp_levels": [2.0, 4.0, 8.0], "risk_percentage": 1.0, "renorm_coeff": 1.0, "leverage": "20"
    },
    
    # ========== 15 MINUT ==========
    
    "ADAUSDT_15m": {
        "symbol": "ADAUSDT", "interval": "15", "ma_choice": "VWAP", "ma_period": 1,
        "std_period_long": 14, "std_coeff_long": 0.8, "atr_period_long": 14, "atr_coeff_long": 1.4,
        "ma_distance_perc_long": 1.5, "stop_loss_perc_long": 4.5,
        "std_period_short": 14, "std_coeff_short": 0.8, "atr_period_short": 14, "atr_coeff_short": 1.4,
        "ma_distance_perc_short": 1.5, "stop_loss_perc_short": 4.5,
        "tp_levels": [2.0, 4.0, 8.0], "risk_percentage": 1.0, "renorm_coeff": 1.0, "leverage": "20"
    },
    
    "ATOMUSDT_15m": {
        "symbol": "ATOMUSDT", "interval": "15", "ma_choice": "HMA", "ma_period": 350,
        "std_period_long": 14, "std_coeff_long": 1.0, "atr_period_long": 14, "atr_coeff_long": 1.3,
        "ma_distance_perc_long": 1.1, "stop_loss_perc_long": 4.5,
        "std_period_short": 14, "std_coeff_short": 2.0, "atr_period_short": 14, "atr_coeff_short": 1.7,
        "ma_distance_perc_short": 1.7, "stop_loss_perc_short": 4.5,
        "tp_levels": [2.0, 4.0, 8.0], "risk_percentage": 1.0, "renorm_coeff": 1.0, "leverage": "20"
    },
    
    "AUDIOUSDT_15m": {
        "symbol": "AUDIOUSDT", "interval": "15", "ma_choice": "SMA", "ma_period": 200,
        "std_period_long": 14, "std_coeff_long": 1.2, "atr_period_long": 14, "atr_coeff_long": 1.1,
        "ma_distance_perc_long": 1.1, "stop_loss_perc_long": 4.5,
        "std_period_short": 7, "std_coeff_short": 1.0, "atr_period_short": 14, "atr_coeff_short": 1.0,
        "ma_distance_perc_short": 1.0, "stop_loss_perc_short": 4.5,
        "tp_levels": [2.0, 4.0, 8.0], "risk_percentage": 1.0, "renorm_coeff": 1.0, "leverage": "10"
    },
    
    "AXSUSDT_15m": {
        "symbol": "AXSUSDT", "interval": "15", "ma_choice": "HMA", "ma_period": 350,
        "std_period_long": 7, "std_coeff_long": 0.8, "atr_period_long": 7, "atr_coeff_long": 1.3,
        "ma_distance_perc_long": 1.3, "stop_loss_perc_long": 4.5,
        "std_period_short": 8, "std_coeff_short": 1.0, "atr_period_short": 14, "atr_coeff_short": 1.5,
        "ma_distance_perc_short": 1.5, "stop_loss_perc_short": 4.5,
        "tp_levels": [2.0, 4.0, 8.0], "risk_percentage": 1.0, "renorm_coeff": 1.0, "leverage": "20"
    },
    
    "BELUSDT_15m": {
        "symbol": "BELUSDT", "interval": "15", "ma_choice": "VWAP", "ma_period": 1,
        "std_period_long": 14, "std_coeff_long": 0.8, "atr_period_long": 14, "atr_coeff_long": 1.6,
        "ma_distance_perc_long": 1.5, "stop_loss_perc_long": 4.5,
        "std_period_short": 14, "std_coeff_short": 0.8, "atr_period_short": 14, "atr_coeff_short": 1.5,
        "ma_distance_perc_short": 1.4, "stop_loss_perc_short": 4.5,
        "tp_levels": [2.0, 4.0, 8.0], "risk_percentage": 1.0, "renorm_coeff": 1.0, "leverage": "10"
    },
    
    "COMPUSDT_15m": {
        "symbol": "COMPUSDT", "interval": "15", "ma_choice": "HMA", "ma_period": 400,
        "std_period_long": 14, "std_coeff_long": 1.5, "atr_period_long": 10, "atr_coeff_long": 1.5,
        "ma_distance_perc_long": 1.5, "stop_loss_perc_long": 4.5,
        "std_period_short": 10, "std_coeff_short": 1.7, "atr_period_short": 14, "atr_coeff_short": 1.7,
        "ma_distance_perc_short": 1.3, "stop_loss_perc_short": 4.5,
        "tp_levels": [2.0, 4.0, 8.0], "risk_percentage": 1.0, "renorm_coeff": 1.0, "leverage": "20"
    },
    
    "CRVUSDT_15m": {
        "symbol": "CRVUSDT", "interval": "15", "ma_choice": "VWMA", "ma_period": 300,
        "std_period_long": 9, "std_coeff_long": 0.9, "atr_period_long": 7, "atr_coeff_long": 1.0,
        "ma_distance_perc_long": 0.7, "stop_loss_perc_long": 4.5,
        "std_period_short": 14, "std_coeff_short": 1.0, "atr_period_short": 14, "atr_coeff_short": 1.5,
        "ma_distance_perc_short": 1.5, "stop_loss_perc_short": 4.5,
        "tp_levels": [2.0, 4.0, 8.0], "risk_percentage": 1.0, "renorm_coeff": 1.0, "leverage": "20"
    },
    
    "DOTUSDT_15m": {
        "symbol": "DOTUSDT", "interval": "15", "ma_choice": "HMA", "ma_period": 400,
        "std_period_long": 14, "std_coeff_long": 1.2, "atr_period_long": 14, "atr_coeff_long": 1.0,
        "ma_distance_perc_long": 1.0, "stop_loss_perc_long": 4.5,
        "std_period_short": 10, "std_coeff_short": 1.7, "atr_period_short": 14, "atr_coeff_short": 1.7,
        "ma_distance_perc_short": 1.3, "stop_loss_perc_short": 4.5,
        "tp_levels": [2.0, 4.0, 8.0], "risk_percentage": 1.0, "renorm_coeff": 1.0, "leverage": "20"
    },
    
    "DYDXUSDT_15m": {
        "symbol": "DYDXUSDT", "interval": "15", "ma_choice": "HMA", "ma_period": 400,
        "std_period_long": 13, "std_coeff_long": 0.7, "atr_period_long": 14, "atr_coeff_long": 0.7,
        "ma_distance_perc_long": 0.6, "stop_loss_perc_long": 4.5,
        "std_period_short": 14, "std_coeff_short": 1.0, "atr_period_short": 14, "atr_coeff_short": 1.1,
        "ma_distance_perc_short": 1.0, "stop_loss_perc_short": 4.5,
        "tp_levels": [2.0, 4.0, 8.0], "risk_percentage": 1.0, "renorm_coeff": 1.0, "leverage": "20"
    },
    
    "EGLDUSDT_15m": {
        "symbol": "EGLDUSDT", "interval": "15", "ma_choice": "VWMA", "ma_period": 120,
        "std_period_long": 14, "std_coeff_long": 1.0, "atr_period_long": 14, "atr_coeff_long": 1.6,
        "ma_distance_perc_long": 1.6, "stop_loss_perc_long": 4.5,
        "std_period_short": 14, "std_coeff_short": 2.0, "atr_period_short": 14, "atr_coeff_short": 2.4,
        "ma_distance_perc_short": 1.9, "stop_loss_perc_short": 4.5,
        "tp_levels": [2.0, 4.0, 8.0], "risk_percentage": 1.0, "renorm_coeff": 1.0, "leverage": "20"
    },
    
    "ENJUSDT_15m": {
        "symbol": "ENJUSDT", "interval": "15", "ma_choice": "VWMA", "ma_period": 300,
        "std_period_long": 7, "std_coeff_long": 0.5, "atr_period_long": 14, "atr_coeff_long": 1.0,
        "ma_distance_perc_long": 1.5, "stop_loss_perc_long": 4.5,
        "std_period_short": 14, "std_coeff_short": 0.5, "atr_period_short": 10, "atr_coeff_short": 0.9,
        "ma_distance_perc_short": 0.9, "stop_loss_perc_short": 4.5,
        "tp_levels": [2.0, 4.0, 8.0], "risk_percentage": 1.0, "renorm_coeff": 1.0, "leverage": "20"
    },
    
    "GRTUSDT_15m": {
        "symbol": "GRTUSDT", "interval": "15", "ma_choice": "SMA", "ma_period": 200,
        "std_period_long": 14, "std_coeff_long": 0.4, "atr_period_long": 14, "atr_coeff_long": 2.8,
        "ma_distance_perc_long": 2.6, "stop_loss_perc_long": 4.5,
        "std_period_short": 14, "std_coeff_short": 1.3, "atr_period_short": 14, "atr_coeff_short": 1.3,
        "ma_distance_perc_short": 1.0, "stop_loss_perc_short": 4.5,
        "tp_levels": [2.0, 4.0, 8.0], "risk_percentage": 1.0, "renorm_coeff": 1.0, "leverage": "20"
    },
    
    "MANAUSDT_15m": {
        "symbol": "MANAUSDT", "interval": "15", "ma_choice": "VWMA", "ma_period": 300,
        "std_period_long": 14, "std_coeff_long": 1.0, "atr_period_long": 14, "atr_coeff_long": 1.3,
        "ma_distance_perc_long": 0.8, "stop_loss_perc_long": 4.5,
        "std_period_short": 14, "std_coeff_short": 0.9, "atr_period_short": 14, "atr_coeff_short": 1.2,
        "ma_distance_perc_short": 1.5, "stop_loss_perc_short": 4.5,
        "tp_levels": [2.0, 4.0, 8.0], "risk_percentage": 1.0, "renorm_coeff": 1.0, "leverage": "20"
    },
    
    "NEARUSDT_15m": {
        "symbol": "NEARUSDT", "interval": "15", "ma_choice": "VWAP", "ma_period": 1,
        "std_period_long": 14, "std_coeff_long": 0.8, "atr_period_long": 14, "atr_coeff_long": 1.6,
        "ma_distance_perc_long": 1.5, "stop_loss_perc_long": 4.5,
        "std_period_short": 10, "std_coeff_short": 1.2, "atr_period_short": 14, "atr_coeff_short": 1.5,
        "ma_distance_perc_short": 1.5, "stop_loss_perc_short": 4.5,
        "tp_levels": [2.0, 4.0, 8.0], "risk_percentage": 1.0, "renorm_coeff": 1.0, "leverage": "20"
    },
    
    "ONEUSDT_15m": {
        "symbol": "ONEUSDT", "interval": "15", "ma_choice": "VWAP", "ma_period": 1,
        "std_period_long": 14, "std_coeff_long": 0.8, "atr_period_long": 14, "atr_coeff_long": 1.6,
        "ma_distance_perc_long": 1.5, "stop_loss_perc_long": 4.5,
        "std_period_short": 10, "std_coeff_short": 0.8, "atr_period_short": 14, "atr_coeff_short": 1.5,
        "ma_distance_perc_short": 1.5, "stop_loss_perc_short": 4.5,
        "tp_levels": [2.0, 4.0, 8.0], "risk_percentage": 1.0, "renorm_coeff": 1.0, "leverage": "10"
    },
    
    "RUNEUSDT_15m": {
        "symbol": "RUNEUSDT", "interval": "15", "ma_choice": "VWAP", "ma_period": 1,
        "std_period_long": 14, "std_coeff_long": 0.8, "atr_period_long": 14, "atr_coeff_long": 1.5,
        "ma_distance_perc_long": 1.5, "stop_loss_perc_long": 4.5,
        "std_period_short": 14, "std_coeff_short": 0.8, "atr_period_short": 14, "atr_coeff_short": 1.2,
        "ma_distance_perc_short": 1.5, "stop_loss_perc_short": 4.5,
        "tp_levels": [2.0, 4.0, 8.0], "risk_percentage": 1.0, "renorm_coeff": 1.0, "leverage": "20"
    },
    
    "SANDUSDT_15m": {
        "symbol": "SANDUSDT", "interval": "15", "ma_choice": "VWMA", "ma_period": 250,
        "std_period_long": 14, "std_coeff_long": 1.1, "atr_period_long": 14, "atr_coeff_long": 1.2,
        "ma_distance_perc_long": 1.2, "stop_loss_perc_long": 4.5,
        "std_period_short": 14, "std_coeff_short": 1.0, "atr_period_short": 14, "atr_coeff_short": 1.1,
        "ma_distance_perc_short": 1.0, "stop_loss_perc_short": 4.5,
        "tp_levels": [2.0, 4.0, 8.0], "risk_percentage": 1.0, "renorm_coeff": 1.0, "leverage": "20"
    },
    
    "SOLUSDT_15m": {
        "symbol": "SOLUSDT", "interval": "15", "ma_choice": "HMA", "ma_period": 350,
        "std_period_long": 11, "std_coeff_long": 1.0, "atr_period_long": 14, "atr_coeff_long": 1.3,
        "ma_distance_perc_long": 1.4, "stop_loss_perc_long": 4.5,
        "std_period_short": 12, "std_coeff_short": 1.0, "atr_period_short": 14, "atr_coeff_short": 1.5,
        "ma_distance_perc_short": 1.1, "stop_loss_perc_short": 4.5,
        "tp_levels": [2.0, 4.0, 8.0], "risk_percentage": 1.0, "renorm_coeff": 1.0, "leverage": "20"
    },
    
    "WAVESUSDT_15m": {
        "symbol": "WAVESUSDT", "interval": "15", "ma_choice": "HMA", "ma_period": 380,
        "std_period_long": 7, "std_coeff_long": 1.2, "atr_period_long": 14, "atr_coeff_long": 1.4,
        "ma_distance_perc_long": 1.2, "stop_loss_perc_long": 4.5,
        "std_period_short": 14, "std_coeff_short": 1.6, "atr_period_short": 14, "atr_coeff_short": 1.6,
        "ma_distance_perc_short": 1.4, "stop_loss_perc_short": 4.5,
        "tp_levels": [2.0, 4.0, 8.0], "risk_percentage": 1.0, "renorm_coeff": 1.0, "leverage": "20"
    },
    
    "XRPUSDT_15m": {
        "symbol": "XRPUSDT", "interval": "15", "ma_choice": "VWAP", "ma_period": 1,
        "std_period_long": 14, "std_coeff_long": 1.5, "atr_period_long": 14, "atr_coeff_long": 1.6,
        "ma_distance_perc_long": 1.6, "stop_loss_perc_long": 4.5,
        "std_period_short": 14, "std_coeff_short": 0.8, "atr_period_short": 14, "atr_coeff_short": 1.5,
        "ma_distance_perc_short": 1.5, "stop_loss_perc_short": 4.5,
        "tp_levels": [2.0, 4.0, 8.0], "risk_percentage": 1.0, "renorm_coeff": 1.0, "leverage": "20"
    },
    
    "YFIUSDT_15m": {
        "symbol": "YFIUSDT", "interval": "15", "ma_choice": "VWAP", "ma_period": 1,
        "std_period_long": 14, "std_coeff_long": 1.1, "atr_period_long": 11, "atr_coeff_long": 1.5,
        "ma_distance_perc_long": 1.6, "stop_loss_perc_long": 4.5,
        "std_period_short": 14, "std_coeff_short": 0.8, "atr_period_short": 14, "atr_coeff_short": 1.5,
        "ma_distance_perc_short": 1.5, "stop_loss_perc_short": 4.5,
        "tp_levels": [2.0, 4.0, 8.0], "risk_percentage": 1.0, "renorm_coeff": 1.0, "leverage": "20"
    },
}

BOT_CONFIGS = [
    # ========== WSZYSTKIE PARY Z PINESCRIPT ==========
    # Możesz zakomentować (#) pary których nie chcesz używać
    
    # === 30 MINUT ===
    PRESETS["BNBUSDT_30m"].copy(),
    # PRESETS["BTCUSDT_30m"].copy(),
    # PRESETS["ETHUSDT_30m"].copy(),
    
    # === 15 MINUT ===
    PRESETS["ADAUSDT_15m"].copy(),
    # PRESETS["ATOMUSDT_15m"].copy(),
    PRESETS["AUDIOUSDT_15m"].copy(),
    # PRESETS["AXSUSDT_15m"].copy(),
    PRESETS["BELUSDT_15m"].copy(),
    # PRESETS["COMPUSDT_15m"].copy(),
    # PRESETS["CRVUSDT_15m"].copy(),
    # PRESETS["DOTUSDT_15m"].copy(),
    # PRESETS["DYDXUSDT_15m"].copy(),
    PRESETS["EGLDUSDT_15m"].copy(),
    # PRESETS["ENJUSDT_15m"].copy(),
    PRESETS["GRTUSDT_15m"].copy(),
    # PRESETS["MANAUSDT_15m"].copy(),
    PRESETS["NEARUSDT_15m"].copy(),
    PRESETS["ONEUSDT_15m"].copy(),
    PRESETS["RUNEUSDT_15m"].copy(),
    PRESETS["SANDUSDT_15m"].copy(),
    # PRESETS["SOLUSDT_15m"].copy(),
    # PRESETS["WAVESUSDT_15m"].copy(),
    PRESETS["XRPUSDT_15m"].copy(),
    PRESETS["YFIUSDT_15m"].copy(),
]

# ========== OPCJE DOSTOSOWANIA ==========

# Opcja 1: Zmień ryzyko dla wszystkich par
for config in BOT_CONFIGS:
    config['risk_percentage'] = 1.0  # Możesz zmienić na 0.5, 1.5, 2.0 itd.

# Opcja 2: Jeśli chcesz tylko kilka wybranych par, zakomentuj powyższe i użyj:
# BOT_CONFIGS = [
#     PRESETS["BTCUSDT_30m"].copy(),
#     PRESETS["ETHUSDT_30m"].copy(),
#     PRESETS["SOLUSDT_15m"].copy(),
# ]

# ==============================================================================
# === KLASA DO OBSŁUGI API BYBIT ===
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
        recv_window = "5000"
        if params is None: params = {}

        if method == "POST":
            payload_str = json.dumps(params, separators=(',', ':'))
        else:
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
                del headers['Content-Type']
                response = self.session.get(url, headers=headers, params=params)
            
            response.raise_for_status()
            data = response.json()

            if data.get("retCode") != 0 and data.get("retCode") not in [110025, 110043]:
                print(colored(f"Błąd API Bybit: {data.get('retMsg')} (retCode: {data.get('retCode')})", "red"), flush=True)
                return None
            return data
        except requests.exceptions.HTTPError as http_err:
            if http_err.response.status_code == 403:
                print(colored(f"KRYTYCZNY BŁĄD 403 (Forbidden): Sprawdź uprawnienia klucza API. {http_err}", "red", attrs=['bold']), flush=True)
            else:
                print(colored(f"Błąd HTTP: {http_err}", "red"), flush=True)
            return None
        except Exception as e:
            print(colored(f"Błąd połączenia: {e}", "red"), flush=True)
            return None

    def get_klines(self, symbol, interval, limit=200):
        endpoint = "/v5/market/kline"
        params = {"category": "linear", "symbol": symbol, "interval": interval, "limit": limit}
        data = self._send_request("GET", endpoint, params)
        if data and data.get("retCode") == 0:
            return data["result"]["list"]
        return []

    def get_instrument_info(self, symbol):
        endpoint = "/v5/market/instruments-info"
        params = {"category": "linear", "symbol": symbol}
        data = self._send_request("GET", endpoint, params)
        if data and data.get("retCode") == 0 and data["result"]["list"]:
            info = data["result"]["list"][0]
            return {
                "minOrderQty": float(info["lotSizeFilter"]["minOrderQty"]),
                "qtyStep": float(info["lotSizeFilter"]["qtyStep"]),
                "tickSize": float(info["priceFilter"]["tickSize"])
            }
        return None

    def get_wallet_balance(self):
        endpoint = "/v5/account/wallet-balance"
        params = {"accountType": "UNIFIED"}
        data = self._send_request("GET", endpoint, params)
        if data and data.get("result") and data["result"].get("list"):
            for coin in data["result"]["list"][0]["coin"]:
                if coin["coin"] == "USDT": 
                    return float(coin["walletBalance"])
        return 0

    def get_last_price(self, symbol):
        endpoint = "/v5/market/tickers"
        params = {"category": "linear", "symbol": symbol}
        data = self._send_request("GET", endpoint, params)
        if data and data.get("retCode") == 0 and data["result"]["list"]:
            return float(data["result"]["list"][0]["lastPrice"])
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
        print(colored(f"--- [{symbol}] Zlecenie: {side} {qty}", "yellow"), flush=True)
        return self._send_request("POST", endpoint, params)

    def set_leverage(self, symbol, leverage):
        endpoint = "/v5/position/set-leverage"
        params = {"category": "linear", "symbol": symbol, "buyLeverage": leverage, "sellLeverage": leverage}
        print(colored(f"--- [{symbol}] Ustawianie dźwigni na {leverage}x...", "cyan"), flush=True)
        return self._send_request("POST", endpoint, params)

    def set_trading_stop(self, symbol, stop_loss=None, take_profit=None):
        """Ustawia SL/TP dla pozycji (pojedynczy TP)"""
        endpoint = "/v5/position/trading-stop"
        params = {"category": "linear", "symbol": symbol, "positionIdx": 0}
        if stop_loss: params["stopLoss"] = str(stop_loss)
        if take_profit: params["takeProfit"] = str(take_profit)
        return self._send_request("POST", endpoint, params)
    
    def cancel_all_orders(self, symbol):
        """Anuluje wszystkie aktywne zlecenia dla symbolu"""
        endpoint = "/v5/order/cancel-all"
        params = {"category": "linear", "symbol": symbol}
        return self._send_request("POST", endpoint, params)
    
    def place_tp_sl_order(self, symbol, side, qty, tp_price=None, sl_price=None, reduce_only=True):
        """Składa zlecenie limit z TP/SL (dla partial TP)"""
        endpoint = "/v5/order/create"
        params = {
            "category": "linear",
            "symbol": symbol,
            "side": side,
            "orderType": "Limit",
            "qty": str(qty),
            "price": str(tp_price) if tp_price else None,
            "timeInForce": "GTC",
            "reduceOnly": reduce_only
        }
        if sl_price:
            params["stopLoss"] = str(sl_price)
        
        return self._send_request("POST", endpoint, params)

# ==============================================================================
# === FUNKCJE POMOCNICZE DLA WSKAŹNIKÓW ===
# ==============================================================================

def calculate_sma(data, period):
    closes = [float(d[4]) for d in data]
    if len(closes) < period: return 0
    return sum(closes[-period:]) / period

def calculate_ema(data, period):
    closes = [float(d[4]) for d in data]
    if len(closes) < period: return 0
    multiplier = 2 / (period + 1)
    ema = sum(closes[:period]) / period
    for i in range(period, len(closes)):
        ema = (closes[i] * multiplier) + (ema * (1 - multiplier))
    return ema

def calculate_wma(data, period):
    closes = [float(d[4]) for d in data]
    if len(closes) < period: return 0
    weights = list(range(1, period + 1))
    weighted_sum = sum(closes[-period + i] * weights[i] for i in range(period))
    return weighted_sum / sum(weights)

def calculate_vwma(data, period):
    if len(data) < period: return 0
    weighted_sum = 0
    volume_sum = 0
    for i in range(-period, 0):
        close = float(data[i][4])
        volume = float(data[i][5])
        weighted_sum += close * volume
        volume_sum += volume
    return weighted_sum / volume_sum if volume_sum > 0 else 0

def calculate_vwap(data):
    if not data: return 0
    weighted_sum = 0
    volume_sum = 0
    for candle in data:
        high = float(candle[2])
        low = float(candle[3])
        close = float(candle[4])
        volume = float(candle[5])
        typical_price = (high + low + close) / 3
        weighted_sum += typical_price * volume
        volume_sum += volume
    return weighted_sum / volume_sum if volume_sum > 0 else 0

def calculate_hma(data, period):
    closes = [float(d[4]) for d in data]
    n = len(closes)
    if n < period: return 0
    half_period = int(period / 2)
    sqrt_period = int(math.sqrt(period))
    wma_half = calculate_wma(data[-half_period:], half_period)
    wma_full = calculate_wma(data[-period:], period)
    raw_hma = 2 * wma_half - wma_full
    temp_data = [[0, 0, 0, 0, raw_hma, 0] for _ in range(sqrt_period)]
    return calculate_wma(temp_data, sqrt_period) if len(temp_data) >= sqrt_period else raw_hma

def calculate_rma(data, period):
    closes = [float(d[4]) for d in data]
    if len(closes) < period: return 0
    rma = sum(closes[:period]) / period
    for i in range(period, len(closes)):
        rma = (rma * (period - 1) + closes[i]) / period
    return rma

def calculate_moving_average(data, ma_type, period):
    if ma_type == "SMA": return calculate_sma(data, period)
    elif ma_type == "EMA": return calculate_ema(data, period)
    elif ma_type == "WMA": return calculate_wma(data, period)
    elif ma_type == "VWMA": return calculate_vwma(data, period)
    elif ma_type == "VWAP": return calculate_vwap(data)
    elif ma_type == "HMA": return calculate_hma(data, period)
    elif ma_type == "RMA": return calculate_rma(data, period)
    else: return calculate_sma(data, period)

def calculate_std_dev(data, period):
    closes = [float(d[4]) for d in data]
    if len(closes) < period: return 0
    recent = closes[-period:]
    mean = sum(recent) / period
    variance = sum((x - mean) ** 2 for x in recent) / period
    return math.sqrt(variance)

def calculate_atr(data, period):
    if len(data) < period + 1: return 0
    tr_values = []
    for i in range(1, len(data)):
        high = float(data[i][2])
        low = float(data[i][3])
        prev_close = float(data[i-1][4])
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        tr_values.append(tr)
    if len(tr_values) < period: return 0
    atr = sum(tr_values[:period]) / period
    for i in range(period, len(tr_values)):
        atr = (atr * (period - 1) + tr_values[i]) / period
    return atr

def round_to_tick(price, tick_size):
    return round(price / tick_size) * tick_size

def round_to_step(qty, qty_step):
    return math.floor(qty / qty_step) * qty_step

# ==============================================================================
# === LOGIKA STRATEGII LEGENDX ===
# ==============================================================================

def calculate_signals(config, klines):
    ma_value = calculate_moving_average(klines, config['ma_choice'], config['ma_period'])
    if ma_value == 0: return None, None
    
    # LONG
    std_long = calculate_std_dev(klines, config['std_period_long'])
    atr_long = calculate_atr(klines, config['atr_period_long'])
    std_value_long = std_long * config['std_coeff_long']
    atr_value_long = atr_long * config['atr_coeff_long']
    long_trigger = ma_value * (1 + config['ma_distance_perc_long'] / 100) + atr_value_long + std_value_long
    
    # SHORT
    std_short = calculate_std_dev(klines, config['std_period_short'])
    atr_short = calculate_atr(klines, config['atr_period_short'])
    std_value_short = std_short * config['std_coeff_short']
    atr_value_short = atr_short * config['atr_coeff_short']
    short_trigger = ma_value * (1 - config['ma_distance_perc_short'] / 100) - atr_value_short - std_value_short
    
    return long_trigger, short_trigger

def calculate_position_size(balance, entry_price, stop_loss_price, risk_percentage, instrument_rules):
    loss_in_usdt = balance * (risk_percentage / 100)
    sl_distance = abs(entry_price - stop_loss_price)
    if sl_distance == 0: return 0
    raw_qty = loss_in_usdt / sl_distance
    if raw_qty < instrument_rules["minOrderQty"]:
        print(colored(f"Obliczona ilość {raw_qty:.6f} poniżej minimum {instrument_rules['minOrderQty']}", "red"), flush=True)
        return 0
    adjusted_qty = round_to_step(raw_qty, instrument_rules["qtyStep"])
    return adjusted_qty

def calculate_tp_levels(entry_price, tp_percentages, renorm_coeff, is_long, tick_size):
    """Oblicza poziomy Take Profit"""
    tp_levels = []
    for tp_perc in tp_percentages:
        if is_long:
            tp_price = entry_price * (1 + (tp_perc / renorm_coeff) / 100)
        else:
            tp_price = entry_price * (1 - (tp_perc / renorm_coeff) / 100)
        tp_price = round_to_tick(tp_price, tick_size)
        tp_levels.append(tp_price)
    return tp_levels

def calculate_partial_tp_quantities(total_qty, num_levels, qty_step):
    """
    Oblicza wielkości dla partial take profit
    Strategia: równe części dla każdego poziomu
    
    Przykład (3 poziomy): 
    - Total: 1.0 BTC, 3 poziomy
    - Każdy TP: 0.333 BTC (1.0 / 3)
    
    Przykład (8 poziomów):
    - Total: 1.0 BTC, 8 poziomy
    - Każdy TP: 0.125 BTC (1.0 / 8)
    """
    qty_per_level = total_qty / num_levels
    qty_per_level = round_to_step(qty_per_level, qty_step)
    
    # Upewnij się że suma nie przekracza total
    quantities = []
    remaining = total_qty
    
    for i in range(num_levels - 1):
        if qty_per_level > remaining:
            qty_per_level = remaining
        quantities.append(qty_per_level)
        remaining -= qty_per_level
    
    # Ostatni poziom dostaje resztę
    if remaining > 0:
        remaining = round_to_step(remaining, qty_step)
        quantities.append(remaining)
    else:
        quantities.append(qty_per_level)
    
    return quantities

def place_partial_take_profits(client, symbol, entry_price, total_qty, tp_levels, is_long, instrument_rules, stop_loss_price):
    """
    Ustawia partial take profit zlecenia dla wszystkich poziomów TP
    Domyślnie: 3 poziomy (optymalne dla małego kapitału)
    """
    num_levels = len(tp_levels)
    quantities = calculate_partial_tp_quantities(total_qty, num_levels, instrument_rules["qtyStep"])
    
    side = "Sell" if is_long else "Buy"  # Przeciwna strona do zamknięcia
    
    print(colored(f"[{symbol}] 🎯 Ustawiam {num_levels} poziomów Partial TP:", "cyan"), flush=True)
    
    successful_orders = 0
    
    for i, (tp_price, qty) in enumerate(zip(tp_levels, quantities), 1):
        if qty < instrument_rules["minOrderQty"]:
            print(colored(f"   TP{i}: Pomijam (qty {qty} < minimum {instrument_rules['minOrderQty']})", "yellow"), flush=True)
            continue
        
        try:
            result = client.place_tp_sl_order(
                symbol=symbol,
                side=side,
                qty=qty,
                tp_price=tp_price,
                reduce_only=True
            )
            
            if result and result.get('retCode') == 0:
                successful_orders += 1
                print(colored(f"   ✓ TP{i}: {tp_price:.4f} ({qty} {symbol.replace('USDT', '')})", "green"), flush=True)
            else:
                print(colored(f"   ✗ TP{i}: Błąd - {result.get('retMsg') if result else 'brak odpowiedzi'}", "red"), flush=True)
            
            time.sleep(0.2)  # Krótka przerwa między zleceniami
            
        except Exception as e:
            print(colored(f"   ✗ TP{i}: Exception - {e}", "red"), flush=True)
    
    # Ustaw główny Stop Loss na pozycji
    if stop_loss_price:
        client.set_trading_stop(symbol, stop_loss=stop_loss_price)
        print(colored(f"   ✓ Stop Loss: {stop_loss_price:.4f}", "red"), flush=True)
    
    print(colored(f"[{symbol}] ✅ Ustawiono {successful_orders}/{num_levels} poziomów TP + SL", "green", attrs=['bold']), flush=True)
    
    return successful_orders

# ==============================================================================
# === GŁÓWNA PĘTLA BOTA ===
# ==============================================================================

def run_legendx_strategy(config):
    client = BybitClient(API_KEY, API_SECRET)
    symbol = config['symbol']
    interval = config['interval']
    leverage = config.get('leverage', '20')  # Pobierz leverage z config, domyślnie 20
    
    print(colored(f"\n{'='*70}", "cyan"))
    print(colored(f"[{symbol}] Bot Legendx uruchomiony!", "green", attrs=['bold']))
    print(colored(f"[{symbol}] Interwał: {interval}m | MA: {config['ma_choice']} ({config['ma_period']}) | Ryzyko: {config['risk_percentage']}% | Leverage: {leverage}x", "cyan"))
    print(colored(f"{'='*70}\n", "cyan"))
    
    leverage_set = False
    rules_fetched = False
    instrument_rules = {}
    
    while True:
        try:
            # Pobierz reguły handlowe
            if not rules_fetched:
                rules = client.get_instrument_info(symbol)
                if rules:
                    instrument_rules = rules
                    rules_fetched = True
                    print(colored(f"[{symbol}] ✓ Reguły handlowe załadowane", "green"), flush=True)
                else:
                    print(colored(f"[{symbol}] ⏳ Oczekiwanie na reguły...", "yellow"), flush=True)
                    time.sleep(10)
                    continue
            
            # Ustaw dźwignię
            if not leverage_set:
                result = client.set_leverage(symbol, leverage)
                if result and (result.get('retCode') == 0 or result.get('retCode') in [110025, 110043]):
                    leverage_set = True
                    print(colored(f"[{symbol}] ✓ Dźwignia ustawiona na {leverage}x", "green"), flush=True)
                else:
                    time.sleep(10)
                    continue
            
            # Pobierz dane historyczne
            klines_raw = client.get_klines(symbol, interval, limit=300)
            if not klines_raw or len(klines_raw) < max(config['atr_period_long'], config['atr_period_short']) + 2:
                print(colored(f"[{symbol}] ⏳ Oczekiwanie na dane historyczne...", "yellow"), flush=True)
                time.sleep(60)
                continue
            
            klines_closed = klines_raw[1:]
            klines_closed.reverse()
            
            # Oblicz sygnały
            long_trigger, short_trigger = calculate_signals(config, klines_closed)
            
            if not long_trigger or not short_trigger:
                print(colored(f"[{symbol}] ⚠️ Błąd kalkulacji sygnałów", "yellow"), flush=True)
                time.sleep(30)
                continue
            
            long_trigger = round_to_tick(long_trigger, instrument_rules["tickSize"])
            short_trigger = round_to_tick(short_trigger, instrument_rules["tickSize"])
            
            # Pobierz aktualną cenę i pozycję
            current_price = client.get_last_price(symbol)
            position_side, position_size, avg_price = client.get_position(symbol)
            
            # Status output
            timestamp = time.strftime('%H:%M:%S')
            price_str = f"{current_price:.4f}"
            long_str = colored(f"↑{long_trigger:.4f}", 'green')
            short_str = colored(f"↓{short_trigger:.4f}", 'red')
            
            if position_size > 0:
                current_pl_perc = 0
                if position_side == "Buy":
                    current_pl_perc = ((current_price - avg_price) / avg_price) * 100 * float(leverage)
                elif position_side == "Sell":
                    current_pl_perc = ((avg_price - current_price) / avg_price) * 100 * float(leverage)
                
                pl_color = "green" if current_pl_perc > 0 else "red"
                pl_str = colored(f"P/L: {current_pl_perc:+.2f}%", pl_color)
                pos_str = colored(f"{position_side} ({position_size})", 'cyan')
                print(f"[{symbol}][{timestamp}] 💰 {price_str} | {long_str} {short_str} | {pos_str} | {pl_str}", flush=True)
            else:
                print(f"[{symbol}][{timestamp}] 📊 {price_str} | {long_str} {short_str} | {colored('No Position', 'yellow')}", flush=True)
            
            # === LOGIKA WEJŚCIA ===
            
            # LONG entry
            if position_side == "None" and current_price >= long_trigger * 0.99:
                balance = client.get_wallet_balance()
                stop_loss_price = long_trigger * (1 - config['stop_loss_perc_long'] / 100 / config['renorm_coeff'])
                stop_loss_price = round_to_tick(stop_loss_price, instrument_rules["tickSize"])
                
                qty = calculate_position_size(balance, long_trigger, stop_loss_price, config['risk_percentage'], instrument_rules)
                
                if qty > 0:
                    print(colored(f"\n{'='*70}", "green", attrs=['bold']))
                    print(colored(f"[{symbol}] 🚀 SYGNAŁ LONG!", "green", attrs=['bold']))
                    print(colored(f"{'='*70}", "green", attrs=['bold']))
                    print(f"Entry: {long_trigger:.4f} | SL: {stop_loss_price:.4f} | Qty: {qty}", flush=True)
                    
                    # 1. Otwórz pozycję Market
                    result = client.place_order(symbol, "Buy", qty)
                    
                    if result and result.get('retCode') == 0:
                        time.sleep(2)  # Czekaj na wypełnienie
                        
                        # 2. Pobierz średnią cenę wejścia
                        _, position_size_check, entry_price = client.get_position(symbol)
                        
                        if entry_price > 0 and position_size_check > 0:
                            # 3. Oblicz poziomy TP
                            tp_levels = calculate_tp_levels(
                                entry_price,
                                config['tp_levels'],
                                config['renorm_coeff'],
                                True,  # is_long
                                instrument_rules["tickSize"]
                            )
                            
                            # 4. Anuluj stare zlecenia (jeśli są)
                            client.cancel_all_orders(symbol)
                            time.sleep(0.5)
                            
                            # 5. Ustaw PARTIAL TAKE PROFITS (8 poziomów)
                            place_partial_take_profits(
                                client,
                                symbol,
                                entry_price,
                                position_size_check,
                                tp_levels,
                                True,  # is_long
                                instrument_rules,
                                stop_loss_price
                            )
                            
                            print(colored(f"{'='*70}\n", "green"))
                        else:
                            print(colored(f"[{symbol}] ⚠️ Pozycja nie znaleziona po otwarciu", "yellow"), flush=True)
            
            # SHORT entry
            elif position_side == "None" and current_price <= short_trigger * 1.01:
                balance = client.get_wallet_balance()
                stop_loss_price = short_trigger * (1 + config['stop_loss_perc_short'] / 100 / config['renorm_coeff'])
                stop_loss_price = round_to_tick(stop_loss_price, instrument_rules["tickSize"])
                
                qty = calculate_position_size(balance, short_trigger, stop_loss_price, config['risk_percentage'], instrument_rules)
                
                if qty > 0:
                    print(colored(f"\n{'='*70}", "red", attrs=['bold']))
                    print(colored(f"[{symbol}] ⚠️ SYGNAŁ SHORT!", "red", attrs=['bold']))
                    print(colored(f"{'='*70}", "red", attrs=['bold']))
                    print(f"Entry: {short_trigger:.4f} | SL: {stop_loss_price:.4f} | Qty: {qty}", flush=True)
                    
                    # 1. Otwórz pozycję Market
                    result = client.place_order(symbol, "Sell", qty)
                    
                    if result and result.get('retCode') == 0:
                        time.sleep(2)  # Czekaj na wypełnienie
                        
                        # 2. Pobierz średnią cenę wejścia
                        _, position_size_check, entry_price = client.get_position(symbol)
                        
                        if entry_price > 0 and position_size_check > 0:
                            # 3. Oblicz poziomy TP
                            tp_levels = calculate_tp_levels(
                                entry_price,
                                config['tp_levels'],
                                config['renorm_coeff'],
                                False,  # is_long = False
                                instrument_rules["tickSize"]
                            )
                            
                            # 4. Anuluj stare zlecenia (jeśli są)
                            client.cancel_all_orders(symbol)
                            time.sleep(0.5)
                            
                            # 5. Ustaw PARTIAL TAKE PROFITS (8 poziomów)
                            place_partial_take_profits(
                                client,
                                symbol,
                                entry_price,
                                position_size_check,
                                tp_levels,
                                False,  # is_long = False
                                instrument_rules,
                                stop_loss_price
                            )
                            
                            print(colored(f"{'='*70}\n", "red"))
                        else:
                            print(colored(f"[{symbol}] ⚠️ Pozycja nie znaleziona po otwarciu", "yellow"), flush=True)
            
            # Czekaj do następnej świecy
            now = datetime.datetime.now(datetime.timezone.utc)
            interval_minutes = int(interval)
            minutes_to_next = interval_minutes - (now.minute % interval_minutes)
            seconds_to_wait = (minutes_to_next * 60) - now.second + 5
            
            if seconds_to_wait > 0:
                print(colored(f"[{symbol}] ⏱️  Następna świeca za {int(seconds_to_wait)}s\n", "blue"), flush=True)
                time.sleep(seconds_to_wait)
            
        except Exception as e:
            print(colored(f"[{symbol}] ❌ BŁĄD: {e}", "red", attrs=['bold']), flush=True)
            import traceback
            traceback.print_exc()
            time.sleep(60)

# ==============================================================================
# === START BOTA ===
# ==============================================================================

def print_banner():
    print("\n" + colored("="*70, "cyan"))
    print(colored("    ██╗     ███████╗ ██████╗ ███████╗███╗   ██╗██████╗ ██╗  ██╗", "cyan", attrs=['bold']))
    print(colored("    ██║     ██╔════╝██╔════╝ ██╔════╝████╗  ██║██╔══██╗╚██╗██╔╝", "cyan", attrs=['bold']))
    print(colored("    ██║     █████╗  ██║  ███╗█████╗  ██╔██╗ ██║██║  ██║ ╚███╔╝ ", "cyan", attrs=['bold']))
    print(colored("    ██║     ██╔══╝  ██║   ██║██╔══╝  ██║╚██╗██║██║  ██║ ██╔██╗ ", "cyan", attrs=['bold']))
    print(colored("    ███████╗███████╗╚██████╔╝███████╗██║ ╚████║██████╔╝██╔╝ ██╗", "cyan", attrs=['bold']))
    print(colored("    ╚══════╝╚══════╝ ╚═════╝ ╚══════╝╚═╝  ╚═══╝╚═════╝ ╚═╝  ╚═╝", "cyan", attrs=['bold']))
    print(colored("="*70, "cyan"))
    print(colored("    BYBIT TRADING BOT | MA + ATR + StdDev Strategy", "white", attrs=['bold']))
    print(colored("="*70, "cyan"))

def validate_config(config):
    required_keys = [
        'symbol', 'interval', 'ma_choice', 'ma_period',
        'std_period_long', 'std_coeff_long', 'atr_period_long', 'atr_coeff_long',
        'ma_distance_perc_long', 'stop_loss_perc_long',
        'std_period_short', 'std_coeff_short', 'atr_period_short', 'atr_coeff_short',
        'ma_distance_perc_short', 'stop_loss_perc_short',
        'tp_levels', 'risk_percentage', 'renorm_coeff'
    ]
    
    for key in required_keys:
        if key not in config:
            print(colored(f"❌ Błąd konfiguracji: brak klucza '{key}'", "red"))
            return False
    return True

if __name__ == "__main__":
    print_banner()
    
    # Walidacja API keys
    if "TWOJ" in API_KEY or "CxQFjz7JivQbTnihTP" in API_KEY:
        print(colored("\n⚠️  UWAGA: Nie ustawiono prawdziwych kluczy API!", "yellow", attrs=['bold']))
        print(colored("Edytuj plik i ustaw API_KEY oraz API_SECRET\n", "yellow"))
        print(colored("TESTUJ ZAWSZE NA TESTNET NAJPIERW!", "red", attrs=['bold']))
        print(colored("Zmień BASE_URL na: https://api-testnet.bybit.com\n", "red"))
    
    # Wyświetl konfiguracje
    print(colored("\n📋 Konfiguracje do uruchomienia:", "white", attrs=['bold']))
    print(colored("-" * 70, "white"))
    
    for i, config in enumerate(BOT_CONFIGS, 1):
        if not validate_config(config):
            print(colored(f"❌ Konfiguracja #{i} jest nieprawidłowa. Pomijam.", "red"))
            continue
        
        print(f"\n{colored(f'Bot #{i}:', 'cyan', attrs=['bold'])}")
        print(f"  Symbol:        {colored(config['symbol'], 'white', attrs=['bold'])}")
        print(f"  Interwał:      {config['interval']} minut")
        print(f"  MA Type:       {config['ma_choice']} ({config['ma_period']})")
        print(f"  Ryzyko:        {config['risk_percentage']}%")
        print(f"  SL Long/Short: {config['stop_loss_perc_long']}% / {config['stop_loss_perc_short']}%")
    
    print(colored("\n" + "="*70, "cyan"))
    print(colored("🚀 Uruchamianie botów...", "green", attrs=['bold']))
    print(colored("="*70 + "\n", "cyan"))
    
    # Uruchom boty w osobnych wątkach
    threads = []
    for i, config in enumerate(BOT_CONFIGS):
        if not validate_config(config):
            continue
        
        thread = threading.Thread(target=run_legendx_strategy, args=(config,))
        thread.daemon = True
        threads.append(thread)
        thread.start()
        print(colored(f"✓ Uruchomiono wątek dla {config['symbol']}", "green"))
        time.sleep(3)
    
    if not threads:
        print(colored("❌ Brak prawidłowych konfiguracji do uruchomienia!", "red"))
        exit(1)
    
    print(colored("\n" + "="*70, "cyan"))
    print(colored("✅ Wszystkie boty uruchomione!", "green", attrs=['bold']))
    print(colored("Naciśnij Ctrl+C aby zatrzymać", "yellow"))
    print(colored("="*70 + "\n", "cyan"))
    
    # Trzymaj główny wątek przy życiu
    try:
        for thread in threads:
            thread.join()
    except KeyboardInterrupt:
        print(colored("\n\n⚠️  Zatrzymywanie botów...", "yellow", attrs=['bold']))
        print(colored("="*70, "yellow"))
        print(colored("✓ Boty zatrzymane. Do zobaczenia!", "green"))
        print(colored("="*70 + "\n", "yellow"))
