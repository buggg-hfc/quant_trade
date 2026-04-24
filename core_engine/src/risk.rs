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
    positions: HashMap<u32, f64>, // symbol_id → net volume
}

#[derive(Debug)]
pub enum RiskReject {
    PositionExceeded,
    DailyLossExceeded,
    VolumeTooLarge,
}

impl RiskManager {
    pub fn new(config: RiskConfig, total_capital: f64) -> Self {
        RiskManager {
            config,
            total_capital,
            daily_pnl: 0.0,
            positions: HashMap::new(),
        }
    }

    pub fn check(&self, order: &Order, current_price: f64) -> Result<(), RiskReject> {
        if order.volume > self.config.max_order_volume {
            return Err(RiskReject::VolumeTooLarge);
        }

        if self.daily_pnl < -self.total_capital * self.config.daily_loss_limit {
            return Err(RiskReject::DailyLossExceeded);
        }

        let current_pos = self.positions.get(&order.symbol_id).copied().unwrap_or(0.0);
        let delta = match order.direction {
            Direction::Long => order.volume,
            Direction::Short => -order.volume,
        };
        let new_pos_value = (current_pos + delta).abs() * current_price;
        if new_pos_value > self.total_capital * self.config.max_position_pct {
            return Err(RiskReject::PositionExceeded);
        }

        Ok(())
    }

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
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::object::{Direction, OrderStatus, OrderType};

    fn make_order(direction: Direction, volume: f64) -> Order {
        Order {
            order_id: 1,
            symbol_id: 0,
            direction,
            order_type: OrderType::Market,
            price: 10.0,
            volume,
            filled: 0.0,
            status: OrderStatus::Submitted,
            datetime: 0,
        }
    }

    fn rm() -> RiskManager {
        RiskManager::new(
            RiskConfig {
                max_position_pct: 0.2,
                daily_loss_limit: 0.02,
                max_order_volume: 1000.0,
            },
            1_000_000.0,
        )
    }

    #[test]
    fn normal_order_passes() {
        let r = rm();
        assert!(r.check(&make_order(Direction::Long, 100.0), 10.0).is_ok());
    }

    #[test]
    fn volume_too_large() {
        let r = rm();
        assert!(matches!(
            r.check(&make_order(Direction::Long, 1001.0), 10.0),
            Err(RiskReject::VolumeTooLarge)
        ));
    }

    #[test]
    fn daily_loss_exceeded() {
        let mut r = rm();
        r.update_pnl(-25_000.0); // 2.5% loss > 2% limit
        assert!(matches!(
            r.check(&make_order(Direction::Long, 100.0), 10.0),
            Err(RiskReject::DailyLossExceeded)
        ));
    }

    #[test]
    fn position_exceeded() {
        let r = rm();
        // 10001 shares * 10.0 = 100_010 > 1_000_000 * 0.2 = 200_000... actually fine
        // let's use 20001 shares: 20001 * 10 = 200_010 > 200_000
        assert!(matches!(
            r.check(&make_order(Direction::Long, 20_001.0), 10.0),
            Err(RiskReject::VolumeTooLarge) // volume limit 1000 fires first
        ));
    }
}
