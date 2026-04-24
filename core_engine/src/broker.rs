use crate::object::{Direction, Order, OrderStatus, OrderType, Trade, Bar};

pub struct BrokerConfig {
    pub commission_rate: f64,
    pub slippage: f64,
    pub price_limit_pct: f64,
    /// Volume available for partial fills (0 = fill entire order)
    pub max_fill_volume_per_bar: f64,
}

pub struct SimBroker {
    pub config: BrokerConfig,
    next_trade_id: u64,
}

pub struct FillResult {
    pub trade: Trade,
    pub is_partial: bool,
}

impl SimBroker {
    pub fn new(config: BrokerConfig) -> Self {
        SimBroker { config, next_trade_id: 1 }
    }

    /// Attempt to match an order against a bar.
    /// Returns None if the order cannot be filled at all (limit not reached, or at price limit).
    /// Returns Some(FillResult) with is_partial=true when only part of the order fills.
    pub fn match_order(&mut self, order: &mut Order, bar: &Bar) -> Option<FillResult> {
        // Reject if bar is at/beyond price limit (涨跌停)
        let limit_up   = bar.open * (1.0 + self.config.price_limit_pct);
        let limit_down = bar.open * (1.0 - self.config.price_limit_pct);
        if bar.close >= limit_up {
            // Limit-up: long orders cannot fill (no seller), short fills OK
            if matches!(order.direction, Direction::Long) {
                order.status = OrderStatus::Rejected;
                return None;
            }
        }
        if bar.close <= limit_down {
            // Limit-down: short orders cannot fill, long fills OK
            if matches!(order.direction, Direction::Short) {
                order.status = OrderStatus::Rejected;
                return None;
            }
        }

        let remaining = order.remaining();
        if remaining < 1e-9 {
            order.status = OrderStatus::Filled;
            return None;
        }

        let fill_price = match order.order_type {
            OrderType::Market => match order.direction {
                Direction::Long  => bar.open * (1.0 + self.config.slippage),
                Direction::Short => bar.open * (1.0 - self.config.slippage),
            },
            OrderType::Limit => match order.direction {
                Direction::Long  if order.price >= bar.low  => order.price,
                Direction::Short if order.price <= bar.high => order.price,
                _ => return None, // limit not triggered
            },
        };

        // Partial fill: cap at max_fill_volume_per_bar if configured
        let fill_volume = if self.config.max_fill_volume_per_bar > 0.0 {
            remaining.min(self.config.max_fill_volume_per_bar)
        } else {
            remaining
        };

        let commission = fill_price * fill_volume * self.config.commission_rate;
        let is_partial = fill_volume < remaining;

        order.filled += fill_volume;
        order.status = if is_partial { OrderStatus::PartiallyFilled } else { OrderStatus::Filled };

        let trade_id = self.next_trade_id;
        self.next_trade_id += 1;

        Some(FillResult {
            trade: Trade {
                trade_id,
                order_id: order.order_id,
                symbol_id: order.symbol_id,
                direction: order.direction,
                price: fill_price,
                volume: fill_volume,
                commission,
                datetime: bar.datetime,
            },
            is_partial,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::object::OrderType;

    fn bar(open: f64, high: f64, low: f64, close: f64) -> Bar {
        Bar { symbol_id: 0, datetime: 0, open, high, low, close, volume: 10_000.0 }
    }

    fn order(direction: Direction, order_type: OrderType, price: f64, volume: f64) -> Order {
        Order {
            order_id: 1, symbol_id: 0, direction, order_type, price, volume,
            filled: 0.0, status: OrderStatus::Submitted, datetime: 0,
        }
    }

    fn broker_no_partial() -> SimBroker {
        SimBroker::new(BrokerConfig {
            commission_rate: 0.0003,
            slippage: 0.001,
            price_limit_pct: 0.10,
            max_fill_volume_per_bar: 0.0,
        })
    }

    fn broker_partial(max_vol: f64) -> SimBroker {
        SimBroker::new(BrokerConfig {
            commission_rate: 0.0003,
            slippage: 0.001,
            price_limit_pct: 0.10,
            max_fill_volume_per_bar: max_vol,
        })
    }

    #[test]
    fn market_buy_fills_at_open_plus_slippage() {
        let mut b = broker_no_partial();
        let mut o = order(Direction::Long, OrderType::Market, 0.0, 100.0);
        let r = b.match_order(&mut o, &bar(10.0, 11.0, 9.5, 10.5)).unwrap();
        assert!((r.trade.price - 10.01).abs() < 1e-9);
        assert_eq!(r.trade.volume, 100.0);
        assert!(!r.is_partial);
        assert_eq!(o.status, OrderStatus::Filled);
    }

    #[test]
    fn market_sell_fills_at_open_minus_slippage() {
        let mut b = broker_no_partial();
        let mut o = order(Direction::Short, OrderType::Market, 0.0, 100.0);
        let r = b.match_order(&mut o, &bar(10.0, 11.0, 9.5, 10.5)).unwrap();
        assert!((r.trade.price - 9.99).abs() < 1e-9);
        assert!(!r.is_partial);
    }

    #[test]
    fn limit_buy_not_triggered() {
        let mut b = broker_no_partial();
        let mut o = order(Direction::Long, OrderType::Limit, 9.0, 100.0);
        assert!(b.match_order(&mut o, &bar(10.0, 11.0, 9.5, 10.5)).is_none());
    }

    #[test]
    fn limit_buy_triggered() {
        let mut b = broker_no_partial();
        let mut o = order(Direction::Long, OrderType::Limit, 9.6, 100.0);
        let r = b.match_order(&mut o, &bar(10.0, 11.0, 9.5, 10.5)).unwrap();
        assert_eq!(r.trade.price, 9.6);
        assert_eq!(o.status, OrderStatus::Filled);
    }

    #[test]
    fn limit_sell_triggered() {
        let mut b = broker_no_partial();
        let mut o = order(Direction::Short, OrderType::Limit, 10.8, 100.0);
        let r = b.match_order(&mut o, &bar(10.0, 11.0, 9.5, 10.5)).unwrap();
        assert_eq!(r.trade.price, 10.8);
    }

    #[test]
    fn limit_up_rejects_long() {
        let mut b = broker_no_partial();
        // open=10, close=11 = open*1.1 → limit_up=11, close>=limit_up → reject long
        let mut o = order(Direction::Long, OrderType::Market, 0.0, 100.0);
        assert!(b.match_order(&mut o, &bar(10.0, 11.0, 10.0, 11.0)).is_none());
        assert_eq!(o.status, OrderStatus::Rejected);
    }

    #[test]
    fn limit_up_allows_short() {
        let mut b = broker_no_partial();
        let mut o = order(Direction::Short, OrderType::Market, 0.0, 100.0);
        // At limit-up day, shorts can still sell (there are buyers)
        let r = b.match_order(&mut o, &bar(10.0, 11.0, 10.0, 11.0));
        assert!(r.is_some());
    }

    #[test]
    fn limit_down_rejects_short() {
        let mut b = broker_no_partial();
        // open=10, close=9 = open*0.9 → limit_down=9.0, close<=limit_down → reject short
        let mut o = order(Direction::Short, OrderType::Market, 0.0, 100.0);
        assert!(b.match_order(&mut o, &bar(10.0, 10.0, 9.0, 9.0)).is_none());
        assert_eq!(o.status, OrderStatus::Rejected);
    }

    #[test]
    fn partial_fill() {
        let mut b = broker_partial(30.0);
        let mut o = order(Direction::Long, OrderType::Market, 0.0, 100.0);
        let r = b.match_order(&mut o, &bar(10.0, 11.0, 9.5, 10.5)).unwrap();
        assert!(r.is_partial);
        assert_eq!(r.trade.volume, 30.0);
        assert_eq!(o.filled, 30.0);
        assert_eq!(o.status, OrderStatus::PartiallyFilled);
    }

    #[test]
    fn commission_computed_correctly() {
        let mut b = broker_no_partial();
        let mut o = order(Direction::Long, OrderType::Market, 0.0, 100.0);
        let r = b.match_order(&mut o, &bar(10.0, 11.0, 9.5, 10.5)).unwrap();
        // price=10.01, vol=100, rate=0.0003 → commission=0.3003
        assert!((r.trade.commission - 0.3003).abs() < 1e-9);
    }
}
