import time
import requests
import pandas as pd
import pandas_ta as ta
import ccxt
from datetime import datetime, timedelta, timezone

# ==========================================
# =============== CONFIG ===================
# ==========================================
BOT_TOKEN = "8965903823:AAErGMaH0mv18qqws3iinwnuNBD_1C77C-w"
CHAT_ID = "1760826142"
SYMBOL = "BTC/USDT"
TIMEFRAME = "5m"

ST1_LENGTH, ST1_MULT = 13, 2.0   # Supertrend #1: ATR length 13, Factor 2
ST2_LENGTH, ST2_MULT = 13, 4.0   # Supertrend #2: ATR length 13, Factor 4

IST = timezone(timedelta(hours=5, minutes=30))


def send_telegram_alert(message: str):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": CHAT_ID, "text": message}, timeout=10)
        if r.status_code != 200:
            print(f"Telegram API Error: {r.text}")
    except Exception as e:
        print(f"Telegram Delivery Failed: {e}")


def get_exchange():
    # Restrict to spot-only market loading and route public data through
    # the unblocked data-vision mirror (avoids fapi/dapi 451 errors).
    return ccxt.binance({
        'enableRateLimit': True,
        'options': {
            'defaultType': 'spot',
            'fetchMarkets': ['spot'],
            'fetchCurrencies': False,
        },
        'urls': {
            'api': {
                'public': 'https://data-api.binance.vision/api/v3'
            }
        }
    })


def fetch_candles(exchange, limit=400):
    ohlcv = exchange.fetch_ohlcv(SYMBOL, timeframe=TIMEFRAME, limit=limit)
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    return df


def get_supertrend_direction(df, length, mult):
    st = ta.supertrend(df['high'], df['low'], df['close'], length=length, multiplier=mult)
    dir_col = [c for c in st.columns if 'SUPERTd' in c][0]
    return st[dir_col]


def main_loop():
    exchange = get_exchange()
    last_processed_candle_time = None

    print("🤖 Dual Supertrend Engine Running on BTC/USDT (5m)...")

    while True:
        try:
            df = fetch_candles(exchange)
            if df.empty:
                time.sleep(10)
                continue

            closed_candle_time = df.iloc[-2]['timestamp']

            # Only evaluate once per newly closed 5m candle
            if closed_candle_time != last_processed_candle_time:

                dir1 = get_supertrend_direction(df, ST1_LENGTH, ST1_MULT)
                dir2 = get_supertrend_direction(df, ST2_LENGTH, ST2_MULT)

                # Previous fully-closed candle (baseline, index -3)
                prev_green = dir1.iloc[-3] == 1 and dir2.iloc[-3] == 1
                prev_red = dir1.iloc[-3] == -1 and dir2.iloc[-3] == -1

                # Newly closed candle (index -2)
                curr_green = dir1.iloc[-2] == 1 and dir2.iloc[-2] == 1
                curr_red = dir1.iloc[-2] == -1 and dir2.iloc[-2] == -1

                readable_time = datetime.fromtimestamp(
                    closed_candle_time / 1000, tz=IST
                ).strftime('%I:%M %p')

                if curr_green and not prev_green:
                    msg = (f"🟢 BUY SIGNAL\n"
                           f"Both Supertrends turned GREEN\n"
                           f"Asset: {SYMBOL}\nTimeframe: {TIMEFRAME}\n"
                           f"Bar Closed At: {readable_time}")
                    print(f"👉 BUY crossover at {readable_time}")
                    send_telegram_alert(msg)

                elif curr_red and not prev_red:
                    msg = (f"🔴 SELL SIGNAL\n"
                           f"Both Supertrends turned RED\n"
                           f"Asset: {SYMBOL}\nTimeframe: {TIMEFRAME}\n"
                           f"Bar Closed At: {readable_time}")
                    print(f"👉 SELL crossover at {readable_time}")
                    send_telegram_alert(msg)

                else:
                    print(f"[{readable_time}] No new crossover. Trend unchanged.")

                last_processed_candle_time = closed_candle_time

        except Exception as e:
            print(f"Execution Error: {e}")

        time.sleep(15)


if __name__ == "__main__":
    main_loop()