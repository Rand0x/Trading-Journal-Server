"""Unit tests for statement parser (MT4, MT5, cTrader, TradeZella formats)."""
import unittest
from server.connectors.statement_parser import _parse_csv, _parse_mt4_html

class TestStatementParser(unittest.TestCase):
    def test_parse_ctrader_csv(self):
        csv_content = """Deal ID,Symbol,Opening Direction,Volume,Opening Time,Closing Time,Entry Price,Closing Price,Net USD,Gross USD,Commission,Swap
1001,EURUSD,Buy,100000,2026-08-10 10:00:00,2026-08-10 11:30:00,1.08500,1.08800,290.00,300.00,-10.00,0.00
1002,GBPUSD,Sell,50000,2026-08-11 14:00:00,2026-08-11 15:00:00,1.29000,1.29200,-105.00,-100.00,-5.00,0.00
"""
        trades = _parse_csv(csv_content)
        self.assertEqual(len(trades), 2)
        self.assertEqual(trades[0]["symbol"], "EURUSD")
        self.assertEqual(trades[0]["direction"], "BUY")
        self.assertEqual(trades[0]["net_profit"], 290.00)
        self.assertEqual(trades[1]["direction"], "SELL")
        self.assertEqual(trades[1]["net_profit"], -105.00)

    def test_parse_tradezella_csv(self):
        csv_content = """Date,Ticker,Type,Quantity,Entry Price,Exit Price,Net P&L,Notes
2026-08-15 09:30,XAUUSD,Long,0.50,2480.00,2495.00,750.00,Breakout trade
2026-08-16 13:00,US30,Short,0.20,40500,40650,-300.00,Chased move
"""
        trades = _parse_csv(csv_content)
        self.assertEqual(len(trades), 2)
        self.assertEqual(trades[0]["symbol"], "XAUUSD")
        self.assertEqual(trades[0]["direction"], "BUY")
        self.assertEqual(trades[0]["net_profit"], 750.00)
        self.assertEqual(trades[1]["symbol"], "US30")
        self.assertEqual(trades[1]["direction"], "SELL")
        self.assertEqual(trades[1]["net_profit"], -300.00)

    def test_parse_mt4_html(self):
        html_content = """
        <html>
        <body>
        <b>Closed Transactions:</b>
        <table border=0>
        <tr><td>Ticket</td><td>Open Time</td><td>Type</td><td>Size</td><td>Item</td><td>Price</td><td>S/L</td><td>T/P</td><td>Close Time</td><td>Price</td><td>Commission</td><td>Taxes</td><td>Swap</td><td>Profit</td></tr>
        <tr bgcolor="#FFFFFF"><td class=msdate>500123</td><td class=msdate>2026.08.20 10:15:00</td><td>buy</td><td class=msdate>1.00</td><td class=msdate>eurusd</td><td class=msdate>1.08200</td><td class=msdate>1.08000</td><td class=msdate>1.08600</td><td class=msdate>2026.08.20 12:00:00</td><td class=msdate>1.08550</td><td class=msdate>-7.00</td><td class=msdate>0.00</td><td class=msdate>0.00</td><td class=msdate>350.00</td></tr>
        </table>
        </body>
        </html>
        """
        trades = _parse_mt4_html(html_content)
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0]["ticket"], "mt4_500123")
        self.assertEqual(trades[0]["symbol"], "eurusd")
        self.assertEqual(trades[0]["direction"], "BUY")
        self.assertEqual(trades[0]["net_profit"], 350.00)

if __name__ == "__main__":
    unittest.main()
