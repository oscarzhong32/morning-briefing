import os
path = r"C:\Users\ZhuanZ\Documents\Codex\2026-06-19\new-chat-2\outputs\morning_briefing\morning_briefing.py"
with open(path, encoding="utf-8") as f:
    c = f.read()

pairs = [
    ("MORNING BRIEFING", "晨间简报"),
    ("Daily Financial Intelligence", "全球金融情报"),
    ("Daily Edition", "每日版"),
    ("Market Snapshot", "市场速览"),
    ("Indices", "股指"),
    ("Currencies", "外汇"),
    ("FX", "外汇"),
    ("Commodities & Crypto", "商品与加密货币"),
    ("Real Assets", "实物资产"),
    ("Top 10 Financial News", "十大金融新闻"),
    ("Market Intelligence", "市场情报"),
    ("Analyst Commentary", "分析师点评"),
    ("Importance: Critical", "重要性：关键"),
    ("Importance: High", "重要性：高"),
    ("Importance: Medium", "重要性：中"),
    ("Importance: Standard", "重要性：普通"),
    ("Instrument", "品种"),
    ("Last", "最新价"),
    ("Change", "涨跌额"),
    ("Change %", "涨跌幅"),
    ("Pair", "货币对"),
    ("Asset", "资产"),
    ("Morning Briefing - ", "晨间简报 - "),
]

for old, new in pairs:
    c = c.replace(old, new)

# Longer text replacements
c = c.replace(
    "Data from public financial APIs. Analysis is AI-generated and for informational purposes only.",
    "数据来源于公开金融API，分析由AI生成，仅供参考。"
)
c = c.replace(
    "This briefing is an automated compilation and does not constitute investment advice.",
    "此为自动生成的简报，不构成投资建议。"
)

with open(path, "w", encoding="utf-8") as f:
    f.write(c)
print("Chinese conversion complete")
