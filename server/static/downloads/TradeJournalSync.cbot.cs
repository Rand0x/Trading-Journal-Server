// TradeJournalSync cBot for cTrader
//
// Read-only account exporter for Trading Journal Server. It does not contain
// any order-placement, order-modification, or position-closing calls.
// Run it locally when the journal server is reachable on your LAN.

using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Serialization;
using cAlgo.API;
using cAlgo.API.Internals;

namespace cAlgo.Robots
{
    [Robot(TimeZone = TimeZones.UTC, AccessRights = AccessRights.None)]
    public class TradeJournalSync : Robot
    {
        [Parameter("Journal Server URL", Group = "Connection", DefaultValue = "http://192.168.1.100:8000/api/sync/ctrader-push")]
        public string JournalServerUrl { get; set; }

        [Parameter("Journal API Key (not cTrader token)", Group = "Connection", DefaultValue = "")]
        public string JournalApiKey { get; set; }

        [Parameter("Sync Interval (minutes)", Group = "Sync", DefaultValue = 5, MinValue = 1, MaxValue = 1440)]
        public int SyncIntervalMinutes { get; set; }

        [Parameter("History Days", Group = "Sync", DefaultValue = 90, MinValue = 1, MaxValue = 3650)]
        public int HistoryDays { get; set; }

        [Parameter("Maximum Closed Trades", Group = "Sync", DefaultValue = 2000, MinValue = 1, MaxValue = 10000)]
        public int MaximumClosedTrades { get; set; }

        [Parameter("M15 Candles per Symbol", Group = "Chart Data", DefaultValue = 160, MinValue = 0, MaxValue = 500)]
        public int CandlesPerSymbol { get; set; }

        private static readonly JsonSerializerOptions JsonOptions = new JsonSerializerOptions
        {
            DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull
        };

        protected override void OnStart()
        {
            if (!Uri.TryCreate(JournalServerUrl, UriKind.Absolute, out _))
            {
                Print("Trade Journal sync stopped: Journal Server URL is invalid.");
                return;
            }

            if (string.IsNullOrWhiteSpace(JournalApiKey))
            {
                Print("Trade Journal sync stopped: enter the Journal API Key from the account card.");
                return;
            }

            Print("Trade Journal cBot started. This cBot only reads account data and sends it to the journal.");
            SyncAccount();
            Timer.Start(TimeSpan.FromMinutes(SyncIntervalMinutes));
        }

        protected override void OnTimer()
        {
            SyncAccount();
        }

        protected override void OnStop()
        {
            Timer.Stop();
        }

        private void SyncAccount()
        {
            try
            {
                var payload = BuildPayload();
                var request = new HttpRequest(new Uri(JournalServerUrl))
                {
                    Method = HttpMethod.Post,
                    Body = JsonSerializer.Serialize(payload, JsonOptions),
                    Timeout = TimeSpan.FromSeconds(20)
                };
                request.Headers.Add("Content-Type", "application/json");
                request.Headers.Add("X-API-Key", JournalApiKey);

                var response = Http.Send(request);
                if (response.IsSuccessful)
                    Print("Trade Journal sync completed: HTTP {0} - {1}", response.StatusCode, response.Body);
                else
                    Print("Trade Journal sync failed: HTTP {0} - {1}", response.StatusCode, response.Body);
            }
            catch (Exception exception)
            {
                Print("Trade Journal sync failed: {0}", exception.Message);
            }
        }

        private JournalPayload BuildPayload()
        {
            var cutoff = Server.TimeInUtc.AddDays(-HistoryDays);
            var closedTrades = History
                .Where(trade => trade.ClosingTime >= cutoff)
                .GroupBy(trade => trade.PositionId)
                .OrderByDescending(group => group.Max(trade => trade.ClosingTime))
                .Take(MaximumClosedTrades)
                .Select(group => ToClosedTrade(group.OrderBy(trade => trade.ClosingTime).ToList()))
                .OrderBy(trade => trade.CloseTime)
                .ToList();

            var openTrades = Positions.Select(ToOpenTrade).ToList();
            AttachCandles(closedTrades, openTrades);

            return new JournalPayload
            {
                AccountNumber = Account.Number.ToString(CultureInfo.InvariantCulture),
                Broker = Account.BrokerName ?? "cTrader",
                Platform = "cTrader",
                Currency = Account.Asset.Name,
                Balance = Account.Balance,
                Equity = Account.Equity,
                Margin = Account.Margin,
                FreeMargin = Account.FreeMargin,
                Leverage = Math.Max(1, (int)Math.Round(Account.PreciseLeverage)),
                ClosedTrades = closedTrades,
                OpenTrades = openTrades
            };
        }

        private JournalTrade ToClosedTrade(List<HistoricalTrade> trades)
        {
            var firstTrade = trades.First();
            var totalLots = trades.Sum(trade => trade.Quantity);
            return new JournalTrade
            {
                Ticket = "ctrader-position-" + firstTrade.PositionId.ToString(CultureInfo.InvariantCulture),
                PositionId = firstTrade.PositionId.ToString(CultureInfo.InvariantCulture),
                Symbol = firstTrade.SymbolName,
                Type = firstTrade.TradeType == TradeType.Buy ? 0 : 1,
                Lots = totalLots,
                OpenTime = ToIsoTime(trades.Min(trade => trade.EntryTime)),
                CloseTime = ToIsoTime(trades.Max(trade => trade.ClosingTime)),
                OpenPrice = trades.Sum(trade => trade.Quantity * trade.EntryPrice) / totalLots,
                ClosePrice = trades.Sum(trade => trade.Quantity * trade.ClosingPrice) / totalLots,
                Commission = trades.Sum(trade => trade.Commissions),
                Swap = trades.Sum(trade => trade.Swap),
                Profit = trades.Sum(trade => trade.NetProfit),
                Comment = CombineNote(firstTrade.Label, firstTrade.Comment),
                PartialCloses = trades.Select(ToPartialClose).ToList()
            };
        }

        private JournalPartialClose ToPartialClose(HistoricalTrade trade)
        {
            return new JournalPartialClose
            {
                Ticket = "ctrader-deal-" + trade.ClosingDealId.ToString(CultureInfo.InvariantCulture),
                Volume = trade.Quantity,
                CloseTime = ToIsoTime(trade.ClosingTime),
                ClosePrice = trade.ClosingPrice,
                Commission = trade.Commissions,
                Swap = trade.Swap,
                GrossProfit = trade.GrossProfit,
                NetProfit = trade.NetProfit
            };
        }

        private JournalTrade ToOpenTrade(Position position)
        {
            return new JournalTrade
            {
                Ticket = "ctrader-position-" + position.Id.ToString(CultureInfo.InvariantCulture),
                PositionId = position.Id.ToString(CultureInfo.InvariantCulture),
                Symbol = position.SymbolName,
                Type = position.TradeType == TradeType.Buy ? 0 : 1,
                Lots = position.Quantity,
                OpenTime = ToIsoTime(position.EntryTime),
                OpenPrice = position.EntryPrice,
                StopLoss = position.StopLoss,
                TakeProfit = position.TakeProfit,
                Commission = position.Commissions,
                Swap = position.Swap,
                Profit = position.NetProfit,
                Comment = CombineNote(position.Label, position.Comment)
            };
        }

        private void AttachCandles(List<JournalTrade> closedTrades, List<JournalTrade> openTrades)
        {
            if (CandlesPerSymbol <= 0)
                return;

            var symbols = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (var trade in closedTrades.Concat(openTrades))
            {
                if (!symbols.Add(trade.Symbol))
                    continue;

                var candles = GetM15Candles(trade.Symbol);
                foreach (var matchingTrade in closedTrades.Concat(openTrades).Where(item => string.Equals(item.Symbol, trade.Symbol, StringComparison.OrdinalIgnoreCase)))
                    matchingTrade.Candles = candles;
            }
        }

        private List<JournalCandle> GetM15Candles(string symbolName)
        {
            try
            {
                var bars = MarketData.GetBars(TimeFrame.Minute15, symbolName);
                while (bars.Count < CandlesPerSymbol && bars.LoadMoreHistory() > 0)
                {
                    // Load enough local history for the requested chart context.
                }

                var startIndex = Math.Max(0, bars.Count - CandlesPerSymbol);
                var candles = new List<JournalCandle>();
                for (var index = startIndex; index < bars.Count; index++)
                {
                    candles.Add(new JournalCandle
                    {
                        Time = ToUnixSeconds(bars.OpenTimes[index]),
                        Open = bars.OpenPrices[index],
                        High = bars.HighPrices[index],
                        Low = bars.LowPrices[index],
                        Close = bars.ClosePrices[index],
                        Volume = bars.TickVolumes[index]
                    });
                }
                return candles;
            }
            catch (Exception exception)
            {
                Print("Could not load M15 candles for {0}: {1}", symbolName, exception.Message);
                return new List<JournalCandle>();
            }
        }

        private static string CombineNote(string label, string comment)
        {
            return string.Join(" | ", new[] { label, comment }.Where(value => !string.IsNullOrWhiteSpace(value)));
        }

        private static string ToIsoTime(DateTime value)
        {
            return DateTime.SpecifyKind(value, DateTimeKind.Utc).ToString("o", CultureInfo.InvariantCulture);
        }

        private static long ToUnixSeconds(DateTime value)
        {
            return new DateTimeOffset(DateTime.SpecifyKind(value, DateTimeKind.Utc)).ToUnixTimeSeconds();
        }
    }

    public class JournalPayload
    {
        [JsonPropertyName("source")]
        public string Source { get; set; } = "ctrader-cbot";

        [JsonPropertyName("account_number")]
        public string AccountNumber { get; set; }

        [JsonPropertyName("broker")]
        public string Broker { get; set; }

        [JsonPropertyName("platform")]
        public string Platform { get; set; }

        [JsonPropertyName("currency")]
        public string Currency { get; set; }

        [JsonPropertyName("balance")]
        public double Balance { get; set; }

        [JsonPropertyName("equity")]
        public double Equity { get; set; }

        [JsonPropertyName("margin")]
        public double Margin { get; set; }

        [JsonPropertyName("free_margin")]
        public double FreeMargin { get; set; }

        [JsonPropertyName("leverage")]
        public int Leverage { get; set; }

        [JsonPropertyName("closed_trades")]
        public List<JournalTrade> ClosedTrades { get; set; }

        [JsonPropertyName("open_trades")]
        public List<JournalTrade> OpenTrades { get; set; }
    }

    public class JournalTrade
    {
        [JsonPropertyName("ticket")]
        public string Ticket { get; set; }

        [JsonPropertyName("position_id")]
        public string PositionId { get; set; }

        [JsonPropertyName("symbol")]
        public string Symbol { get; set; }

        [JsonPropertyName("type")]
        public int Type { get; set; }

        [JsonPropertyName("lots")]
        public double Lots { get; set; }

        [JsonPropertyName("open_time")]
        public string OpenTime { get; set; }

        [JsonPropertyName("close_time")]
        public string CloseTime { get; set; }

        [JsonPropertyName("open_price")]
        public double OpenPrice { get; set; }

        [JsonPropertyName("close_price")]
        public double? ClosePrice { get; set; }

        [JsonPropertyName("stop_loss")]
        public double? StopLoss { get; set; }

        [JsonPropertyName("take_profit")]
        public double? TakeProfit { get; set; }

        [JsonPropertyName("commission")]
        public double Commission { get; set; }

        [JsonPropertyName("swap")]
        public double Swap { get; set; }

        [JsonPropertyName("profit")]
        public double Profit { get; set; }

        [JsonPropertyName("comment")]
        public string Comment { get; set; }

        [JsonPropertyName("candles")]
        public List<JournalCandle> Candles { get; set; }

        [JsonPropertyName("partial_closes")]
        public List<JournalPartialClose> PartialCloses { get; set; }
    }

    public class JournalPartialClose
    {
        [JsonPropertyName("ticket")]
        public string Ticket { get; set; }

        [JsonPropertyName("volume")]
        public double Volume { get; set; }

        [JsonPropertyName("close_time")]
        public string CloseTime { get; set; }

        [JsonPropertyName("close_price")]
        public double ClosePrice { get; set; }

        [JsonPropertyName("commission")]
        public double Commission { get; set; }

        [JsonPropertyName("swap")]
        public double Swap { get; set; }

        [JsonPropertyName("gross_profit")]
        public double GrossProfit { get; set; }

        [JsonPropertyName("net_profit")]
        public double NetProfit { get; set; }
    }

    public class JournalCandle
    {
        [JsonPropertyName("time")]
        public long Time { get; set; }

        [JsonPropertyName("open")]
        public double Open { get; set; }

        [JsonPropertyName("high")]
        public double High { get; set; }

        [JsonPropertyName("low")]
        public double Low { get; set; }

        [JsonPropertyName("close")]
        public double Close { get; set; }

        [JsonPropertyName("volume")]
        public double Volume { get; set; }
    }
}
