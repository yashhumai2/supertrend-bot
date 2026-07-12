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
    exchange = ccxt.kraken({
        'enableRateLimit': True
    })
    last_processed_candle_time = None
    last_signal = None
    
    print("🤖 Live Engine Running inside Background Thread...")
    
    while True:
        try:
            ohlcv = exchange.fetch_ohlcv(SYMBOL, timeframe=TIMEFRAME, limit=100)
            if not ohlcv:
                time.sleep(10)
                continue
                
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            closed_candle = df.iloc[-2]
            current_candle_time = closed_candle['timestamp']
            
            if current_candle_time != last_processed_candle_time:
                st1 = ta.supertrend(df['high'], df['low'], df['close'], length=13, multiplier=2.0)
                st2 = ta.supertrend(df['high'], df['low'], df['close'], length=13, multiplier=4.0)
                
                dir1_col = [c for c in st1.columns if 'SUPERTd' in c][0]
                dir2_col = [c for c in st2.columns if 'SUPERTd' in c][0]
                
                dir1_prev = st1[dir1_col].iloc[-3]
                dir2_prev = st2[dir2_col].iloc[-3]
                
                if dir1_prev == 1 and dir2_prev == 1:
                    prev_signal = "BUY"
                elif dir1_prev == -1 and dir2_prev == -1:
                    prev_signal = "SELL"
                else:
                    prev_signal = "NEUTRAL"
                    
                if last_signal is None:
                    last_signal = prev_signal
                
                dir1 = st1[dir1_col].iloc[-2]
                dir2 = st2[dir2_col].iloc[-2]
                
                ist_timezone = timezone(timedelta(hours=5, minutes=30))
                readable_time = datetime.fromtimestamp(current_candle_time / 1000, tz=ist_timezone).strftime('%I:%M %p')
                
                if dir1 == 1 and dir2 == 1:
                    current_signal = "BUY"
                elif dir1 == -1 and dir2 == -1:
                    current_signal = "SELL"
                else:
                    current_signal = "NEUTRAL"
                
                if current_signal != last_signal:
                    if current_signal != "NEUTRAL":
                        if current_signal == "BUY":
                            msg = f" BUY SIGNAL\nBoth Supertrends turned GREEN\nAsset: {SYMBOL}\nTimeframe: {TIMEFRAME}\nBar Closed At: {readable_time}"
                        else:
                            msg = f" SELL SIGNAL\nBoth Supertrends turned RED\nAsset: {SYMBOL}\nTimeframe: {TIMEFRAME}\nBar Closed At: {readable_time}"
                        
                        send_telegram_alert(msg)
                    last_signal = current_signal
                
                last_processed_candle_time = current_candle_time
                
        except Exception as e:
            print(f"Execution Error: {e}")
            
        time.sleep(15)

@app.on_event("startup")
def startup_event():
    # Spin up the trading engine in a separated background process thread 
    threading.Thread(target=trading_bot_loop, daemon=True).start()

@app.get("/")
def home():
    # Public web check route to satisfy Render's port checker and external cron pings
    return {"status": "active", "engine": "running", "timestamp": str(datetime.now())}