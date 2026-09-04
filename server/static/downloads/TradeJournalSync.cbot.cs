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

        [Parameter("Sync Real Candles for Chart", Group = "Chart Data", DefaultValue = true)]
        public bool SyncCandles { get; set; }

        [Parameter("Max Real Bars per Trade", Group = "Chart Data", DefaultValue = 500, MinValue = 50, MaxValue = 2000)]
        public int MaxCandlesPerTrade { get; set; }

        [Parameter("Max Recent Trades with Candles", Group = "Chart Data", DefaultValue = 10, MinValue = 1, MaxValue = 50)]
        public int MaxTradesWithCandles { get; set; }

        private static readonly JsonSerializerOptions JsonOptions = new JsonSerializerOptions
        {
            DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull
        };

        private readonly Dictionary<int, long> _positionToOrderMap = new Dictionary<int, long>();

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

            try
            {
                PendingOrders.Filled += OnPendingOrderFilled;
                PendingOrders.Created += args => SyncAccount();
                PendingOrders.Cancelled += args => SyncAccount();
                PendingOrders.Modified += args => SyncAccount();
                Positions.Opened += args => SyncAccount();
                Positions.Closed += args => SyncAccount();
            }
            catch (Exception ex)
            {
                Print("Event subscription notice: {0}", ex.Message);
            }

            SyncAccount();
            Timer.Start(TimeSpan.FromMinutes(SyncIntervalMinutes));
        }

        private void OnPendingOrderFilled(PendingOrderFilledEventArgs args)
        {
            try
            {
                if (args.Position != null && args.PendingOrder != null)
                {
                    _positionToOrderMap[args.Position.Id] = args.PendingOrder.Id;
                }
            }
            catch {}
            SyncAccount();
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

            var pendingOrders = PendingOrders.Select(ToPendingOrder).ToList();
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
                OpenTrades = openTrades,
                PendingOrders = pendingOrders
            };
        }

        private JournalTrade ToClosedTrade(List<HistoricalTrade> trades)
        {
            var firstTrade = trades.First();
            var totalLots = trades.Sum(trade => trade.Quantity);
            long? orderId = null;
            if (_positionToOrderMap.TryGetValue(firstTrade.PositionId, out var mappedOrderId))
            {
                orderId = mappedOrderId;
            }

            return new JournalTrade
            {
                Ticket = "ctrader-position-" + firstTrade.PositionId.ToString(CultureInfo.InvariantCulture),
                PositionId = firstTrade.PositionId.ToString(CultureInfo.InvariantCulture),
                OrderId = orderId.HasValue ? orderId.Value.ToString(CultureInfo.InvariantCulture) : null,
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
            long? orderId = null;
            if (_positionToOrderMap.TryGetValue(position.Id, out var mappedOrderId))
            {
                orderId = mappedOrderId;
            }

            return new JournalTrade
            {
                Ticket = "ctrader-position-" + position.Id.ToString(CultureInfo.InvariantCulture),
                PositionId = position.Id.ToString(CultureInfo.InvariantCulture),
                OrderId = orderId.HasValue ? orderId.Value.ToString(CultureInfo.InvariantCulture) : null,
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
                Comment = CombineNote(position.Label, position.Comment),
                Status = "OPEN"
            };
        }

        private JournalTrade ToPendingOrder(PendingOrder order)
        {
            return new JournalTrade
            {
                Ticket = "ctrader-order-" + order.Id.ToString(CultureInfo.InvariantCulture),
                OrderId = order.Id.ToString(CultureInfo.InvariantCulture),
                OrderType = order.OrderType.ToString(),
                Symbol = order.SymbolName,
                Type = order.TradeType == TradeType.Buy ? 0 : 1,
                Lots = order.Quantity,
                OpenTime = ToIsoTime(Server.TimeInUtc),
                OpenPrice = order.TargetPrice,
                StopLoss = order.StopLoss,
                TakeProfit = order.TakeProfit,
                Comment = CombineNote(order.Label, order.Comment),
                Status = "PENDING"
            };
        }

        private struct ChartTimeframeInfo
        {
            public TimeFrame TimeFrame;
            public string Name;
            public int Seconds;
        }

        private static readonly ChartTimeframeInfo[] SupportedTimeframes = new[]
        {
            new ChartTimeframeInfo { TimeFrame = TimeFrame.Minute15, Name = "M15", Seconds = 900 },
            new ChartTimeframeInfo { TimeFrame = TimeFrame.Hour,     Name = "H1",  Seconds = 3600 },
            new ChartTimeframeInfo { TimeFrame = TimeFrame.Hour4,    Name = "H4",  Seconds = 14400 },
            new ChartTimeframeInfo { TimeFrame = TimeFrame.Daily,    Name = "D1",  Seconds = 86400 }
        };

        private static ChartTimeframeInfo SelectTimeframe(DateTime openTime, DateTime closeTime, int maxBars)
        {
            double durationSeconds = Math.Max(0, (closeTime - openTime).TotalSeconds);
            foreach (var tf in SupportedTimeframes)
            {
                double requiredBars = (durationSeconds / tf.Seconds) + 16;
                if (requiredBars <= maxBars)
                    return tf;
            }
            return SupportedTimeframes[SupportedTimeframes.Length - 1]; // D1 fallback
        }

        private void AttachCandles(List<JournalTrade> closedTrades, List<JournalTrade> openTrades)
        {
            if (!SyncCandles || MaxCandlesPerTrade <= 0)
                return;

            foreach (var openTrade in openTrades)
            {
                if (DateTime.TryParse(openTrade.OpenTime, CultureInfo.InvariantCulture, DateTimeStyles.AdjustToUniversal | DateTimeStyles.AssumeUniversal, out var openTime))
                {
                    openTrade.Candles = GetCandlesForTrade(openTrade.Symbol, openTime, Server.TimeInUtc, MaxCandlesPerTrade);
                }
            }

            var recentClosed = closedTrades
                .Where(t => !string.IsNullOrEmpty(t.CloseTime))
                .OrderByDescending(t => t.CloseTime)
                .Take(MaxTradesWithCandles)
                .ToList();

            foreach (var trade in recentClosed)
            {
                if (DateTime.TryParse(trade.OpenTime, CultureInfo.InvariantCulture, DateTimeStyles.AdjustToUniversal | DateTimeStyles.AssumeUniversal, out var openTime) &&
                    DateTime.TryParse(trade.CloseTime, CultureInfo.InvariantCulture, DateTimeStyles.AdjustToUniversal | DateTimeStyles.AssumeUniversal, out var closeTime))
                {
                    trade.Candles = GetCandlesForTrade(trade.Symbol, openTime, closeTime, MaxCandlesPerTrade);
                }
            }
        }

        private List<JournalCandle> GetCandlesForTrade(string symbolName, DateTime openTime, DateTime closeTime, int maxBars)
        {
            try
            {
                var tfInfo = SelectTimeframe(openTime, closeTime, maxBars);
                var bars = MarketData.GetBars(tfInfo.TimeFrame, symbolName);
                var fromTime = openTime.AddSeconds(-8 * tfInfo.Seconds);
                var toTime = closeTime.AddSeconds(8 * tfInfo.Seconds);
                if (toTime > Server.TimeInUtc)
                    toTime = Server.TimeInUtc;

                int loadAttempts = 0;
                while (bars.Count > 0 && bars.OpenTimes[0] > fromTime && loadAttempts < 25 && bars.LoadMoreHistory() > 0)
                {
                    loadAttempts++;
                }

                if (bars.Count == 0)
                    return new List<JournalCandle>();

                int startIndex = -1;
                for (int i = 0; i < bars.Count; i++)
                {
                    if (bars.OpenTimes[i] >= fromTime)
                    {
                        startIndex = i;
                        break;
                    }
                }
                if (startIndex < 0)
                    startIndex = (fromTime <= bars.OpenTimes[0]) ? 0 : -1;

                if (startIndex < 0)
                    return new List<JournalCandle>();

                int endIndex = -1;
                for (int i = bars.Count - 1; i >= 0; i--)
                {
                    if (bars.OpenTimes[i] <= toTime)
                    {
                        endIndex = i;
                        break;
                    }
                }
                if (endIndex < 0)
                    endIndex = (toTime >= bars.OpenTimes[bars.Count - 1]) ? bars.Count - 1 : -1;

                if (endIndex < 0 || endIndex < startIndex)
                    return new List<JournalCandle>();

                int count = endIndex - startIndex + 1;
                if (count > maxBars)
                {
                    startIndex = Math.Max(0, endIndex - maxBars + 1);
                }

                var candles = new List<JournalCandle>();
                for (int i = startIndex; i <= endIndex; i++)
                {
                    candles.Add(new JournalCandle
                    {
                        Timeframe = tfInfo.Name,
                        Time = ToUnixSeconds(bars.OpenTimes[i]),
                        Open = bars.OpenPrices[i],
                        High = bars.HighPrices[i],
                        Low = bars.LowPrices[i],
                        Close = bars.ClosePrices[i],
                        Volume = bars.TickVolumes[i]
                    });
                }
                return candles;
            }
            catch (Exception exception)
            {
                Print("Could not load candles for {0}: {1}", symbolName, exception.Message);
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

        [JsonPropertyName("pending_orders")]
        public List<JournalTrade> PendingOrders { get; set; } = new List<JournalTrade>();
    }

    public class JournalTrade
    {
        [JsonPropertyName("ticket")]
        public string Ticket { get; set; }

        [JsonPropertyName("position_id")]
        public string PositionId { get; set; }

        [JsonPropertyName("order_id")]
        public string OrderId { get; set; }

        [JsonPropertyName("order_type")]
        public string OrderType { get; set; }

        [JsonPropertyName("status")]
        public string Status { get; set; }

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
        [JsonPropertyName("timeframe")]
        public string Timeframe { get; set; } = "M15";

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
