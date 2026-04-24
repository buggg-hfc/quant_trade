use pyo3::prelude::*;
use pyo3::types::PyList;
use std::collections::HashMap;

use crate::broker::{BrokerConfig, SimBroker};
use crate::metrics::{BacktestMetrics, MetricsEngine};
use crate::object::{Bar, Direction, Order, OrderStatus, OrderType, Position};
use crate::risk::{RiskConfig, RiskManager};

// ─── Python-facing config object ─────────────────────────────────────────────

#[pyclass]
pub struct BrokerConfigPy {
    #[pyo3(get, set)] pub commission_rate: f64,
    #[pyo3(get, set)] pub slippage: f64,
    #[pyo3(get, set)] pub price_limit_pct: f64,
    #[pyo3(get, set)] pub initial_capital: f64,
    #[pyo3(get, set)] pub max_position_pct: f64,
    #[pyo3(get, set)] pub daily_loss_limit: f64,
    #[pyo3(get, set)] pub max_order_volume: f64,
    /// Per-bar partial fill cap; 0 = unlimited (fill entire order in one bar)
    #[pyo3(get, set)] pub max_fill_volume_per_bar: f64,
}

#[pymethods]
impl BrokerConfigPy {
    #[new]
    #[pyo3(signature = (
        commission_rate = 0.0003,
        slippage = 0.001,
        price_limit_pct = 0.10,
        initial_capital = 1_000_000.0,
        max_position_pct = 0.2,
        daily_loss_limit = 0.02,
        max_order_volume = 1000.0,
        max_fill_volume_per_bar = 0.0,
    ))]
    pub fn new(
        commission_rate: f64, slippage: f64, price_limit_pct: f64,
        initial_capital: f64, max_position_pct: f64, daily_loss_limit: f64,
        max_order_volume: f64, max_fill_volume_per_bar: f64,
    ) -> Self {
        BrokerConfigPy {
            commission_rate, slippage, price_limit_pct, initial_capital,
            max_position_pct, daily_loss_limit, max_order_volume, max_fill_volume_per_bar,
        }
    }
}

// ─── BacktestRunner ───────────────────────────────────────────────────────────

#[pyclass]
pub struct BacktestRunner {
    broker: SimBroker,
    risk: RiskManager,
    metrics: MetricsEngine,
    strategy_on_bar: PyObject,
    strategy_on_trade: PyObject,
    next_order_id: u64,
    /// Cash on hand; changes with every trade.
    cash: f64,
    /// symbol_id → Position (tracks avg_price, unrealized/realized P&L for reporting).
    positions: HashMap<u32, Position>,
    /// symbol_id → most recently seen close price (for equity computation).
    latest_price: HashMap<u32, f64>,
}

impl BacktestRunner {
    /// Equity = cash + sum(net_volume × latest_price) for all positions.
    fn compute_equity(&self) -> f64 {
        let market_value: f64 = self.positions.values()
            .filter_map(|pos| {
                self.latest_price.get(&pos.symbol_id).map(|&px| pos.net_volume * px)
            })
            .sum();
        self.cash + market_value
    }
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
                max_fill_volume_per_bar: config.max_fill_volume_per_bar,
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
            cash: config.initial_capital,
            positions: HashMap::new(),
            latest_price: HashMap::new(),
        }
    }

    /// Run the full backtest loop.
    ///
    /// GIL is held for the entire batch — backtest-only.
    /// Do NOT use this pattern in live trading (see EventEngine for live GIL policy).
    ///
    /// `bars` must be sorted by datetime; multi-symbol bars are interleaved by time.
    pub fn run_batch(&mut self, bars: Vec<Bar>) -> PyResult<BacktestMetrics> {
        Python::with_gil(|py| {
            for bar in &bars {
                // Update latest known price for this symbol
                self.latest_price.insert(bar.symbol_id, bar.close);

                // ── 1. Ask strategy for orders ───────────────────────────────────────
                let result = self.strategy_on_bar.call1(py, (bar.clone(),))?;
                let order_list = result.downcast_bound::<PyList>(py)?;

                // ── 2. Parse + risk-filter orders ────────────────────────────────────
                let mut parsed: Vec<Order> = Vec::new();
                for item in order_list.iter() {
                    let (symbol_id, direction_long, order_type_limit, price, volume):
                        (u32, bool, bool, f64, f64) = item.extract()?;
                    let direction = if direction_long { Direction::Long } else { Direction::Short };
                    let order_type = if order_type_limit { OrderType::Limit } else { OrderType::Market };
                    let o = Order {
                        order_id: self.next_order_id, symbol_id,
                        direction, order_type, price, volume,
                        filled: 0.0, status: OrderStatus::Submitted, datetime: bar.datetime,
                    };
                    self.next_order_id += 1;
                    if self.risk.check(&o, bar.close).is_ok() {
                        parsed.push(o);
                    }
                }

                // ── 3. Match orders, update cash + positions ─────────────────────────
                for order in &mut parsed {
                    if let Some(fr) = self.broker.match_order(order, bar) {
                        let t = &fr.trade;

                        // Cash accounting — no double-counting with M2M
                        match t.direction {
                            Direction::Long  => self.cash -= t.price * t.volume + t.commission,
                            Direction::Short => self.cash += t.price * t.volume - t.commission,
                        }

                        let pos = self.positions.entry(t.symbol_id)
                            .or_insert_with(|| Position::new(t.symbol_id));
                        let realized = pos.apply_trade(t.direction, t.price, t.volume);

                        // P&L for win/loss tracking (realized portion of THIS fill minus commission)
                        let trade_pnl = realized - t.commission;
                        self.risk.update_pnl(trade_pnl);
                        self.risk.update_position(
                            t.symbol_id,
                            match t.direction { Direction::Long => t.volume, Direction::Short => -t.volume },
                        );
                        self.metrics.record_trade(trade_pnl);

                        // ── 4. Notify Python strategy of trade ──────────────────────
                        self.strategy_on_trade.call1(py, (
                            t.trade_id, t.order_id, t.symbol_id,
                            matches!(t.direction, Direction::Long),
                            t.price, t.volume, t.commission, t.datetime,
                        ))?;
                    }
                }

                // ── 5. Update unrealized P&L in position (for reporting only) ────────
                if let Some(pos) = self.positions.get_mut(&bar.symbol_id) {
                    pos.mark_to_market(bar.close);
                }

                // ── 6. Record bar equity = cash + market value ───────────────────────
                self.metrics.record_bar_equity(self.compute_equity());
            }

            Ok(self.metrics.finalize())
        })
    }

    /// Return current positions as a list of (symbol_id, net_volume, avg_price, upnl, rpnl).
    pub fn get_positions(&self) -> Vec<(u32, f64, f64, f64, f64)> {
        self.positions.values()
            .filter(|p| p.net_volume.abs() > 1e-9)
            .map(|p| (p.symbol_id, p.net_volume, p.avg_price, p.unrealized_pnl, p.realized_pnl))
            .collect()
    }

    /// Current equity = cash + market value of all open positions.
    pub fn current_equity(&self) -> f64 {
        self.compute_equity()
    }

    /// Cash on hand (excluding position market value).
    pub fn current_cash(&self) -> f64 {
        self.cash
    }
}
