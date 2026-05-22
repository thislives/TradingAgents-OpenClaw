#!/usr/bin/env python3
"""
A股多Agent投研工作流系统 v1.0
基于 TradingAgents-AStock 框架简化版

架构: 数据采集 → 7 Analyst分析 → Quality Gate → Bull/Bear辩论 → Portfolio Manager → 最终信号
"""

import sys
import json
import time
import urllib.request
import urllib.parse
import ssl
from datetime import datetime
from typing import Optional, Dict, List, Any

# =============================================================================
# 数据层 (data_layer) - 带重试+fallback的行情数据获取
# =============================================================================

class DataLayer:
    """数据采集层：多源获取 + 重试机制 + fallback"""

    def __init__(self, max_retries: int = 3, timeout: int = 10):
        self.max_retries = max_retries
        self.timeout = timeout
        self.errors = []  # 记录所有错误

    def _log_error(self, source: str, method: str, error: str):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        msg = f"[{ts}] {source}.{method} failed: {error}"
        self.errors.append(msg)
        print(f"  ⚠️ {msg}")

    def _create_ssl_context(self):
        """创建SSL上下文"""
        try:
            return ssl.create_default_context()
        except Exception:
            return None

    def _fetch_url(self, url: str, headers: dict = None, proxy: str = None) -> dict:
        """带重试的HTTP请求"""
        if headers is None:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': 'https://www.eastmoney.com/'
            }

        for attempt in range(self.max_retries):
            try:
                req = urllib.request.Request(url, headers=headers)
                if proxy:
                    req.set_proxy(proxy, 'http')

                ctx = self._create_ssl_context()
                kwargs = {'timeout': self.timeout}
                if ctx:
                    kwargs['context'] = ctx

                with urllib.request.urlopen(req, **kwargs) as response:
                    return json.loads(response.read().decode('utf-8'))
            except Exception as e:
                if attempt < self.max_retries - 1:
                    time.sleep(1)
                    continue
                return {"error": str(e)}
        return {"error": "Max retries exceeded"}

    def get_secid(self, code: str) -> str:
        """获取东方财富的 secid"""
        code = str(code).strip()
        if code.startswith('6'):
            return f"1.{code}"
        elif code.startswith('00') or code.startswith('30') or code.startswith('688'):
            return f"0.{code}"
        elif code.startswith('8') or code.startswith('4'):
            return f"0.{code}"
        return f"1.{code}"

    # ---- 实时行情 ----
    def get_price_eastmoney(self, code: str) -> dict:
        """东方财富实时行情"""
        secid = self.get_secid(code)
        url = (f"https://push2.eastmoney.com/api/qt/stock/get"
               f"?secid={secid}&fields=f43,f44,f45,f46,f47,f48,f57,f58,f60,f169,f170,f171")
        return self._fetch_url(url)

    def get_price_sina(self, code: str) -> dict:
        """新浪实时行情 (fallback)"""
        try:
            # 转换代码格式
            if code.startswith('6'):
                scode = f"sh{code}"
            else:
                scode = f"sz{code}"
            url = f"https://hq.sinajs.cn/list={scode}"
            headers = {'Referer': 'https://finance.sina.com.cn/', 'User-Agent': 'Mozilla/5.0'}
            req = urllib.request.Request(url, headers=headers)
            ctx = self._create_ssl_context()
            kwargs = {'timeout': self.timeout}
            if ctx:
                kwargs['context'] = ctx
            with urllib.request.urlopen(req, **kwargs) as response:
                raw = response.read().decode('gbk')
            # 格式: var hq_str_sz300750="宁德时代,414.700,411.630,...";
            if '=' in raw:
                raw = raw.split('=')[1]
            raw = raw.strip('"').strip(';').strip()
            parts = raw.split(',')
            if len(parts) >= 10:
                try:
                    name = parts[0]
                    current_price = float(parts[1]) if parts[1] else 0
                    prev_close = float(parts[2]) if parts[2] else 0
                    open_price = float(parts[3]) if parts[3] else 0
                    high = float(parts[4]) if parts[4] else 0
                    low = float(parts[6]) if parts[6] else 0
                    turnover = float(parts[9]) if parts[9] else 0
                    change_val = current_price - prev_close
                    change_pct = (change_val / prev_close * 100) if prev_close > 0 else 0
                    return {
                        "data": {
                            "f57": code,
                            "f58": name,
                            "f43": str(current_price),
                            "f46": str(change_val),
                            "f44": f"{change_pct:.2f}",
                            "f45": str(high),
                            "f47": str(low),
                            "f48": str(turnover),
                            "f60": str(prev_close),
                        }
                    }
                except (ValueError, IndexError) as e:
                    return {"error": f"Sina parse error: {e}"}
            return {"error": "Sina data format unexpected"}
        except Exception as e:
            return {"error": str(e)}

    def get_price_tencent(self, code: str) -> dict:
        """腾讯实时行情 (fallback)"""
        try:
            scode = f"hk{code}"
            url = f"https://qt.gtimg.cn/q={scode}"
            headers = {'Referer': 'https://gu.qq.com/', 'User-Agent': 'Mozilla/5.0'}
            data = self._fetch_url(url, headers=headers)
            if 'error' not in data:
                raw = data.get('data', {})
                if isinstance(raw, dict):
                    content = raw.get('data', '')
                else:
                    content = str(raw)
                # 格式: v_sz300750="...";
                if '=' in content:
                    content = content.split('=')[1]
                content = content.strip('"').strip(';')
                parts = content.split('~')
                if len(parts) >= 33:
                    try:
                        price_val = float(parts[3]) if parts[3] else 0
                        change_val = float(parts[4]) if parts[4] else 0
                        change_pct_val = float(parts[5]) if parts[5] else 0
                        # 腾讯格式: change_pct 是百分点字符串，如 "4.170" 表示 4.170%
                        return {
                            "data": {
                                "f57": code,
                                "f58": parts[1],
                                "f43": parts[3],
                                "f46": parts[4],
                                "f44": parts[5],
                                "f45": parts[6],
                                "f47": parts[7],
                                "f48": parts[9],
                                "f60": parts[10],
                            }
                        }
                    except (ValueError, IndexError):
                        pass
            return {"error": "Tencent parse failed"}
        except Exception as e:
            return {"error": str(e)}

    def get_price(self, code: str) -> dict:
        """多源获取实时行情，自动fallback"""
        # 主源：新浪（稳定）
        data = self.get_price_sina(code)
        if 'error' not in data and data.get('data'):
            return data

        self._log_error("sina", "get_price", data.get('error', 'no data'))

        # Fallback 1: 东方财富
        data = self.get_price_eastmoney(code)
        if 'error' not in data and data.get('data'):
            return data

        self._log_error("eastmoney", "get_price", data.get('error', 'no data'))

        # Fallback 2: 腾讯
        data = self.get_price_tencent(code)
        if 'error' not in data and data.get('data'):
            return data

        self._log_error("tencent", "get_price", data.get('error', 'no data'))

        return {"error": "All price sources failed", "code": code}

    # ---- K线数据 ----
    def get_kline_eastmoney(self, code: str, days: int = 60) -> dict:
        """东方财富K线"""
        secid = self.get_secid(code)
        end_date = datetime.now().strftime("%Y%m%d")
        start_date_dt = datetime.now()
        for _ in range(days + 60):
            start_date_dt = start_date_dt - __import__('datetime').timedelta(days=1)
        start_date = start_date_dt.strftime("%Y%m%d")
        url = (f"https://push2his.eastmoney.com/api/qt/stock/kline/get"
               f"?secid={secid}&fields1=f1,f2,f3,f4,f5,f6"
               f"&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
               f"&klt=101&fqt=0&beg={start_date}&end={end_date}")
        return self._fetch_url(url)

    def get_kline_sina(self, code: str, days: int = 60) -> dict:
        """新浪K线 (fallback)"""
        try:
            if code.startswith('6'):
                scode = f"sh{code}"
            else:
                scode = f"sz{code}"
            # 使用日K线
            url = (f"http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
                   f"CN_MarketData.getKLineData?symbol={scode}&scale=240&ma=no&datalen={days}")
            headers = {'Referer': 'https://finance.sina.com.cn/', 'User-Agent': 'Mozilla/5.0'}
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                raw = response.read().decode('utf-8')
            data = json.loads(raw.strip())
            if isinstance(data, list) and len(data) > 0:
                klines = []
                for item in data:
                    try:
                        day = item.get('day', '')
                        o = item.get('open', '')
                        close = item.get('close', '')
                        high = item.get('high', '')
                        low = item.get('low', '')
                        volume = item.get('volume', '')
                        klines.append(f"{day},{o},{close},{high},{low},{volume}")
                    except (KeyError, TypeError):
                        pass
                if klines:
                    return {"data": {"klines": klines}}
            return {"error": "Sina kline parse failed"}
        except Exception as e:
            return {"error": str(e)}

    def get_kline(self, code: str, days: int = 60) -> dict:
        """获取K线，自动fallback"""
        data = self.get_kline_eastmoney(code, days)
        if 'error' not in data and data.get('data', {}).get('klines'):
            return data
        self._log_error("eastmoney", "get_kline", data.get('error', 'no data'))

        # Fallback: 新浪
        data = self.get_kline_sina(code, days)
        if 'error' not in data and data.get('data', {}).get('klines'):
            return data
        self._log_error("sina", "get_kline", data.get('error', 'no data'))

        return {"error": "Kline sources failed", "code": code}

    # ---- 财务数据 (akshare) ----
    def get_financials_akshare(self, code: str) -> dict:
        """akshare财务数据"""
        try:
            import akshare as ak
            result = {}
            try:
                # 股票财务分析数据
                df = ak.stock_financial_analysis_indicator(symbol=code, start_year="2020")
                if df is not None and len(df) > 0:
                    result['financial_analysis'] = df.to_dict('records')[-5:] if len(df) >= 5 else df.to_dict('records')
            except Exception:
                pass

            try:
                # 主要财务指标
                df2 = ak.stock_financial_main_data(symbol=code)
                if df2 is not None and len(df2) > 0:
                    result['financial_main'] = df2.to_dict('records')[-5:] if len(df2) >= 5 else df2.to_dict('records')
            except Exception:
                pass

            return result if result else {"error": "No financial data available"}
        except Exception as e:
            return {"error": str(e)}

    def get_financials(self, code: str) -> dict:
        """财务数据获取"""
        data = self.get_financials_akshare(code)
        if 'error' not in data and data:
            return data
        self._log_error("akshare", "get_financials", data.get('error', 'no data'))
        return data

    # ---- 龙虎榜 (akshare) ----
    def get_top_list_akshare(self, code: str) -> dict:
        """akshare龙虎榜数据"""
        try:
            import akshare as ak
            try:
                df = ak.stock_individual_analyze_em(symbol=code)
                if df is not None and len(df) > 0:
                    return {"top_list": df.to_dict('records')}
            except Exception:
                pass
            try:
                df = ak.stock_hot_tgb_em()
                if df is not None and len(df) > 0:
                    return {"hot_rank": df.to_dict('records')}
            except Exception:
                pass
            return {"error": "No top list data available"}
        except Exception as e:
            return {"error": str(e)}

    def get_top_list(self, code: str) -> dict:
        """龙虎榜获取"""
        data = self.get_top_list_akshare(code)
        if 'error' not in data and data.get('top_list'):
            return data
        self._log_error("akshare", "get_top_list", data.get('error', 'no data'))
        return data

    # ---- 资金流 (akshare) ----
    def get_money_flow_akshare(self, code: str) -> dict:
        """akshare资金流数据"""
        try:
            import akshare as ak
            try:
                market = 'sz' if code.startswith(('00', '30', '688')) else 'sh'
                df = ak.stock_individual_fund_flow(stock=code, market=market)
                if df is not None and len(df) > 0:
                    return {"money_flow": df.to_dict('records')}
            except Exception:
                pass
            return {"error": "No money flow data available"}
        except Exception as e:
            return {"error": str(e)}

    def get_money_flow(self, code: str) -> dict:
        """资金流获取"""
        data = self.get_money_flow_akshare(code)
        if 'error' not in data and data:
            return data
        self._log_error("akshare", "get_money_flow", data.get('error', 'no data'))
        return data

    # ---- 新闻舆情 (akshare) ----
    def get_news_akshare(self, code: str) -> dict:
        """akshare新闻舆情"""
        try:
            import akshare as ak
            news_list = []
            try:
                df = ak.stock_news_em(symbol=code)
                if df is not None and len(df) > 0:
                    news_list.extend(df.to_dict('records')[:20])
            except Exception:
                pass
            return {"news": news_list} if news_list else {"error": "No news data available"}
        except Exception as e:
            return {"error": str(e)}

    def get_news(self, code: str) -> dict:
        """新闻舆情获取"""
        data = self.get_news_akshare(code)
        if 'error' not in data and data.get('news'):
            return data
        self._log_error("akshare", "get_news", data.get('error', 'no data'))
        return data

    # ---- 政策数据 (web search) ----
    def get_policy(self, code: str) -> dict:
        """政策数据 - 通过东方财富获取"""
        try:
            secid = self.get_secid(code)
            # 尝试获取公司公告/新闻
            url = f"https://np-anotice-stock.eastmoney.com/api/security/ann?cb=&sr=-1&page_size=5&page_index=1&ann_type=SHA,CYB,SZE&client_source=web&stock_list={secid}"
            data = self._fetch_url(url)
            if 'error' not in data and data.get('data', {}).get('list'):
                announcements = data['data']['list']
                return {"announcements": announcements}
            return {"announcements": []}
        except Exception as e:
            self._log_error("eastmoney", "get_policy", str(e))
            return {"error": str(e)}


# =============================================================================
# 7个Analyst - 每个独立函数，输出结构化分析报告
# =============================================================================

def market_analyst(code: str, data: dict) -> dict:
    """
    市场技术分析 (market analyst)
    分析价格走势、K线形态、均线系统
    """
    try:
        price_data = data.get('price', {})
        kline_data = data.get('kline', {})

        findings = []
        score = "C"
        conclusion = "数据不足，无法判断"

        # 解析价格
        d = price_data.get('data', {})
        if d and not price_data.get('error'):
            name = d.get('f58', code)
            current_price = d.get('f43', 0)
            change_pct = d.get('f44', 0)
            high = d.get('f45', 0)
            low = d.get('f47', 0)
            prev_close = d.get('f60', 0)
            turnover = d.get('f48', 0)

            if current_price and current_price != '0':
                findings.append(f"最新价: {current_price}，涨跌幅: {change_pct}%")
                findings.append(f"最高: {high}，最低: {low}，昨收: {prev_close}")

                # 涨跌判断
                try:
                    change_float = float(change_pct) if isinstance(change_pct, (int, float)) else 0
                    if change_float > 3:
                        findings.append("价格强势，今日涨幅超过3%")
                    elif change_float > 0:
                        findings.append("价格小幅上涨")
                    elif change_float < -3:
                        findings.append("价格弱势，今日跌幅超过3%")
                    elif change_float < 0:
                        findings.append("价格小幅下跌")
                    else:
                        findings.append("价格基本持平")
                except (ValueError, TypeError):
                    pass

                # 涨跌额
                try:
                    change_val = float(d.get('f46', 0))
                    if change_val > 0:
                        findings.append(f"上涨 {change_val} 元")
                    elif change_val < 0:
                        findings.append(f"下跌 {abs(change_val)} 元")
                except (ValueError, TypeError):
                    pass

        # 解析K线
        klines = kline_data.get('data', {}).get('klines', []) if not kline_data.get('error') else []
        if klines and len(klines) >= 5:
            recent_closes = []
            for line in klines[-5:]:
                parts = line.split(',')
                if len(parts) >= 4:
                    try:
                        recent_closes.append(float(parts[2]))
                    except (ValueError, IndexError):
                        pass

            if len(recent_closes) >= 5:
                ma5 = sum(recent_closes) / 5
                latest_close = recent_closes[-1]
                try:
                    change_pct_5d = (latest_close - recent_closes[0]) / recent_closes[0] * 100
                    findings.append(f"5日均线: {ma5:.2f}，最新收盘: {latest_close:.2f}")
                    findings.append(f"5日涨跌: {change_pct_5d:.2f}%")

                    # 均线判断
                    if latest_close > ma5:
                        findings.append("价格站稳5日均线上方，短期强势")
                        score = "B"
                    else:
                        findings.append("价格跌破5日均线，短期弱势")
                        score = "C"

                    # 趋势判断
                    if change_pct_5d > 10:
                        findings.append("5日涨幅超10%，强势上涨趋势")
                        score = "A"
                    elif change_pct_5d > 5:
                        findings.append("5日涨幅5%-10%，多头趋势")
                        if score != "A":
                            score = "B"
                    elif change_pct_5d < -10:
                        findings.append("5日跌幅超10%，强势下跌趋势")
                        score = "D"
                    elif change_pct_5d < -5:
                        findings.append("5日跌幅5%-10%，空头趋势")
                        if score not in ["D", "F"]:
                            score = "C"
                except (ValueError, TypeError, ZeroDivisionError):
                    pass

        if not findings:
            return {
                "analyst": "market",
                "score": "C",
                "findings": ["价格数据不可用"],
                "conclusion": "数据不可用，标记C级"
            }

        # 生成结论
        if score == "A":
            conclusion = "市场技术面强势，建议关注做多机会"
        elif score == "B":
            conclusion = "市场技术面偏多，短线可考虑介入"
        elif score == "C":
            conclusion = "市场技术面中性，建议观望"
        elif score == "D":
            conclusion = "市场技术面偏弱，注意控制风险"
        elif score == "F":
            conclusion = "市场技术面极弱，建议回避"

        return {
            "analyst": "market",
            "score": score,
            "findings": findings,
            "conclusion": conclusion
        }

    except Exception as e:
        return {
            "analyst": "market",
            "score": "C",
            "findings": [f"分析异常: {str(e)}"],
            "conclusion": "数据不可用，标记C级"
        }


def fundamentals_analyst(code: str, data: dict) -> dict:
    """
    基本面分析 (fundamentals analyst)
    分析财务数据、盈利能力、成长性
    """
    try:
        fin_data = data.get('financials', {})

        findings = []
        score = "C"
        conclusion = "数据不足，无法判断"

        if fin_data and not fin_data.get('error'):
            # 财务分析指标
            if fin_data.get('financial_analysis'):
                fa_records = fin_data['financial_analysis']
                if fa_records:
                    latest = fa_records[-1] if isinstance(fa_records, list) else {}
                    try:
                        roe = latest.get('净资产收益率(%)', latest.get('ROE', 0))
                        if roe and roe > 0:
                            findings.append(f"净资产收益率(ROE): {roe}%")
                            if roe > 15:
                                findings.append("ROE优秀，超过15%")
                                score = "A"
                            elif roe > 8:
                                findings.append("ROE良好，在8%-15%区间")
                                score = "B"
                            elif roe > 0:
                                score = "C"
                            else:
                                findings.append("ROE为负，盈利能力存疑")
                                score = "D"
                    except (KeyError, TypeError):
                        pass

                    try:
                        gross_margin = latest.get('销售毛利率(%)', latest.get('grossMargin', 0))
                        if gross_margin and gross_margin > 0:
                            findings.append(f"销售毛利率: {gross_margin}%")
                            if gross_margin > 30:
                                findings.append("毛利率优秀，超过30%，具备定价权")
                                if score == "C":
                                    score = "B"
                            elif gross_margin < 10:
                                findings.append("毛利率偏低，竞争激烈")
                    except (KeyError, TypeError):
                        pass

                    try:
                        revenue_growth = latest.get('营业总收入同比增长率(%)', latest.get('revenueGrowth', 0))
                        if revenue_growth and revenue_growth > 0:
                            findings.append(f"营收同比增长率: {revenue_growth}%")
                            if revenue_growth > 20:
                                findings.append("营收增长强劲，超过20%")
                    except (KeyError, TypeError):
                        pass

            # 主要财务数据
            if fin_data.get('financial_main'):
                fm_records = fin_data['financial_main']
                if fm_records:
                    latest = fm_records[-1] if isinstance(fm_records, list) else {}
                    try:
                        pe = latest.get('市盈率(TTM)', latest.get('PE', 0))
                        if pe and pe > 0:
                            findings.append(f"市盈率(TTM): {pe}")
                            if pe < 20:
                                findings.append("PE估值偏低，具有估值优势")
                                if score == "C":
                                    score = "B"
                            elif pe > 50:
                                findings.append("PE估值偏高，成长预期已充分反映")
                                if score not in ["D", "F"]:
                                    score = "C"
                    except (KeyError, TypeError):
                        pass

        if not findings:
            return {
                "analyst": "fundamentals",
                "score": "C",
                "findings": ["财务数据不可用"],
                "conclusion": "数据不可用，标记C级"
            }

        # 生成结论
        if score == "A":
            conclusion = "基本面优秀，盈利能力强劲，具备长期投资价值"
        elif score == "B":
            conclusion = "基本面良好，财务状况健康"
        elif score == "C":
            conclusion = "基本面一般，需进一步跟踪验证"
        elif score == "D":
            conclusion = "基本面较弱，注意盈利风险"
        elif score == "F":
            conclusion = "基本面存在重大问题，建议回避"

        return {
            "analyst": "fundamentals",
            "score": score,
            "findings": findings,
            "conclusion": conclusion
        }

    except Exception as e:
        return {
            "analyst": "fundamentals",
            "score": "C",
            "findings": [f"分析异常: {str(e)}"],
            "conclusion": "数据不可用，标记C级"
        }


def sentiment_analyst(code: str, data: dict) -> dict:
    """
    资金情绪分析 (sentiment analyst)
    分析资金流向、主力动向、情绪指标
    """
    try:
        money_flow = data.get('money_flow', {})
        top_list = data.get('top_list', {})

        findings = []
        score = "C"
        conclusion = "数据不足，无法判断"

        # 资金流数据
        if money_flow and not money_flow.get('error') and money_flow.get('money_flow'):
            mf_records = money_flow['money_flow']
            if mf_records and len(mf_records) > 0:
                try:
                    # 尝试解析字段
                    if isinstance(mf_records[0], dict):
                        # 找主力净流入相关字段
                        record = mf_records[-1]
                        # 东方财富格式
                        main_net = record.get('主力净流入', record.get('主力净流入净额', 0))
                        super_net = record.get('超大单净流入', record.get('超大单净流入净额', 0))
                        big_net = record.get('大单净流入', record.get('大单净流入净额', 0))

                        if main_net and isinstance(main_net, (int, float)) and main_net != 0:
                            findings.append(f"主力净流入: {main_net / 100000000:.2f}亿元")
                            if main_net > 0:
                                findings.append("主力资金净流入，积极布局")
                                score = "B"
                            else:
                                findings.append("主力资金净流出，谨慎观望")
                                score = "C"
                except (KeyError, TypeError, ValueError):
                    pass

        # 龙虎榜数据
        if top_list and not top_list.get('error') and top_list.get('top_list'):
            tl_records = top_list['top_list']
            if tl_records and len(tl_records) > 0:
                findings.append(f"龙虎榜记录: {len(tl_records)}条")
                try:
                    if isinstance(tl_records[0], dict):
                        # 找买入/卖出相关字段
                        buy_total = 0
                        sell_total = 0
                        for rec in tl_records:
                            buy = rec.get('买入金额', rec.get('买入', 0))
                            sell = rec.get('卖出金额', rec.get('卖出', 0))
                            if isinstance(buy, (int, float)):
                                buy_total += buy
                            if isinstance(sell, (int, float)):
                                sell_total += sell

                        if buy_total > 0 or sell_total > 0:
                            if buy_total > sell_total:
                                findings.append(f"龙虎榜买入>卖出，资金净流入")
                                if score == "C":
                                    score = "B"
                            else:
                                findings.append(f"龙虎榜卖出>买入，资金净流出")
                except (KeyError, TypeError, ValueError):
                    pass

        if not findings:
            return {
                "analyst": "sentiment",
                "score": "C",
                "findings": ["资金流向数据不可用"],
                "conclusion": "数据不可用，标记C级"
            }

        # 生成结论
        if score == "A":
            conclusion = "资金情绪积极，主力大幅净流入，看涨情绪强烈"
        elif score == "B":
            conclusion = "资金情绪偏多，短线资金积极介入"
        elif score == "C":
            conclusion = "资金情绪中性，观望为主"
        elif score == "D":
            conclusion = "资金情绪偏弱，主力净流出"
        elif score == "F":
            conclusion = "资金情绪极弱，主力出逃明显"

        return {
            "analyst": "sentiment",
            "score": score,
            "findings": findings,
            "conclusion": conclusion
        }

    except Exception as e:
        return {
            "analyst": "sentiment",
            "score": "C",
            "findings": [f"分析异常: {str(e)}"],
            "conclusion": "数据不可用，标记C级"
        }


def news_analyst(code: str, data: dict) -> dict:
    """
    新闻舆情分析 (news analyst)
    分析新闻、公告、研报等舆情信息
    """
    try:
        news_data = data.get('news', {})
        policy_data = data.get('policy', {})

        findings = []
        score = "C"
        conclusion = "数据不足，无法判断"

        news_list = news_data.get('news', []) if not news_data.get('error') else []
        ann_list = policy_data.get('announcements', []) if not policy_data.get('error') else []

        total_items = len(news_list) + len(ann_list)

        if total_items == 0:
            return {
                "analyst": "news",
                "score": "C",
                "findings": ["新闻舆情数据不可用"],
                "conclusion": "数据不可用，标记C级"
            }

        findings.append(f"获取到 {len(news_list)} 条新闻，{len(ann_list)} 条公告")

        # 分析新闻关键词
        positive_words = ['业绩增长', '订单', '合作', '突破', '创新', '增持', '回购', '涨停', '强势']
        negative_words = ['减持', '预警', '亏损', '诉讼', '处罚', '跌停', '业绩下滑', '风险']

        positive_count = 0
        negative_count = 0

        # 检查公告
        for ann in ann_list:
            try:
                title = str(ann.get('title', ann.get('公告标题', '')))
                for word in positive_words:
                    if word in title:
                        positive_count += 1
                for word in negative_words:
                    if word in title:
                        negative_count += 1
            except (KeyError, TypeError):
                pass

        # 检查新闻
        for news in news_list:
            try:
                content = str(news.get('content', news.get('内容', '')))[:200]
                for word in positive_words:
                    if word in content:
                        positive_count += 1
                for word in negative_words:
                    if word in content:
                        negative_count += 1
            except (KeyError, TypeError):
                pass

        if positive_count > negative_count:
            findings.append(f"舆情偏正面（正面{positive_count}条 vs 负面{negative_count}条）")
            score = "B"
        elif negative_count > positive_count:
            findings.append(f"舆情偏负面（正面{positive_count}条 vs 负面{negative_count}条）")
            score = "D"
        else:
            findings.append(f"舆情中性（正面{positive_count}条 vs 负面{negative_count}条）")
            score = "C"

        if positive_count >= 3:
            findings.append("正面消息密集发布，市场关注度高")
            if score == "B":
                score = "A"
        elif negative_count >= 3:
            findings.append("负面消息较多，需警惕风险")
            if score == "D":
                score = "F"

        if not findings:
            findings.append("新闻数据有限，无法形成有效判断")

        # 生成结论
        if score == "A":
            conclusion = "新闻舆情积极正面，多重利好共振"
        elif score == "B":
            conclusion = "新闻舆情偏多，整体氛围偏暖"
        elif score == "C":
            conclusion = "新闻舆情中性，无明显方向"
        elif score == "D":
            conclusion = "新闻舆情偏空，需关注风险事件"
        elif score == "F":
            conclusion = "新闻舆情极弱，多重利空压制"

        return {
            "analyst": "news",
            "score": score,
            "findings": findings,
            "conclusion": conclusion
        }

    except Exception as e:
        return {
            "analyst": "news",
            "score": "C",
            "findings": [f"分析异常: {str(e)}"],
            "conclusion": "数据不可用，标记C级"
        }


def policy_analyst(code: str, data: dict) -> dict:
    """
    政策环境分析 (policy analyst)
    分析宏观政策、行业政策对公司影响
    """
    try:
        policy_data = data.get('policy', {})
        price_data = data.get('price', {})

        findings = []
        score = "C"
        conclusion = "数据不足，无法判断"

        ann_list = policy_data.get('announcements', []) if not policy_data.get('error') else []

        # 通过股票代码判断所属板块
        sector_keywords = {
            '科技/半导体': ['科技', '半导体', '芯片', '集成电路', 'AI', '人工智能', '软件'],
            '新能源': ['新能源', '光伏', '锂电', '储能', '电动车', '电池'],
            '医药': ['医药', '生物', '医疗', '疫苗', '中药', '器械'],
            '消费': ['消费', '食品', '饮料', '家电', '纺织', '零售'],
            '金融': ['银行', '保险', '证券', '金融', '信托'],
            '基建': ['基建', '建筑', '工程', '建材', '钢铁', '水泥'],
        }

        # 简单判断行业（基于代码前缀）
        industry = "主板"
        if code.startswith('688'):
            industry = "科创板-科技"
        elif code.startswith('300'):
            industry = "创业板"

        findings.append(f"所属板块: {industry}")

        if ann_list and len(ann_list) > 0:
            findings.append(f"最近公告: {len(ann_list)}条")

            # 分析公告类型
            announcement_types = {}
            for ann in ann_list:
                try:
                    ann_type = ann.get('ann_type', ann.get('类型', '其他'))
                    announcement_types[ann_type] = announcement_types.get(ann_type, 0) + 1
                except (KeyError, TypeError):
                    pass

            for ann_type, count in announcement_types.items():
                findings.append(f"  {ann_type}: {count}条")

            # 检查重大事项
            for ann in ann_list[:5]:
                try:
                    title = str(ann.get('title', ann.get('公告标题', '')))
                    if any(k in title for k in ['收购', '重组', '定增', '激励', '战略']):
                        findings.append(f"重大事项: {title[:30]}")
                except (KeyError, TypeError):
                    pass

            score = "B"
        else:
            findings.append("暂无最新公告披露")
            score = "C"

        if not findings:
            findings.append("政策相关信息有限")

        # 生成结论
        if score == "A":
            conclusion = "政策环境积极，重大战略布局推进中"
        elif score == "B":
            conclusion = "政策环境偏暖，有积极事项推进"
        elif score == "C":
            conclusion = "政策环境中性，无明显催化剂"
        elif score == "D":
            conclusion = "政策环境偏弱，存在政策风险"
        elif score == "F":
            conclusion = "政策环境极弱，受政策明显压制"

        return {
            "analyst": "policy",
            "score": score,
            "findings": findings,
            "conclusion": conclusion
        }

    except Exception as e:
        return {
            "analyst": "policy",
            "score": "C",
            "findings": [f"分析异常: {str(e)}"],
            "conclusion": "数据不可用，标记C级"
        }


def hot_money_analyst(code: str, data: dict) -> dict:
    """
    热钱游资分析 (hot money analyst)
    分析龙虎榜、营业部席位、短线资金动向
    """
    try:
        top_list = data.get('top_list', {})
        money_flow = data.get('money_flow', {})

        findings = []
        score = "C"
        conclusion = "数据不足，无法判断"

        tl_records = top_list.get('top_list', []) if not top_list.get('error') else []

        if tl_records and len(tl_records) > 0:
            findings.append(f"龙虎榜数据: {len(tl_records)}条记录")

            # 分析买卖力量
            try:
                buy_total = 0
                sell_total = 0
                for rec in tl_records:
                    buy = rec.get('买入金额', rec.get('买入', 0))
                    sell = rec.get('卖出金额', rec.get('卖出', 0))
                    if isinstance(buy, (int, float)):
                        buy_total += float(buy)
                    if isinstance(sell, (int, float)):
                        sell_total += float(sell)

                if buy_total > 0 or sell_total > 0:
                    net = buy_total - sell_total
                    if abs(net) > 0:
                        findings.append(f"龙虎榜净额: {net/100000000:.2f}亿元")
                        if net > 0:
                            findings.append("买入席位占优，热钱参与积极")
                            score = "B"
                        else:
                            findings.append("卖出席位占优，热钱撤退明显")
                            score = "D"
            except (ValueError, TypeError, KeyError):
                pass

            # 分析营业部
            broker_names = set()
            for rec in tl_records:
                try:
                    broker = rec.get('营业部', rec.get('买入营业部', ''))
                    if broker:
                        broker_names.add(broker)
                except (KeyError, TypeError):
                    pass

            if broker_names:
                findings.append(f"涉及营业部: {len(broker_names)}个")

        elif money_flow and not money_flow.get('error') and money_flow.get('money_flow'):
            findings.append("龙虎榜暂无数据，转用资金流分析")
            score = "C"
        else:
            return {
                "analyst": "hot_money",
                "score": "C",
                "findings": ["热钱数据不可用"],
                "conclusion": "数据不可用，标记C级"
            }

        if not findings:
            findings.append("热钱数据有限")

        # 生成结论
        if score == "A":
            conclusion = "热钱高度活跃，多路游资强势介入，短线机会突出"
        elif score == "B":
            conclusion = "热钱参与积极，短线资金活跃"
        elif score == "C":
            conclusion = "热钱参与度一般，无明显短线机会"
        elif score == "D":
            conclusion = "热钱参与度低，短线资金撤离"
        elif score == "F":
            conclusion = "热钱明显出逃，短期规避"

        return {
            "analyst": "hot_money",
            "score": score,
            "findings": findings,
            "conclusion": conclusion
        }

    except Exception as e:
        return {
            "analyst": "hot_money",
            "score": "C",
            "findings": [f"分析异常: {str(e)}"],
            "conclusion": "数据不可用，标记C级"
        }


def lockup_analyst(code: str, data: dict) -> dict:
    """
    限售股/解禁分析 (lockup analyst)
    分析解禁压力、股东减持风险、股权结构
    """
    try:
        price_data = data.get('price', {})
        policy_data = data.get('policy', {})

        findings = []
        score = "C"
        conclusion = "数据不足，无法判断"

        # 通过行情数据判断股价位置
        d = price_data.get('data', {})
        if d and not price_data.get('error'):
            try:
                current_price = float(d.get('f43', 0))
                prev_close = float(d.get('f60', 0))
                high = float(d.get('f45', 0))
                low = float(d.get('f47', 0))

                if current_price > 0 and prev_close > 0:
                    position_pct = (current_price - low) / (high - low) * 100 if high > low else 50

                    findings.append(f"当前价: {current_price}，历史区间: {low}-{high}")
                    findings.append(f"价格位置: {position_pct:.1f}%")

                    if position_pct > 80:
                        findings.append("股价处于历史高位，解禁减持压力大")
                        score = "D"
                    elif position_pct > 60:
                        findings.append("股价处于中高位，有一定解禁压力")
                        score = "C"
                    elif position_pct > 40:
                        findings.append("股价处于中间位置，解禁压力中性")
                        score = "B"
                    elif position_pct > 20:
                        findings.append("股价处于中低位，解禁压力较小")
                        score = "B"
                    else:
                        findings.append("股价处于历史低位，解禁减持动力弱")
                        score = "A"
            except (ValueError, TypeError, ZeroDivisionError):
                pass

        # 检查公告中的减持/解禁信息
        ann_list = policy_data.get('announcements', []) if not policy_data.get('error') else []
        for ann in ann_list:
            try:
                title = str(ann.get('title', ann.get('公告标题', '')))
                if any(k in title for k in ['减持', '解禁', '股份流通', '限售']):
                    findings.append(f"相关公告: {title[:40]}")
            except (KeyError, TypeError):
                pass

        if not findings:
            return {
                "analyst": "lockup",
                "score": "C",
                "findings": ["限售股数据不可用"],
                "conclusion": "数据不可用，标记C级"
            }

        # 生成结论
        if score == "A":
            conclusion = "解禁压力极小，股价低位，安全性高"
        elif score == "B":
            conclusion = "解禁压力较小，股价位置适中"
        elif score == "C":
            conclusion = "解禁压力中性，需关注后续公告"
        elif score == "D":
            conclusion = "解禁压力较大，高位减持风险"
        elif score == "F":
            conclusion = "解禁压力极大，高位减持风险突出"

        return {
            "analyst": "lockup",
            "score": score,
            "findings": findings,
            "conclusion": conclusion
        }

    except Exception as e:
        return {
            "analyst": "lockup",
            "score": "C",
            "findings": [f"分析异常: {str(e)}"],
            "conclusion": "数据不可用，标记C级"
        }


# =============================================================================
# Quality Gate - 质量审查
# =============================================================================

def quality_gate(reports: list) -> dict:
    """
    质量审查门控
    Layer 1: 硬检查（report长度<50chars=FAIL，缺失关键字段=扣分）
    Layer 2: 统计A/B级数量，4+ PASS，2-3 LLM_REVIEW，<2 FAIL
    """
    try:
        scores = {}
        valid_reports = []

        # Layer 1: 硬检查
        for report in reports:
            if not isinstance(report, dict):
                continue

            analyst_name = report.get('analyst', 'unknown')
            findings = report.get('findings', [])
            score = report.get('score', 'F')

            # 检查字段完整性
            has_fields = all([
                'analyst' in report,
                'score' in report,
                'findings' in report,
                'conclusion' in report
            ])

            # 检查findings是否为空
            findings_count = len(findings) if isinstance(findings, list) else 0

            # 检查report字符串长度（findings汇总）
            findings_str = str(findings)
            findings_len = len(findings_str)

            # 评分
            if not has_fields:
                scores[analyst_name] = {"status": "FAIL", "reason": "缺失关键字段", "score": "F"}
            elif findings_len < 50:
                scores[analyst_name] = {"status": "FAIL", "reason": f"分析过短({findings_len}chars)", "score": "C"}
            elif score in ["A", "B", "C"]:
                scores[analyst_name] = {"status": "PASS", "reason": "正常", "score": score}
            else:
                scores[analyst_name] = {"status": "PASS", "reason": "正常", "score": score}

        # 统计PASS/FAIL
        passed = sum(1 for v in scores.values() if v["status"] == "PASS")
        failed = sum(1 for v in scores.values() if v["status"] == "FAIL")

        # 有效报告
        valid_reports = [r for r in reports if isinstance(r, dict) and r.get('score')]

        # Layer 2: 质量判定
        score_counts = {"A": 0, "B": 0, "C": 0, "D": 0, "F": 0}
        for report in valid_reports:
            s = report.get('score', 'C')
            if s in score_counts:
                score_counts[s] += 1

        ab_count = score_counts["A"] + score_counts["B"]

        if ab_count >= 4:
            decision = "PASS"
            quality_summary = f"质量优秀：A级{score_counts['A']}个 + B级{score_counts['B']}个 = {ab_count}个高质量报告"
        elif ab_count >= 2:
            decision = "LLM_REVIEW"
            quality_summary = f"质量中等，需人工复核：A级{score_counts['A']}个 + B级{score_counts['B']}个 = {ab_count}个，{score_counts['C']}个C级报告"
        else:
            decision = "FAIL"
            quality_summary = f"质量不足：A级{score_counts['A']}个 + B级{score_counts['B']}个 = {ab_count}个，高级报告过少"

        # 添加详细统计
        quality_summary += f"，其中D级{score_counts['D']}个，F级{score_counts['F']}个"

        return {
            "decision": decision,
            "scores": scores,
            "score_counts": score_counts,
            "quality_summary": quality_summary,
            "passed": passed,
            "failed": failed
        }

    except Exception as e:
        return {
            "decision": "FAIL",
            "scores": {},
            "score_counts": {"A": 0, "B": 0, "C": 0, "D": 0, "F": 0},
            "quality_summary": f"Quality Gate 异常: {str(e)}，默认FAIL",
            "passed": 0,
            "failed": 0
        }


# =============================================================================
# Bull/Bear Debate - 多空辩论
# =============================================================================

def bull_bear_debate(reports: list, quality_summary: str) -> dict:
    """
    多空辩论
    基于7份报告生成多头和空头论据
    """
    try:
        if not reports or len(reports) == 0:
            return {
                "bull": ["数据不足，无法形成多头论据"],
                "bear": ["数据不足，无法形成空头论据"],
                "verdict": "Neutral",
                "reasoning": "报告数量不足，默认中性"
            }

        bull_arguments = []
        bear_arguments = []

        # 收集各analyst的论据
        for report in reports:
            if not isinstance(report, dict):
                continue

            analyst = report.get('analyst', 'unknown')
            score = report.get('score', 'C')
            findings = report.get('findings', [])
            conclusion = report.get('conclusion', '')

            if not isinstance(findings, list):
                continue

            # 多头论据（A/B级 + 正面发现）
            if score in ['A', 'B']:
                if analyst == 'market':
                    for f in findings:
                        if any(kw in f for kw in ['强势', '多头', '上涨', '涨', '高']):
                            bull_arguments.append(f"[市场技术] {f}")
                elif analyst == 'fundamentals':
                    for f in findings:
                        if any(kw in f for kw in ['优秀', '良好', '增长', '强劲', '优势']):
                            bull_arguments.append(f"[基本面] {f}")
                elif analyst == 'sentiment':
                    for f in findings:
                        if any(kw in f for kw in ['净流入', '积极', '介入', '做多']):
                            bull_arguments.append(f"[资金情绪] {f}")
                elif analyst == 'news':
                    for f in findings:
                        if any(kw in f for kw in ['正面', '利好', '积极', '看涨']):
                            bull_arguments.append(f"[新闻舆情] {f}")
                elif analyst == 'policy':
                    for f in findings:
                        if any(kw in f for kw in ['积极', '利好', '战略', '推进']):
                            bull_arguments.append(f"[政策环境] {f}")
                elif analyst == 'hot_money':
                    for f in findings:
                        if any(kw in f for kw in ['积极', '强势', '介入']):
                            bull_arguments.append(f"[热钱游资] {f}")
                elif analyst == 'lockup':
                    for f in findings:
                        if any(kw in f for kw in ['低位', '压力小', '安全']):
                            bull_arguments.append(f"[限售解禁] {f}")

            # 空头论据（D/F级 + 负面发现）
            elif score in ['D', 'F']:
                if analyst == 'market':
                    for f in findings:
                        if any(kw in f for kw in ['弱势', '空头', '下跌', '跌', '低']):
                            bear_arguments.append(f"[市场技术] {f}")
                elif analyst == 'fundamentals':
                    for f in findings:
                        if any(kw in f for kw in ['弱', '亏损', '下滑', '风险', '偏低']):
                            bear_arguments.append(f"[基本面] {f}")
                elif analyst == 'sentiment':
                    for f in findings:
                        if any(kw in f for kw in ['净流出', '撤离', '谨慎', '观望']):
                            bear_arguments.append(f"[资金情绪] {f}")
                elif analyst == 'news':
                    for f in findings:
                        if any(kw in f for kw in ['负面', '利空', '风险', '警惕']):
                            bear_arguments.append(f"[新闻舆情] {f}")
                elif analyst == 'policy':
                    for f in findings:
                        if any(kw in f for kw in ['压制', '风险', '偏弱']):
                            bear_arguments.append(f"[政策环境] {f}")
                elif analyst == 'hot_money':
                    for f in findings:
                        if any(kw in f for kw in ['撤退', '出逃', '撤离', '规避']):
                            bear_arguments.append(f"[热钱游资] {f}")
                elif analyst == 'lockup':
                    for f in findings:
                        if any(kw in f for kw in ['高位', '压力大', '减持']):
                            bear_arguments.append(f"[限售解禁] {f}")

        # 去重
        bull_arguments = list(dict.fromkeys(bull_arguments))
        bear_arguments = list(dict.fromkeys(bear_arguments))

        # 限制数量
        bull_arguments = bull_arguments[:5]
        bear_arguments = bear_arguments[:5]

        # 判断裁决
        if len(bull_arguments) > len(bear_arguments) * 1.5:
            verdict = "Bull"
            reasoning = f"多头论据{len(bull_arguments)}条 vs 空头论据{len(bear_arguments)}条，多头明显占优"
        elif len(bear_arguments) > len(bull_arguments) * 1.5:
            verdict = "Bear"
            reasoning = f"空头论据{len(bear_arguments)}条 vs 多头论据{len(bull_arguments)}条，空头明显占优"
        elif bull_arguments and not bear_arguments:
            verdict = "Bull"
            reasoning = f"纯多头环境，多头{len(bull_arguments)}条，无空头论据"
        elif bear_arguments and not bull_arguments:
            verdict = "Bear"
            reasoning = f"纯空头环境，空头{len(bear_arguments)}条，无多头论据"
        elif bull_arguments > bear_arguments:
            verdict = "Bull"
            reasoning = f"多头论据{len(bull_arguments)}条略占优，空头{len(bear_arguments)}条"
        elif bear_arguments > bull_arguments:
            verdict = "Bear"
            reasoning = f"空头论据{len(bear_arguments)}条略占优，多头{len(bull_arguments)}条"
        else:
            verdict = "Neutral"
            reasoning = f"多空均衡，各{len(bull_arguments)}条论据"

        return {
            "bull": bull_arguments if bull_arguments else ["无明确多头论据"],
            "bear": bear_arguments if bear_arguments else ["无明确空头论据"],
            "verdict": verdict,
            "reasoning": reasoning
        }

    except Exception as e:
        return {
            "bull": [f"辩论异常: {str(e)}"],
            "bear": [f"辩论异常: {str(e)}"],
            "verdict": "Neutral",
            "reasoning": "辩论模块异常，默认中性"
        }


# =============================================================================
# Portfolio Manager - 组合管理/最终信号
# =============================================================================

def portfolio_manager(bull_bear: dict, reports: list, quality: dict) -> dict:
    """
    组合管理器
    基于辩论结果+报告质量做出最终决策
    5级信号体系 + 仓位建议
    """
    try:
        verdict = bull_bear.get('verdict', 'Neutral')
        reasoning_base = bull_bear.get('reasoning', '')

        # 收集评分
        score_a = 0
        score_b = 0
        score_c = 0
        score_d = 0
        score_f = 0

        for report in reports:
            if isinstance(report, dict):
                s = report.get('score', 'C')
                if s == 'A': score_a += 1
                elif s == 'B': score_b += 1
                elif s == 'C': score_c += 1
                elif s == 'D': score_d += 1
                elif s == 'F': score_f += 1

        # 综合评分 (满分100)
        total_score = score_a * 100 + score_b * 80 + score_c * 60 + score_d * 30 + score_f * 0
        max_possible = len(reports) * 100 if reports else 7 * 100
        normalized_score = int(total_score / max_possible * 100) if max_possible > 0 else 50

        # 质量调整
        quality_decision = quality.get('decision', 'FAIL')
        if quality_decision == 'PASS':
            quality_multiplier = 1.0
        elif quality_decision == 'LLM_REVIEW':
            quality_multiplier = 0.9
        else:
            quality_multiplier = 0.8

        adjusted_score = int(normalized_score * quality_multiplier)

        # 信号判定
        if verdict == "Bull" and adjusted_score >= 70:
            signal = "BUY"
            position = "15%-20%仓位"
            reasoning = (f"综合评分{adjusted_score}分，多头信号确认。"
                       f"基本面{'优秀' if score_a >= 2 else '良好' if score_b >= 2 else '一般'}，"
                       f"建议积极布局，仓位{position}。{reasoning_base}")
        elif verdict == "Bull" and adjusted_score >= 50:
            signal = "OVERWEIGHT"
            position = "10%-15%仓位"
            reasoning = (f"综合评分{adjusted_score}分，多头信号偏强。"
                       f"建议适度超配，仓位{position}。{reasoning_base}")
        elif verdict == "Bear" and adjusted_score < 40:
            signal = "SELL"
            position = "0%-5%仓位"
            reasoning = (f"综合评分{adjusted_score}分，空头信号确认。"
                       f"建议减仓或清仓，仓位控制在{position}。{reasoning_base}")
        elif verdict == "Bear" and adjusted_score < 60:
            signal = "UNDERWEIGHT"
            position = "5%-10%仓位"
            reasoning = (f"综合评分{adjusted_score}分，空头信号偏强。"
                       f"建议低配，仓位{position}。{reasoning_base}")
        elif verdict == "Neutral" or (adjusted_score >= 40 and adjusted_score < 70):
            signal = "HOLD"
            position = "5%-10%仓位"
            reasoning = (f"综合评分{adjusted_score}分，多空信号均衡。"
                       f"建议中性持仓，仓位{position}，等待进一步信号。{reasoning_base}")
        else:
            signal = "HOLD"
            position = "5%-10%仓位"
            reasoning = (f"综合评分{adjusted_score}分，信号不明确。"
                       f"建议中性持仓观察，仓位{position}。{reasoning_base}")

        return {
            "signal": signal,
            "score": adjusted_score,
            "position": position,
            "reasoning": reasoning,
            "details": {
                "verdict": verdict,
                "raw_score": normalized_score,
                "quality_multiplier": quality_multiplier,
                "score_breakdown": {
                    "A": score_a, "B": score_b, "C": score_c, "D": score_d, "F": score_f
                }
            }
        }

    except Exception as e:
        return {
            "signal": "HOLD",
            "score": 50,
            "position": "5%-10%仓位",
            "reasoning": f"Portfolio Manager 异常: {str(e)}，默认HOLD",
            "details": {"error": str(e)}
        }


# =============================================================================
# 主工作流 - run_full_analysis
# =============================================================================

def run_full_analysis(code: str, name: str = None) -> dict:
    """
    完整投研工作流
    数据采集 → 7 Analyst分析 → Quality Gate → Bull/Bear辩论 → Portfolio Manager → 最终信号
    """
    start_time = datetime.now()
    timestamp = start_time.strftime("%Y-%m-%d %H:%M:%S")

    print(f"\n{'='*60}")
    print(f"🚀 启动多Agent投研工作流 | 股票: {code} | 时间: {timestamp}")
    print(f"{'='*60}")

    result = {
        "meta": {
            "code": code,
            "name": name or code,
            "start_time": timestamp,
            "workflow_version": "1.0"
        },
        "data_collection": {},
        "analyst_reports": [],
        "quality_gate": {},
        "bull_bear_debate": {},
        "portfolio_signal": {},
        "errors": []
    }

    # ---- Step 1: 数据采集 ----
    print(f"\n📊 Step 1: 数据采集...")
    data_layer = DataLayer(max_retries=3, timeout=10)

    try:
        price_data = data_layer.get_price(code)
        result["data_collection"]["price"] = price_data
        print(f"  ✓ 实时行情: {'成功' if not price_data.get('error') else '失败'}")
    except Exception as e:
        result["data_collection"]["price"] = {"error": str(e)}
        result["errors"].append(f"数据采集-price: {str(e)}")
        print(f"  ✗ 实时行情: {str(e)}")

    try:
        kline_data = data_layer.get_kline(code, days=60)
        result["data_collection"]["kline"] = kline_data
        print(f"  ✓ K线数据: {'成功' if not kline_data.get('error') else '失败'}")
    except Exception as e:
        result["data_collection"]["kline"] = {"error": str(e)}
        result["errors"].append(f"数据采集-kline: {str(e)}")
        print(f"  ✗ K线数据: {str(e)}")

    try:
        financials = data_layer.get_financials(code)
        result["data_collection"]["financials"] = financials
        print(f"  ✓ 财务数据: {'成功' if not financials.get('error') else '失败'}")
    except Exception as e:
        result["data_collection"]["financials"] = {"error": str(e)}
        result["errors"].append(f"数据采集-financials: {str(e)}")
        print(f"  ✗ 财务数据: {str(e)}")

    try:
        top_list = data_layer.get_top_list(code)
        result["data_collection"]["top_list"] = top_list
        print(f"  ✓ 龙虎榜: {'成功' if not top_list.get('error') else '失败'}")
    except Exception as e:
        result["data_collection"]["top_list"] = {"error": str(e)}
        result["errors"].append(f"数据采集-top_list: {str(e)}")
        print(f"  ✗ 龙虎榜: {str(e)}")

    try:
        money_flow = data_layer.get_money_flow(code)
        result["data_collection"]["money_flow"] = money_flow
        print(f"  ✓ 资金流: {'成功' if not money_flow.get('error') else '失败'}")
    except Exception as e:
        result["data_collection"]["money_flow"] = {"error": str(e)}
        result["errors"].append(f"数据采集-money_flow: {str(e)}")
        print(f"  ✗ 资金流: {str(e)}")

    try:
        news_data = data_layer.get_news(code)
        result["data_collection"]["news"] = news_data
        print(f"  ✓ 新闻舆情: {'成功' if not news_data.get('error') else '失败'}")
    except Exception as e:
        result["data_collection"]["news"] = {"error": str(e)}
        result["errors"].append(f"数据采集-news: {str(e)}")
        print(f"  ✗ 新闻舆情: {str(e)}")

    try:
        policy_data = data_layer.get_policy(code)
        result["data_collection"]["policy"] = policy_data
        print(f"  ✓ 政策公告: {'成功' if not policy_data.get('error') else '失败'}")
    except Exception as e:
        result["data_collection"]["policy"] = {"error": str(e)}
        result["errors"].append(f"数据采集-policy: {str(e)}")
        print(f"  ✗ 政策公告: {str(e)}")

    # 记录数据层错误
    result["errors"].extend(data_layer.errors)

    # ---- Step 2: 7个Analyst分析 ----
    print(f"\n🔍 Step 2: 7个Analyst分析...")
    data = result["data_collection"]

    analysts = [
        ("market", market_analyst),
        ("fundamentals", fundamentals_analyst),
        ("sentiment", sentiment_analyst),
        ("news", news_analyst),
        ("policy", policy_analyst),
        ("hot_money", hot_money_analyst),
        ("lockup", lockup_analyst),
    ]

    for analyst_name, analyst_func in analysts:
        try:
            report = analyst_func(code, data)
            result["analyst_reports"].append(report)
            score = report.get('score', '?')
            print(f"  ✓ {analyst_name}: 评分={score}")
        except Exception as e:
            fallback_report = {
                "analyst": analyst_name,
                "score": "C",
                "findings": [f"分析异常: {str(e)}"],
                "conclusion": "数据不可用，标记C级"
            }
            result["analyst_reports"].append(fallback_report)
            result["errors"].append(f"Analyst-{analyst_name}: {str(e)}")
            print(f"  ✗ {analyst_name}: 异常降级C级 - {str(e)}")

    # ---- Step 3: Quality Gate ----
    print(f"\n🚪 Step 3: Quality Gate 审查...")
    try:
        quality = quality_gate(result["analyst_reports"])
        result["quality_gate"] = quality
        decision = quality.get('decision', 'FAIL')
        summary = quality.get('quality_summary', '')
        print(f"  ✓ 决策: {decision} | {summary}")
    except Exception as e:
        result["quality_gate"] = {
            "decision": "FAIL",
            "scores": {},
            "quality_summary": f"Quality Gate 异常: {str(e)}，默认FAIL"
        }
        result["errors"].append(f"Quality Gate: {str(e)}")
        print(f"  ✗ Quality Gate 异常: {str(e)}")

    # ---- Step 4: Bull/Bear Debate ----
    print(f"\n⚔️ Step 4: Bull/Bear 多空辩论...")
    try:
        debate = bull_bear_debate(result["analyst_reports"], result["quality_gate"].get('quality_summary', ''))
        result["bull_bear_debate"] = debate
        verdict = debate.get('verdict', 'Neutral')
        print(f"  ✓ 裁决: {verdict}")
        for b in debate.get('bull', [])[:3]:
            print(f"    多头: {b}")
        for b in debate.get('bear', [])[:3]:
            print(f"    空头: {b}")
    except Exception as e:
        result["bull_bear_debate"] = {
            "bull": ["辩论异常"],
            "bear": ["辩论异常"],
            "verdict": "Neutral",
            "reasoning": f"Bull/Bear辩论异常: {str(e)}"
        }
        result["errors"].append(f"Bull/Bear Debate: {str(e)}")
        print(f"  ✗ Bull/Bear辩论异常: {str(e)}")

    # ---- Step 5: Portfolio Manager ----
    print(f"\n💼 Step 5: Portfolio Manager 决策...")
    try:
        signal = portfolio_manager(
            result["bull_bear_debate"],
            result["analyst_reports"],
            result["quality_gate"]
        )
        result["portfolio_signal"] = signal
        sig = signal.get('signal', 'HOLD')
        pos = signal.get('position', '')
        score = signal.get('score', 0)
        print(f"  ✓ 最终信号: {sig} | 综合评分: {score}分 | 建议仓位: {pos}")
    except Exception as e:
        result["portfolio_signal"] = {
            "signal": "HOLD",
            "score": 50,
            "position": "5%-10%仓位",
            "reasoning": f"Portfolio Manager 异常: {str(e)}，默认HOLD"
        }
        result["errors"].append(f"Portfolio Manager: {str(e)}")
        print(f"  ✗ Portfolio Manager 异常: {str(e)}")

    # ---- 完成 ----
    end_time = datetime.now()
    end_timestamp = end_time.strftime("%Y-%m-%d %H:%M:%S")
    duration = (end_time - start_time).total_seconds()

    result["meta"]["end_time"] = end_timestamp
    result["meta"]["duration_seconds"] = duration

    print(f"\n{'='*60}")
    print(f"✅ 多Agent投研工作流完成 | 耗时: {duration:.2f}秒")
    print(f"{'='*60}")

    return result


# =============================================================================
# 输出格式化
# =============================================================================

def format_report(result: dict) -> str:
    """将结果格式化为可读的报告"""
    lines = []
    lines.append("\n" + "=" * 70)
    lines.append("📊 A股多Agent投研分析报告")
    lines.append("=" * 70)

    meta = result.get('meta', {})
    lines.append(f"\n股票代码: {meta.get('code', 'N/A')}")
    lines.append(f"股票名称: {meta.get('name', meta.get('code', 'N/A'))}")
    lines.append(f"分析时间: {meta.get('start_time', 'N/A')}")
    lines.append(f"工作流版本: {meta.get('workflow_version', 'N/A')}")
    lines.append(f"总耗时: {meta.get('duration_seconds', 0):.2f}秒")

    # 股票基本信息
    price_data = result.get('data_collection', {}).get('price', {})
    if not price_data.get('error') and price_data.get('data'):
        d = price_data['data']
        lines.append(f"\n--- 股票信息 ---")
        lines.append(f"股票名称: {d.get('f58', 'N/A')}")
        lines.append(f"最新价: {d.get('f43', 'N/A')}")
        lines.append(f"涨跌幅: {d.get('f44', 'N/A')}%")
        lines.append(f"最高价: {d.get('f45', 'N/A')}")
        lines.append(f"最低价: {d.get('f47', 'N/A')}")
        lines.append(f"昨收: {d.get('f60', 'N/A')}")
        lines.append(f"成交额: {d.get('f48', 'N/A')}")

    # 7个Analyst报告
    lines.append(f"\n--- 7个Analyst分析报告 ---")
    for report in result.get('analyst_reports', []):
        if isinstance(report, dict):
            lines.append(f"\n【{report.get('analyst', 'N/A')}】评分: {report.get('score', 'N/A')}")
            lines.append(f"  结论: {report.get('conclusion', 'N/A')}")
            findings = report.get('findings', [])
            if findings:
                for f in findings[:5]:
                    lines.append(f"  - {f}")

    # Quality Gate
    qg = result.get('quality_gate', {})
    lines.append(f"\n--- Quality Gate ---")
    lines.append(f"决策: {qg.get('decision', 'N/A')}")
    lines.append(f"质量摘要: {qg.get('quality_summary', 'N/A')}")
    sc = qg.get('score_counts', {})
    lines.append(f"A级: {sc.get('A', 0)}个 | B级: {sc.get('B', 0)}个 | C级: {sc.get('C', 0)}个 | D级: {sc.get('D', 0)}个 | F级: {sc.get('F', 0)}个")

    # Bull/Bear Debate
    bb = result.get('bull_bear_debate', {})
    lines.append(f"\n--- 多空辩论 ---")
    lines.append(f"裁决: {bb.get('verdict', 'N/A')}")
    lines.append(f"推理: {bb.get('reasoning', 'N/A')}")
    lines.append("多头论据:")
    for b in bb.get('bull', []):
        lines.append(f"  + {b}")
    lines.append("空头论据:")
    for b in bb.get('bear', []):
        lines.append(f"  - {b}")

    # 最终信号
    ps = result.get('portfolio_signal', {})
    lines.append(f"\n--- 最终投资信号 ---")
    lines.append(f"信号: 【{ps.get('signal', 'N/A')}】")
    lines.append(f"综合评分: {ps.get('score', 'N/A')}分")
    lines.append(f"建议仓位: {ps.get('position', 'N/A')}")
    lines.append(f"推理: {ps.get('reasoning', 'N/A')}")

    # 错误日志
    errors = result.get('errors', [])
    if errors:
        lines.append(f"\n--- 错误日志 ({len(errors)}条) ---")
        for err in errors[:10]:
            lines.append(f"  ! {err}")
        if len(errors) > 10:
            lines.append(f"  ... 还有{len(errors)-10}条错误")

    lines.append("\n" + "=" * 70)
    lines.append("报告生成完毕")
    lines.append("=" * 70)

    return "\n".join(lines)


# =============================================================================
# Main
# =============================================================================

if __name__ == "__main__":
    code = sys.argv[1] if len(sys.argv) > 1 else "300750"
    name = sys.argv[2] if len(sys.argv) > 2 else None

    print(f"开始分析股票: {code}")

    result = run_full_analysis(code, name)

    # 打印格式化报告
    report_text = format_report(result)
    print(report_text)

    # 保存JSON结果
    json_file = f"/root/.openclaw/workspace/scripts/workflow_result_{code}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    try:
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2, default=str)
        print(f"\n📁 JSON结果已保存: {json_file}")
    except Exception as e:
        print(f"\n⚠️ 保存JSON失败: {str(e)}")