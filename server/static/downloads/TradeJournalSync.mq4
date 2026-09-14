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
input int      InpSyncInterval  = 60;                                        // Full Sync Interval (Seconds)
input int      InpLiveInterval  = 5;                                         // Live Candle Interval (Seconds)
input bool     InpSyncCandles   = true;                                      // Attach Real Candles for Chart Replay
input int      InpCandleBars    = 2000;                                      // Maximum real chart bars per trade/timeframe
input int      InpCandleTrades  = 10;                                        // Number of recent trades to attach candles to

//--- Global variables
datetime g_lastSyncTime = 0;
datetime g_lastHistorySync = 0;
uint     g_lastSyncTick = 0;
uint     g_lastLiveTick = 0;
bool     g_syncPending = false;
int      g_lastTotalOpenOrders = -1;
int      g_lastTotalHistoryOrders = -1;
double   g_lastOrdersStateHash = -1.0;

void SendLiveCandles();
void SyncHistoryCandles();
void RequestSync(string reason = "");
int  CheckTradeStateChanges();

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
   
   // Timer runs every 1s for accurate anti-spam cooldown processing
   EventSetTimer(1);
   
   // Create on-chart manual sync button
   ObjectCreate(0, "BtnJournalSync", OBJ_BUTTON, 0, 0, 0);
   ObjectSetInteger(0, "BtnJournalSync", OBJPROP_CORNER, CORNER_LEFT_UPPER);
   ObjectSetInteger(0, "BtnJournalSync", OBJPROP_XDISTANCE, 20);
   ObjectSetInteger(0, "BtnJournalSync", OBJPROP_YDISTANCE, 30);
   ObjectSetInteger(0, "BtnJournalSync", OBJPROP_XSIZE, 130);
   ObjectSetInteger(0, "BtnJournalSync", OBJPROP_YSIZE, 28);
   ObjectSetString(0, "BtnJournalSync", OBJPROP_TEXT, "Sync to Journal");
   ObjectSetInteger(0, "BtnJournalSync", OBJPROP_BGCOLOR, C'30,58,138');
   ObjectSetInteger(0, "BtnJournalSync", OBJPROP_COLOR, clrWhite);
   ObjectSetInteger(0, "BtnJournalSync", OBJPROP_FONTSIZE, 9);
   ChartRedraw();

   // Initialize order state baseline
   CheckTradeStateChanges();

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
   ObjectDelete(0, "BtnJournalSync");
   ChartRedraw();
   Print("TradeJournalSync MT4 Stopped.");
}

//+------------------------------------------------------------------+
//| Chart event function for manual button clicks                    |
//+------------------------------------------------------------------+
void OnChartEvent(const int id, const long &lparam, const double &dparam, const string &sparam)
{
   if(id == CHARTEVENT_OBJECT_CLICK && sparam == "BtnJournalSync")
   {
      Print("Manual sync triggered via chart button.");
      ObjectSetInteger(0, "BtnJournalSync", OBJPROP_STATE, false);
      ChartRedraw();
      g_lastHistorySync = 0;
      RequestSync("Manual Button Click");
   }
}

//+------------------------------------------------------------------+
//| Detect changes in orders, position count, and SL/TP modifications|
//+------------------------------------------------------------------+
int CheckTradeStateChanges()
{
   int totalOpen = OrdersTotal();
   int totalHist = OrdersHistoryTotal();

   if(g_lastTotalOpenOrders < 0)
   {
      g_lastTotalOpenOrders = totalOpen;
      g_lastTotalHistoryOrders = totalHist;
      return 0;
   }

   if(totalOpen != g_lastTotalOpenOrders || totalHist != g_lastTotalHistoryOrders)
   {
      g_lastTotalOpenOrders = totalOpen;
      g_lastTotalHistoryOrders = totalHist;
      return 1; // Count changed (open, close, pending triggered/deleted)
   }

   // Check if SL/TP/Lots modified on any open or pending order
   double stateHash = 0.0;
   for(int i = 0; i < totalOpen; i++)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      stateHash += (double)OrderTicket() + (OrderLots() * 100.0) + OrderOpenPrice() + OrderStopLoss() + OrderTakeProfit();
   }

   if(g_lastOrdersStateHash < 0.0)
   {
      g_lastOrdersStateHash = stateHash;
      return 0;
   }

   if(MathAbs(stateHash - g_lastOrdersStateHash) > 0.0001)
   {
      g_lastOrdersStateHash = stateHash;
      return 2; // Order modified (SL/TP/Lots)
   }

   return 0;
}

//+------------------------------------------------------------------+
//| Request sync with 5-second anti-spam cooldown                    |
//+------------------------------------------------------------------+
void RequestSync(string reason = "")
{
   uint now = GetTickCount();
   if(g_lastSyncTick == 0 || (now - g_lastSyncTick) >= 5000)
   {
      if(StringLen(reason) > 0)
         PrintFormat("TradeJournalSync MT4: Instant sync triggered (%s)...", reason);
      SyncToServer();
   }
   else
   {
      if(!g_syncPending)
      {
         double elapsed = (double)(now - g_lastSyncTick) / 1000.0;
         if(StringLen(reason) > 0)
            PrintFormat("TradeJournalSync MT4: Sync queued (%s), waiting for 5s cooldown (elapsed: %.1fs)...", reason, elapsed);
         g_syncPending = true;
      }
   }
}

//+------------------------------------------------------------------+
//| Timer event function (called every 1s)                           |
//+------------------------------------------------------------------+
void OnTimer()
{
   uint now = GetTickCount();

   // 1. Send live candles at configured InpLiveInterval (default 5s)
   if(InpLiveInterval > 0 && (now - g_lastLiveTick >= (uint)(InpLiveInterval * 1000)))
   {
      g_lastLiveTick = now;
      SendLiveCandles();
   }

   // 2. Detect trade state changes (fallback for trade open/close/modify)
   int change = CheckTradeStateChanges();
   if(change > 0)
   {
      RequestSync(change == 1 ? "Order count change" : "Order SL/TP/Lots modification");
   }

   // 3. Execute pending sync once 5s cooldown has elapsed
   if(g_syncPending && (now - g_lastSyncTick >= 5000))
   {
      Print("TradeJournalSync MT4: Executing queued sync after 5s cooldown...");
      SyncToServer();
      return;
   }

   // 4. Periodic full sync interval (default 60s)
   if(InpSyncInterval > 0 && (now - g_lastSyncTick >= (uint)(InpSyncInterval * 1000)))
   {
      SyncToServer();
   }
}

//+------------------------------------------------------------------+
//| Trade event function (called on any trade activity in MT4)       |
//+------------------------------------------------------------------+
void OnTrade()
{
   RequestSync("OnTrade Event");
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
   if(tf == PERIOD_M1) return(60);
   if(tf == PERIOD_M5) return(300);
   if(tf == PERIOD_H1) return(3600);
   if(tf == PERIOD_H4) return(14400);
   if(tf == PERIOD_D1) return(86400);
   return(900); // M15
}

string TimeframeName(int tf)
{
   if(tf == PERIOD_M1) return("M1");
   if(tf == PERIOD_M5) return("M5");
   if(tf == PERIOD_H1) return("H1");
   if(tf == PERIOD_H4) return("H4");
   if(tf == PERIOD_D1) return("D1");
   return("M15");
}

int SelectChartTimeframe(datetime openTime, datetime closeTime, int maxBars)
{
   int timeframes[6] = {PERIOD_M1, PERIOD_M5, PERIOD_M15, PERIOD_H1, PERIOD_H4, PERIOD_D1};
   int duration = (int)MathMax(0, closeTime - openTime);
   for(int index = 0; index < 6; index++)
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
   datetime toTime = MathMin(TimeCurrent(), closeTime + (8 * seconds));
   datetime minFromTime = toTime - ((datetime)maxBars * seconds);
   datetime fromTime = (datetime)MathMin(openTime - (8 * seconds), minFromTime);
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

   // Pending orders
   string pendingOrdersJson = "[";
   int addedPending = 0;
   for(int k = 0; k < totalOpen; k++)
   {
      if(!OrderSelect(k, SELECT_BY_POS, MODE_TRADES)) continue;
      int pType = OrderType();
      if(pType != OP_BUYLIMIT && pType != OP_SELLLIMIT &&
         pType != OP_BUYSTOP && pType != OP_SELLSTOP) continue;

      int pDir = (pType == OP_BUYLIMIT || pType == OP_BUYSTOP) ? 0 : 1;
      string pOrderType = (pType == OP_BUYLIMIT || pType == OP_SELLLIMIT) ? "Limit" : "Stop";
      string pCandlesJson = "[]";
      if(InpSyncCandles && addedPending < InpCandleTrades)
      {
         int pChartTf = SelectChartTimeframe(OrderOpenTime(), TimeCurrent(), InpCandleBars);
         pCandlesJson = GetCandlesJson(OrderSymbol(), pChartTf, OrderOpenTime(), TimeCurrent(), InpCandleBars);
      }

      if(addedPending > 0) pendingOrdersJson += ",";
      pendingOrdersJson += StringFormat(
         "{\"ticket\":\"mt4-order-%d\",\"order_id\":\"%d\",\"order_type\":\"%s\",\"symbol\":\"%s\",\"type\":%d,\"lots\":%.2f,\"open_time\":\"%s\",\"open_price\":%.5f,\"stop_loss\":%.5f,\"take_profit\":%.5f,\"comment\":\"%s\",\"status\":\"PENDING\",\"candles\":%s}",
         OrderTicket(),
         OrderTicket(),
         pOrderType,
         OrderSymbol(),
         pDir,
         OrderLots(),
         TimeToStr(OrderOpenTime(), TIME_DATE|TIME_SECONDS),
         OrderOpenPrice(),
         OrderStopLoss(),
         OrderTakeProfit(),
         JsonEscape(OrderComment()),
         pCandlesJson
      );
      addedPending++;
   }
   pendingOrdersJson += "]";

   // Root payload
   string payload = StringFormat(
      "{\"account_number\":\"%d\",\"broker\":\"%s\",\"platform\":\"MT4\",\"currency\":\"%s\",\"balance\":%.2f,\"equity\":%.2f,\"margin\":%.2f,\"free_margin\":%.2f,\"leverage\":%d,\"closed_trades\":%s,\"open_trades\":%s,\"pending_orders\":%s}",
      login, JsonEscape(broker), currency, balance, equity, margin, freeMargin, leverage, closedTradesJson, openTradesJson, pendingOrdersJson
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

   g_lastSyncTick = GetTickCount();
   g_syncPending = false;
   CheckTradeStateChanges();

   if(res == 200)
   {
      Print("TradeJournalSync MT4: Successfully synced ", addedTrades, " trades to Server!");
      g_lastSyncTime = TimeCurrent();
      if(TimeCurrent() - g_lastHistorySync >= 900)
      {
         g_lastHistorySync = TimeCurrent();
         SyncHistoryCandles();
      }
   }
   else
   {
      PrintFormat("TradeJournalSync MT4: WebRequest failed! Code: %d, Error: %d. Check URL whitelist.", res, GetLastError());
   }
}

//+------------------------------------------------------------------+
//| Collect unique active symbols from orders and history            |
//+------------------------------------------------------------------+
void GetActiveSymbols(string &symbols[], int &totalSymbols)
{
   totalSymbols = 0;
   ArrayResize(symbols, 64);

   // Current chart symbol
   symbols[totalSymbols++] = Symbol();

   // Open and pending trades
   int totalTrades = OrdersTotal();
   for(int i = 0; i < totalTrades && totalSymbols < 60; i++)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      string sym = OrderSymbol();
      bool exists = false;
      for(int s = 0; s < totalSymbols; s++)
      {
         if(symbols[s] == sym) { exists = true; break; }
      }
      if(!exists) symbols[totalSymbols++] = sym;
   }

   // History orders (last 30 days)
   int totalHist = OrdersHistoryTotal();
   for(int k = totalHist - 1; k >= 0 && totalSymbols < 60; k--)
   {
      if(!OrderSelect(k, SELECT_BY_POS, MODE_HISTORY)) continue;
      string hSym = OrderSymbol();
      if(StringLen(hSym) == 0) continue;
      bool exists = false;
      for(int s = 0; s < totalSymbols; s++)
      {
         if(symbols[s] == hSym) { exists = true; break; }
      }
      if(!exists) symbols[totalSymbols++] = hSym;
   }

   ArrayResize(symbols, totalSymbols);
}

//+------------------------------------------------------------------+
//| Helper to derive candles endpoint URL from InpServerUrl          |
//+------------------------------------------------------------------+
string GetCandlesEndpointUrl()
{
   string candlesUrl = InpServerUrl;
   if(StringFind(candlesUrl, "/api/sync/mql") >= 0)
   {
      StringReplace(candlesUrl, "/api/sync/mql", "/api/sync/candles");
   }
   else if(StringSubstr(candlesUrl, StringLen(candlesUrl) - 1, 1) == "/")
   {
      candlesUrl = candlesUrl + "api/sync/candles";
   }
   else
   {
      candlesUrl = candlesUrl + "/api/sync/candles";
   }
   return candlesUrl;
}

//+------------------------------------------------------------------+
//| Send newest forming candle (bar 0) & open trades PnL live        |
//+------------------------------------------------------------------+
void SendLiveCandles()
{
   if(StringLen(InpApiKey) == 0) return;

   // 1. Gather live open trades PnL & current market prices
   int totalTrades = OrdersTotal();
   string openTradesJson = "[";
   int openCount = 0;
   for(int i = 0; i < totalTrades; i++)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      int oType = OrderType();
      if(oType != OP_BUY && oType != OP_SELL) continue;

      int ticket = OrderTicket();
      string oSym = OrderSymbol();
      double profit = OrderProfit();
      double curPrice = OrderClosePrice();
      double sl = OrderStopLoss();
      double tp = OrderTakeProfit();

      if(openCount > 0) openTradesJson += ",";
      openTradesJson += StringFormat(
         "{\"ticket\":\"%d\",\"symbol\":\"%s\",\"profit\":%.2f,\"current_price\":%.5f,\"stop_loss\":%.5f,\"take_profit\":%.5f}",
         ticket, oSym, profit, curPrice, sl, tp
      );
      openCount++;
   }
   openTradesJson += "]";

   // Account live equity & balance
   double balance = AccountBalance();
   double equity = AccountEquity();
   double margin = AccountMargin();
   double freeMargin = AccountFreeMargin();

   // 2. Gather live candle bar 0 for active symbols
   string candlesJson = "[]";
   int candleCount = 0;
   if(InpSyncCandles)
   {
      string symbols[];
      int totalSymbols = 0;
      GetActiveSymbols(symbols, totalSymbols);
      if(totalSymbols > 0)
      {
         int timeframes[6] = {PERIOD_M1, PERIOD_M5, PERIOD_M15, PERIOD_H1, PERIOD_H4, PERIOD_D1};
         candlesJson = "[";
         bool first = true;
         for(int s = 0; s < totalSymbols; s++)
         {
            string sym = symbols[s];
            for(int t = 0; t < 6; t++)
            {
               datetime cTime = iTime(sym, timeframes[t], 0);
               if(cTime <= 0) continue;

               double cOpen = iOpen(sym, timeframes[t], 0);
               double cHigh = iHigh(sym, timeframes[t], 0);
               double cLow = iLow(sym, timeframes[t], 0);
               double cClose = iClose(sym, timeframes[t], 0);
               long cVol = iVolume(sym, timeframes[t], 0);

               if(!first) candlesJson += ",";
               candlesJson += StringFormat(
                  "{\"symbol\":\"%s\",\"timeframe\":\"%s\",\"time\":%d,\"open\":%.5f,\"high\":%.5f,\"low\":%.5f,\"close\":%.5f,\"volume\":%d}",
                  sym, TimeframeName(timeframes[t]), (long)cTime, cOpen, cHigh, cLow, cClose, cVol
               );
               first = false;
               candleCount++;
            }
         }
         candlesJson += "]";
      }
   }

   if(candleCount == 0 && openCount == 0) return;

   string liveJson = StringFormat(
      "{\"equity\":%.2f,\"balance\":%.2f,\"margin\":%.2f,\"free_margin\":%.2f,\"open_trades\":%s,\"candles\":%s}",
      equity, balance, margin, freeMargin, openTradesJson, candlesJson
   );

   string candlesUrl = GetCandlesEndpointUrl();

   char postData[];
   char result[];
   string resultHeaders;
   StringToCharArray(liveJson, postData, 0, WHOLE_ARRAY, CP_UTF8);
   ArrayResize(postData, ArraySize(postData) - 1);

   string headers = StringFormat("Content-Type: application/json\r\nX-API-Key: %s\r\n", InpApiKey);
   ResetLastError();
   WebRequest("POST", candlesUrl, headers, 3000, postData, result, resultHeaders);
}

//+------------------------------------------------------------------+
//| Download up to 2000 candles for each timeframe for active markets|
//+------------------------------------------------------------------+
void SyncHistoryCandles()
{
   if(!InpSyncCandles) return;
   if(StringLen(InpApiKey) == 0) return;

   string symbols[];
   int totalSymbols = 0;
   GetActiveSymbols(symbols, totalSymbols);
   if(totalSymbols == 0) return;

   int timeframes[6] = {PERIOD_M1, PERIOD_M5, PERIOD_M15, PERIOD_H1, PERIOD_H4, PERIOD_D1};
   string candlesUrl = GetCandlesEndpointUrl();
   string headers = StringFormat("Content-Type: application/json\r\nX-API-Key: %s\r\n", InpApiKey);

   for(int s = 0; s < totalSymbols; s++)
   {
      string sym = symbols[s];
      for(int t = 0; t < 6; t++)
      {
         int tf = timeframes[t];
         int available = iBars(sym, tf);
         if(available <= 0) continue;

         int barsCount = MathMin(InpCandleBars, available);
         string batchJson = StringFormat("{\"symbol\":\"%s\",\"timeframe\":\"%s\",\"candles\":[", sym, TimeframeName(tf));
         int added = 0;

         for(int i = barsCount - 1; i >= 0; i--)
         {
            datetime cTime = iTime(sym, tf, i);
            if(cTime <= 0) continue;

            if(added > 0) batchJson += ",";
            batchJson += StringFormat(
               "{\"time\":%d,\"open\":%.5f,\"high\":%.5f,\"low\":%.5f,\"close\":%.5f,\"volume\":%d}",
               (long)cTime,
               iOpen(sym, tf, i),
               iHigh(sym, tf, i),
               iLow(sym, tf, i),
               iClose(sym, tf, i),
               iVolume(sym, tf, i)
            );
            added++;
         }
         batchJson += "]}";

         if(added == 0) continue;

         char postData[];
         char result[];
         string resultHeaders;
         StringToCharArray(batchJson, postData, 0, WHOLE_ARRAY, CP_UTF8);
         ArrayResize(postData, ArraySize(postData) - 1);

         ResetLastError();
         WebRequest("POST", candlesUrl, headers, 5000, postData, result, resultHeaders);
      }
   }
}
