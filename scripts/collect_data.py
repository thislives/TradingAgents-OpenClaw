#!/usr/bin/env python3
"""快速采集股票行情+K线数据（Sina API，稳定）"""
import json, os, urllib.request, ssl, time
from datetime import datetime, timedelta

def get_price(code):
    scode = f"sh{code}" if code.startswith('6') else f"sz{code}"
    url = f"https://hq.sinajs.cn/list={scode}"
    req = urllib.request.Request(url, headers={
        'Referer': 'https://finance.sina.com.cn/', 'User-Agent': 'Mozilla/5.0'
    })
    with urllib.request.urlopen(req, timeout=8) as r:
        raw = r.read().decode('gbk')
    raw = raw.split('=')[1].strip('"').strip(';').strip()
    parts = raw.split(',')
    if len(parts) < 10: return None
    cur = float(parts[1]) if parts[1] else 0
    prev = float(parts[2]) if parts[2] else 0
    return {
        "name": parts[0], "code": code,
        "current_price": cur, "prev_close": prev,
        "open": float(parts[3]) if parts[3] else 0,
        "high": float(parts[4]) if parts[4] else 0,
        "low": float(parts[6]) if parts[6] else 0,
        "volume": float(parts[9]) if parts[9] else 0,
        "change": cur - prev,
        "change_pct": (cur-prev)/prev*100 if prev else 0,
    }

def get_kline_sina(code, days=60):
    scode = f"sh{code}" if code.startswith('6') else f"sz{code}"
    url = f"http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={scode}&scale=240&ma=no&datalen={days}"
    req = urllib.request.Request(url, headers={
        'Referer': 'https://finance.sina.com.cn/', 'User-Agent': 'Mozilla/5.0'
    })
    with urllib.request.urlopen(req, timeout=8) as r:
        raw = r.read().decode('utf-8')
    import json as j  # avoid name conflict
    return j.loads(raw.strip())

def calc_indicators(klines):
    """计算均线、MACD、RSI、布林带"""
    if not klines: return {}
    closes = []
    highs = []
    lows = []
    volumes = []
    dates = []
    for item in klines:
        try:
            closes.append(float(item['close']))
            highs.append(float(item['high']))
            lows.append(float(item['low']))
            volumes.append(float(item['volume']))
            dates.append(item['day'])
        except: continue
    if not closes: return {}
    latest = closes[0]
    # 均线
    ma5 = sum(closes[:5])/5 if len(closes)>=5 else sum(closes)/len(closes)
    ma10 = sum(closes[:10])/10 if len(closes)>=10 else sum(closes)/len(closes)
    ma20 = sum(closes[:20])/20 if len(closes)>=20 else sum(closes)/len(closes)
    ma60 = sum(closes)/len(closes) if closes else 0
    # 涨跌幅
    change_5d = (closes[0]-closes[4])/closes[4]*100 if len(closes)>=5 else 0
    change_20d = (closes[0]-closes[19])/closes[19]*100 if len(closes)>=20 else 0
    # RSI
    gains = 0; losses = 0
    for i in range(1, min(15, len(closes))):
        diff = closes[i-1] - closes[i]
        if diff > 0: gains += diff
        else: losses += abs(diff)
    rsi = 50
    if gains+losses > 0:
        rsi = 100 - 100/(1+gains/losses) if losses else 100
    # 布林带
    bb_upper = ma20 + 2*sum(abs(c-ma20) for c in closes[:20])/20 if len(closes)>=20 else ma20+ma20*0.1
    bb_lower = ma20 - 2*sum(abs(c-ma20) for c in closes[:20])/20 if len(closes)>=20 else ma20-ma20*0.1
    # MACD简化
    ema12 = sum(closes[:12])/12 if len(closes)>=12 else sum(closes)/len(closes)
    ema26 = sum(closes[:26])/26 if len(closes)>=26 else sum(closes)/len(closes)
    macd = ema12 - ema26
    return {
        "latest_close": latest, "open": closes[-1] if len(closes)>0 else latest,
        "ma5": round(ma5,2), "ma10": round(ma10,2),
        "ma20": round(ma20,2), "ma60": round(ma60,2),
        "rsi": round(rsi,1),
        "boll_upper": round(bb_upper,2),
        "boll_lower": round(bb_lower,2),
        "boll_mid": round(ma20,2),
        "macd": round(macd,4),
        "change_5d": round(change_5d,2),
        "change_20d": round(change_20d,2),
        "highest": max(closes), "lowest": min(closes),
        "volume_avg_5d": sum(volumes[:5])/5 if len(volumes)>=5 else 0,
        "volume_avg_20d": sum(volumes[:20])/20 if len(volumes)>=20 else 0,
        "total_days": len(closes),
        "first_date": dates[-1] if dates else "",
        "last_date": dates[0] if dates else "",
    }

if __name__ == "__main__":
    import sys
    code = sys.argv[1].strip().zfill(6) if len(sys.argv) > 1 else "300750"
    out_dir = "/tmp/analyst_workflow"
    os.makedirs(out_dir, exist_ok=True)

    result = {"code": code, "collected_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "errors": []}

    # 行情
    print(f"[1/2] 行情: {code}...")
    p = get_price(code)
    if p:
        result["price"] = p
        print(f"  OK: {p['name']} ¥{p['current_price']:.2f} ({p['change_pct']:+.2f}%)")
    else:
        result["errors"].append("price failed")

    # K线
    print(f"[2/2] K线: {code}...")
    try:
        klines = get_kline_sina(code, 60)
        if klines:
            result["klines"] = klines
            result["indicators"] = calc_indicators(klines)
            idx = result["indicators"]
            print(f"  OK: {len(klines)}条K线")
            print(f"  收盘:{idx['latest_close']} MA5:{idx['ma5']} MA10:{idx['ma10']} MA20:{idx['ma20']}")
            print(f"  RSI:{idx['rsi']} MACD:{idx['macd']} 布林:({idx['boll_lower']},{idx['boll_mid']},{idx['boll_upper']})")
            print(f"  5日涨跌:{idx['change_5d']:+.2f}% 20日涨跌:{idx['change_20d']:+.2f}%")
        else:
            result["errors"].append("kline: no data")
            print(f"  FAIL: no data")
    except Exception as e:
        result["errors"].append(f"kline: {e}")
        print(f"  FAIL: {e}")

    # 保存
    out_path = os.path.join(out_dir, f"{code}_data.json")
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, default=str)
    print(f"\n保存: {out_path} ({os.path.getsize(out_path)//1024}KB)")
    print(f"错误: {len(result['errors'])}条")
