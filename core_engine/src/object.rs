use pyo3::prelude::*;
use serde::{Deserialize, Serialize};

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
        symbol_id: u32,
        datetime: i64,
        open: f64,
        high: f64,
        low: f64,
        close: f64,
        volume: f64,
    ) -> Self {
        Bar { symbol_id, datetime, open, high, low, close, volume }
    }

    pub fn __repr__(&self) -> String {
        format!(
            "Bar(symbol_id={}, dt={}, O={} H={} L={} C={} V={})",
            self.symbol_id, self.datetime,
            self.open, self.high, self.low, self.close, self.volume
        )
    }
}

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
        symbol_id: u32,
        datetime: i64,
        last_price: f64,
        bid_price: f64,
        ask_price: f64,
        volume: f64,
    ) -> Self {
        Tick { symbol_id, datetime, last_price, bid_price, ask_price, volume }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub enum Direction {
    Long,
    Short,
}

#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub enum OrderType {
    Limit,
    Market,
}

#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub enum OrderStatus {
    Submitted,
    Accepted,
    PartiallyFilled,
    Filled,
    Cancelled,
    Rejected,
}

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
