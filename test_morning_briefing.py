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
        self.assertIn("美元流动性", [item["title"] for item in structured["liquidity_assets"]])
        self.assertTrue(structured["senior_insight"])
        self.assertTrue(structured["entity_watch"])

    def test_html_uses_bank_sections_instead_of_top_ten_heading(self):
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

        self.assertIn("全球宏观", html)
        self.assertIn("内地及港澳", html)
        self.assertIn("中东宏观", html)
        self.assertIn("市场流动性与大类资产", html)
        self.assertIn("今日高层洞察", html)
        self.assertIn("重点关注实体动态", html)
        self.assertNotIn("十大金融新闻", html)


if __name__ == "__main__":
    unittest.main()
