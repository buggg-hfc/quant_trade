use pyo3::prelude::*;
use pyo3::types::PyList;

use crate::broker::{BrokerConfig, SimBroker};
use crate::metrics::{BacktestMetrics, MetricsEngine};
use crate::object::{Bar, Direction, Order, OrderStatus, OrderType};
use crate::risk::{RiskConfig, RiskManager};

#[pyclass]
pub struct BrokerConfigPy {
    #[pyo3(get, set)]
    pub commission_rate: f64,
    #[pyo3(get, set)]
    pub slippage: f64,
    #[pyo3(get, set)]
    pub price_limit_pct: f64,
    #[pyo3(get, set)]
    pub initial_capital: f64,
    #[pyo3(get, set)]
    pub max_position_pct: f64,
    #[pyo3(get, set)]
    pub daily_loss_limit: f64,
    #[pyo3(get, set)]
    pub max_order_volume: f64,
}

#[pymethods]
impl BrokerConfigPy {
    #[new]
    pub fn new(
        commission_rate: f64,
        slippage: f64,
        price_limit_pct: f64,
        initial_capital: f64,
        max_position_pct: f64,
        daily_loss_limit: f64,
        max_order_volume: f64,
    ) -> Self {
        BrokerConfigPy {
            commission_rate,
            slippage,
            price_limit_pct,
            initial_capital,
            max_position_pct,
            daily_loss_limit,
            max_order_volume,
        }
    }
}

#[pyclass]
pub struct BacktestRunner {
    broker: SimBroker,
    risk: RiskManager,
    metrics: MetricsEngine,
    strategy_on_bar: PyObject,
    strategy_on_trade: PyObject,
    next_order_id: u64,
}

#[pymethods]
impl BacktestRunner {
    #[new]
    pub fn new(
        config: &BrokerConfigPy,
        strategy_on_bar: PyObject,
        strategy_on_trade: PyObject,
    ) -> Self {
        BacktestRunner {
            broker: SimBroker::new(BrokerConfig {
                commission_rate: config.commission_rate,
                slippage: config.slippage,
                price_limit_pct: config.price_limit_pct,
            }),
            risk: RiskManager::new(
                RiskConfig {
                    max_position_pct: config.max_position_pct,
                    daily_loss_limit: config.daily_loss_limit,
                    max_order_volume: config.max_order_volume,
                },
                config.initial_capital,
            ),
            metrics: MetricsEngine::new(config.initial_capital),
            strategy_on_bar,
            strategy_on_trade,
            next_order_id: 1,
        }
    }

    /// GIL held for entire batch — backtest-only; do NOT use this path in live trading.
    pub fn run_batch(&mut self, bars: Vec<Bar>) -> PyResult<BacktestMetrics> {
        Python::with_gil(|py| {
            for bar in &bars {
                // 1. Python strategy decides on orders
                let result = self.strategy_on_bar.call1(py, (bar.clone(),))?;
                let order_list = result.downcast_bound::<PyList>(py)?;

                // 2. Parse and risk-filter orders
                let mut valid_orders: Vec<Order> = Vec::new();
                for item in order_list.iter() {
                    let (symbol_id, direction_long, order_type_limit, price, volume): (
                        u32, bool, bool, f64, f64,
                    ) = item.extract()?;
                    let direction =
                        if direction_long { Direction::Long } else { Direction::Short };
                    let order_type =
                        if order_type_limit { OrderType::Limit } else { OrderType::Market };
                    let order = Order {
                        order_id: self.next_order_id,
                        symbol_id,
                        direction,
                        order_type,
                        price,
                        volume,
                        filled: 0.0,
                        status: OrderStatus::Submitted,
                        datetime: bar.datetime,
                    };
                    self.next_order_id += 1;
                    if self.risk.check(&order, bar.close).is_ok() {
                        valid_orders.push(order);
                    }
                }

                // 3. Match and notify strategy
                let mut bar_pnl = 0.0f64;
                for order in &mut valid_orders {
                    if let Some(trade) = self.broker.match_order(order, bar) {
                        let delta = match trade.direction {
                            Direction::Long => trade.volume,
                            Direction::Short => -trade.volume,
                        };
                        self.risk.update_position(trade.symbol_id, delta);
                        let gross_pnl = delta * (bar.close - trade.price);
                        bar_pnl += gross_pnl - trade.commission;

                        // 4. Notify Python strategy of trade
                        self.strategy_on_trade.call1(py, (
                            trade.trade_id,
                            trade.order_id,
                            trade.symbol_id,
                            matches!(trade.direction, Direction::Long),
                            trade.price,
                            trade.volume,
                            trade.commission,
                            trade.datetime,
                        ))?;
                    }
                }

                self.risk.update_pnl(bar_pnl);
                let is_win = bar_pnl > 0.0;
                if bar_pnl.abs() > 1e-9 {
                    self.metrics.update(bar_pnl, is_win);
                }
            }
            Ok(self.metrics.finalize())
        })
    }
}
