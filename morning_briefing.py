#!/usr/bin/env python3
"""Morning Financial Briefing — Bloomberg-style daily newsletter"""

import smtplib
import ssl
import json
import os
import sys
import datetime
import html as htmlmod
import re
import time
import urllib.request
import urllib.error
import urllib.parse
import xml.etree.ElementTree as ET
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, 'config.json')
AGNES_BASE_URL = os.environ.get('AGNES_BASE_URL', 'https://apihub.agnes-ai.com/v1')
AGNES_MODEL = os.environ.get('AGNES_MODEL', 'agnes-2.0-flash')
RSS_CANDIDATE_LIMIT = 50
NEWSAPI_CANDIDATE_LIMIT = 20
GNEWS_CANDIDATE_LIMIT = 20
NEWS_CANDIDATE_LIMIT = RSS_CANDIDATE_LIMIT + NEWSAPI_CANDIDATE_LIMIT + GNEWS_CANDIDATE_LIMIT

def load_config():
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)

def fetch_rss(url, timeout=15):
    """Fetch and parse an RSS feed, returning list of (title, link, description, pub_date)."""
    items = []
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
        root = ET.fromstring(data)
        # Handle both RSS and Atom
        ns = {}
        for item in root.iter('item'):
            title = item.findtext('title', '') or ''
            link = item.findtext('link', '') or ''
            desc = item.findtext('description', '') or ''
            pub = item.findtext('pubDate', '') or ''
            items.append((title.strip(), link.strip(), desc.strip(), pub.strip()))
        # Atom format
        for entry in root.iter('{http://www.w3.org/2005/Atom}entry'):
            title_el = entry.find('{http://www.w3.org/2005/Atom}title')
            title = title_el.text.strip() if title_el is not None and title_el.text else ''
            link_el = entry.find('{http://www.w3.org/2005/Atom}link')
            link = link_el.get('href', '') if link_el is not None else ''
            desc_el = entry.find('{http://www.w3.org/2005/Atom}summary')
            desc = desc_el.text.strip() if desc_el is not None and desc_el.text else ''
            pub_el = entry.find('{http://www.w3.org/2005/Atom}published')
            pub = pub_el.text.strip() if pub_el is not None and pub_el.text else ''
            if title:
                items.append((title.strip(), link.strip(), desc.strip(), pub.strip()))
    except Exception as e:
        print(f'  [WARN] Failed to fetch {url}: {e}', file=sys.stderr)
    return items

def normalize_candidate(title, link, description, pub_date, source_name, market_data):
    clean_desc = re.sub(r'<[^>]+>', '', description or '')
    analysis = generate_analysis(title, clean_desc, market_data)
    return {
        'title': (title or '').strip(),
        'link': (link or '').strip(),
        'description': clean_desc.strip(),
        'pub_date': (pub_date or '').strip(),
        'source': source_name,
        'analysis': analysis,
    }

def fetch_newsapi_articles(config, market_data):
    cfg = config.get('briefing', {}).get('newsapi', {})
    api_key = os.environ.get('NEWSAPI_KEY') or cfg.get('api_key', '')
    if not api_key:
        return []
    params = {
        'apiKey': api_key,
        'pageSize': str(NEWSAPI_CANDIDATE_LIMIT),
        'sortBy': 'publishedAt',
        'language': cfg.get('language', 'en'),
    }
    if cfg.get('country'):
        params['country'] = cfg['country']
    if cfg.get('q'):
        params['q'] = cfg['q']
    elif cfg.get('sources'):
        params['sources'] = cfg['sources']
    url = 'https://newsapi.org/v2/everything?' + urllib.parse.urlencode(params)
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        articles = data.get('articles', [])[:NEWSAPI_CANDIDATE_LIMIT]
        out = []
        for article in articles:
            out.append(normalize_candidate(
                article.get('title', ''),
                article.get('url', ''),
                article.get('description', '') or article.get('content', ''),
                article.get('publishedAt', ''),
                article.get('source', {}).get('name', 'NewsAPI'),
                market_data
            ))
        return out
    except Exception as e:
        print(f'  [WARN] NewsAPI fetch failed: {e}', file=sys.stderr)
        return []

def fetch_gnews_articles(config, market_data):
    cfg = config.get('briefing', {}).get('gnews', {})
    api_key = os.environ.get('GNEWS_KEY') or cfg.get('api_key', '')
    if not api_key:
        return []
    params = {
        'apikey': api_key,
        'max': str(GNEWS_CANDIDATE_LIMIT),
        'sortby': 'publishedAt',
        'lang': cfg.get('language', 'en'),
    }
    if cfg.get('country'):
        params['country'] = cfg['country']
    if cfg.get('q'):
        params['q'] = cfg['q']
    url = 'https://gnews.io/api/v4/search?' + urllib.parse.urlencode(params)
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        articles = data.get('articles', [])[:GNEWS_CANDIDATE_LIMIT]
        out = []
        for article in articles:
            out.append(normalize_candidate(
                article.get('title', ''),
                article.get('url', ''),
                article.get('description', '') or article.get('content', ''),
                article.get('publishedAt', ''),
                article.get('source', {}).get('name', 'GNews'),
                market_data
            ))
        return out
    except Exception as e:
        print(f'  [WARN] GNews fetch failed: {e}', file=sys.stderr)
        return []

def fetch_yahoo_finance_data(symbol):
    """Fetch current price data from Yahoo Finance (unofficial API)."""
    url = f'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=1d&interval=1d'
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        result = data['chart']['result'][0]
        meta = result['meta']
        current = meta.get('regularMarketPrice', meta.get('chartPreviousClose', 0))
        prev_close = meta.get('chartPreviousClose', current)
        change = current - prev_close
        change_pct = (change / prev_close * 100) if prev_close else 0
        return {
            'price': current,
            'change': 0.0 if abs(change) < 1e-8 else round(change, 2),
            'change_pct': 0.0 if abs(change_pct) < 1e-8 else round(change_pct, 2),
            'name': meta.get('shortName') or meta.get('symbol', symbol)
        }
    except Exception as e:
        print(f'  [WARN] Yahoo Finance data failed for {symbol}: {e}', file=sys.stderr)
        return None

def collect_market_data(config):
    """Fetch all configured market data."""
    m = config['briefing']['market_data_symbols']
    data = {}
    for category, symbols in m.items():
        data[category] = {}
        for name, symbol in symbols.items():
            print(f'  Fetching {name} ({symbol})...', file=sys.stderr)
            result = fetch_yahoo_finance_data(symbol)
            if result:
                data[category][name] = result
            time.sleep(0.3)  # Rate limiting
    return data

def score_news_item(title, desc, link, pub_date, source_weights, keyword_scores):
    """Score a news item by keywords, source authority, and time decay."""
    text = (title + ' ' + desc).lower()
    score = 0
    fire = ['fed', 'federal reserve', 'interest rate decision', 'rate cut', 'rate hike',
            'inflation', 'cpi', 'ppi', 'nonfarm payroll', 'jobs report', 'gdp',
            'recession', 'economic crisis', 'market crash', 'correction', 'bear market']
    critical = ['central bank', 'monetary policy', 'quantitative easing', 'tightening',
                'tariff', 'trade war', 'sanction', 'geopolitical', 'war', 'conflict',
                'ai', 'artificial intelligence', 'nvidia', 'semiconductor',
                'china', 'chinese economy', 'us-china']
    high = ['oil', 'crude', 'opec', 'gold', 'bitcoin', 'crypto',
            'earnings', 'quarterly results', 'guidance',
            'merger', 'acquisition', 'takeover', 'ipo',
            'treasury', 'bond yield', 'credit spread', 'default',
            'banking', 'financial crisis', 'liquidity',
            'dollar', 'currency crisis', 'forex']
    for w in fire:
        if w in text:
            score += keyword_scores.get('fire', 30)
            break
    for w in critical:
        if w in text:
            score += keyword_scores.get('critical', 25)
            break
    for w in high:
        if w in text:
            score += keyword_scores.get('high', 20)
            break
    for domain, weight in source_weights.items():
        if domain in link.lower():
            score += weight
            break
    else:
        score += source_weights.get('default', 10)
    import email.utils as eut
    try:
        parsed = eut.parsedate_to_datetime(pub_date)
        now = datetime.datetime.now(parsed.tzinfo) if parsed.tzinfo else datetime.datetime.now()
        hours_ago = (now - parsed).total_seconds() / 3600
        decay = max(0.0, 1.0 - (hours_ago / 48.0))
        score = int(score * (0.5 + 0.5 * decay))
    except:
        pass
    return score

def collect_news(config, market_data):
    print('  Fetching financial news...', file=sys.stderr)
    all_items = []
    seen_links = set()
    sw = config['briefing'].get('source_weights', {})
    ks = config['briefing'].get('keyword_scores', {})
    for url in config['briefing'].get('news_sources', []):
        items = fetch_rss(url)
        for title, link, desc, pub in items:
            if link and link not in seen_links:
                seen_links.add(link)
                clean_desc = re.sub(r'<[^>]+>', '', desc)
                analysis = generate_analysis(title, clean_desc, market_data)
                score = score_news_item(title, clean_desc, link, pub, sw, ks)
                all_items.append({
                    'title': title.strip(),
                    'link': link.strip(),
                    'description': clean_desc.strip(),
                    'pub_date': pub.strip(),
                    'source': 'rss',
                    'analysis': analysis,
                    'score': score
                })
    for item in fetch_newsapi_articles(config, market_data):
        marker = item.get('link') or item.get('title')
        if marker and marker not in seen_links:
            seen_links.add(marker)
            item['score'] = max(item.get('score', 0), score_news_item(item['title'], item['description'], item.get('link', ''), item.get('pub_date', ''), sw, ks))
            all_items.append(item)
    for item in fetch_gnews_articles(config, market_data):
        marker = item.get('link') or item.get('title')
        if marker and marker not in seen_links:
            seen_links.add(marker)
            item['score'] = max(item.get('score', 0), score_news_item(item['title'], item['description'], item.get('link', ''), item.get('pub_date', ''), sw, ks))
            all_items.append(item)

    all_items.sort(key=lambda x: (-x.get('score', 0), x.get('pub_date', '')))
    print(f'  Scored {len(all_items)} items, selecting top {NEWS_CANDIDATE_LIMIT}', file=sys.stderr)
    for i, item in enumerate(all_items[:NEWS_CANDIDATE_LIMIT]):
        msg = '    #' + str(i+1) + ': [' + str(item['score']) + 'pts] ' + item['title'][:60] + '...'
        print(msg, file=sys.stderr)
    return all_items[:NEWS_CANDIDATE_LIMIT]
def strip_tags(text):
    return re.sub(r'<[^>]+>', '', text)

def generate_analysis(title, desc, market_data):
    """Generate Bloomberg-style professional analysis based on news content."""
    text = (title + " " + desc).lower()
    a = []

    if any(w in text for w in ["fed", "federal reserve", "rate hike", "rate cut", "interest rate", "monetary", "central bank", "powell", "ecb", "boj"]):
        if any(w in text for w in ["rate cut", "cut rate", "easing", "dovish", "lower rate"]):
            a.append("Policy signal: Dovish tilt supports risk appetite. Bond yields may compress, favouring duration and growth equities.")
        elif any(w in text for w in ["rate hike", "raise rate", "tighten", "hawkish", "higher rate"]):
            a.append("Policy signal: Hawkish bias pressures valuations. Higher discount rates weigh on long-duration assets.")
        else:
            a.append("Policy watch: Market parsing central bank communication for forward guidance. Implied rate path remains a key volatility driver.")
    if any(w in text for w in ["inflation", "cpi", "ppi", "price pressure"]):
        if any(w in text for w in ["cool", "slow", "drop", "fall", "decline", "moderate", "ease", "soften"]):
            a.append("Inflation trajectory: Disinflation trend intact. Supports peak-rate narrative and rate-sensitive sectors.")
        elif any(w in text for w in ["hot", "rise", "surge", "accelerate", "sticky"]):
            a.append("Inflation watch: Sticky price pressures complicate policy path. Markets may reprice rate expectations.")
        else:
            a.append("Inflation monitor: Data dependency remains high. Deviation from trend shifts policy probability distribution.")
    if any(w in text for w in ["tariff", "trade war", "import", "export", "us-china"]):
        a.append("Trade landscape: Tariff recalibrates supply-chain positioning. Sectors with cross-border exposure face margin uncertainty.")
    if any(w in text for w in ["gdp", "economy", "economic growth", "recession", "slowdown"]):
        if any(w in text for w in ["recession", "slowdown", "contract", "weak"]):
            a.append("Macro outlook: Growth concerns mounting. Cyclicals underperform defensives; credit spreads may widen.")
        elif any(w in text for w in ["grow", "expansion", "boom", "strong"]):
            a.append("Macro outlook: Expansion momentum underpins earnings revisions. Cyclical and value factors extend outperformance.")
        else:
            a.append("Macro snapshot: Growth trajectory critical for allocation. Divergence between hard data and sentiment warrants monitoring.")
    if any(w in text for w in ["oil", "crude", "energy", "opec", "brent", "wti"]):
        if any(w in text for w in ["cut", "supply", "output cut", "production cut"]):
            a.append("Energy supply: Supply discipline supports crude. Geopolitical risk premium persists.")
        elif any(w in text for w in ["fall", "drop", "demand worry"]):
            a.append("Energy markets: Demand concerns weigh on crude. Downstream margins benefit from lower input costs.")
        else:
            a.append("Energy markets: Crude sensitive to macro-demand narrative and supply coordination.")
    if any(w in text for w in ["gold", "precious metal", "bullion"]):
        if any(w in text for w in ["record", "rally", "high", "surge"]):
            a.append("Precious metals: Safe-haven demand and rate expectations driving prices. Break above resistance could accelerate momentum.")
        else:
            a.append("Precious metals: Direction tied to real yields and dollar dynamics. Central-bank buying provides structural floor.")
    if any(w in text for w in ["stock", "equity", "rally", "sell-off", "correction", "nasdaq"]):
        if any(w in text for w in ["rally", "surge", "gain", "record", "high"]):
            a.append("Equity markets: Momentum-driven advance. Monitor for positioning extremes and concentration risk.")
        elif any(w in text for w in ["sell", "drop", "fall", "decline", "correction", "plunge"]):
            a.append("Equity markets: Risk-off rotation. Defensives and quality attracting flows.")
        else:
            a.append("Equity markets: Elevated volatility regime. Factor rotation favours quality and low-beta exposure.")
    if any(w in text for w in ["ai", "artificial intelligence", "semiconductor", "chip", "nvidia", "tech"]):
        a.append("Technology: AI-related capex drives structural growth narrative. Valuation discipline is key as market prices multi-year adoption.")
    if any(w in text for w in ["china", "chinese", "beijing", "shanghai", "hong kong", "asia"]):
        a.append("Asia-Pacific: Policy stimulus and regulatory direction are key swing factors. Capital flows sensitive to macro data surprises.")
    if any(w in text for w in ["dollar", "currency", "forex", "yen", "euro", "exchange rate"]):
        a.append("外汇: Dollar direction is centre of gravity for macro trades. Rate differentials and risk appetite drive near-term positioning.")
    if any(w in text for w in ["merger", "acquisition", "takeover", "deal", "ipo"]):
        a.append("Deal flow: Corporate activity signals management confidence. Premiums and financing conditions shape risk-reward for arbitrage.")
    if any(w in text for w in ["earnings", "revenue", "profit", "quarterly", "results", "guidance", "eps"]):
        a.append("Earnings watch: Fundamentals under scrutiny. Guidance revisions carry more weight than headline beats.")
    if any(w in text for w in ["bond", "treasury", "yield", "curve", "spread", "credit", "duration"]):
        a.append("Fixed income: Yield dynamics reflect macro repricing. Curve steepening/flattening trades express rate-view divergence.")
    if any(w in text for w in ["war", "conflict", "sanction", "geopolitical", "ukraine", "russia", "middle east"]):
        a.append("Geopolitical: Risk premium embedded in energy and defence-linked assets. Tail-risk hedging through volatility and gold in demand.")
    if any(w in text for w in ["bank", "banking", "regulation", "lending", "credit", "deposit"]):
        a.append("Financial sector: Regulatory developments influence capital return decisions. NIM trajectories and credit quality are key drivers.")
    if any(w in text for w in ["job", "employment", "unemployment", "payroll", "labour", "wage", "nonfarm"]):
        a.append("Labour market: Employment data is a critical policy input. Wage dynamics have implications for services inflation.")
    if any(w in text for w in ["real estate", "housing", "property", "mortgage", "reit"]):
        a.append("Property: Higher rates continue transmitting through the sector. CRE repricing presents both risk and selective opportunity.")
    if not a:
        a.append("Market context: This development adds to the prevailing macro narrative. Cross-asset correlations suggest a regime-sensitive response.")
    return " | ".join(a[:2])


def format_price(val):
    if val >= 1000:
        return f'{val:,.2f}'
    elif val >= 1:
        return f'{val:.2f}'
    elif val >= 0.01:
        return f'{val:.4f}'
    else:
        return f'{val:.6f}'

def arrow(val):
    return '▲' if val > 1e-10 else ('▼' if val < -1e-10 else '─')

def color_class(val):
    return 'positive' if val >= 0 else 'negative'


def score_class(score):
    if score >= 80: return 'critical'
    if score >= 60: return 'high'
    if score >= 40: return 'medium'
    return 'standard'

def score_text(score):
    if score >= 80: return 'Critical'
    if score >= 60: return 'High'
    if score >= 40: return 'Medium'
    return 'Standard'

BANK_SECTION_ORDER = [
    'global_macro',
    'mainland_hk_macao',
    'middle_east_macro',
    'liquidity_assets',
    'senior_insight',
    'entity_watch',
    'sources',
]

BANK_SECTION_TITLES = {
    'global_macro': '全球宏观',
    'mainland_hk_macao': '内地及港澳',
    'middle_east_macro': '中东宏观',
    'liquidity_assets': '市场流动性与大类资产',
    'senior_insight': '今日高层洞察',
    'entity_watch': '重点关注实体动态',
    'sources': '来源',
}

NEWS_SECTION_KEYS = ('global_macro', 'mainland_hk_macao', 'middle_east_macro')
MAX_NEWS_PER_SECTION = 10

def get_local_now(config):
    tz_name = config.get('briefing', {}).get('timezone', 'Asia/Hong_Kong')
    try:
        from zoneinfo import ZoneInfo
        return datetime.datetime.now(ZoneInfo(tz_name))
    except Exception:
        if tz_name == 'Asia/Hong_Kong':
            return datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc).astimezone(
                datetime.timezone(datetime.timedelta(hours=8))
            )
        return datetime.datetime.now()

def truncate_text(text, limit):
    text = re.sub(r'\s+', ' ', strip_tags(text or '')).strip()
    return text if len(text) <= limit else text[:limit - 3].rstrip() + '...'

def market_line(name, info):
    if not info:
        return ''
    return f'{name}{format_price(info["price"])}，{info["change_pct"]:+.2f}%'

def item_summary(item):
    desc = truncate_text(item.get('description', ''), 90)
    impact = item.get('analysis') or '该事件对跨资产风险偏好和资金流向具有跟踪价值。'
    return {
        'title': truncate_text(item.get('title', ''), 90),
        'summary': desc,
        'impact': truncate_text(impact, 140),
        'link': item.get('link', ''),
        'score': item.get('score', 0),
        'importance': int(item.get('importance', item.get('score', 0)) or 0),
    }

def classify_news_item(item):
    text = (item.get('title', '') + ' ' + item.get('description', '') + ' ' + item.get('analysis', '')).lower()
    if any(w in text for w in ['middle east', 'iran', 'israel', 'gaza', 'lebanon', 'hormuz', 'saudi', 'uae', 'qatar', 'opec']):
        return 'middle_east_macro'
    if any(w in text for w in ['china', 'hong kong', 'macau', 'macao', 'pboc', 'yuan', 'renminbi', 'rmb', 'hang seng', 'shanghai', 'beijing', 'cnh', 'hkd']):
        return 'mainland_hk_macao'
    return 'global_macro'

def default_liquidity_assets(market_data):
    indices = market_data.get('indices', {})
    currencies = market_data.get('currencies', {})
    commodities = market_data.get('commodities', {})
    hang_seng = market_line('恒指', indices.get('Hang Seng'))
    spx = market_line('S&P 500', indices.get('S&P 500'))
    nasdaq = market_line('NASDAQ', indices.get('NASDAQ'))
    usdcnh = market_line('USD/CNH', currencies.get('USD/CNH'))
    gold = market_line('黄金', commodities.get('Gold'))
    oil = market_line('原油', commodities.get('Crude Oil'))
    return [
        {'title': '人民币流动性', 'body': f'人民币资金面维持观察，{usdcnh or "USD/CNH等待更新"}；外部美元利率与境内政策工具仍是短端资金价格的关键变量。'},
        {'title': '港元流动性', 'body': f'港元资产关注港股成交与联系汇率区间，{hang_seng or "恒指等待更新"}；南向资金和IPO情绪影响本地风险偏好。'},
        {'title': '美元流动性', 'body': '美元资金环境取决于美联储政策预期、美债收益率与美元指数方向，高利率维持对风险资产估值的约束。'},
        {'title': '股票市场', 'body': f'权益市场分化运行，{spx or "美股等待更新"}，{nasdaq or "纳指等待更新"}；亚洲市场重点关注政策预期与科技板块弹性。'},
        {'title': '美债市场', 'body': '美债收益率仍是全球资产定价锚，期限利差变化将影响成长股、黄金和高息货币表现。'},
        {'title': '黄金及能源', 'body': f'{gold or "黄金等待更新"}，{oil or "原油等待更新"}；实际利率、美元方向及地缘风险共同驱动避险资产。'},
    ]

def default_entity_watch(news_items):
    entities = [
        ('Nvidia', ['nvidia', 'semiconductor', 'chip', 'ai']),
        ('腾讯控股 0700.HK', ['tencent', '0700', 'hong kong tech']),
        ('汇丰控股/渣打集团', ['hsbc', 'standard chartered', 'bank']),
        ('香港特别行政区政府', ['hong kong', 'ipo', 'offshore yuan']),
        ('人民银行', ['pboc', 'people bank', 'yuan', 'renminbi']),
    ]
    rows = []
    used = set()
    for name, keywords in entities:
        for item in news_items:
            text = (item.get('title', '') + ' ' + item.get('description', '')).lower()
            if item.get('link') not in used and any(k in text for k in keywords):
                used.add(item.get('link'))
                rows.append({
                    'entity': name,
                    'summary': truncate_text(item.get('title', ''), 80),
                    'impact': truncate_text(item.get('analysis', ''), 130),
                    'link': item.get('link', ''),
                })
                break
    if not rows:
        for item in news_items[:4]:
            rows.append({
                'entity': truncate_text(item.get('title', '').split(' - ')[0], 40),
                'summary': truncate_text(item.get('title', ''), 80),
                'impact': truncate_text(item.get('analysis', ''), 130),
                'link': item.get('link', ''),
            })
    return rows[:5]

def normalize_news_entry(item):
    if not isinstance(item, dict):
        return item_summary({'title': str(item), 'description': '', 'analysis': '', 'link': '', 'score': 0})
    normalized = {
        'title': truncate_text(item.get('title') or item.get('headline') or '', 90),
        'summary': truncate_text(item.get('summary') or item.get('description') or '', 110),
        'impact': truncate_text(item.get('impact') or item.get('analysis') or '', 150),
        'link': item.get('link') or '',
        'score': item.get('score', 0),
    }
    if not normalized['summary']:
        normalized['summary'] = '市场仍需关注该事件对风险偏好、利率路径及跨资产资金流向的影响。'
    if not normalized['impact']:
        normalized['impact'] = '对相关资产价格和配置节奏具有跟踪意义。'
    try:
        normalized['importance'] = int(item.get('importance', item.get('score', 0)))
    except Exception:
        normalized['importance'] = 0
    return normalized

def news_belongs_to_section(item, section_key):
    text = (item.get('title', '') + ' ' + item.get('summary', '') + ' ' + item.get('impact', '')).lower()
    if section_key == 'global_macro':
        return any(w in text for w in [
            'fed', 'federal reserve', 'ecb', 'boj', 'central bank', 'inflation', 'cpi', 'gdp',
            'recession', 'market', 'stocks', 'equity', 'tech', 'nvidia', 'semiconductor', 'bitcoin',
            'crypto', 'dollar', 'yields', 'treasury', 'bond', 'trade', 'tariff', 'g7'
        ]) and not any(w in text for w in ['hong kong', 'china', 'macau', 'macao', 'pboc', 'yuan', 'rmb'])
    if section_key == 'mainland_hk_macao':
        return any(w in text for w in ['china', 'hong kong', 'macau', 'macao', 'pboc', 'yuan', 'renminbi', 'rmb', 'hang seng', 'shanghai', 'beijing', 'shenzhen', 'a股', '港股', '人民銀行', '人民银行'])
    if section_key == 'middle_east_macro':
        return any(w in text for w in ['middle east', 'iran', 'israel', 'gaza', 'lebanon', 'hormuz', 'saudi', 'uae', 'qatar', 'opec', 'iraq', 'kuwait', 'bahrain', 'yemen'])
    return True

def sort_section_items(items):
    def score_of(item):
        return int(item.get('importance', item.get('score', 0)) or 0)
    return sorted(items, key=lambda item: (-score_of(item), item.get('title', '')))

def normalize_structured_briefing(data, market_data, news_items):
    structured = {key: data.get(key, []) if isinstance(data, dict) else [] for key in BANK_SECTION_ORDER}
    fallback_by_section = {key: [] for key in NEWS_SECTION_KEYS}
    seen_links = {key: set() for key in NEWS_SECTION_KEYS}

    for item in news_items:
        summary = item_summary(item)
        fallback_by_section[classify_news_item(item)].append(summary)

    for key in NEWS_SECTION_KEYS:
        existing = structured.get(key, [])
        if not isinstance(existing, list):
            existing = []
        normalized = [normalize_news_entry(item) for item in existing]
        normalized = [
            item for item in normalized
            if item.get('title') and news_belongs_to_section(item, key)
        ]
        for item in normalized:
            seen_links[key].add(item.get('link') or item.get('title'))

        candidates = [c for c in fallback_by_section[key] if news_belongs_to_section(c, key)]
        for candidate in candidates:
            marker = candidate.get('link') or candidate.get('title')
            if marker in seen_links[key]:
                continue
            normalized.append(candidate)
            seen_links[key].add(marker)
            if len(normalized) >= MAX_NEWS_PER_SECTION:
                break

        normalized = sort_section_items(normalized)
        structured[key] = normalized[:MAX_NEWS_PER_SECTION]

    liquidity = structured.get('liquidity_assets')
    if not isinstance(liquidity, list) or not liquidity:
        structured['liquidity_assets'] = default_liquidity_assets(market_data)

    insight = structured.get('senior_insight')
    if not isinstance(insight, str) or not insight.strip():
        top_titles = '；'.join(truncate_text(i.get('title', ''), 35) for i in news_items[:3])
        structured['senior_insight'] = (
            f'今日核心变量集中在政策预期、美元利率与区域风险的再定价。{top_titles}。'
            '配置上宜关注美元流动性对权益估值的压制、人民币及港元资产的政策支撑，以及能源与黄金的事件驱动波动。'
        )

    entity_watch = structured.get('entity_watch')
    if not isinstance(entity_watch, list) or not entity_watch:
        structured['entity_watch'] = default_entity_watch(news_items)

    sources = structured.get('sources')
    if not isinstance(sources, list) or not sources:
        structured['sources'] = sorted({re.sub(r'^www\.', '', urllib.parse.urlparse(i.get('link', '')).netloc) for i in news_items if i.get('link')})

    return {key: structured[key] for key in BANK_SECTION_ORDER}

def build_structured_briefing(market_data, news_items, ai_client=None):
    if ai_client:
        try:
            ai_result = ai_client(market_data, news_items)
            if validate_structured_briefing(ai_result):
                return normalize_structured_briefing(ai_result, market_data, news_items)
            print('  [WARN] Agnes response failed validation; using rule fallback.', file=sys.stderr)
        except Exception as e:
            print(f'  [WARN] Agnes briefing generation failed: {e}', file=sys.stderr)

    structured = {key: [] for key in BANK_SECTION_ORDER}
    for item in news_items:
        section = classify_news_item(item)
        if len(structured[section]) < 5:
            structured[section].append(item_summary(item))

    for section in NEWS_SECTION_KEYS:
        if not structured[section]:
            for item in news_items:
                if item_summary(item) not in structured[section]:
                    structured[section].append(item_summary(item))
                    break

    structured['liquidity_assets'] = default_liquidity_assets(market_data)
    top_titles = '；'.join(truncate_text(i.get('title', ''), 35) for i in news_items[:3])
    structured['senior_insight'] = (
        f'今日核心变量集中在政策预期、美元利率与区域风险的再定价。{top_titles}。'
        '配置上宜关注美元流动性对权益估值的压制、人民币及港元资产的政策支撑，以及能源与黄金的事件驱动波动。'
    )
    structured['entity_watch'] = default_entity_watch(news_items)
    structured['sources'] = sorted({re.sub(r'^www\.', '', urllib.parse.urlparse(i.get('link', '')).netloc) for i in news_items if i.get('link')})
    return normalize_structured_briefing(structured, market_data, news_items)

def validate_structured_briefing(data):
    if not isinstance(data, dict):
        return False
    for key in BANK_SECTION_ORDER:
        if key not in data:
            return False
    return isinstance(data.get('senior_insight'), str) and isinstance(data.get('liquidity_assets'), list)

def agnes_structured_briefing(market_data, news_items):
    api_key = os.environ.get('AGNES_API_KEY')
    if not api_key:
        return None
    payload_items = []
    for item in news_items[:NEWS_CANDIDATE_LIMIT]:
        payload_items.append({
            'title': truncate_text(item.get('title', ''), 160),
            'description': truncate_text(item.get('description', ''), 220),
            'analysis': truncate_text(item.get('analysis', ''), 180),
            'link': item.get('link', ''),
            'score': item.get('score', 0),
        })
    prompt = {
        'market_data': market_data,
        'news_items': payload_items,
        'classification_rules': {
            'global_macro': '美国、欧洲、日本、全球央行、通胀、增长、贸易、科技、银行、加密货币等全球宏观和市场新闻。',
            'mainland_hk_macao': '仅限中国内地、香港、澳门、人民币、人民银行、A股、港股、沪深交易所、中资金融机构及粤港澳相关新闻。',
            'middle_east_macro': '仅限中东地区、海湾、伊朗、以色列、巴勒斯坦、黎巴嫩、霍尔木兹、OPEC、区域能源供应及地缘风险新闻。',
        },
        'instructions': [
            '先从全部候选新闻中判断每条新闻归属，再为每个新闻栏目选择最多10条最相关新闻。',
            '不要为了凑数把不相关新闻放入栏目；例如 South Africa 不属于内地及港澳。',
            '为每条新闻生成 importance 影响力分数，10分制或100分制都可以，分数越高影响越大。',
            '如果某栏目不足10条，返回已有相关新闻即可，不要补不相关内容。',
            '标题、摘要、影响与 importance 必须基于候选新闻，不要编造不存在的具体事件。',
        ],
        'required_json_schema': {
            'global_macro': [{'title': 'str', 'summary': 'str', 'impact': 'str', 'importance': 'int', 'link': 'str'}],
            'mainland_hk_macao': [{'title': 'str', 'summary': 'str', 'impact': 'str', 'importance': 'int', 'link': 'str'}],
            'middle_east_macro': [{'title': 'str', 'summary': 'str', 'impact': 'str', 'importance': 'int', 'link': 'str'}],
            'liquidity_assets': [{'title': 'str', 'body': 'str'}],
            'senior_insight': 'str',
            'entity_watch': [{'entity': 'str', 'summary': 'str', 'impact': 'str', 'importance': 'int', 'link': 'str'}],
            'sources': ['str'],
        },
    }
    body = {
        'model': AGNES_MODEL,
        'messages': [
            {'role': 'system', 'content': '你是银行投资晨报编辑。只输出合法 JSON，不要 Markdown。语气专业、简洁、中文。'},
            {'role': 'user', 'content': json.dumps(prompt, ensure_ascii=False)},
        ],
        'temperature': 0.2,
    }
    req = urllib.request.Request(
        AGNES_BASE_URL.rstrip('/') + '/chat/completions',
        data=json.dumps(body).encode('utf-8'),
        headers={
            'Authorization': 'Bearer ' + api_key,
            'Content-Type': 'application/json',
        },
        method='POST',
    )
    with urllib.request.urlopen(req, timeout=35) as resp:
        raw = json.loads(resp.read().decode('utf-8'))
    content = raw['choices'][0]['message']['content'].strip()
    if content.startswith('```'):
        content = re.sub(r'^```(?:json)?\s*|\s*```$', '', content, flags=re.S)
    return json.loads(content)

def render_news_item(item):
    link = htmlmod.escape(item.get('link', ''))
    title = htmlmod.escape(item.get('title', ''))
    summary = htmlmod.escape(item.get('summary', ''))
    impact = htmlmod.escape(item.get('impact', ''))
    importance = item.get('importance', item.get('score', 0))
    title_html = f'<a href="{link}" class="bank-news-title" target="_blank">{title}</a>' if link else f'<span class="bank-news-title">{title}</span>'
    return f'''
        <div class="bank-news-item">
            {title_html}
            <div class="bank-news-line"><span>影響力 {importance}：</span>{summary} {impact}</div>
        </div>'''

def render_bank_sections(structured):
    def news_section(key):
        rows = ''.join(render_news_item(i) for i in structured.get(key, []))
        return f'<div class="section-title">{BANK_SECTION_TITLES[key]}</div><div class="bank-section">{rows}</div>'

    liquidity_rows = ''.join(
        f'<div class="asset-note"><span>{htmlmod.escape(i.get("title", ""))}</span>{htmlmod.escape(i.get("body", ""))}</div>'
        for i in structured.get('liquidity_assets', [])
    )
    entity_rows = ''.join(
        f'''<div class="bank-news-item">
            <span class="bank-news-title">{htmlmod.escape(i.get("entity", ""))}</span>
            <div class="bank-news-line"><span>摘要与潜在影响：</span>{htmlmod.escape(i.get("summary", ""))} {htmlmod.escape(i.get("impact", ""))}</div>
        </div>'''
        for i in structured.get('entity_watch', [])
    )
    sources = ' &middot; '.join(htmlmod.escape(s) for s in structured.get('sources', []) if s)
    return f'''
{news_section('global_macro')}
{news_section('mainland_hk_macao')}
{news_section('middle_east_macro')}
<div class="section-title">{BANK_SECTION_TITLES['liquidity_assets']}</div>
<div class="bank-section">{liquidity_rows}</div>
<div class="section-title">{BANK_SECTION_TITLES['senior_insight']}</div>
<div class="insight-box">{htmlmod.escape(structured.get('senior_insight', ''))}</div>
<div class="section-title">{BANK_SECTION_TITLES['entity_watch']}</div>
<div class="bank-section">{entity_rows}</div>
<div class="sources-line">来源：{sources}</div>'''

def build_html_briefing(market_data, news_items, date_str, structured_briefing=None):
    """Build Bloomberg-style HTML email."""
    m = market_data

    # --- Market Table Rows ---
    def idx_row(name, info):
        if not info:
            return ''
        return (
            f'<tr><td class="name">{name}</td>'
            f'<td class="price">{format_price(info["price"])}</td>'
            f'<td class="{color_class(info["change"])}">{arrow(info["change"])} {info["change"]:+.2f}</td>'
            f'<td class="{color_class(info["change_pct"])}">{arrow(info["change_pct"])} {info["change_pct"]:+.2f}%</td></tr>'
        )

    def curr_row(name, info):
        if not info:
            return ''
        return (
            f'<tr><td class="name">{name}</td>'
            f'<td class="price">{format_price(info["price"])}</td>'
            f'<td class="{color_class(info["change"])}">{arrow(info["change"])} {info["change"]:+.4f}</td>'
            f'<td class="{color_class(info["change_pct"])}">{arrow(info["change_pct"])} {info["change_pct"]:+.2f}%</td></tr>'
        )

    def comm_row(name, info):
        if not info:
            return ''
        return (
            f'<tr><td class="name">{name}</td>'
            f'<td class="price">{format_price(info["price"])}</td>'
            f'<td class="{color_class(info["change"])}">{arrow(info["change"])} {info["change"]:+.2f}</td>'
            f'<td class="{color_class(info["change_pct"])}">{arrow(info["change_pct"])} {info["change_pct"]:+.2f}%</td></tr>'
        )

    indices_rows = ''.join(idx_row(n, i) for n, i in m.get('indices', {}).items())
    currencies_rows = ''.join(curr_row(n, i) for n, i in m.get('currencies', {}).items())
    commodities_rows = ''.join(comm_row(n, i) for n, i in m.get('commodities', {}).items())
    if structured_briefing is None:
        structured_briefing = build_structured_briefing(market_data, news_items)
    bank_sections = render_bank_sections(structured_briefing)

    html_content = f'''<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
body {{
    margin: 0;
    padding: 0;
    background-color: #0a0a0a;
    font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Arial, Helvetica, sans-serif;
    color: #d4d4d4;
}}
.container {{
    max-width: 680px;
    margin: 0 auto;
    padding: 20px;
}}
.header {{
    border-bottom: 3px solid #ffd700;
    padding-bottom: 20px;
    margin-bottom: 24px;
}}
.header-top {{
    display: flex;
    justify-content: space-between;
    align-items: baseline;
}}
.brand {{
    font-size: 28px;
    font-weight: 700;
    color: #ffd700;
    letter-spacing: 1px;
}}
.brand-sub {{
    font-size: 11px;
    color: #888;
    letter-spacing: 2px;
    text-transform: uppercase;
}}
.date-badge {{
    text-align: right;
    font-size: 13px;
    color: #aaa;
    font-weight: 300;
}}
.edition {{
    color: #ffd700;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 3px;
    margin-bottom: 4px;
}}
.section-title {{
    font-size: 13px;
    font-weight: 600;
    color: #ffd700;
    text-transform: uppercase;
    letter-spacing: 2px;
    margin-top: 28px;
    margin-bottom: 12px;
    padding-bottom: 6px;
    border-bottom: 1px solid #333;
}}
.section-title .count {{
    color: #666;
    font-weight: 400;
}}
table {{
    width: 100%;
    border-collapse: collapse;
}}
th {{
    font-size: 10px;
    font-weight: 600;
    color: #888;
    text-transform: uppercase;
    letter-spacing: 1px;
    padding: 6px 8px;
    border-bottom: 1px solid #333;
    text-align: right;
}}
th:first-child {{
    text-align: left;
}}
td {{
    padding: 7px 8px;
    font-size: 13px;
    border-bottom: 1px solid #1a1a1a;
}}
td.name {{
    font-weight: 500;
    color: #e0e0e0;
}}
td.price {{
    font-family: 'Consolas', 'Courier New', monospace;
    text-align: right;
    color: #fff;
    font-weight: 500;
}}
td.positive {{
    font-family: 'Consolas', 'Courier New', monospace;
    text-align: right;
    color: #00c853;
}}
td.negative {{
    font-family: 'Consolas', 'Courier New', monospace;
    text-align: right;
    color: #ff1744;
}}
tr:hover td {{
    background-color: #141414;
}}
.news-table td.news-number {{
    width: 32px;
    font-family: 'Consolas', monospace;
    font-size: 12px;
    color: #555;
    text-align: center;
    vertical-align: top;
    padding-top: 10px;
}}
.news-table td.news-content {{
    padding: 8px 4px 10px 0;
}}
.news-title {{
    font-size: 14px;
    font-weight: 600;
    color: #e0e0e0;
    text-decoration: none;
    line-height: 1.4;
}}
.news-title::after {{
        content: " \u2197";
        font-size: 11px;
        color: #666;
        margin-left: 3px;
    }}
.news-title:hover {{
    color: #ffd700;
}}
.news-desc {{
    font-size: 12px;
    color: #888;
    margin-top: 3px;
    line-height: 1.4;
}}
.bank-section {{
    border-left: 2px solid #333;
    padding-left: 12px;
}}
.bank-news-item {{
    padding: 9px 0 11px;
    border-bottom: 1px solid #1a1a1a;
}}
.bank-news-title {{
    font-size: 14px;
    font-weight: 650;
    color: #f0f0f0;
    text-decoration: none;
    line-height: 1.45;
}}
.bank-news-title:hover {{
    color: #ffd700;
}}
.bank-news-line {{
    font-size: 12px;
    color: #9b9b9b;
    margin-top: 4px;
    line-height: 1.55;
}}
.bank-news-line span {{
    color: #ffd700;
    font-weight: 600;
}}
.asset-note {{
    font-size: 12px;
    color: #a8a8a8;
    line-height: 1.6;
    padding: 8px 0;
    border-bottom: 1px solid #1a1a1a;
}}
.asset-note span {{
    display: block;
    color: #e0e0e0;
    font-weight: 650;
    margin-bottom: 2px;
}}
.insight-box {{
    border: 1px solid #333;
    background: #111;
    padding: 12px 14px;
    color: #d8d8d8;
    font-size: 13px;
    line-height: 1.65;
}}
.sources-line {{
    margin-top: 22px;
    color: #666;
    font-size: 11px;
    line-height: 1.5;
}}
.footer {{
    margin-top: 32px;
    padding-top: 16px;
    border-top: 1px solid #222;
    font-size: 11px;
    color: #666;
    text-align: center;
    line-height: 1.6;
}}
.footer .disclaimer {{
    color: #444;
    font-size: 10px;
    margin-top: 8px;
}}
</style>
</head>
<body bgcolor="#0a0a0a" style="margin:0;padding:0;background-color:#0a0a0a;color:#d4d4d4;">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" bgcolor="#0a0a0a" style="background-color:#0a0a0a;width:100%;margin:0;padding:0;">
<tr>
<td align="center" bgcolor="#0a0a0a" style="background-color:#0a0a0a;">
<div class="container" style="background-color:#0a0a0a;color:#d4d4d4;max-width:680px;margin:0 auto;padding:20px;">

<!-- Header -->
<div class="header">
    <div class="header-top">
        <div>
            <div class="brand">晨间简报</div>
            <div class="brand-sub">全球金融情报</div>
        </div>
        <div class="date-badge">
            <div class="edition">每日版</div>
            <div>{date_str}</div>
        </div>
    </div>
</div>

<!-- Market Overview -->
<div class="section-title">市场速览 <span class="count">| 股指</span></div>
<table>
    <thead>
        <tr><th>品种</th><th>最新价</th><th>涨跌额</th><th>涨跌额 %</th></tr>
    </thead>
    <tbody>
        {indices_rows}
    </tbody>
</table>

<div class="section-title">外汇</div>
<table>
    <thead>
        <tr><th>货币对</th><th>最新价</th><th>涨跌额</th><th>涨跌额 %</th></tr>
    </thead>
    <tbody>
        {currencies_rows}
    </tbody>
</table>

<div class="section-title">商品与加密货币</div>
<table>
    <thead>
        <tr><th>资产</th><th>最新价</th><th>涨跌额</th><th>涨跌额 %</th></tr>
    </thead>
    <tbody>
        {commodities_rows}
    </tbody>
</table>

<!-- Bank-style News Briefing -->
{bank_sections}

<!-- Footer -->
<div class="footer">
    Morning Briefing &middot; Generated on {date_str}<br>
    <div class="disclaimer">
        数据来源于公开金融API，分析由AI生成，仅供参考。<br>
        此为自动生成的简报，不构成投资建议。
    </div>
</div>

</div>
</td>
</tr>
</table>
</body>
</html>'''
    return html_content

def build_text_briefing(market_data, news_items, date_str, structured_briefing=None):
    """Build a plain-text version for email fallback."""
    if structured_briefing is None:
        structured_briefing = build_structured_briefing(market_data, news_items)
    lines = []
    lines.append('=' * 66)
    lines.append('  晨间简报 — 全球金融情报')
    lines.append(f'  {date_str}')
    lines.append('=' * 66)
    lines.append('')

    for category, label in [('indices', 'MARKET OVERVIEW — 股指'),
                             ('currencies', 'CURRENCIES'),
                             ('commodities', 'COMMODITIES & CRYPTO')]:
        if category in market_data and market_data[category]:
            lines.append(f'── {label} ──')
            lines.append(f'{"品种":<24} {"最新价":>12} {"涨跌额":>10} {"Chg%":>8}')
            lines.append('-' * 54)
            for name, info in market_data[category].items():
                if info:
                    p = format_price(info['price'])
                    c = f'{info["change"]:+.2f}' if abs(info['change']) < 100 else f'{info["change"]:+.2f}'
                    cp = f'{info["change_pct"]:+.2f}%'
                    lines.append(f'{name:<24} {p:>12} {c:>10} {cp:>8}')
            lines.append('')

    for key in ('global_macro', 'mainland_hk_macao', 'middle_east_macro'):
        lines.append(f'--- {BANK_SECTION_TITLES[key]} ---')
        for item in structured_briefing.get(key, []):
            lines.append(f'  - {item.get("title", "")}')
            lines.append(f'    摘要与影响：{item.get("summary", "")} {item.get("impact", "")}')
            if item.get('link'):
                lines.append(f'    Link: {item.get("link")}')
        lines.append('')

    lines.append(f'--- {BANK_SECTION_TITLES["liquidity_assets"]} ---')
    for item in structured_briefing.get('liquidity_assets', []):
        lines.append(f'  - {item.get("title", "")}: {item.get("body", "")}')
    lines.append('')

    lines.append(f'--- {BANK_SECTION_TITLES["senior_insight"]} ---')
    lines.append(structured_briefing.get('senior_insight', ''))
    lines.append('')

    lines.append(f'--- {BANK_SECTION_TITLES["entity_watch"]} ---')
    for item in structured_briefing.get('entity_watch', []):
        lines.append(f'  - {item.get("entity", "")}: {item.get("summary", "")} {item.get("impact", "")}')
        lines.append('')

    if structured_briefing.get('sources'):
        lines.append('来源：' + ', '.join(structured_briefing.get('sources', [])))

    lines.append('')
    lines.append('=' * 66)
    lines.append('Generated by Morning Briefing Automation')
    lines.append('For informational purposes only. Not investment advice.')
    return '\n'.join(lines)

def send_email(config, html_content, text_content):
    import os as _os
    email_cfg = config['email']
    password = _os.environ.get('BRIEFING_EMAIL_PASSWORD') or email_cfg.get('sender_password', '')
    if not password:
        print("  [ERROR] No email password configured.", file=sys.stderr)
        return False
    recipients = email_cfg.get('recipient_emails', [email_cfg.get('recipient_email', '')])
    msg = MIMEMultipart('alternative')
    msg['Subject'] = f"晨间简报 - {datetime.date.today().strftime('%A, %B %d, %Y')}"
    msg['From'] = email_cfg['sender_email']
    msg['To'] = ', '.join(recipients)
    msg['X-Priority'] = '1'
    msg.attach(MIMEText(text_content, 'plain', 'utf-8'))
    msg.attach(MIMEText(html_content, 'html', 'utf-8'))
    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(email_cfg['smtp_server'], email_cfg['smtp_port']) as server:
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
            server.login(email_cfg['sender_email'], password)
            server.send_message(msg)
        print(f'  Email sent to {len(recipients)} recipient(s)!', file=sys.stderr)
        return True
    except Exception as e:
        print(f'  [ERROR] Failed to send email: {e}', file=sys.stderr)
        return False

def main():
    print('Loading config...', file=sys.stderr)
    config = load_config()

    now_local = get_local_now(config)
    today = now_local.date()
    date_str = now_local.strftime('%A, %B %d, %Y')

    # Weekday check
    if config['briefing']['weekdays_only'] and today.weekday() >= 5:
        print('Weekend — skipping briefing (weekdays only).', file=sys.stderr)
        return 0

    print(f'Generating Morning Briefing for {date_str}', file=sys.stderr)
    print('Collecting market data...', file=sys.stderr)
    market_data = collect_market_data(config)

    print('Collecting news...', file=sys.stderr)
    news = collect_news(config, market_data)

    print('Building bank-style news structure...', file=sys.stderr)
    ai_client = agnes_structured_briefing if os.environ.get('AGNES_API_KEY') else None
    structured = build_structured_briefing(market_data, news, ai_client=ai_client)

    print('Building briefing HTML...', file=sys.stderr)
    html_content = build_html_briefing(market_data, news, date_str, structured_briefing=structured)
    text_content = build_text_briefing(market_data, news, date_str, structured_briefing=structured)

    # Save a local copy for reference
    output_dir = SCRIPT_DIR
    html_path = os.path.join(output_dir, f'briefing_{today.isoformat()}.html')
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    print(f'  Saved: {html_path}', file=sys.stderr)

    # Send email
    pw = __import__('os').environ.get('BRIEFING_EMAIL_PASSWORD') or config['email'].get('sender_password', '')
    if pw:
        print('Sending email...', file=sys.stderr)
        send_email(config, html_content, text_content)
    else:
        print('  [INFO] Email password not configured — skipping send.', file=sys.stderr)
        print('  [INFO] Briefing saved locally.', file=sys.stderr)

    print('Done.', file=sys.stderr)
    return 0

if __name__ == '__main__':
    sys.exit(main())
