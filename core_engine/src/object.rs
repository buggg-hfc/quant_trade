use pyo3::prelude::*;
use serde::{Deserialize, Serialize};

// ─── Bar ─────────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
#[pyclass]
pub struct Bar {
    #[pyo3(get, set)]
    pub symbol_id: u32,
    #[pyo3(get, set)]
    pub datetime: i64,
    #[pyo3(get, set)]
    pub open: f64,
    #[pyo3(get, set)]
    pub high: f64,
    #[pyo3(get, set)]
    pub low: f64,
    #[pyo3(get, set)]
    pub close: f64,
    #[pyo3(get, set)]
    pub volume: f64,
}

#[pymethods]
impl Bar {
    #[new]
    pub fn new(
        symbol_id: u32, datetime: i64,
        open: f64, high: f64, low: f64, close: f64, volume: f64,
    ) -> Self {
        Bar { symbol_id, datetime, open, high, low, close, volume }
    }

    pub fn __repr__(&self) -> String {
        format!(
            "Bar(sym={}, dt={}, O={} H={} L={} C={} V={})",
            self.symbol_id, self.datetime,
            self.open, self.high, self.low, self.close, self.volume,
        )
    }
}

// ─── Tick ────────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
#[pyclass]
pub struct Tick {
    #[pyo3(get, set)]
    pub symbol_id: u32,
    #[pyo3(get, set)]
    pub datetime: i64,
    #[pyo3(get, set)]
    pub last_price: f64,
    #[pyo3(get, set)]
    pub bid_price: f64,
    #[pyo3(get, set)]
    pub ask_price: f64,
    #[pyo3(get, set)]
    pub volume: f64,
}

#[pymethods]
impl Tick {
    #[new]
    pub fn new(
        symbol_id: u32, datetime: i64,
        last_price: f64, bid_price: f64, ask_price: f64, volume: f64,
    ) -> Self {
        Tick { symbol_id, datetime, last_price, bid_price, ask_price, volume }
    }
}

// ─── Enums ───────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub enum Direction { Long, Short }

#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub enum OrderType { Limit, Market }

#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub enum OrderStatus {
    Submitted,
    Accepted,
    PartiallyFilled,
    Filled,
    Cancelled,
    Rejected,
}

// ─── Order ───────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Order {
    pub order_id: u64,
    pub symbol_id: u32,
    pub direction: Direction,
    pub order_type: OrderType,
    pub price: f64,
    pub volume: f64,
    pub filled: f64,
    pub status: OrderStatus,
    pub datetime: i64,
}

impl Order {
    pub fn remaining(&self) -> f64 {
        self.volume - self.filled
    }
}

// ─── Trade ───────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Trade {
    pub trade_id: u64,
    pub order_id: u64,
    pub symbol_id: u32,
    pub direction: Direction,
    pub price: f64,
    pub volume: f64,
    pub commission: f64,
    pub datetime: i64,
}

// ─── Position (exposed to Python) ────────────────────────────────────────────

#[pyclass]
#[derive(Debug, Clone)]
pub struct Position {
    #[pyo3(get)]
    pub symbol_id: u32,
    #[pyo3(get)]
    pub net_volume: f64,
    #[pyo3(get)]
    pub avg_price: f64,
    #[pyo3(get)]
    pub unrealized_pnl: f64,
    #[pyo3(get)]
    pub realized_pnl: f64,
}

#[pymethods]
impl Position {
    pub fn __repr__(&self) -> String {
        format!(
            "Position(sym={}, net={}, avg_px={:.4}, upnl={:.2}, rpnl={:.2})",
            self.symbol_id, self.net_volume, self.avg_price,
            self.unrealized_pnl, self.realized_pnl,
        )
    }
}

impl Position {
    pub fn new(symbol_id: u32) -> Self {
        Position { symbol_id, net_volume: 0.0, avg_price: 0.0, unrealized_pnl: 0.0, realized_pnl: 0.0 }
    }

    /// Update position after a fill; returns realized P&L from this trade.
    pub fn apply_trade(&mut self, direction: Direction, fill_price: f64, fill_volume: f64) -> f64 {
        let signed_vol = match direction {
            Direction::Long => fill_volume,
            Direction::Short => -fill_volume,
        };
        let prev_net = self.net_volume;
        let new_net = prev_net + signed_vol;

        let realized = if prev_net.abs() < 1e-9 {
            // Flat → open new position
            self.avg_price = fill_price;
            self.net_volume = new_net;
            0.0
        } else if prev_net.signum() == signed_vol.signum() {
            // Adding to same side: weighted average price
            let total_cost = self.avg_price * prev_net.abs() + fill_price * fill_volume;
            let total_vol = prev_net.abs() + fill_volume;
            self.avg_price = total_cost / total_vol;
            self.net_volume = new_net;
            0.0
        } else {
            // Closing (partial, full, or flip to opposite side)
            let close_vol = prev_net.abs().min(fill_volume);
            let rpnl = (fill_price - self.avg_price) * close_vol * prev_net.signum();
            self.realized_pnl += rpnl;
            self.net_volume = new_net;
            if new_net.abs() < 1e-9 {
                self.avg_price = 0.0; // fully flat
            } else {
                self.avg_price = fill_price; // flipped side: new avg = fill price
            }
            rpnl
        };
        realized
    }

    pub fn mark_to_market(&mut self, current_price: f64) -> f64 {
        if self.net_volume.abs() < 1e-9 {
            self.unrealized_pnl = 0.0;
            return 0.0;
        }
        let upnl = (current_price - self.avg_price) * self.net_volume;
        let prev = self.unrealized_pnl;
        self.unrealized_pnl = upnl;
        upnl - prev // change in unrealized (used for equity update)
    }
}
