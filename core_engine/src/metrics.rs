use pyo3::prelude::*;

#[pyclass]
#[derive(Debug, Clone)]
pub struct BacktestMetrics {
    #[pyo3(get)]
    pub total_return: f64,
    #[pyo3(get)]
    pub annualized_return: f64,
    #[pyo3(get)]
    pub sharpe: f64,
    #[pyo3(get)]
    pub max_drawdown: f64,
    #[pyo3(get)]
    pub calmar: f64,
    #[pyo3(get)]
    pub win_rate: f64,
    #[pyo3(get)]
    pub total_trades: u64,
}

#[pymethods]
impl BacktestMetrics {
    pub fn __repr__(&self) -> String {
        format!(
            "BacktestMetrics(return={:.2}%, sharpe={:.3}, max_dd={:.2}%, calmar={:.3}, win_rate={:.1}%, trades={})",
            self.total_return * 100.0,
            self.sharpe,
            self.max_drawdown * 100.0,
            self.calmar,
            self.win_rate * 100.0,
            self.total_trades,
        )
    }
}

pub struct MetricsEngine {
    initial_capital: f64,
    equity_curve: Vec<f64>,
    returns: Vec<f64>,
    wins: u64,
    total_trades: u64,
    current_equity: f64,
    trading_days: f64,
}

impl MetricsEngine {
    pub fn new(initial_capital: f64) -> Self {
        MetricsEngine {
            initial_capital,
            equity_curve: vec![initial_capital],
            returns: Vec::new(),
            wins: 0,
            total_trades: 0,
            current_equity: initial_capital,
            trading_days: 0.0,
        }
    }

    pub fn update(&mut self, pnl: f64, is_win: bool) {
        self.current_equity += pnl;
        let prev = *self.equity_curve.last().unwrap();
        let ret = (self.current_equity - prev) / prev;
        self.equity_curve.push(self.current_equity);
        self.returns.push(ret);
        self.total_trades += 1;
        if is_win {
            self.wins += 1;
        }
        self.trading_days += 1.0 / 252.0; // approximate; refined later
    }

    pub fn finalize(&self) -> BacktestMetrics {
        let total_return =
            (self.current_equity - self.initial_capital) / self.initial_capital;
        let n = self.trading_days.max(1.0 / 252.0);
        let annualized_return = (1.0 + total_return).powf(1.0 / n) - 1.0;

        let sharpe = self.compute_sharpe();
        let max_drawdown = self.compute_max_drawdown();
        let calmar = if max_drawdown.abs() > 1e-9 {
            annualized_return / max_drawdown.abs()
        } else {
            f64::INFINITY
        };
        let win_rate = if self.total_trades > 0 {
            self.wins as f64 / self.total_trades as f64
        } else {
            0.0
        };

        BacktestMetrics {
            total_return,
            annualized_return,
            sharpe,
            max_drawdown,
            calmar,
            win_rate,
            total_trades: self.total_trades,
        }
    }

    fn compute_sharpe(&self) -> f64 {
        if self.returns.len() < 2 {
            return 0.0;
        }
        let mean = self.returns.iter().sum::<f64>() / self.returns.len() as f64;
        let variance = self.returns.iter().map(|r| (r - mean).powi(2)).sum::<f64>()
            / (self.returns.len() - 1) as f64;
        let std = variance.sqrt();
        if std < 1e-12 {
            return 0.0;
        }
        mean / std * 252f64.sqrt()
    }

    fn compute_max_drawdown(&self) -> f64 {
        let mut peak = self.initial_capital;
        let mut max_dd = 0.0f64;
        for &eq in &self.equity_curve {
            if eq > peak {
                peak = eq;
            }
            let dd = (eq - peak) / peak;
            if dd < max_dd {
                max_dd = dd;
            }
        }
        max_dd
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use approx::assert_abs_diff_eq;

    #[test]
    fn zero_trades_returns_zeros() {
        let m = MetricsEngine::new(1_000_000.0);
        let r = m.finalize();
        assert_abs_diff_eq!(r.total_return, 0.0, epsilon = 1e-9);
        assert_eq!(r.total_trades, 0);
    }

    #[test]
    fn single_win_metrics() {
        let mut m = MetricsEngine::new(100_000.0);
        m.update(10_000.0, true); // +10%
        let r = m.finalize();
        assert_abs_diff_eq!(r.total_return, 0.1, epsilon = 1e-9);
        assert_abs_diff_eq!(r.win_rate, 1.0, epsilon = 1e-9);
        assert_eq!(r.max_drawdown, 0.0);
    }

    #[test]
    fn max_drawdown_correct() {
        let mut m = MetricsEngine::new(100_000.0);
        m.update(10_000.0, true);  // equity = 110_000 (peak)
        m.update(-20_000.0, false); // equity = 90_000 → dd = (90-110)/110 ≈ -18.18%
        let r = m.finalize();
        assert!(r.max_drawdown < -0.18);
        assert!(r.max_drawdown > -0.19);
    }
}
