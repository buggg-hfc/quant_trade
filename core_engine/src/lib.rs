mod backtest;
mod bar_builder;
mod broker;
mod event;
mod metrics;
mod object;
mod risk;

use pyo3::prelude::*;

#[pymodule]
fn quant_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    // Data objects
    m.add_class::<object::Bar>()?;
    m.add_class::<object::Tick>()?;
    m.add_class::<object::Position>()?;

    // Event engine
    m.add_class::<event::EventEngine>()?;

    // Backtest
    m.add_class::<backtest::BrokerConfigPy>()?;
    m.add_class::<backtest::BacktestRunner>()?;
    m.add_class::<metrics::BacktestMetrics>()?;

    Ok(())
}
