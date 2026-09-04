//+------------------------------------------------------------------+
//|                                           TradeJournalSync.mq5   |
//|                       Trading Journal Connector                  |
//|                      https://github.com/tradingview/lightweight-charts |
//+------------------------------------------------------------------+
#property copyright   "Trading Journal"
#property link        "http://localhost:8000"
#property version     "1.00"
#property description "Auto-syncs closed trades, balance, equity, and market candle data"
#property description "to your Trading Journal server (READ-ONLY)."

//--- Inputs
input string   InpServerUrl     = "http://192.168.1.100:8000/api/sync/mql"; // Journal Server URL
input string   InpApiKey        = "";                                        // Journal API Key from Web UI
input int      InpSyncInterval  = 60;                                        // Sync Interval (Seconds)
input bool     InpSyncCandles   = true;                                      // Attach Real Candles for Chart Replay
input int      InpCandleBars    = 500;                                       // Maximum real chart bars per trade
input int      InpCandleTrades  = 10;                                        // Number of recent trades to attach candles to

//--- Global variables
datetime g_lastSyncTime = 0;

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
{
   Print("=== TradeJournalSync Initializing ===");
   Print("Server URL: ", InpServerUrl);
   if(StringLen(InpApiKey) == 0)
   {
      Print("Journal API Key is required. Copy it from the account card in the web UI.");
      return(INIT_PARAMETERS_INCORRECT);
   }
   Print("Journal API Key configured.");
   Print("Note: Ensure '", InpServerUrl, "' is added to MT5 Tools -> Options -> Expert Advisors -> Allow WebRequest!");
   
   EventSetTimer(InpSyncInterval);
   // Perform immediate initial sync
   SyncToServer();
   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| Expert deinitialization function                                 |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   EventKillTimer();
   Print("TradeJournalSync Stopped.");
}

//+------------------------------------------------------------------+
//| Timer event function                                             |
//+------------------------------------------------------------------+
void OnTimer()
{
   SyncToServer();
}

//+------------------------------------------------------------------+
//| Trade transaction event function (real-time instant sync)        |
//+------------------------------------------------------------------+
void OnTradeTransaction(const MqlTradeTransaction& trans,
                        const MqlTradeRequest& request,
                        const MqlTradeResult& result)
{
   if(trans.type == TRADE_TRANSACTION_DEAL_ADD ||
      trans.type == TRADE_TRANSACTION_ORDER_ADD ||
      trans.type == TRADE_TRANSACTION_ORDER_DELETE ||
      trans.type == TRADE_TRANSACTION_ORDER_UPDATE)
   {
      Print("Trade/Order transaction detected! Triggering instant sync...");
      SyncToServer();
   }
}

//+------------------------------------------------------------------+
//| Escape string for JSON                                           |
//+------------------------------------------------------------------+
string JsonEscape(string text)
{
   StringReplace(text, "\\", "\\\\");
   StringReplace(text, "\"", "\\\"");
   StringReplace(text, "\r", "");
   StringReplace(text, "\n", "\\n");
   return text;
}

//+------------------------------------------------------------------+
//| Build Candle Bars JSON array for a symbol and timeframe          |
//+------------------------------------------------------------------+
int TimeframeSeconds(ENUM_TIMEFRAMES tf)
{
   if(tf == PERIOD_H1) return(3600);
   if(tf == PERIOD_H4) return(14400);
   if(tf == PERIOD_D1) return(86400);
   return(900); // M15
}

string TimeframeName(ENUM_TIMEFRAMES tf)
{
   if(tf == PERIOD_H1) return("H1");
   if(tf == PERIOD_H4) return("H4");
   if(tf == PERIOD_D1) return("D1");
   return("M15");
}

ENUM_TIMEFRAMES SelectChartTimeframe(datetime openTime, datetime closeTime, int maxBars)
{
   ENUM_TIMEFRAMES timeframes[4] = {PERIOD_M15, PERIOD_H1, PERIOD_H4, PERIOD_D1};
   int duration = (int)MathMax(0, closeTime - openTime);
   for(int index = 0; index < 4; index++)
   {
      int seconds = TimeframeSeconds(timeframes[index]);
      if((duration / seconds) + 16 <= maxBars)
         return(timeframes[index]);
   }
   return(PERIOD_D1);
}

string GetCandlesJson(string symbol, ENUM_TIMEFRAMES tf, datetime openTime, datetime closeTime, int maxBars)
{
   MqlRates rates[];
   ArraySetAsSeries(rates, false);
   int seconds = TimeframeSeconds(tf);
   datetime toTime = (datetime)MathMin(TimeCurrent(), closeTime + (8 * seconds));
   datetime minFromTime = toTime - ((datetime)MathMin(maxBars, 140) * seconds);
   datetime fromTime = (datetime)MathMin(openTime - (8 * seconds), minFromTime);
   int copied = CopyRates(symbol, tf, fromTime, toTime, rates);
   if(copied <= 0) return "[]";

   int startIdx = 0;
   if(copied > maxBars)
   {
      startIdx = copied - maxBars;
   }

   string json = "[";
   bool first = true;
   for(int i = startIdx; i < copied; i++)
   {
      if(!first) json += ",";
      json += StringFormat("{\"timeframe\":\"%s\",\"time\":%d,\"open\":%.5f,\"high\":%.5f,\"low\":%.5f,\"close\":%.5f,\"volume\":%.0f}",
                           TimeframeName(tf), (long)rates[i].time, rates[i].open, rates[i].high, rates[i].low, rates[i].close, (double)rates[i].tick_volume);
      first = false;
   }
   json += "]";
   return json;
}

//+------------------------------------------------------------------+
//| Perform HTTP WebRequest Sync to Trading Journal Server            |
//+------------------------------------------------------------------+
void SyncToServer()
{
   long login = AccountInfoInteger(ACCOUNT_LOGIN);
   double balance = AccountInfoDouble(ACCOUNT_BALANCE);
   double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   double margin = AccountInfoDouble(ACCOUNT_MARGIN);
   double freeMargin = AccountInfoDouble(ACCOUNT_MARGIN_FREE);
   long leverage = AccountInfoInteger(ACCOUNT_LEVERAGE);
   string currency = AccountInfoString(ACCOUNT_CURRENCY);
   string broker = AccountInfoString(ACCOUNT_COMPANY);

   // Select deal history for past 30 days
   datetime fromDate = TimeCurrent() - (30 * 24 * 3600);
   datetime toDate = TimeCurrent();
   HistorySelect(fromDate, toDate);

   int totalDeals = HistoryDealsTotal();
   string closedTradesJson = "[";
   int addedTrades = 0;

   for(int i = totalDeals - 1; i >= 0 && addedTrades < 100; i--)
   {
      ulong dealTicket = HistoryDealGetTicket(i);
      if(dealTicket <= 0) continue;

      long entryType = HistoryDealGetInteger(dealTicket, DEAL_ENTRY);
      // We are interested in exit deals (DEAL_ENTRY_OUT or DEAL_ENTRY_INOUT)
      if(entryType != DEAL_ENTRY_OUT && entryType != DEAL_ENTRY_INOUT) continue;

      long dealType = HistoryDealGetInteger(dealTicket, DEAL_TYPE);
      if(dealType != DEAL_TYPE_BUY && dealType != DEAL_TYPE_SELL) continue;

      string symbol = HistoryDealGetString(dealTicket, DEAL_SYMBOL);
      double volume = HistoryDealGetDouble(dealTicket, DEAL_VOLUME);
      double closePrice = HistoryDealGetDouble(dealTicket, DEAL_PRICE);
      double profit = HistoryDealGetDouble(dealTicket, DEAL_PROFIT);
      double commission = HistoryDealGetDouble(dealTicket, DEAL_COMMISSION);
      double swap = HistoryDealGetDouble(dealTicket, DEAL_SWAP);
      datetime closeTime = (datetime)HistoryDealGetInteger(dealTicket, DEAL_TIME);
      string comment = HistoryDealGetString(dealTicket, DEAL_COMMENT);
      ulong orderTicket = HistoryDealGetInteger(dealTicket, DEAL_ORDER);
      ulong positionId = HistoryDealGetInteger(dealTicket, DEAL_POSITION_ID);

      // In MT5, deal direction on exit is opposite to position direction
      // If closing deal was SELL, original position was BUY (0). If closing deal was BUY, position was SELL (1).
      int posType = (dealType == DEAL_TYPE_SELL) ? 0 : 1;

      datetime openTime = closeTime - 3600;
      double openPrice = closePrice;
      for(int historyIndex = 0; historyIndex < totalDeals; historyIndex++)
      {
         ulong entryTicket = HistoryDealGetTicket(historyIndex);
         if(HistoryDealGetInteger(entryTicket, DEAL_POSITION_ID) != positionId) continue;
         if(HistoryDealGetInteger(entryTicket, DEAL_ENTRY) != DEAL_ENTRY_IN) continue;
         datetime entryTime = (datetime)HistoryDealGetInteger(entryTicket, DEAL_TIME);
         if(entryTime < openTime)
         {
            openTime = entryTime;
            openPrice = HistoryDealGetDouble(entryTicket, DEAL_PRICE);
         }
      }

      // Candle data: the complete real entry-to-exit range at an automatic timeframe.
      string candlesJson = "[]";
      if(InpSyncCandles && addedTrades < InpCandleTrades)
      {
         ENUM_TIMEFRAMES chartTf = SelectChartTimeframe(openTime, closeTime, InpCandleBars);
         candlesJson = GetCandlesJson(symbol, chartTf, openTime, closeTime, InpCandleBars);
      }

      if(addedTrades > 0) closedTradesJson += ",";
      closedTradesJson += StringFormat(
         "{\"ticket\":\"%s\",\"symbol\":\"%s\",\"type\":%d,\"lots\":%.2f,\"open_time\":\"%s\",\"close_time\":\"%s\",\"open_price\":%.5f,\"close_price\":%.5f,\"stop_loss\":0.0,\"take_profit\":0.0,\"commission\":%.2f,\"swap\":%.2f,\"profit\":%.2f,\"comment\":\"%s\",\"candles\":%s}",
         IntegerToString(dealTicket),
         symbol,
         posType,
         volume,
         TimeToString(openTime, TIME_DATE|TIME_SECONDS),
         TimeToString(closeTime, TIME_DATE|TIME_SECONDS),
         openPrice,
         closePrice,
         commission,
         swap,
         profit,
         JsonEscape(comment),
         candlesJson
      );
      addedTrades++;
   }
   closedTradesJson += "]";

   // Open positions
   string openTradesJson = "[";
   int totalPositions = PositionsTotal();
   for(int p = 0; p < totalPositions; p++)
   {
      ulong posTicket = PositionGetTicket(p);
      if(posTicket <= 0) continue;
      string pSymbol = PositionGetString(POSITION_SYMBOL);
      long pType = PositionGetInteger(POSITION_TYPE);
      double pVol = PositionGetDouble(POSITION_VOLUME);
      double pOpenPrice = PositionGetDouble(POSITION_PRICE_OPEN);
      double pSL = PositionGetDouble(POSITION_SL);
      double pTP = PositionGetDouble(POSITION_TP);
      double pProfit = PositionGetDouble(POSITION_PROFIT);
      datetime pTime = (datetime)PositionGetInteger(POSITION_TIME);

      string openCandlesJson = "[]";
      if(InpSyncCandles && p < InpCandleTrades)
      {
         ENUM_TIMEFRAMES openChartTf = SelectChartTimeframe(pTime, TimeCurrent(), InpCandleBars);
         openCandlesJson = GetCandlesJson(pSymbol, openChartTf, pTime, TimeCurrent(), InpCandleBars);
      }

      if(p > 0) openTradesJson += ",";
      openTradesJson += StringFormat(
         "{\"ticket\":\"%s\",\"symbol\":\"%s\",\"type\":%d,\"lots\":%.2f,\"open_time\":\"%s\",\"open_price\":%.5f,\"stop_loss\":%.5f,\"take_profit\":%.5f,\"profit\":%.2f,\"candles\":%s}",
         IntegerToString(posTicket),
         pSymbol,
         (int)pType,
         pVol,
         TimeToString(pTime, TIME_DATE|TIME_SECONDS),
         pOpenPrice,
         pSL,
         pTP,
         pProfit,
         openCandlesJson
      );
   }
   openTradesJson += "]";

   // Pending orders (Limit / Stop)
   string pendingOrdersJson = "[";
   int totalOrders = OrdersTotal();
   int addedPending = 0;
   for(int i = 0; i < totalOrders; i++)
   {
      ulong oTicket = OrderGetTicket(i);
      if(oTicket <= 0) continue;
      ENUM_ORDER_TYPE oType = (ENUM_ORDER_TYPE)OrderGetInteger(ORDER_TYPE);
      if(oType != ORDER_TYPE_BUY_LIMIT && oType != ORDER_TYPE_SELL_LIMIT &&
         oType != ORDER_TYPE_BUY_STOP && oType != ORDER_TYPE_SELL_STOP) continue;

      int oDir = (oType == ORDER_TYPE_BUY_LIMIT || oType == ORDER_TYPE_BUY_STOP) ? 0 : 1;
      string oSymbol = OrderGetString(ORDER_SYMBOL);
      double oVolume = OrderGetDouble(ORDER_VOLUME_INITIAL);
      double oPrice = OrderGetDouble(ORDER_PRICE_OPEN);
      double oSL = OrderGetDouble(ORDER_SL);
      double oTP = OrderGetDouble(ORDER_TP);
      datetime oTime = (datetime)OrderGetInteger(ORDER_TIME_SETUP);
      string oComment = OrderGetString(ORDER_COMMENT);

      string pendingCandlesJson = "[]";
      if(InpSyncCandles && addedPending < InpCandleTrades)
      {
         datetime pOrderTime = oTime > 0 ? oTime : TimeCurrent();
         ENUM_TIMEFRAMES pChartTf = SelectChartTimeframe(pOrderTime, TimeCurrent(), InpCandleBars);
         pendingCandlesJson = GetCandlesJson(oSymbol, pChartTf, pOrderTime, TimeCurrent(), InpCandleBars);
      }

      if(addedPending > 0) pendingOrdersJson += ",";
      pendingOrdersJson += StringFormat(
         "{\"ticket\":\"mt5-order-%s\",\"order_id\":\"%s\",\"symbol\":\"%s\",\"type\":%d,\"lots\":%.2f,\"open_time\":\"%s\",\"open_price\":%.5f,\"stop_loss\":%.5f,\"take_profit\":%.5f,\"comment\":\"%s\",\"status\":\"PENDING\",\"candles\":%s}",
         IntegerToString(oTicket),
         IntegerToString(oTicket),
         oSymbol,
         oDir,
         oVolume,
         TimeToString(oTime > 0 ? oTime : TimeCurrent(), TIME_DATE|TIME_SECONDS),
         oPrice,
         oSL,
         oTP,
         JsonEscape(oComment),
         pendingCandlesJson
      );
      addedPending++;
   }
   pendingOrdersJson += "]";

   // Construct root payload
   string payload = StringFormat(
      "{\"account_number\":\"%d\",\"broker\":\"%s\",\"platform\":\"MT5\",\"currency\":\"%s\",\"balance\":%.2f,\"equity\":%.2f,\"margin\":%.2f,\"free_margin\":%.2f,\"leverage\":%d,\"closed_trades\":%s,\"open_trades\":%s,\"pending_orders\":%s}",
      login, JsonEscape(broker), currency, balance, equity, margin, freeMargin, leverage, closedTradesJson, openTradesJson, pendingOrdersJson
   );

   // Prepare HTTP Request
   char postData[];
   char result[];
   string resultHeaders;
   StringToCharArray(payload, postData, 0, WHOLE_ARRAY, CP_UTF8);
   ArrayResize(postData, ArraySize(postData) - 1); // remove trailing null byte

   string headers = StringFormat("Content-Type: application/json\r\nX-API-Key: %s\r\n", InpApiKey);

   ResetLastError();
   int timeout = 5000;
   int res = WebRequest("POST", InpServerUrl, headers, timeout, postData, result, resultHeaders);

   if(res == 200)
   {
      Print("TradeJournalSync: Successfully synced ", addedTrades, " trades to Journal Server! Response: 200 OK");
      g_lastSyncTime = TimeCurrent();
   }
   else
   {
      PrintFormat("TradeJournalSync: Sync failed! HTTP Code: %d, Error: %d. Make sure '%s' is in Allowed WebRequest URLs.", res, GetLastError(), InpServerUrl);
   }
}
