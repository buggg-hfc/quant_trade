use crate::object::{Bar, Direction, Order, OrderStatus, OrderType, Trade};

pub struct BrokerConfig {
    pub commission_rate: f64,
    pub slippage: f64,
    pub price_limit_pct: f64,
}

pub struct SimBroker {
    config: BrokerConfig,
    next_trade_id: u64,
}

impl SimBroker {
    pub fn new(config: BrokerConfig) -> Self {
        SimBroker { config, next_trade_id: 1 }
    }

    pub fn match_order(&mut self, order: &mut Order, bar: &Bar) -> Option<Trade> {
        // reject if price is outside limit band
        let prev_close = bar.open; // simplified; backtest engine tracks this separately
        let upper = prev_close * (1.0 + self.config.price_limit_pct);
        let lower = prev_close * (1.0 - self.config.price_limit_pct);
        if bar.close >= upper || bar.close <= lower {
            order.status = OrderStatus::Rejected;
            return None;
        }

        let fill_price = match order.order_type {
            OrderType::Market => match order.direction {
                Direction::Long => bar.open * (1.0 + self.config.slippage),
                Direction::Short => bar.open * (1.0 - self.config.slippage),
            },
            OrderType::Limit => {
                match order.direction {
                    Direction::Long if order.price >= bar.low => order.price,
                    Direction::Short if order.price <= bar.high => order.price,
                    _ => return None, // limit not triggered
                }
            }
        };

        let fill_volume = order.volume - order.filled;
        let commission = fill_price * fill_volume * self.config.commission_rate;

        order.filled = order.volume;
        order.status = OrderStatus::Filled;

        let trade_id = self.next_trade_id;
        self.next_trade_id += 1;

        Some(Trade {
            trade_id,
            order_id: order.order_id,
            symbol_id: order.symbol_id,
            direction: order.direction,
            price: fill_price,
            volume: fill_volume,
            commission,
            datetime: bar.datetime,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::object::{OrderStatus, OrderType};

    fn make_bar(open: f64, high: f64, low: f64, close: f64) -> Bar {
        Bar { symbol_id: 0, datetime: 0, open, high, low, close, volume: 1000.0 }
    }

    fn make_order(direction: Direction, order_type: OrderType, price: f64) -> Order {
        Order {
            order_id: 1,
            symbol_id: 0,
            direction,
            order_type,
            price,
            volume: 100.0,
            filled: 0.0,
            status: OrderStatus::Submitted,
            datetime: 0,
        }
    }

    fn broker() -> SimBroker {
        SimBroker::new(BrokerConfig {
            commission_rate: 0.0003,
            slippage: 0.001,
            price_limit_pct: 0.10,
        })
    }

    #[test]
    fn market_buy_fills() {
        let mut b = broker();
        let bar = make_bar(10.0, 11.0, 9.5, 10.5);
        let mut order = make_order(Direction::Long, OrderType::Market, 0.0);
        let trade = b.match_order(&mut order, &bar);
        assert!(trade.is_some());
        assert_eq!(order.status, OrderStatus::Filled);
        let t = trade.unwrap();
        assert!((t.price - 10.01).abs() < 1e-9); // 10 * 1.001
    }

    #[test]
    fn limit_buy_not_triggered() {
        let mut b = broker();
        let bar = make_bar(10.0, 11.0, 9.5, 10.5);
        let mut order = make_order(Direction::Long, OrderType::Limit, 9.0); // below low
        let trade = b.match_order(&mut order, &bar);
        assert!(trade.is_none());
    }

    #[test]
    fn limit_buy_triggered() {
        let mut b = broker();
        let bar = make_bar(10.0, 11.0, 9.5, 10.5);
        let mut order = make_order(Direction::Long, OrderType::Limit, 9.8); // >= low
        let trade = b.match_order(&mut order, &bar);
        assert!(trade.is_some());
        assert_eq!(order.status, OrderStatus::Filled);
    }

    #[test]
    fn upper_limit_rejects() {
        let mut b = broker();
        // close == open * 1.10, exactly at limit → rejected
        let bar = make_bar(10.0, 11.0, 10.0, 11.0);
        let mut order = make_order(Direction::Long, OrderType::Market, 0.0);
        // price_limit_pct = 0.10, upper = 10 * 1.10 = 11.0, close = 11.0 → >= upper
        let trade = b.match_order(&mut order, &bar);
        assert!(trade.is_none());
        assert_eq!(order.status, OrderStatus::Rejected);
    }
}
