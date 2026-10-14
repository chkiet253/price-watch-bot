"""Regression checks for the two source formats that previously lost prices."""

import json
import unittest
import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import patch

import price_bot as bot


class SourceChecks(unittest.TestCase):
    def test_sjc_seed_survives_source_failure_without_losing_its_date(self):
        seed = bot.Quote("Vàng SJC", "mua 14,030,000 / bán 14,333,000", "đồng/chỉ",
                         bot.SOURCES["gold"], date(2026, 10, 14))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "quotes.json"
            with patch.object(bot, "CACHE_PATH", path):
                bot.save_price_cache({seed.name: seed})
            cache = bot.load_price_cache(path)
        older = bot.Quote(seed.name, "mua 14,100,000 / bán 14,400,000", seed.unit,
                          seed.source, date(2026, 10, 13))
        bot.use_latest_dated_quote(older, cache)
        missing = bot.Quote(seed.name, None, seed.unit, seed.source, None)
        result = bot.use_latest_dated_quote(missing, cache)
        self.assertTrue(result.cached)
        self.assertEqual(result.value, seed.value)
        self.assertEqual(result.source_date, seed.source_date)

    def test_coffee_css_prices_stay_attached_to_their_row_dates(self):
        page = bot.parse_page("""
            <style>
              .today::after { content:'93,000'; }
              .delta::after { content:'-200'; }
              .old::after { content:'93,200'; }
              .padding::after { display:inline-block; content:' '; }
            </style>
            <h1>Giá cà phê Đắk Lắk 14/10/2026</h1>
            <table>
              <tr><td>13/10/2026</td><td><span class="old"></span></td></tr>
              <tr><td>14/10/2026</td><td><span class="today padding"></span></td>
                  <td><span class="delta padding"></span></td></tr>
            </table>
        """)
        with patch.object(bot, "fetch_page", return_value=page):
            quote = bot.parse_coffee()[0]
        self.assertEqual(quote.value, "93,000 (thay đổi -200)")
        self.assertEqual(quote.source_date, date(2026, 10, 14))

    def test_empty_coffee_cells_reuse_a_dated_quote(self):
        page = bot.parse_page("""
            <h1>Giá cà phê Đắk Lắk 14/10/2026</h1>
            <table><tr><td>14/10/2026</td><td><span class="unknown"></span></td></tr></table>
        """)
        with patch.object(bot, "fetch_page", return_value=page):
            missing = bot.parse_coffee()[0]
        old = bot.Quote(missing.name, "93,200", missing.unit, missing.source, date(2026, 10, 13))
        result = bot.use_latest_dated_quote(missing, {old.name: old})
        self.assertTrue(result.cached)
        self.assertEqual(result.value, "93,200")
        self.assertEqual(result.source_date, date(2026, 10, 13))

    def test_sjc_service_selects_small_bars_and_converts_luong_to_chi(self):
        payload = {
            "success": True, "latestDate": "13:46 14/10/2026",
            "data": [
                {"TypeName": "Vàng nhẫn SJC", "Buy": "139,800", "Sell": "142,800"},
                {"TypeName": "Vàng SJC 1L, 10L, 1KG", "Buy": "140,300", "Sell": "143,300"},
                {"TypeName": "Vàng SJC 0.5 chỉ, 1 chỉ, 2 chỉ", "Buy": "140,300", "Sell": "143,330"},
            ],
        }
        with patch.object(bot, "fetch_content", return_value=json.dumps(payload)) as fetch:
            quote = bot.parse_gold()[0]
        fetch.assert_called_once_with(bot.SJC_PRICE_SERVICE, data=b"")
        self.assertEqual(quote.value, "mua 14,030,000 / bán 14,333,000")
        self.assertEqual(quote.unit, "đồng/chỉ")
        self.assertEqual(quote.source_date, date(2026, 10, 14))
        payload["latestDate"] = ""
        with patch.object(bot, "fetch_content", return_value=json.dumps(payload)):
            undated = bot.use_latest_dated_quote(bot.parse_gold()[0], {})
        self.assertIsNone(undated.value)


if __name__ == "__main__":
    unittest.main()
