use crate::object::{Direction, Order};
use std::collections::HashMap;

pub struct RiskConfig {
    pub max_position_pct: f64,
    pub daily_loss_limit: f64,
    pub max_order_volume: f64,
}

pub struct RiskManager {
    config: RiskConfig,
    total_capital: f64,
    daily_pnl: f64,
    /// symbol_id → signed net volume
    positions: HashMap<u32, f64>,
}

#[derive(Debug, PartialEq)]
pub enum RiskReject {
    PositionExceeded,
    DailyLossExceeded,
    VolumeTooLarge,
}

impl RiskManager {
    pub fn new(config: RiskConfig, total_capital: f64) -> Self {
        RiskManager { config, total_capital, daily_pnl: 0.0, positions: HashMap::new() }
    }

    pub fn check(&self, order: &Order, current_price: f64) -> Result<(), RiskReject> {
        if order.volume > self.config.max_order_volume {
            return Err(RiskReject::VolumeTooLarge);
        }
        if self.daily_pnl < -(self.total_capital * self.config.daily_loss_limit) {
            return Err(RiskReject::DailyLossExceeded);
        }
        let current_pos = self.positions.get(&order.symbol_id).copied().unwrap_or(0.0);
        let delta = match order.direction {
            Direction::Long  =>  order.volume,
            Direction::Short => -order.volume,
        };
        let new_pos_value = (current_pos + delta).abs() * current_price;
        if new_pos_value > self.total_capital * self.config.max_position_pct {
            return Err(RiskReject::PositionExceeded);
        }
        Ok(())
    }

    /// Returns only the orders that pass all risk checks.
    pub fn filter<'a>(&self, orders: &'a [Order], price: f64) -> Vec<&'a Order> {
        orders.iter().filter(|o| self.check(o, price).is_ok()).collect()
    }

    pub fn update_position(&mut self, symbol_id: u32, delta: f64) {
        *self.positions.entry(symbol_id).or_insert(0.0) += delta;
    }

    pub fn update_pnl(&mut self, pnl: f64) {
        self.daily_pnl += pnl;
    }

    pub fn reset_daily(&mut self) {
        self.daily_pnl = 0.0;
    }

    pub fn net_position(&self, symbol_id: u32) -> f64 {
        self.positions.get(&symbol_id).copied().unwrap_or(0.0)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::object::{OrderStatus, OrderType};

    fn order(direction: Direction, volume: f64) -> Order {
        Order {
            order_id: 1, symbol_id: 0, direction,
            order_type: OrderType::Market, price: 10.0,
            volume, filled: 0.0, status: OrderStatus::Submitted, datetime: 0,
        }
    }

    fn rm() -> RiskManager {
        RiskManager::new(
            RiskConfig { max_position_pct: 0.2, daily_loss_limit: 0.02, max_order_volume: 1000.0 },
            1_000_000.0,
        )
    }

    #[test]
    fn normal_order_passes() {
        assert!(rm().check(&order(Direction::Long, 100.0), 10.0).is_ok());
    }

    #[test]
    fn volume_too_large() {
        assert_eq!(rm().check(&order(Direction::Long, 1001.0), 10.0), Err(RiskReject::VolumeTooLarge));
    }

    #[test]
    fn daily_loss_exceeded() {
        let mut r = rm();
        r.update_pnl(-25_000.0); // 2.5% > 2% limit
        assert_eq!(r.check(&order(Direction::Long, 100.0), 10.0), Err(RiskReject::DailyLossExceeded));
    }

    #[test]
    fn position_limit_exceeded() {
        let mut r = RiskManager::new(
            RiskConfig { max_position_pct: 0.2, daily_loss_limit: 0.10, max_order_volume: 100_000.0 },
            1_000_000.0,
        );
        // 25 000 shares × 10.0 = 250 000 > 200 000 (20% of 1M)
        assert_eq!(r.check(&order(Direction::Long, 25_000.0), 10.0), Err(RiskReject::PositionExceeded));
    }

    #[test]
    fn existing_position_counts_toward_limit() {
        let mut r = RiskManager::new(
            RiskConfig { max_position_pct: 0.2, daily_loss_limit: 0.10, max_order_volume: 100_000.0 },
            1_000_000.0,
        );
        r.update_position(0, 15_000.0); // already 150 000 in
        // adding 6 000 → 210 000 > 200 000
        assert_eq!(r.check(&order(Direction::Long, 6_000.0), 10.0), Err(RiskReject::PositionExceeded));
    }

    #[test]
    fn reset_daily_clears_pnl() {
        let mut r = rm();
        r.update_pnl(-25_000.0);
        r.reset_daily();
        assert!(r.check(&order(Direction::Long, 100.0), 10.0).is_ok());
    }

    #[test]
    fn filter_removes_bad_orders() {
        let r = rm();
        let good = order(Direction::Long, 100.0);
        let bad  = order(Direction::Long, 9999.0);
        let orders = [good, bad];
        let filtered = r.filter(&orders, 10.0);
        assert_eq!(filtered.len(), 1);
        assert_eq!(filtered[0].volume, 100.0);
    }
}
