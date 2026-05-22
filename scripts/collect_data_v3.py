#!/usr/bin/env python3
"""
V3 数据采集器 — 健壮多源 (Sina+Tencent dual-source, no heavy deps)
产品: 行情/技术指标/财务估值/公告
"""
import json, os, sys, time, urllib.request, ssl
from datetime import datetime

ssl._create_default_https_context = ssl._create_unverified_context
OUT = '/tmp/analyst_workflow'

def fetch(url, timeout=10, retries=3, headers=None):
    hdrs = headers or {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    for a in range(retries):
        try:
            req = urllib.request.Request(url, headers=hdrs)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:
            if a == retries-1: raise
            time.sleep(2*(a+1))

def get_price_tencent(code):
    """腾讯行情: 行情+PE+市值+52周高低"""
    scode = f"sh{code}" if code.startswith('6') else f"sz{code}"
    url = f"https://qt.gtimg.cn/q={scode}"
    raw = fetch(url, headers={'Referer':'https://gu.qq.com/'}).decode('gbk')
    parts = raw.split('~')
    if len(parts) < 50: raise ValueError(f"字段不足({len(parts)})")
    return {
        'name': parts[1], 'code': parts[2],
        'price': float(parts[3]), 'yesterday_close': float(parts[4]),
        'open': float(parts[5]), 'high': float(parts[33]),
        'low': float(parts[34]), 'volume': int(parts[6]),
        'amount': float(parts[37])*10000 if parts[37].replace('.','').isdigit() else 0,
        'change': float(parts[31]), 'change_pct': float(parts[32]),
        'pe': float(parts[39]) if parts[39] != '' else None,
        'turnover': float(parts[38]) if parts[38] != '' else None,
        'market_cap': float(parts[44]) if parts[44] != '' else None,
        'float_cap': float(parts[45]) if parts[45] != '' else None,
        'high_52w': float(parts[47]) if parts[47] != '' else None,
        'low_52w': float(parts[48]) if parts[48] != '' else None,
        'source': 'tencent'
    }

def get_kline_sina(code):
    """Sina日K(60条, 无代理)"""
    scode = f"sh{code}" if code.startswith('6') else f"sz{code}"
    url = f"https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={scode}&scale=240&ma=no&datalen=60"
    raw = fetch(url, headers={'Referer':'https://finance.sina.com.cn/'}).decode('gbk')
    data = json.loads(raw)
    if not data: raise ValueError("K线为空")
    return data

def calc_indicators(kline, current_price):
    """全量技术指标计算"""
    closes = [float(d['close']) for d in kline]
    highs = [float(d['high']) for d in kline]
    lows = [float(d['low']) for d in kline]
    vols = [float(d['volume']) for d in kline]

    # MA
    def ma(n):
        return round(sum(closes[-n:])/n, 2) if len(closes) >= n else None
    ma5, ma10, ma20, ma60 = ma(5), ma(10), ma(20), ma(60)

    # RSI(14)
    gains = losses = 0
    for i in range(-14, 0):
        d = closes[i]-closes[i-1]
        gains += max(d, 0); losses += max(-d, 0)
    rsi = round(100-100/(1+gains/losses), 1) if losses > 0 else 100

    # MACD
    ema12 = ema26 = closes[0]
    ema12_list, ema26_list = [], []
    for c in closes:
        ema12 = c*2/13 + ema12*11/13
        ema26 = c*2/27 + ema26*25/27
        ema12_list.append(ema12)
        ema26_list.append(ema26)
    dif = round(ema12-ema26, 4)
    dea_vals = [ema12_list[i]-ema26_list[i] for i in range(len(closes))]
    dea = round(sum(dea_vals[-9:])/9, 4) if len(dea_vals)>=9 else 0
    macd_hist = round(2*(dif-dea), 4)

    # Bollinger
    boll_mid = ma20 or 0
    if boll_mid and len(closes) >= 20:
        std = (sum((c-boll_mid)**2 for c in closes[-20:])/20)**0.5
        boll_up = round(boll_mid + 2*std, 2)
        boll_lo = round(boll_mid - 2*std, 2)
    else:
        boll_up = boll_lo = None

    # Volume
    avg_v5 = sum(vols[-5:])/5
    avg_v20 = sum(vols[-20:])/20

    # Price changes
    chg_5d = round((closes[-1]/closes[-6]-1)*100, 2) if len(closes)>=6 else None
    chg_20d = round((closes[-1]/closes[-21]-1)*100, 2) if len(closes)>=21 else None

    # Trend
    ma_bull = ma5 and ma10 and ma20 and ma5 > ma10 > ma20
    above_ma20 = current_price > (ma20 or 0)

    return {
        'latest_close': round(closes[-1], 2),
        'data_start': kline[0]['day'], 'data_end': kline[-1]['day'],
        'ma5': ma5, 'ma10': ma10, 'ma20': ma20, 'ma60': ma60,
        'rsi': rsi, 'macd_dif': dif, 'macd_dea': dea, 'macd_hist': macd_hist,
        'boll_upper': boll_up, 'boll_mid': boll_mid, 'boll_lower': boll_lo,
        'avg_vol_5d': int(avg_v5), 'avg_vol_20d': int(avg_v20),
        'vol_ratio': round(avg_v5/avg_v20, 2) if avg_v20>0 else 1,
        'change_5d': chg_5d, 'change_20d': chg_20d,
        'ma_trend': '多头排列' if ma_bull else ('空头排列' if ma5 and ma20 and ma5<ma20 else '震荡'),
        'rsi_zone': '超卖' if rsi<30 else ('超买' if rsi>70 else ('偏强' if rsi>60 else '正常')),
        'support': round(min(lows[-20:]), 2), 'resistance': round(max(highs[-20:]), 2),
        'above_boll_upper': boll_up and current_price > boll_up,
        'above_ma20': above_ma20,
    }

def get_news_sina(code):
    """Sina新闻(不依赖akshare)"""
    try:
        scode = f"sh{code}" if code.startswith('6') else f"sz{code}"
        url = f"https://vip.stock.finance.sina.com.cn/corp/go.php/vCB_AllNewsStock/symbol/{scode}.phtml"
        raw = fetch(url, timeout=8).decode('gbk')
        # Extract news titles via simple parsing
        items = []
        for line in raw.split('\n'):
            if 'target="_blank"' in line and '<a' in line:
                import re
                m = re.search(r'>([^<]{10,100})<', line)
                if m: items.append(m.group(1))
        return items[:10]
    except:
        return []

def main():
    code = sys.argv[1].strip().zfill(6)
    print(f"\n📊 V3数据采集: {code}")

    # 1. 腾讯行情
    print("[1/4] 行情(腾讯)...")
    price = get_price_tencent(code)
    print(f"  ✅ {price['name']} ¥{price['price']} ({price['change_pct']:+.2f}%) "
          f"PE={price['pe']}, 市值={price['market_cap']}亿")

    # 2. K线+指标
    print("[2/4] K线+技术指标(Sina)...")
    kline = get_kline_sina(code)
    ind = calc_indicators(kline, price['price'])
    print(f"  ✅ {len(kline)}条K线({kline[0]['day']}~{kline[-1]['day']})")
    print(f"     RSI={ind['rsi']}({ind['rsi_zone']}) {ind['ma_trend']} "
          f"VolRatio={ind['vol_ratio']}x 20日: {ind['change_20d']:+.2f}%")

    # 3. 新闻公告
    print("[3/4] 新闻(Sina)...")
    news = get_news_sina(code)
    print(f"  ✅ {len(news)}条")

    # 4. 市场环境上下文
    print("[4/4] 市场环境...")
    context = {
        'a_share_rules': {
            't1': 'T+1当日买入次日卖出',
            'limit': '主板±10%, 科创/创业板±20%, ST±5%',
            'min_lot': '主板100股/手, 科创200股/手',
        },
        'valuation_context': f"PE={price['pe']}, A股行业中位数约25-35x, 成长股溢价可达40-60x",
        'market_note': '当前处于年报/一季报密集期，业绩对股价影响权重增大',
    }
    print(f"  ✅ A股规则+估值上下文已加载")

    # Save
    os.makedirs(OUT, exist_ok=True)
    data = {
        'code': code, 'name': price['name'],
        'timestamp': datetime.now().isoformat(),
        'price': price, 'indicators': ind,
        'news': news, 'context': context,
        'kline_dates': {'start': kline[0]['day'], 'end': kline[-1]['day']},
    }
    path = f'{OUT}/{code}_data_v3.json'
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n✅ 完成: {path} ({os.path.getsize(path)//1024}KB)")

if __name__ == '__main__':
    main()
