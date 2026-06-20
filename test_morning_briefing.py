import unittest

import morning_briefing as mb


class MorningBriefingStructureTests(unittest.TestCase):
    def sample_market_data(self):
        return {
            "indices": {
                "S&P 500": {"price": 6100.12, "change": -12.3, "change_pct": -0.2},
                "Hang Seng": {"price": 24312.0, "change": -181.0, "change_pct": -0.74},
            },
            "currencies": {
                "USD/CNH": {"price": 7.1835, "change": 0.0123, "change_pct": 0.17},
            },
            "commodities": {
                "Gold": {"price": 3350.5, "change": 18.2, "change_pct": 0.55},
                "Crude Oil": {"price": 78.52, "change": -1.2, "change_pct": -1.51},
            },
        }

    def sample_news(self):
        return [
            {
                "title": "Fed holds rates as dot plot turns hawkish",
                "description": "Treasury yields rose after the Federal Reserve signaled caution.",
                "link": "https://example.com/fed",
                "pub_date": "",
                "analysis": "Policy watch.",
                "score": 88,
            },
            {
                "title": "PBOC improves offshore yuan liquidity tools in Hong Kong",
                "description": "The move supports RMB assets and cross-border settlement.",
                "link": "https://example.com/pboc",
                "pub_date": "",
                "analysis": "Asia-Pacific.",
                "score": 72,
            },
            {
                "title": "Oil risk premium eases as Middle East shipping stabilizes",
                "description": "Crude traders watch Iran and regional supply routes.",
                "link": "https://example.com/oil",
                "pub_date": "",
                "analysis": "Energy markets.",
                "score": 64,
            },
            {
                "title": "G7 focuses on critical minerals and supply chain security",
                "description": "Industrial policy competition remains a global macro theme.",
                "link": "https://example.com/g7",
                "pub_date": "",
                "analysis": "Trade landscape.",
                "score": 62,
            },
            {
                "title": "Hong Kong IPO activity ranks near the top globally",
                "description": "Capital markets reform supports investment banking and custody demand.",
                "link": "https://example.com/hk-ipo",
                "pub_date": "",
                "analysis": "Asia-Pacific.",
                "score": 60,
            },
            {
                "title": "Israel and Lebanon tensions keep regional credit spreads volatile",
                "description": "Middle East risk remains event driven.",
                "link": "https://example.com/israel-lebanon",
                "pub_date": "",
                "analysis": "Geopolitical.",
                "score": 58,
            },
        ]

    def test_build_structured_briefing_contains_bank_sections_without_ai(self):
        structured = mb.build_structured_briefing(
            self.sample_market_data(),
            self.sample_news(),
            ai_client=None,
        )

        self.assertEqual(
            list(structured.keys()),
            [
                "global_macro",
                "mainland_hk_macao",
                "middle_east_macro",
                "liquidity_assets",
                "senior_insight",
                "entity_watch",
                "sources",
            ],
        )
        self.assertTrue(structured["global_macro"])
        self.assertTrue(structured["mainland_hk_macao"])
        self.assertTrue(structured["middle_east_macro"])
        self.assertIn("\u7f8e\u5143\u6d41\u52a8\u6027", [item["title"] for item in structured["liquidity_assets"]])
        self.assertTrue(structured["senior_insight"])
        self.assertTrue(structured["entity_watch"])

    def test_ai_result_keeps_related_items_and_caps_each_section_at_ten(self):
        def sparse_ai_client(_market_data, _news_items):
            return {
                "global_macro": [
                    {"title": "AI global one", "summary": "s", "impact": "i", "link": ""},
                    {"title": "AI global two", "summary": "s", "impact": "i", "link": ""},
                ],
                "mainland_hk_macao": [
                    {"title": "AI HK one", "summary": "s", "impact": "i", "link": ""},
                ],
                "middle_east_macro": [
                    {"title": "AI ME one", "summary": "s", "impact": "i", "link": ""},
                ],
                "liquidity_assets": [],
                "senior_insight": "Insight",
                "entity_watch": [],
                "sources": [],
            }

        structured = mb.build_structured_briefing(
            self.sample_market_data(),
            self.sample_news(),
            ai_client=sparse_ai_client,
        )

        self.assertLessEqual(len(structured["global_macro"]), 10)
        self.assertLessEqual(len(structured["mainland_hk_macao"]), 10)
        self.assertLessEqual(len(structured["middle_east_macro"]), 10)

    def test_section_padding_does_not_cross_fill_unrelated_news(self):
        news = [
            {
                "title": "South Africa central bank warns inflation expectations are rising",
                "description": "The governor discussed inflation risks in South Africa.",
                "link": "https://example.com/south-africa",
                "analysis": "Policy watch.",
                "score": 80,
            },
            {
                "title": "Hong Kong IPO activity ranks near the top globally",
                "description": "Capital markets reform supports Hong Kong investment banking.",
                "link": "https://example.com/hk-ipo",
                "analysis": "Asia-Pacific.",
                "score": 70,
            },
        ]

        structured = mb.build_structured_briefing(
            self.sample_market_data(),
            news,
            ai_client=None,
        )

        mainland_titles = [item["title"] for item in structured["mainland_hk_macao"]]
        self.assertTrue(any("Hong Kong" in title for title in mainland_titles))
        self.assertFalse(any("South Africa" in title for title in mainland_titles))
        self.assertGreaterEqual(len(mainland_titles), 1)

    def test_ai_misclassified_news_is_removed_before_padding(self):
        def misclassified_ai_client(_market_data, _news_items):
            return {
                "global_macro": [
                    {"title": "South Africa inflation expectations rise", "summary": "South Africa central bank warning.", "impact": "Rates risk.", "link": ""},
                ],
                "mainland_hk_macao": [
                    {"title": "European stocks rebound as stagflation risks ease", "summary": "Europe equity markets recover.", "impact": "Risk sentiment.", "link": ""},
                ],
                "middle_east_macro": [
                    {"title": "Iraq asks oil fields to lift output after US-Iran deal", "summary": "Middle East supply routes improve.", "impact": "Oil risk premium.", "link": ""},
                ],
                "liquidity_assets": [],
                "senior_insight": "Insight",
                "entity_watch": [],
                "sources": [],
            }

        structured = mb.build_structured_briefing(
            self.sample_market_data(),
            self.sample_news(),
            ai_client=misclassified_ai_client,
        )

        mainland_titles = [item["title"] for item in structured["mainland_hk_macao"]]
        self.assertFalse(any("European" in title for title in mainland_titles))
        self.assertTrue(any("PBOC" in title or "Hong Kong" in title for title in mainland_titles))
        self.assertGreaterEqual(len(mainland_titles), 1)

    def test_rendered_news_sections_cap_at_ten_items_each(self):
        structured = mb.build_structured_briefing(
            self.sample_market_data(),
            self.sample_news(),
            ai_client=None,
        )

        html = mb.render_bank_sections(structured)

        for title in ("\u5168\u7403\u5b8f\u89c2", "\u5185\u5730\u53ca\u6e2f\u6fb3", "\u4e2d\u4e1c\u5b8f\u89c2"):
            start = html.index(f'<div class="section-title">{title}</div>')
            next_start = html.find('<div class="section-title">', start + 1)
            section_html = html[start:] if next_start == -1 else html[start:next_start]
            self.assertLessEqual(section_html.count('class="bank-news-item"'), 10)

    def test_collect_news_combines_rss_newsapi_and_gnews(self):
        config = {
            "briefing": {
                "news_sources": ["rss-1"],
                "newsapi": {"enabled": True},
                "gnews": {"enabled": True},
            }
        }

        rss_items = [("RSS one", "https://example.com/rss-1", "desc", "Wed, 18 Jun 2026 00:00:00 GMT")]
        newsapi_items = [{
            "title": "API one",
            "description": "desc",
            "url": "https://example.com/api-1",
            "publishedAt": "2026-06-18T00:00:00Z",
            "source": {"name": "Source A"},
        }]
        gnews_items = [{
            "title": "GNews one",
            "description": "desc",
            "url": "https://example.com/gnews-1",
            "publishedAt": "2026-06-18T00:00:00Z",
            "source": {"name": "Source B"},
        }]

        old_fetch_rss = mb.fetch_rss
        old_fetch_newsapi = getattr(mb, "fetch_newsapi_articles", None)
        old_fetch_gnews = getattr(mb, "fetch_gnews_articles", None)
        mb.fetch_rss = lambda url, timeout=15: rss_items
        mb.fetch_newsapi_articles = lambda config, market_data: newsapi_items
        mb.fetch_gnews_articles = lambda config, market_data: gnews_items
        try:
            combined = mb.collect_news(config, self.sample_market_data())
        finally:
            mb.fetch_rss = old_fetch_rss
            if old_fetch_newsapi is not None:
                mb.fetch_newsapi_articles = old_fetch_newsapi
            if old_fetch_gnews is not None:
                mb.fetch_gnews_articles = old_fetch_gnews

        titles = [item["title"] for item in combined]
        self.assertIn("RSS one", titles)
        self.assertIn("API one", titles)
        self.assertIn("GNews one", titles)

    def test_ai_sector_items_sorted_by_importance_and_capped_at_ten(self):
        items = [
            {"title": f"Item {i}", "importance": i, "score": i}
            for i in range(1, 13)
        ]

        sorted_items = mb.sort_section_items(items)[:10]
        sorted_titles = [item["title"] for item in sorted_items]
        self.assertEqual(len(sorted_titles), 10)
        self.assertEqual(sorted_titles[0], "Item 12")
        self.assertEqual(sorted_titles[-1], "Item 3")

    def test_agnes_receives_up_to_fifty_news_items(self):
        captured = {}

        def fake_urlopen(req, timeout):
            captured["body"] = req.data.decode("utf-8")

            class Response:
                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc, tb):
                    return False

                def read(self):
                    return (
                        b'{"choices":[{"message":{"content":"{\\"global_macro\\":[],'
                        b'\\"mainland_hk_macao\\":[],\\"middle_east_macro\\":[],'
                        b'\\"liquidity_assets\\":[],\\"senior_insight\\":\\"x\\",'
                        b'\\"entity_watch\\":[],\\"sources\\":[]}"}}]}'
                    )

            return Response()

        old_urlopen = mb.urllib.request.urlopen
        old_key = mb.os.environ.get("AGNES_API_KEY")
        mb.urllib.request.urlopen = fake_urlopen
        mb.os.environ["AGNES_API_KEY"] = "test-key"
        try:
            news = [
                {
                    "title": f"News item {i}",
                    "description": "Description",
                    "link": f"https://example.com/{i}",
                    "analysis": "Analysis",
                    "score": i,
                }
                for i in range(60)
            ]
            mb.agnes_structured_briefing(self.sample_market_data(), news)
        finally:
            mb.urllib.request.urlopen = old_urlopen
            if old_key is None:
                mb.os.environ.pop("AGNES_API_KEY", None)
            else:
                mb.os.environ["AGNES_API_KEY"] = old_key

        self.assertLessEqual(captured["body"].count("News item "), 90)

    def test_html_uses_bank_sections_and_inline_dark_email_shell(self):
        structured = mb.build_structured_briefing(
            self.sample_market_data(),
            self.sample_news(),
            ai_client=None,
        )

        html = mb.build_html_briefing(
            self.sample_market_data(),
            self.sample_news(),
            "Monday, June 22, 2026",
            structured_briefing=structured,
        )

        self.assertIn("\u5168\u7403\u5b8f\u89c2", html)
        self.assertIn("\u5185\u5730\u53ca\u6e2f\u6fb3", html)
        self.assertIn("\u4e2d\u4e1c\u5b8f\u89c2", html)
        self.assertIn("\u5e02\u573a\u6d41\u52a8\u6027\u4e0e\u5927\u7c7b\u8d44\u4ea7", html)
        self.assertIn("\u4eca\u65e5\u9ad8\u5c42\u6d1e\u5bdf", html)
        self.assertIn("\u91cd\u70b9\u5173\u6ce8\u5b9e\u4f53\u52a8\u6001", html)
        self.assertNotIn("\u5341\u5927\u91d1\u878d\u65b0\u95fb", html)
        self.assertIn('bgcolor="#0a0a0a"', html)
        self.assertIn('style="background-color:#0a0a0a;', html)


if __name__ == "__main__":
    unittest.main()
