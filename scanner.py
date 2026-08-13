import requests
import pandas as pd
import time

BASE_URL = "https://fapi.binance.com"

TIMEFRAME = "1h"
LIMIT = 100

# Сколько монет проверять
MAX_SYMBOLS = 100


def get_symbols():
    url = BASE_URL + "/fapi/v1/exchangeInfo"
    data = requests.get(url, timeout=10).json()

    symbols = []

    for s in data["symbols"]:
        if (
            s["status"] == "TRADING"
            and s["quoteAsset"] == "USDT"
            and s["contractType"] == "PERPETUAL"
        ):
            symbols.append(s["symbol"])

    return symbols[:MAX_SYMBOLS]


def get_klines(symbol):
    url = BASE_URL + "/fapi/v1/klines"

    params = {
        "symbol": symbol,
        "interval": TIMEFRAME,
        "limit": LIMIT
    }

    r = requests.get(url, params=params, timeout=10)

    if r.status_code != 200:
        return None

    data = r.json()

    if len(data) < 50:
        return None

    df = pd.DataFrame(data, columns=[
        "time",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "close_time",
        "quote_volume",
        "trades",
        "buy_volume",
        "buy_quote_volume",
        "ignore"
    ])

    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col])

    return df


def calculate_indicators(df):

    df["EMA20"] = df["close"].ewm(span=20).mean()
    df["EMA50"] = df["close"].ewm(span=50).mean()

    delta = df["close"].diff()

    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)

    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()

    rs = avg_gain / avg_loss

    df["RSI"] = 100 - (100 / (1 + rs))

    df["VOL_AVG"] = df["volume"].rolling(20).mean()

    df["ATR"] = (
        df["high"] - df["low"]
    ).rolling(14).mean()

    return df


def find_signal(symbol, df):

    last = df.iloc[-1]
    prev = df.iloc[-2]

    score_long = 0
    score_short = 0

    reasons_long = []
    reasons_short = []

    # EMA trend
    if last["EMA20"] > last["EMA50"]:
        score_long += 2
        reasons_long.append("EMA20 > EMA50")

    if last["EMA20"] < last["EMA50"]:
        score_short += 2
        reasons_short.append("EMA20 < EMA50")

    # RSI
    if 50 < last["RSI"] < 70:
        score_long += 1
        reasons_long.append("RSI bullish")

    if 30 < last["RSI"] < 50:
        score_short += 1
        reasons_short.append("RSI bearish")

    # Volume
    if last["volume"] > last["VOL_AVG"] * 1.5:

        if last["close"] > last["open"]:
            score_long += 2
            reasons_long.append("Volume spike + green candle")

        elif last["close"] < last["open"]:
            score_short += 2
            reasons_short.append("Volume spike + red candle")

    # Breakout
    previous_high = df["high"].iloc[-21:-1].max()
    previous_low = df["low"].iloc[-21:-1].min()

    if last["close"] > previous_high:
        score_long += 3
        reasons_long.append("Breakout HIGH")

    if last["close"] < previous_low:
        score_short += 3
        reasons_short.append("Breakout LOW")

    # Candle momentum
    candle_change = (
        (last["close"] - last["open"])
        / last["open"]
    ) * 100

    if candle_change > 1:
        score_long += 1
        reasons_long.append("Strong bullish candle")

    if candle_change < -1:
        score_short += 1
        reasons_short.append("Strong bearish candle")

    # Result
    if score_long >= 5 and score_long > score_short:

        return {
            "symbol": symbol,
            "signal": "LONG",
            "score": score_long,
            "price": last["close"],
            "rsi": last["RSI"],
            "volume": last["volume"],
            "reasons": reasons_long
        }

    if score_short >= 5 and score_short > score_long:

        return {
            "symbol": symbol,
            "signal": "SHORT",
            "score": score_short,
            "price": last["close"],
            "rsi": last["RSI"],
            "volume": last["volume"],
            "reasons": reasons_short
        }

    return None


def main():

    print("=" * 60)
    print("BINANCE FUTURES CRYPTO SCANNER")
    print("TIMEFRAME:", TIMEFRAME)
    print("=" * 60)

    symbols = get_symbols()

    print("Symbols:", len(symbols))
    print()

    results = []

    for i, symbol in enumerate(symbols):

        try:

            df = get_klines(symbol)

            if df is None:
                continue

            df = calculate_indicators(df)

            signal = find_signal(symbol, df)

            if signal:
                results.append(signal)

                print(
                    signal["signal"],
                    signal["symbol"],
                    "SCORE:",
                    signal["score"],
                    "PRICE:",
                    round(signal["price"], 6),
                    "RSI:",
                    round(signal["rsi"], 2)
                )

            print(
                f"\rScanning: {i + 1}/{len(symbols)}",
                end=""
            )

            time.sleep(0.05)

        except Exception:
            continue

    print("\n")
    print("=" * 60)
    print("TOP SIGNALS")
    print("=" * 60)

    results.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    for r in results[:10]:

        print()
        print(
            f"{r['signal']} | "
            f"{r['symbol']} | "
            f"SCORE {r['score']} | "
            f"RSI {r['rsi']:.2f}"
        )

        print(
            "Reasons:",
            ", ".join(r["reasons"])
        )

    print()
    print("=" * 60)


if __name__ == "__main__":
    main()
