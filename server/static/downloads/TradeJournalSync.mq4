//+------------------------------------------------------------------+
//|                                           TradeJournalSync.mq4   |
//|                       Trading Journal Connector                  |
//|                      https://github.com/tradingview/lightweight-charts |
//+------------------------------------------------------------------+
#property copyright   "Trading Journal"
#property link        "http://localhost:8000"
#property version     "1.00"
#property strict
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
   Print("=== TradeJournalSync MT4 Initializing ===");
   Print("Server URL: ", InpServerUrl);
   if(StringLen(InpApiKey) == 0)
   {
      Print("Journal API Key is required. Copy it from the account card in the web UI.");
      return(INIT_PARAMETERS_INCORRECT);
   }
   Print("Journal API Key configured.");
   Print("Note: Ensure '", InpServerUrl, "' is added to MT4 Tools -> Options -> Expert Advisors -> Allow WebRequest!");
   
   EventSetTimer(InpSyncInterval);
   SyncToServer();
   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| Expert deinitialization function                                 |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   EventKillTimer();
   Print("TradeJournalSync MT4 Stopped.");
}

//+------------------------------------------------------------------+
//| Timer event function                                             |
//+------------------------------------------------------------------+
void OnTimer()
{
   SyncToServer();
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
//| Build Candle Bars JSON array for MT4                             |
//+------------------------------------------------------------------+
int TimeframeSeconds(int tf)
{
   if(tf == PERIOD_H1) return(3600);
   if(tf == PERIOD_H4) return(14400);
   if(tf == PERIOD_D1) return(86400);
   return(900); // M15
}

string TimeframeName(int tf)
{
   if(tf == PERIOD_H1) return("H1");
   if(tf == PERIOD_H4) return("H4");
   if(tf == PERIOD_D1) return("D1");
   return("M15");
}

int SelectChartTimeframe(datetime openTime, datetime closeTime, int maxBars)
{
   int timeframes[4] = {PERIOD_M15, PERIOD_H1, PERIOD_H4, PERIOD_D1};
   int duration = (int)MathMax(0, closeTime - openTime);
   for(int index = 0; index < 4; index++)
   {
      int seconds = TimeframeSeconds(timeframes[index]);
      if((duration / seconds) + 16 <= maxBars)
         return(timeframes[index]);
   }
   return(PERIOD_D1);
}

string GetCandlesJson(string symbol, int tf, datetime openTime, datetime closeTime, int maxBars)
{
   int seconds = TimeframeSeconds(tf);
   datetime fromTime = openTime - (8 * seconds);
   datetime toTime = MathMin(TimeCurrent(), closeTime + (8 * seconds));
   int oldestShift = iBarShift(symbol, tf, fromTime, false);
   int newestShift = iBarShift(symbol, tf, toTime, false);
   if(oldestShift < 0 || newestShift < 0) return("[]");
   if(oldestShift < newestShift)
   {
      int tmp = oldestShift;
      oldestShift = newestShift;
      newestShift = tmp;
   }
   if(oldestShift - newestShift + 1 > maxBars)
   {
      oldestShift = newestShift + maxBars - 1;
   }

   string json = "[";
   int added = 0;
   for(int i = oldestShift; i >= newestShift; i--)
   {
      datetime t = iTime(symbol, tf, i);
      double o = iOpen(symbol, tf, i);
      double h = iHigh(symbol, tf, i);
      double l = iLow(symbol, tf, i);
      double c = iClose(symbol, tf, i);
      long v = iVolume(symbol, tf, i);

      if(added > 0) json += ",";
      json += StringFormat("{\"timeframe\":\"%s\",\"time\":%d,\"open\":%.5f,\"high\":%.5f,\"low\":%.5f,\"close\":%.5f,\"volume\":%d}",
                           TimeframeName(tf), (long)t, o, h, l, c, v);
      added++;
   }
   json += "]";
   return json;
}

//+------------------------------------------------------------------+
//| Perform HTTP WebRequest Sync to Trading Journal Server            |
//+------------------------------------------------------------------+
void SyncToServer()
{
   int login = AccountNumber();
   double balance = AccountBalance();
   double equity = AccountEquity();
   double margin = AccountMargin();
   double freeMargin = AccountFreeMargin();
   int leverage = AccountLeverage();
   string currency = AccountCurrency();
   string broker = AccountCompany();

   // History orders
   int totalHistory = OrdersHistoryTotal();
   string closedTradesJson = "[";
   int addedTrades = 0;

   for(int i = totalHistory - 1; i >= 0 && addedTrades < 100; i--)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_HISTORY)) continue;

      int orderType = OrderType();
      if(orderType != OP_BUY && orderType != OP_SELL) continue;

      int ticket = OrderTicket();
      string symbol = OrderSymbol();
      double lots = OrderLots();
      double openPrice = OrderOpenPrice();
      double closePrice = OrderClosePrice();
      double sl = OrderStopLoss();
      double tp = OrderTakeProfit();
      double comm = OrderCommission();
      double swap = OrderSwap();
      double profit = OrderProfit();
      datetime openTime = OrderOpenTime();
      datetime closeTime = OrderCloseTime();
      string comment = OrderComment();

      string candlesJson = "[]";
      if(InpSyncCandles && addedTrades < InpCandleTrades)
      {
         int chartTf = SelectChartTimeframe(openTime, closeTime, InpCandleBars);
         candlesJson = GetCandlesJson(symbol, chartTf, openTime, closeTime, InpCandleBars);
      }

      if(addedTrades > 0) closedTradesJson += ",";
      closedTradesJson += StringFormat(
         "{\"ticket\":\"%d\",\"symbol\":\"%s\",\"type\":%d,\"lots\":%.2f,\"open_time\":\"%s\",\"close_time\":\"%s\",\"open_price\":%.5f,\"close_price\":%.5f,\"stop_loss\":%.5f,\"take_profit\":%.5f,\"commission\":%.2f,\"swap\":%.2f,\"profit\":%.2f,\"comment\":\"%s\",\"candles\":%s}",
         ticket,
         symbol,
         orderType,
         lots,
         TimeToStr(openTime, TIME_DATE|TIME_SECONDS),
         TimeToStr(closeTime, TIME_DATE|TIME_SECONDS),
         openPrice,
         closePrice,
         sl,
         tp,
         comm,
         swap,
         profit,
         JsonEscape(comment),
         candlesJson
      );
      addedTrades++;
   }
   closedTradesJson += "]";

   // Open orders
   string openTradesJson = "[";
   int totalOpen = OrdersTotal();
   int openAdded = 0;

   for(int j = 0; j < totalOpen; j++)
   {
      if(!OrderSelect(j, SELECT_BY_POS, MODE_TRADES)) continue;
      int oType = OrderType();
      if(oType != OP_BUY && oType != OP_SELL) continue;

      string openCandlesJson = "[]";
      if(InpSyncCandles && openAdded < InpCandleTrades)
      {
         int openChartTf = SelectChartTimeframe(OrderOpenTime(), TimeCurrent(), InpCandleBars);
         openCandlesJson = GetCandlesJson(OrderSymbol(), openChartTf, OrderOpenTime(), TimeCurrent(), InpCandleBars);
      }

      if(openAdded > 0) openTradesJson += ",";
      openTradesJson += StringFormat(
         "{\"ticket\":\"%d\",\"symbol\":\"%s\",\"type\":%d,\"lots\":%.2f,\"open_time\":\"%s\",\"open_price\":%.5f,\"stop_loss\":%.5f,\"take_profit\":%.5f,\"profit\":%.2f,\"candles\":%s}",
         OrderTicket(),
         OrderSymbol(),
         oType,
         OrderLots(),
         TimeToStr(OrderOpenTime(), TIME_DATE|TIME_SECONDS),
         OrderOpenPrice(),
         OrderStopLoss(),
         OrderTakeProfit(),
         OrderProfit(),
         openCandlesJson
      );
      openAdded++;
   }
   openTradesJson += "]";

   // Root payload
   string payload = StringFormat(
      "{\"account_number\":\"%d\",\"broker\":\"%s\",\"platform\":\"MT4\",\"currency\":\"%s\",\"balance\":%.2f,\"equity\":%.2f,\"margin\":%.2f,\"free_margin\":%.2f,\"leverage\":%d,\"closed_trades\":%s,\"open_trades\":%s}",
      login, JsonEscape(broker), currency, balance, equity, margin, freeMargin, leverage, closedTradesJson, openTradesJson
   );

   char postData[];
   char result[];
   string resultHeaders;
   StringToCharArray(payload, postData, 0, WHOLE_ARRAY, CP_UTF8);
   ArrayResize(postData, ArraySize(postData) - 1);

   string headers = StringFormat("Content-Type: application/json\r\nX-API-Key: %s\r\n", InpApiKey);

   ResetLastError();
   int timeout = 5000;
   int res = WebRequest("POST", InpServerUrl, headers, timeout, postData, result, resultHeaders);

   if(res == 200)
   {
      Print("TradeJournalSync MT4: Successfully synced ", addedTrades, " trades to Server!");
      g_lastSyncTime = TimeCurrent();
   }
   else
   {
      PrintFormat("TradeJournalSync MT4: WebRequest failed! Code: %d, Error: %d. Check URL whitelist.", res, GetLastError());
   }
}
