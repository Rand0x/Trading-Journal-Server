//+------------------------------------------------------------------+
//|                                           TradeJournalSync.mq5   |
//|                       Raspberry Pi Trading Journal Connector     |
//|                      https://github.com/tradingview/lightweight-charts |
//+------------------------------------------------------------------+
#property copyright   "Trading Journal Raspi"
#property link        "http://localhost:8000"
#property version     "1.00"
#property description "Auto-syncs closed trades, balance, equity, and market candle data"
#property description "to your Raspberry Pi Trading Journal server (READ-ONLY)."

//--- Inputs
input string   InpServerUrl     = "http://192.168.1.100:8000/api/sync/mql"; // Journal Server URL
input string   InpApiKey        = "key_demo_tradezella_raspi_mt5";          // API Key from Web UI
input int      InpSyncInterval  = 60;                                        // Sync Interval (Seconds)
input bool     InpSyncCandles   = true;                                      // Attach M15 Candles for Chart Replay
input int      InpCandleBars    = 60;                                        // Number of Candlesticks per Trade

//--- Global variables
datetime g_lastSyncTime = 0;

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
{
   Print("=== TradeJournalSync Initializing ===");
   Print("Server URL: ", InpServerUrl);
   Print("API Key: ", InpApiKey);
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
   if(trans.type == TRADE_TRANSACTION_DEAL_ADD)
   {
      Print("Trade deal detected! Triggering instant sync...");
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
string GetCandlesJson(string symbol, ENUM_TIMEFRAMES tf, datetime tradeTime, int count)
{
   MqlRates rates[];
   ArraySetAsSeries(rates, true);
   int copied = CopyRates(symbol, tf, tradeTime + (count/2 * 900), count, rates);
   if(copied <= 0) return "[]";

   string json = "[";
   for(int i = copied - 1; i >= 0; i--)
   {
      json += StringFormat("{\"time\":%d,\"open\":%.5f,\"high\":%.5f,\"low\":%.5f,\"close\":%.5f,\"volume\":%.0f}",
                           (long)rates[i].time, rates[i].open, rates[i].high, rates[i].low, rates[i].close, (double)rates[i].tick_volume);
      if(i > 0) json += ",";
   }
   json += "]";
   return json;
}

//+------------------------------------------------------------------+
//| Perform HTTP WebRequest Sync to Raspberry Pi Server              |
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

   for(int i = 0; i < totalDeals; i++)
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

      // Candle data
      string candlesJson = "[]";
      if(InpSyncCandles && addedTrades < 10) // Limit candle attachment to last 10 trades to conserve bandwidth
      {
         candlesJson = GetCandlesJson(symbol, PERIOD_M15, closeTime, InpCandleBars);
      }

      if(addedTrades > 0) closedTradesJson += ",";
      closedTradesJson += StringFormat(
         "{\"ticket\":\"%s\",\"symbol\":\"%s\",\"type\":%d,\"lots\":%.2f,\"open_time\":\"%s\",\"close_time\":\"%s\",\"open_price\":%.5f,\"close_price\":%.5f,\"stop_loss\":0.0,\"take_profit\":0.0,\"commission\":%.2f,\"swap\":%.2f,\"profit\":%.2f,\"comment\":\"%s\",\"candles\":%s}",
         IntegerToString(dealTicket),
         symbol,
         posType,
         volume,
         TimeToString(closeTime - 3600, TIME_DATE|TIME_SECONDS),
         TimeToString(closeTime, TIME_DATE|TIME_SECONDS),
         closePrice,
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

      if(p > 0) openTradesJson += ",";
      openTradesJson += StringFormat(
         "{\"ticket\":\"%s\",\"symbol\":\"%s\",\"type\":%d,\"lots\":%.2f,\"open_time\":\"%s\",\"open_price\":%.5f,\"stop_loss\":%.5f,\"take_profit\":%.5f,\"profit\":%.2f}",
         IntegerToString(posTicket),
         pSymbol,
         (int)pType,
         pVol,
         TimeToString(pTime, TIME_DATE|TIME_SECONDS),
         pOpenPrice,
         pSL,
         pTP,
         pProfit
      );
   }
   openTradesJson += "]";

   // Construct root payload
   string payload = StringFormat(
      "{\"account_number\":\"%d\",\"broker\":\"%s\",\"platform\":\"MT5\",\"currency\":\"%s\",\"balance\":%.2f,\"equity\":%.2f,\"margin\":%.2f,\"free_margin\":%.2f,\"leverage\":%d,\"closed_trades\":%s,\"open_trades\":%s}",
      login, JsonEscape(broker), currency, balance, equity, margin, freeMargin, leverage, closedTradesJson, openTradesJson
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
