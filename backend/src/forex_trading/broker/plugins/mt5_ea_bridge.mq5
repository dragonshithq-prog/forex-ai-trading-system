//+------------------------------------------------------------------+
//|  MT5 EA Bridge Server                                            |
//|  Listens on TCP port 3001, accepts JSON commands from the        |
//|  Python MT5BridgePlugin and executes MT5 operations.             |
//|                                                                  |
//|  Supported commands (newline-terminated JSON):                   |
//|    {"cmd":"ping"}                                                |
//|    {"cmd":"account_info"}                                        |
//|    {"cmd":"positions"}                                           |
//|    {"cmd":"place_order","symbol":...,"side":...,"quantity":...,  |
//|           "order_type":...,"price":...,"stop_loss":...,          |
//|           "take_profit":...}                                     |
//|    {"cmd":"modify_order","ticket":...,"price":...,"stop_loss":...|
//|           ,"take_profit":...}                                    |
//|    {"cmd":"cancel_order","ticket":...}                           |
//|    {"cmd":"subscribe","symbols":[...]}                           |
//|    {"cmd":"unsubscribe","symbols":[...]}                         |
//|    {"cmd":"history","from":"ISO8601"}                            |
//+------------------------------------------------------------------+
#property copyright "Forex Trading Bot"
#property version   "1.00"
#property strict

#define BRIDGE_PORT     3001
#define MAX_CLIENTS     8
#define RECV_BUFSIZE    4096
#define SEND_BUFSIZE    8192
#define HEARTBEAT_MAGIC "pong"

//--- server socket
SOCKET g_server = INVALID_HANDLE;
SOCKET g_clients[MAX_CLIENTS];
int    g_client_count = 0;

//--- tick subscription
string g_subscribed_symbols[];
int    g_subscribed_count = 0;

//+------------------------------------------------------------------+
//| Expert initialisation                                            |
//+------------------------------------------------------------------+
int OnInit()
  {
   ArrayFill(g_clients, 0, MAX_CLIENTS, (SOCKET)INVALID_HANDLE);

   g_server = SocketCreate();
   if(g_server == INVALID_HANDLE)
     {
      Print("[Bridge] SocketCreate failed: ", GetLastError());
      return INIT_FAILED;
     }

   if(!SocketBind(g_server, BRIDGE_PORT))
     {
      Print("[Bridge] SocketBind failed on port ", BRIDGE_PORT, " err=", GetLastError());
      SocketClose(g_server);
      return INIT_FAILED;
     }

   if(!SocketListen(g_server, MAX_CLIENTS))
     {
      Print("[Bridge] SocketListen failed: ", GetLastError());
      SocketClose(g_server);
      return INIT_FAILED;
     }

   Print("[Bridge] Listening on port ", BRIDGE_PORT);
   return INIT_SUCCEEDED;
  }

//+------------------------------------------------------------------+
//| Expert deinitialization                                          |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   for(int i = 0; i < MAX_CLIENTS; i++)
      if(g_clients[i] != INVALID_HANDLE)
         SocketClose(g_clients[i]);
   if(g_server != INVALID_HANDLE)
      SocketClose(g_server);
   Print("[Bridge] Server stopped.");
  }

//+------------------------------------------------------------------+
//| Expert tick handler - drives accept + read loop                  |
//+------------------------------------------------------------------+
void OnTick()
  {
   //--- accept new clients (non-blocking)
   AcceptClients();

   //--- read from existing clients
   for(int i = 0; i < MAX_CLIENTS; i++)
     {
      if(g_clients[i] == INVALID_HANDLE) continue;
      string line = ReadLine(g_clients[i]);
      if(line == NULL) continue;
      if(StringLen(line) == 0) continue;
      string response = HandleCommand(line);
      SendLine(g_clients[i], response);
     }

   //--- push subscribed tick snapshots
   PushTicks();
  }

//+------------------------------------------------------------------+
//| Accept pending connections                                       |
//+------------------------------------------------------------------+
void AcceptClients()
  {
   while(true)
     {
      SOCKET client = SocketAccept(g_server, 0);  // non-blocking: timeout=0
      if(client == INVALID_HANDLE) break;

      //--- find a free slot
      bool placed = false;
      for(int i = 0; i < MAX_CLIENTS; i++)
        {
         if(g_clients[i] == INVALID_HANDLE)
           {
            g_clients[i] = client;
            g_client_count++;
            Print("[Bridge] Client connected slot=", i);
            placed = true;
            break;
           }
        }
      if(!placed)
        {
         Print("[Bridge] Max clients reached, rejecting.");
         SocketClose(client);
        }
     }
  }

//+------------------------------------------------------------------+
//| Non-blocking line read (returns NULL if nothing ready)           |
//+------------------------------------------------------------------+
string ReadLine(SOCKET sock)
  {
   string result = "";
   uchar  ch[];
   ArrayResize(ch, 1);

   while(true)
     {
      int received = SocketRead(sock, ch, 1, 0);
      if(received <= 0)
        {
         //--- socket closed or no data
         if(received == 0 && StringLen(result) == 0)
            return NULL;
         break;
        }
      string c = CharArrayToString(ch);
      if(c == "\n") break;
      result += c;
     }
   return StringTrimRight(StringTrimLeft(result));
  }

//+------------------------------------------------------------------+
//| Send a line (appends \n)                                         |
//+------------------------------------------------------------------+
void SendLine(SOCKET sock, string text)
  {
   string msg = text + "\n";
   uchar  buf[];
   StringToCharArray(msg, buf, 0, StringLen(msg));
   int sent = SocketSend(sock, buf, ArraySize(buf));
   if(sent < 0)
      Print("[Bridge] SendLine failed: ", GetLastError());
  }

//+------------------------------------------------------------------+
//| JSON key extractor  (simple key:"value" or key:number)           |
//+------------------------------------------------------------------+
string JsonGetString(string json, string key)
  {
   string search = "\"" + key + "\"";
   int pos = StringFind(json, search);
   if(pos < 0) return "";
   pos += StringLen(search);
   //--- skip whitespace and colon
   while(pos < StringLen(json) && (StringGetCharacter(json, pos) == ' ' ||
                                    StringGetCharacter(json, pos) == ':'))
      pos++;
   if(StringGetCharacter(json, pos) == '"')
     {
      pos++;
      int end = StringFind(json, "\"", pos);
      if(end < 0) return "";
      return StringSubstr(json, pos, end - pos);
     }
   //--- numeric value
   int end = pos;
   while(end < StringLen(json))
     {
      ushort c = StringGetCharacter(json, end);
      if(c == ',' || c == '}' || c == ']' || c == ' ' || c == '\n') break;
      end++;
     }
   return StringSubstr(json, pos, end - pos);
  }

double JsonGetDouble(string json, string key)
  {
   string v = JsonGetString(json, key);
   if(v == "") return 0.0;
   return StringToDouble(v);
  }

long JsonGetLong(string json, string key)
  {
   string v = JsonGetString(json, key);
   if(v == "") return 0;
   return StringToInteger(v);
  }

//+------------------------------------------------------------------+
//| Build error response                                             |
//+------------------------------------------------------------------+
string ErrResp(string msg)
  {
   return "{\"status\":\"error\",\"error\":\"" + EscapeJson(msg) + "\"}";
  }

string OkResp(string data_json)
  {
   return "{\"status\":\"ok\",\"data\":" + data_json + "}";
  }

string EscapeJson(string s)
  {
   StringReplace(s, "\\", "\\\\");
   StringReplace(s, "\"", "\\\"");
   StringReplace(s, "\n", "\\n");
   StringReplace(s, "\r", "\\r");
   return s;
  }

//+------------------------------------------------------------------+
//| Dispatch JSON command                                            |
//+------------------------------------------------------------------+
string HandleCommand(string json)
  {
   string cmd = JsonGetString(json, "cmd");

   if(cmd == "ping")         return "{\"status\":\"ok\"}";
   if(cmd == "account_info") return CmdAccountInfo();
   if(cmd == "positions")    return CmdPositions();
   if(cmd == "place_order")  return CmdPlaceOrder(json);
   if(cmd == "modify_order") return CmdModifyOrder(json);
   if(cmd == "cancel_order") return CmdCancelOrder(json);
   if(cmd == "subscribe")    return CmdSubscribe(json);
   if(cmd == "unsubscribe")  return CmdUnsubscribe(json);
   if(cmd == "history")      return CmdHistory(json);

   return ErrResp("unknown command: " + cmd);
  }

//+------------------------------------------------------------------+
//| Account info                                                     |
//+------------------------------------------------------------------+
string CmdAccountInfo()
  {
   string data = "{";
   data += "\"login\":"    + IntegerToString(AccountInfoInteger(ACCOUNT_LOGIN))     + ",";
   data += "\"balance\":"  + DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE), 2)  + ",";
   data += "\"equity\":"   + DoubleToString(AccountInfoDouble(ACCOUNT_EQUITY), 2)   + ",";
   data += "\"margin\":"   + DoubleToString(AccountInfoDouble(ACCOUNT_MARGIN), 2)   + ",";
   data += "\"free_margin\":" + DoubleToString(AccountInfoDouble(ACCOUNT_FREEMARGIN), 2) + ",";
   data += "\"profit\":"   + DoubleToString(AccountInfoDouble(ACCOUNT_PROFIT), 2)   + ",";
   data += "\"currency\":\"" + AccountInfoString(ACCOUNT_CURRENCY)                   + "\",";
   data += "\"leverage\":"  + IntegerToString(AccountInfoInteger(ACCOUNT_LEVERAGE))  + ",";
   data += "\"server\":\""  + EscapeJson(AccountInfoString(ACCOUNT_SERVER))          + "\"";
   data += "}";
   return OkResp(data);
  }

//+------------------------------------------------------------------+
//| Open positions                                                   |
//+------------------------------------------------------------------+
string CmdPositions()
  {
   string arr = "[";
   int total = PositionsTotal();
   for(int i = 0; i < total; i++)
     {
      ulong ticket = PositionGetTicket(i);
      if(!PositionSelectByTicket(ticket)) continue;
      if(i > 0) arr += ",";
      arr += "{";
      arr += "\"ticket\":"        + IntegerToString(ticket)                                       + ",";
      arr += "\"symbol\":\""      + EscapeJson(PositionGetString(POSITION_SYMBOL))                + "\",";
      arr += "\"type\":"          + IntegerToString(PositionGetInteger(POSITION_TYPE))            + ",";
      arr += "\"volume\":"        + DoubleToString(PositionGetDouble(POSITION_VOLUME), 2)         + ",";
      arr += "\"price_open\":"    + DoubleToString(PositionGetDouble(POSITION_PRICE_OPEN), 5)     + ",";
      arr += "\"price_current\":" + DoubleToString(PositionGetDouble(POSITION_PRICE_CURRENT), 5) + ",";
      arr += "\"sl\":"            + DoubleToString(PositionGetDouble(POSITION_SL), 5)             + ",";
      arr += "\"tp\":"            + DoubleToString(PositionGetDouble(POSITION_TP), 5)             + ",";
      arr += "\"profit\":"        + DoubleToString(PositionGetDouble(POSITION_PROFIT), 2)         + ",";
      arr += "\"swap\":"          + DoubleToString(PositionGetDouble(POSITION_SWAP), 2)           + ",";
      arr += "\"commission\":0";
      arr += "}";
     }
   arr += "]";
   return OkResp(arr);
  }

//+------------------------------------------------------------------+
//| Place order                                                      |
//+------------------------------------------------------------------+
string CmdPlaceOrder(string json)
  {
   string symbol     = JsonGetString(json, "symbol");
   string side       = JsonGetString(json, "side");
   string order_type = JsonGetString(json, "order_type");
   double quantity   = JsonGetDouble(json, "quantity");
   double price      = JsonGetDouble(json, "price");
   double sl         = JsonGetDouble(json, "stop_loss");
   double tp         = JsonGetDouble(json, "take_profit");

   if(symbol == "" || quantity <= 0)
      return ErrResp("invalid symbol or quantity");

   ENUM_ORDER_TYPE mql_type;
   if(order_type == "limit")
      mql_type = (side == "buy" || side == "long") ? ORDER_TYPE_BUY_LIMIT  : ORDER_TYPE_SELL_LIMIT;
   else if(order_type == "stop")
      mql_type = (side == "buy" || side == "long") ? ORDER_TYPE_BUY_STOP   : ORDER_TYPE_SELL_STOP;
   else
      mql_type = (side == "buy" || side == "long") ? ORDER_TYPE_BUY        : ORDER_TYPE_SELL;

   double exec_price = (price > 0) ? price :
                       (mql_type == ORDER_TYPE_BUY ? SymbolInfoDouble(symbol, SYMBOL_ASK)
                                                   : SymbolInfoDouble(symbol, SYMBOL_BID));

   MqlTradeRequest  req = {};
   MqlTradeResult   res = {};
   req.action    = TRADE_ACTION_DEAL;
   req.symbol    = symbol;
   req.volume    = quantity;
   req.type      = mql_type;
   req.price     = exec_price;
   req.sl        = sl;
   req.tp        = tp;
   req.deviation = 10;
   req.magic     = 20240101;
   req.comment   = "bridge";
   req.type_filling = ORDER_FILLING_IOC;

   if(!OrderSend(req, res))
     {
      string err = "OrderSend failed retcode=" + IntegerToString(res.retcode);
      return ErrResp(err);
     }

   string data = "{\"ticket\":" + IntegerToString(res.order) +
                 ",\"deal\":"   + IntegerToString(res.deal)  +
                 ",\"price\":"  + DoubleToString(res.price, 5) + "}";
   return OkResp(data);
  }

//+------------------------------------------------------------------+
//| Modify order (pending or position SL/TP)                         |
//+------------------------------------------------------------------+
string CmdModifyOrder(string json)
  {
   long   ticket = JsonGetLong(json, "ticket");
   double price  = JsonGetDouble(json, "price");
   double sl     = JsonGetDouble(json, "stop_loss");
   double tp     = JsonGetDouble(json, "take_profit");

   if(ticket <= 0)
      return ErrResp("invalid ticket");

   //--- try as position
   if(PositionSelectByTicket((ulong)ticket))
     {
      MqlTradeRequest req = {};
      MqlTradeResult  res = {};
      req.action   = TRADE_ACTION_SLTP;
      req.symbol   = PositionGetString(POSITION_SYMBOL);
      req.position = (ulong)ticket;
      req.sl       = sl;
      req.tp       = tp;
      if(!OrderSend(req, res))
         return ErrResp("SLTP modify failed: " + IntegerToString(res.retcode));
      return "{\"status\":\"ok\"}";
     }

   //--- try as pending order
   if(OrderSelect((ulong)ticket))
     {
      MqlTradeRequest req = {};
      MqlTradeResult  res = {};
      req.action = TRADE_ACTION_MODIFY;
      req.order  = (ulong)ticket;
      req.price  = price;
      req.sl     = sl;
      req.tp     = tp;
      if(!OrderSend(req, res))
         return ErrResp("modify failed: " + IntegerToString(res.retcode));
      return "{\"status\":\"ok\"}";
     }

   return ErrResp("ticket not found");
  }

//+------------------------------------------------------------------+
//| Cancel pending order                                             |
//+------------------------------------------------------------------+
string CmdCancelOrder(string json)
  {
   long ticket = JsonGetLong(json, "ticket");
   if(ticket <= 0)
      return ErrResp("invalid ticket");

   if(!OrderSelect((ulong)ticket))
      return ErrResp("order not found");

   MqlTradeRequest req = {};
   MqlTradeResult  res = {};
   req.action = TRADE_ACTION_REMOVE;
   req.order  = (ulong)ticket;
   if(!OrderSend(req, res))
      return ErrResp("cancel failed: " + IntegerToString(res.retcode));
   return "{\"status\":\"ok\"}";
  }

//+------------------------------------------------------------------+
//| Subscribe to symbols for tick push                               |
//+------------------------------------------------------------------+
string CmdSubscribe(string json)
  {
   //--- parse array: ["EURUSD","GBPUSD",...]
   int start = StringFind(json, "[");
   int end   = StringFind(json, "]");
   if(start < 0 || end < 0)
      return ErrResp("invalid symbols array");

   string arr = StringSubstr(json, start + 1, end - start - 1);
   string parts[];
   int count = StringSplit(arr, ',', parts);
   for(int i = 0; i < count; i++)
     {
      string sym = parts[i];
      StringReplace(sym, "\"", "");
      sym = StringTrimLeft(StringTrimRight(sym));
      if(sym == "") continue;
      //--- add if not already present
      bool found = false;
      for(int j = 0; j < g_subscribed_count; j++)
         if(g_subscribed_symbols[j] == sym) { found = true; break; }
      if(!found)
        {
         ArrayResize(g_subscribed_symbols, g_subscribed_count + 1);
         g_subscribed_symbols[g_subscribed_count++] = sym;
        }
     }
   return "{\"status\":\"ok\"}";
  }

//+------------------------------------------------------------------+
//| Unsubscribe from symbols                                         |
//+------------------------------------------------------------------+
string CmdUnsubscribe(string json)
  {
   int start = StringFind(json, "[");
   int end   = StringFind(json, "]");
   if(start < 0 || end < 0)
      return ErrResp("invalid symbols array");

   string arr = StringSubstr(json, start + 1, end - start - 1);
   string parts[];
   StringSplit(arr, ',', parts);

   for(int p = 0; p < ArraySize(parts); p++)
     {
      string sym = parts[p];
      StringReplace(sym, "\"", "");
      sym = StringTrimLeft(StringTrimRight(sym));
      for(int i = 0; i < g_subscribed_count; i++)
        {
         if(g_subscribed_symbols[i] == sym)
           {
            for(int j = i; j < g_subscribed_count - 1; j++)
               g_subscribed_symbols[j] = g_subscribed_symbols[j + 1];
            g_subscribed_count--;
            ArrayResize(g_subscribed_symbols, g_subscribed_count);
            break;
           }
        }
     }
   return "{\"status\":\"ok\"}";
  }

//+------------------------------------------------------------------+
//| Trade history                                                    |
//+------------------------------------------------------------------+
string CmdHistory(string json)
  {
   string from_str = JsonGetString(json, "from");
   datetime from_dt = (from_str != "") ? StringToTime(from_str) : 0;
   datetime to_dt   = TimeCurrent();

   HistorySelect(from_dt, to_dt);

   string arr = "[";
   int total = HistoryDealsTotal();
   for(int i = 0; i < total; i++)
     {
      ulong ticket = HistoryDealGetTicket(i);
      if(i > 0) arr += ",";
      arr += "{";
      arr += "\"ticket\":"      + IntegerToString(ticket)                                           + ",";
      arr += "\"symbol\":\""    + EscapeJson(HistoryDealGetString(ticket, DEAL_SYMBOL))              + "\",";
      arr += "\"type\":"        + IntegerToString(HistoryDealGetInteger(ticket, DEAL_TYPE))          + ",";
      arr += "\"volume\":"      + DoubleToString(HistoryDealGetDouble(ticket, DEAL_VOLUME), 2)       + ",";
      arr += "\"price\":"       + DoubleToString(HistoryDealGetDouble(ticket, DEAL_PRICE), 5)        + ",";
      arr += "\"profit\":"      + DoubleToString(HistoryDealGetDouble(ticket, DEAL_PROFIT), 2)       + ",";
      arr += "\"commission\":"  + DoubleToString(HistoryDealGetDouble(ticket, DEAL_COMMISSION), 2)   + ",";
      arr += "\"swap\":"        + DoubleToString(HistoryDealGetDouble(ticket, DEAL_SWAP), 2)         + ",";
      arr += "\"time\":"        + IntegerToString(HistoryDealGetInteger(ticket, DEAL_TIME));
      arr += "}";
     }
   arr += "]";
   return OkResp(arr);
  }

//+------------------------------------------------------------------+
//| Push current tick snapshots for subscribed symbols               |
//+------------------------------------------------------------------+
void PushTicks()
  {
   if(g_subscribed_count == 0 || g_client_count == 0) return;

   for(int s = 0; s < g_subscribed_count; s++)
     {
      string sym = g_subscribed_symbols[s];
      MqlTick tick;
      if(!SymbolInfoTick(sym, tick)) continue;

      string msg = "{\"type\":\"tick\"";
      msg += ",\"symbol\":\""  + EscapeJson(sym)                       + "\"";
      msg += ",\"bid\":"        + DoubleToString(tick.bid, 5);
      msg += ",\"ask\":"        + DoubleToString(tick.ask, 5);
      msg += ",\"volume\":"     + DoubleToString(tick.volume, 0);
      msg += ",\"time\":"       + IntegerToString(tick.time);
      msg += "}";

      for(int i = 0; i < MAX_CLIENTS; i++)
        {
         if(g_clients[i] == INVALID_HANDLE) continue;
         int r = SendLine(g_clients[i], msg);
        }
     }
  }
//+------------------------------------------------------------------+
