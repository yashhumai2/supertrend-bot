import threading
import time
from fastapi import FastAPI
import ccxt
import pandas as pd
import pandas_ta as ta
import requests
from datetime import datetime, timedelta, timezone

app = FastAPI()

# ==========================================
# =============== CONFIG ===================
# ==========================================
BOT_TOKEN = "8965903823:AAErGMaH0mv18qqws3iinwnuNBD_1C77C-w"
CHAT_ID = "1760826142"
SYMBOL = "BTC/USDT"
TIMEFRAME = "5m"

def send_telegram_alert(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message}
    try:
        response = requests.post(url, json=payload)
        if response.status_code != 200:
            print(f"Telegram API Error: {response.text}")
    except Exception as e:
        print(f"Telegram Delivery Failed: {e}")

def trading_bot_loop():
    # Force CCXT to route public requests via the unblocked vision mirror,
    # and restrict market loading to SPOT only so it never calls
    # fapi.binance.com / dapi.binance.com (which 451 on restricted regions).
    exchange = ccxt.binance({
        'enableRateLimit': True,
        'options': {
            'defaultType': 'spot',
            'fetchMarkets': ['spot'],   # stop implicit futures (fapi/dapi) market loading
            'fetchCurrencies': False,   # avoid extra sapi call some setups trigger
        },
        'urls': {
            'api': {
                'public': 'https://data-api.binance.vision/api/v3'
            }
        }
    })

    # One-time confirmation of what actually got loaded, so the log
    # makes it obvious if futures endpoints are (not) being touched.
    try:
        exchange.load_markets()
        types_loaded = set(m.get('type') for m in exchange.markets.values())
        print(f"✅ Markets loaded. Types present: {types_loaded}")
    except Exception as e:
        print(f"⚠️ load_markets() failed: {e}")

    last_processed_candle_time = None
    print("🤖 Live Engine Running: Monitoring Binance via unblocked Data Mirror...")

    while True:
        try:
            # Fetch 400 candles for full Supertrend line calibration
            ohlcv = exchange.fetch_ohlcv(SYMBOL, timeframe=TIMEFRAME, limit=400)
            if not ohlcv:
                time.sleep(10)
                continue

            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            closed_candle = df.iloc[-2]
            current_candle_time = closed_candle['timestamp']

            # Run trend validation only when a 5-minute block closes completely
            if current_candle_time != last_processed_candle_time:

                # Compute Supertrends
                st1 = ta.supertrend(df['high'], df['low'], df['close'], length=13, multiplier=2.0)
                st2 = ta.supertrend(df['high'], df['low'], df['close'], length=13, multiplier=4.0)

                dir1_col = [c for c in st1.columns if 'SUPERTd' in c][0]
                dir2_col = [c for c in st2.columns if 'SUPERTd' in c][0]

                # 1. Look at baseline candle BEFORE the closed one (index -3)
                dir1_prev = st1[dir1_col].iloc[-3]
                dir2_prev = st2[dir2_col].iloc[-3]

                was_both_green = (dir1_prev == 1 and dir2_prev == 1)
                was_both_red = (dir1_prev == -1 and dir2_prev == -1)

                # 2. Look at the newly finalized closed candle (index -2)
                dir1_curr = st1[dir1_col].iloc[-2]
                dir2_curr = st2[dir2_col].iloc[-2]

                is_both_green = (dir1_curr == 1 and dir2_curr == 1)
                is_both_red = (dir1_curr == -1 and dir2_curr == -1)

                # Format to local Indian Standard Time (IST)
                ist_timezone = timezone(timedelta(hours=5, minutes=30))
                readable_time = datetime.fromtimestamp(current_candle_time / 1000, tz=ist_timezone).strftime('%I:%M %p')

                # STRICT CROSSOVER FILTERS
                if is_both_green and not was_both_green:
                    msg = f"🟢 BUY SIGNAL\nBoth Supertrends turned GREEN\nAsset: {SYMBOL}\nTimeframe: {TIMEFRAME}\nBar Closed At: {readable_time}"
                    print(f"👉 Fresh Binance BUY Crossover Arrow Detected at {readable_time}!")
                    send_telegram_alert(msg)

                elif is_both_red and not was_both_red:
                    msg = f"🔴 SELL SIGNAL\nBoth Supertrends turned RED\nAsset: {SYMBOL}\nTimeframe: {TIMEFRAME}\nBar Closed At: {readable_time}"
                    print(f"👉 Fresh Binance SELL Crossover Arrow Detected at {readable_time}!")
                    send_telegram_alert(msg)

                else:
                    print(f"[{readable_time}] Bar closed. Holding current trend structure. No new arrow.")

                last_processed_candle_time = current_candle_time

        except Exception as e:
            print(f"Execution Error: {e}")

        time.sleep(15)

@app.on_event("startup")
def startup_event():
    threading.Thread(target=trading_bot_loop, daemon=True).start()

@app.api_route("/", methods=["GET", "HEAD"])
def home():
    ist_timezone = timezone(timedelta(hours=5, minutes=30))
    return {"status": "active", "engine": "running", "ist_time": str(datetime.now(ist_timezone))}