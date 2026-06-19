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
import xml.etree.ElementTree as ET
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, 'config.json')

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
    for url in config['briefing']['news_sources']:
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
                    'analysis': analysis,
                    'score': score
                })
    all_items.sort(key=lambda x: (-x['score'], x['pub_date']))
    print(f'  Scored {len(all_items)} items, selecting top 10', file=sys.stderr)
    for i, item in enumerate(all_items[:10]):
        msg = '    #' + str(i+1) + ': [' + str(item['score']) + 'pts] ' + item['title'][:60] + '...'
        print(msg, file=sys.stderr)
    return all_items[:10]
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
        a.append("FX: Dollar direction is centre of gravity for macro trades. Rate differentials and risk appetite drive near-term positioning.")
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
def build_html_briefing(market_data, news_items, date_str):
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

    # --- Top 10 News with Analysis ---
    news_rows = ''
    for i, item in enumerate(news_items):
        sd = strip_tags(item['description'])[:200]
        if len(strip_tags(item['description'])) > 200:
            sd += '...'
        news_rows += f'''
        <tr>
            <td class="news-number">{i+1:02d}</td>
            <td class="news-content">
                <a href="{htmlmod.escape(item['link'])}" class="news-title" target="_blank">{htmlmod.escape(item['title'])}</a>
                <div class="news-desc">{htmlmod.escape(sd)}</div>
                <div class="analysis-box">
                    <div class="analysis-label">Analyst Commentary</div>
                    <div class="analysis-text">{htmlmod.escape(item['analysis'])}</div>
                    <div class="score-bar">
                        <span class="score-dot {score_class(item['score'])}"></span>
                        <span class="score-label">Importance: {score_text(item['score'])}</span>
                    </div>
                </div>
            </td>
        </tr>'''

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
<body>
<div class="container">

<!-- Header -->
<div class="header">
    <div class="header-top">
        <div>
            <div class="brand">MORNING BRIEFING</div>
            <div class="brand-sub">Daily Financial Intelligence</div>
        </div>
        <div class="date-badge">
            <div class="edition">Daily Edition</div>
            <div>{date_str}</div>
        </div>
    </div>
</div>

<!-- Market Overview -->
<div class="section-title">Market Snapshot <span class="count">| Indices</span></div>
<table>
    <thead>
        <tr><th>Instrument</th><th>Last</th><th>Change</th><th>Change %</th></tr>
    </thead>
    <tbody>
        {indices_rows}
    </tbody>
</table>

<div class="section-title">Currencies</div>
<table>
    <thead>
        <tr><th>Pair</th><th>Last</th><th>Change</th><th>Change %</th></tr>
    </thead>
    <tbody>
        {currencies_rows}
    </tbody>
</table>

<div class="section-title">Commodities & Crypto</div>
<table>
    <thead>
        <tr><th>Asset</th><th>Last</th><th>Change</th><th>Change %</th></tr>
    </thead>
    <tbody>
        {commodities_rows}
    </tbody>
</table>

<!-- Top 10 -->
<div class="section-title">Top 10 Financial News <span class="count">| Market Intelligence</span></div>
<table class="news-table">
    <tbody>
        {news_rows}
    </tbody>
</table>

<!-- Footer -->
<div class="footer">
    Morning Briefing &middot; Generated on {date_str}<br>
    <div class="disclaimer">
        Data from public financial APIs. Analysis is AI-generated and for informational purposes only.<br>
        This briefing is an automated compilation and does not constitute investment advice.
    </div>
</div>

</div>
</body>
</html>'''
    return html_content

def build_text_briefing(market_data, news_items, date_str):
    """Build a plain-text version for email fallback."""
    lines = []
    lines.append('=' * 66)
    lines.append('  MORNING BRIEFING — Daily Financial Intelligence')
    lines.append(f'  {date_str}')
    lines.append('=' * 66)
    lines.append('')

    for category, label in [('indices', 'MARKET OVERVIEW — Indices'),
                             ('currencies', 'CURRENCIES'),
                             ('commodities', 'COMMODITIES & CRYPTO')]:
        if category in market_data and market_data[category]:
            lines.append(f'── {label} ──')
            lines.append(f'{"Instrument":<24} {"Last":>12} {"Change":>10} {"Chg%":>8}')
            lines.append('-' * 54)
            for name, info in market_data[category].items():
                if info:
                    p = format_price(info['price'])
                    c = f'{info["change"]:+.2f}' if abs(info['change']) < 100 else f'{info["change"]:+.2f}'
                    cp = f'{info["change_pct"]:+.2f}%'
                    lines.append(f'{name:<24} {p:>12} {c:>10} {cp:>8}')
            lines.append('')

    lines.append('--- TOP 10 FINANCIAL NEWS ---')
    lines.append('')
    for i, item in enumerate(news_items):
        sd = strip_tags(item['description'])[:120]
        if len(strip_tags(item['description'])) > 120:
            sd += '...'
        lines.append(f'  {i+1:2d}. {strip_tags(item["title"])}')
        lines.append(f'       {sd}')
        lines.append(f'       Link: {item["link"]}')
        lines.append(f'       Analysis: {item["analysis"]}')
        lines.append('')

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
    msg['Subject'] = f'Morning Briefing - {datetime.date.today().strftime('%A, %B %d, %Y')}'
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

    today = datetime.date.today()
    now_local = datetime.datetime.now()
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

    print('Building briefing HTML...', file=sys.stderr)
    html_content = build_html_briefing(market_data, news, date_str)
    text_content = build_text_briefing(market_data, news, date_str)

    # Save a local copy for reference
    output_dir = SCRIPT_DIR
    html_path = os.path.join(output_dir, f'briefing_{today.isoformat()}.html')
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    print(f'  Saved: {html_path}', file=sys.stderr)

    # Send email
    if config['email']['sender_password']:
        print('Sending email...', file=sys.stderr)
        send_email(config, html_content, text_content)
    else:
        print('  [INFO] Email password not configured — skipping send.', file=sys.stderr)
        print('  [INFO] Briefing saved locally.', file=sys.stderr)

    print('Done.', file=sys.stderr)
    return 0

if __name__ == '__main__':
    sys.exit(main())
