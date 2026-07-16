"""MT5 Manager handles the connection to MetaTrader 5 trading platform.

This class provides methods to connect to MT5, get market data,
place orders, and manage trading operations.
"""
import MetaTrader5 as mt5
import time
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class MT5Manager:
    def __init__(self):
        self.connected = False
        self.connection_status = "disconnected"
        self._symbol = "EURUSD"
        self._timeframe = mt5.TIMEFRAME_M1

    def connect(self, login: int, password: str, server: str,
                symbol: str = "EURUSD", timeframe: int = mt5.TIMEFRAME_M1) -> bool:
        """Connect to MetaTrader 5 trading server.

        Args:
            login: Trading account login number
            password: Trading account password
            server: Server name (e.g., "MetaQuotes-Demo", "MetaQuotes-Demo1")
            symbol: Symbol to trade (default: EURUSD)
            timeframe: Timeframe for market data (default: M1)

        Returns:
            bool: True if connection successful, False otherwise
        """
        try:
            already_init = mt5.initialize()
            if already_init and mt5.terminal_info() is not None:
                mt5.shutdown()

            if not mt5.initialize(login=login, password=password, server=server):
                err = mt5.last_error()
                logger.error(f"Failed to initialize MT5: {err}")
                return False

            self._symbol = symbol
            self._timeframe = timeframe
            self.connected = True
            self.connection_status = "connected"
            logger.info(f"Successfully connected to MT5 server: {server}")
            return True

        except Exception as e:
            logger.error(f"Error connecting to MT5: {str(e)}")
            return False
            
    def disconnect(self) -> bool:
        """Disconnect from MetaTrader 5 trading server."""
        try:
            mt5.shutdown()
            self.connected = False
            self.connection_status = "disconnected"
            logger.info("Disconnected from MT5 server")
            return True
        except Exception as e:
            logger.error(f"Error disconnecting from MT5: {str(e)}")
            return False
            
    def is_connected(self) -> bool:
        """Check if currently connected to MT5 server."""
        return self.connected
        
    def get_account_info(self) -> Dict[str, Any]:
        """Get account information from MT5."""
        if not self.connected:
            return {}

        try:
            mt5.symbol_select(self._symbol, True)
            info = mt5.account_info()
            if info is None:
                return {}

            return {
                'balance': info.balance,
                'equity': info.equity,
                'margin': info.margin,
                'free_margin': info.margin_free,
                'margin_level': info.margin_level,
                'credit': info.credit,
                'stop_out_level': info.sof,
            }
        except Exception as e:
            logger.error(f"Error getting account info: {str(e)}")
            return {}
            
    def get_ohlcv(self, symbol: str = None, timeframe: int = None, count: int = 500) -> list[Dict[str, Any]]:
        """Get historical OHLCV data."""
        if not self.connected:
            return []
        sym = symbol or self._symbol
        tf = timeframe or self._timeframe
        try:
            mt5.symbol_select(sym, True)
            rates = mt5.copy_rates_from_pos(sym, tf, 0, count)
            if rates is None:
                return []
            result = []
            for r in rates:
                result.append({
                    'time': r.time,
                    'open': r.open,
                    'high': r.high,
                    'low': r.low,
                    'close': r.close,
                    'volume': r.tick_volume or r.real_volume,
                    'spread': r.spread,
                })
            return result
        except Exception as e:
            logger.error(f"Error getting OHLCV: {str(e)}")
            return []

    def get_market_data(self, symbol: str = "EURUSD") -> Dict[str, Any]:
        """Get current market data for a symbol."""
        if not self.connected:
            return {}
            
        try:
            # Get tick data
            tick = mt5.symbol_info_tick(symbol)
            if not tick:
                return {}
                
            return {
                'bid': tick.bid,
                'ask': tick.ask,
                'last': tick.last,
                'volume': tick.volume,
                'time': tick.time,
            }
        except Exception as e:
            logger.error(f"Error getting market data: {str(e)}")
            return {}
            
    def get_price_info(self, symbol: str = "EURUSD") -> Dict[str, Any]:
        """Get price information for a symbol."""
        if not self.connected:
            return {}
            
        try:
            symbol_info = mt5.symbol_info(symbol)
            if not symbol_info:
                return {}
                
            return {
                'spread': symbol_info.spread,
                'digits': symbol_info.digits,
                'trade_execution_speed': symbol_info.execution_speed,
                'trade_tick_size': symbol_info.trade_tick_size,
                'trade_min_volume': symbol_info.trade_min_volume,
                'trade_max_volume': symbol_info.trade_max_volume,
                'trade_step': symbol_info.trade_step,
            }
        except Exception as e:
            logger.error(f"Error getting price info: {str(e)}")
            return {}
            
    def get_positions(self) -> Dict[str, Any]:
        """Get current open positions."""
        if not self.connected:
            return {}
            
        try:
            positions = mt5.positions_get()
            if not positions:
                return {}
                
            positions_data = {}
            for pos in positions:
                symbol = pos.symbol
                if symbol not in positions_data:
                    positions_data[symbol] = {}

                positions_data[symbol].update({
                    'ticket': pos.ticket,
                    'symbol': symbol,
                    'volume': pos.volume,
                    'type': pos.type,
                    'price': pos.price_open,
                    'sl': pos.sl,
                    'tp': pos.tp,
                    'commission': pos.commission,
                    'swap': pos.swap,
                    'profit': pos.profit,
                    'magic': pos.magic,
                    'comment': pos.comment,
                })

            return positions_data
        except Exception as e:
            logger.error(f"Error getting positions: {str(e)}")
            return {}
            
    def send_order(self, symbol: str, volume: float,
                  type: int, price: Optional[float] = None,
                  stop_loss: Optional[float] = None,
                  take_profit: Optional[float] = None,
                  deviation: int = 10) -> Dict[str, Any]:
        """Send a trading order to MT5."""
        if not self.connected:
            return {"error": "Not connected"}

        try:
            if price is None:
                tick = mt5.symbol_info_tick(symbol)
                if tick is None:
                    return {"error": "Cannot get current price"}
                price = tick.ask if type == mt5.ORDER_TYPE_BUY else tick.bid

            request = {
                'action': mt5.TRADE_ACTION_DEAL,
                'symbol': symbol,
                'volume': volume,
                'type': type,
                'price': price,
                'sl': stop_loss,
                'tp': take_profit,
                'deviation': deviation,
                'type_filling': mt5.ORDER_FILLING_IOC,
                'type_time': mt5.ORDER_TIME_GTC,
            }

            result = mt5.order_send(request)
            if result.retcode != mt5.TRADE_RETCODE_DONE:
                logger.error(f"Order failed: {result.comment} (retcode={result.retcode})")
                return {"error": result.comment, "retcode": result.retcode}

            logger.info(f"Order sent: ticket={result.order}")
            return {
                "ticket": result.order,
                "price": result.price,
                "volume": result.volume,
            }
        except Exception as e:
            logger.error(f"Error sending order: {str(e)}")
            return {"error": str(e)}
            
    def close_position(self, symbol: str) -> bool:
        """Close an open position for a symbol."""
        if not self.connected:
            return False
            
        try:
            # Get current positions
            positions = self.get_positions()
            if symbol not in positions:
                return False
                
            position = positions[symbol]
            volume = abs(position['volume'])
            type_ = position['type']

            if type_ == mt5.POSITION_TYPE_BUY:
                order_type = mt5.ORDER_TYPE_SELL
            elif type_ == mt5.POSITION_TYPE_SELL:
                order_type = mt5.ORDER_TYPE_BUY
            else:
                return False

            tick = mt5.symbol_info_tick(symbol)
            price = tick.ask if type_ == mt5.POSITION_TYPE_SELL else tick.bid

            result = mt5.order_send({
                'action': mt5.TRADE_ACTION_DEAL,
                'symbol': symbol,
                'volume': volume,
                'type': order_type,
                'price': price,
                'position': position.get('ticket', 0),
                'type_filling': mt5.ORDER_FILLING_IOC,
                'type_time': mt5.ORDER_TIME_GTC,
            })
            
            if result.retcode != mt5.TRADE_RETCODE_DONE:
                logger.error(f"Failed to close position: {result.comment}")
                return False
                
            logger.info(f"Position closed successfully: {symbol}")
            return True
        except Exception as e:
            logger.error(f"Error closing position: {str(e)}")
            return False