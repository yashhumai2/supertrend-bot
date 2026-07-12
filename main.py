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
    # Use Kraken: Highly stable public feed for cloud deployments
    exchange = ccxt.kraken({'enableRateLimit': True})
    last_processed_candle_time = None
    
    print("🤖 Live Engine Running: Monitoring strict arrow crossovers...")
    
    while True:
        try:
            # Fetch 400 candles instead of 100 to give the mathematical lines proper warm-up room
            ohlcv = exchange.fetch_ohlcv(SYMBOL, timeframe=TIMEFRAME, limit=400)
            if not ohlcv:
                time.sleep(10)
                continue
                
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            closed_candle = df.iloc[-2]
            current_candle_time = closed_candle['timestamp']
            
            # Run math only once per closed 5-minute bar
            if current_candle_time != last_processed_candle_time:
                
                # Compute Supertrends
                st1 = ta.supertrend(df['high'], df['low'], df['close'], length=13, multiplier=2.0)
                st2 = ta.supertrend(df['high'], df['low'], df['close'], length=13, multiplier=4.0)
                
                dir1_col = [c for c in st1.columns if 'SUPERTd' in c][0]
                dir2_col = [c for c in st2.columns if 'SUPERTd' in c][0]
                
                # 1. Look at the baseline candle BEFORE the closed one (index -3)
                dir1_prev = st1[dir1_col].iloc[-3]
                dir2_prev = st2[dir2_col].iloc[-3]
                
                was_both_green = (dir1_prev == 1 and dir2_prev == 1)
                was_both_red = (dir1_prev == -1 and dir2_prev == -1)
                
                # 2. Look at the newly finalized closed candle (index -2)
                dir1_curr = st1[dir1_col].iloc[-2]
                dir2_curr = st2[dir2_col].iloc[-2]
                
                is_both_green = (dir1_curr == 1 and dir2_curr == 1)
                is_both_red = (dir1_curr == -1 and dir2_curr == -1)
                
                # Setup IST timezone alignment formatting
                ist_timezone = timezone(timedelta(hours=5, minutes=30))
                readable_time = datetime.fromtimestamp(current_candle_time / 1000, tz=ist_timezone).strftime('%I:%M %p')
                
                # STRICT CROSSOVER FILTERS:
                # A BUY arrow prints ONLY if both are green now, but weren't both green on the last candle
                if is_both_green and not was_both_green:
                    msg = f"🟢 BUY SIGNAL\nBoth Supertrends turned GREEN\nAsset: {SYMBOL}\nTimeframe: {TIMEFRAME}\nBar Closed At: {readable_time}"
                    print(f"👉 Fresh BUY Crossover Arrow Detected at {readable_time}!")
                    send_telegram_alert(msg)
                    
                # A SELL arrow prints ONLY if both are red now, but weren't both red on the last candle
                elif is_both_red and not was_both_red:
                    msg = f"🔴 SELL SIGNAL\nBoth Supertrends turned RED\nAsset: {SYMBOL}\nTimeframe: {TIMEFRAME}\nBar Closed At: {readable_time}"
                    print(f"👉 Fresh SELL Crossover Arrow Detected at {readable_time}!")
                    send_telegram_alert(msg)
                
                else:
                    print(f"[{readable_time}] Bar closed. Continuous trend zone maintained. No new arrow.")
                
                last_processed_candle_time = current_candle_time
                
        except Exception as e:
            print(f"Execution Error: {e}")
            
        time.sleep(15)

@app.on_event("startup")
def startup_event():
    threading.Thread(target=trading_bot_loop, daemon=True).start()

# Accept both GET and HEAD methods to keep UptimeRobot happy and healthy
@app.api_route("/", methods=["GET", "HEAD"])
def home():
    ist_timezone = timezone(timedelta(hours=5, minutes=30))
    return {"status": "active", "engine": "running", "ist_time": str(datetime.now(ist_timezone))}