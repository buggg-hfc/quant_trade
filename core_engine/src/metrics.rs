use pyo3::prelude::*;

const TRADING_DAYS_PER_YEAR: f64 = 252.0;
const RISK_FREE_RATE: f64 = 0.02; // 2% annual, matching default settings

#[pyclass]
#[derive(Debug, Clone)]
pub struct BacktestMetrics {
    #[pyo3(get)] pub total_return: f64,
    #[pyo3(get)] pub annualized_return: f64,
    #[pyo3(get)] pub sharpe: f64,
    #[pyo3(get)] pub sortino: f64,
    #[pyo3(get)] pub max_drawdown: f64,
    #[pyo3(get)] pub calmar: f64,
    #[pyo3(get)] pub win_rate: f64,
    #[pyo3(get)] pub total_trades: u64,
    #[pyo3(get)] pub profit_factor: f64,
    #[pyo3(get)] pub initial_capital: f64,
    #[pyo3(get)] pub final_equity: f64,
}

#[pymethods]
impl BacktestMetrics {
    pub fn __repr__(&self) -> String {
        format!(
            "BacktestMetrics(return={:.2}%, sharpe={:.3}, sortino={:.3}, \
             max_dd={:.2}%, calmar={:.3}, win_rate={:.1}%, trades={}, \
             profit_factor={:.2})",
            self.total_return * 100.0,
            self.sharpe, self.sortino,
            self.max_drawdown * 100.0,
            self.calmar,
            self.win_rate * 100.0,
            self.total_trades,
            self.profit_factor,
        )
    }
}

pub struct MetricsEngine {
    initial_capital: f64,
    /// Equity recorded at every bar (mark-to-market).
    equity_curve: Vec<f64>,
    /// Per-bar returns (from equity_curve).
    bar_returns: Vec<f64>,
    /// Per-trade P&L (realized + commission).
    trade_pnls: Vec<f64>,
    wins: u64,
    total_trades: u64,
}

impl MetricsEngine {
    pub fn new(initial_capital: f64) -> Self {
        MetricsEngine {
            initial_capital,
            equity_curve: vec![initial_capital],
            bar_returns: Vec::new(),
            trade_pnls: Vec::new(),
            wins: 0,
            total_trades: 0,
        }
    }

    /// Called once per bar with the current equity value (after M2M + all fills).
    pub fn record_bar_equity(&mut self, equity: f64) {
        let prev = *self.equity_curve.last().unwrap();
        let ret = if prev.abs() > 1e-12 { (equity - prev) / prev } else { 0.0 };
        self.equity_curve.push(equity);
        self.bar_returns.push(ret);
    }

    /// Called for each trade's net P&L (after commission).
    pub fn record_trade(&mut self, net_pnl: f64) {
        self.trade_pnls.push(net_pnl);
        self.total_trades += 1;
        if net_pnl > 0.0 {
            self.wins += 1;
        }
    }

    pub fn finalize(&self) -> BacktestMetrics {
        let final_equity = *self.equity_curve.last().unwrap_or(&self.initial_capital);
        let total_return = (final_equity - self.initial_capital) / self.initial_capital;

        let n_bars = self.bar_returns.len() as f64;
        // Approximate trading years from bar count (assumes daily bars by default)
        let trading_years = (n_bars / TRADING_DAYS_PER_YEAR).max(1.0 / TRADING_DAYS_PER_YEAR);
        let annualized_return = (1.0 + total_return).powf(1.0 / trading_years) - 1.0;

        let daily_rf = RISK_FREE_RATE / TRADING_DAYS_PER_YEAR;
        let sharpe = self.compute_sharpe(daily_rf);
        let sortino = self.compute_sortino(daily_rf);
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
        let profit_factor = self.compute_profit_factor();

        BacktestMetrics {
            total_return,
            annualized_return,
            sharpe,
            sortino,
            max_drawdown,
            calmar,
            win_rate,
            total_trades: self.total_trades,
            profit_factor,
            initial_capital: self.initial_capital,
            final_equity,
        }
    }

    fn compute_sharpe(&self, daily_rf: f64) -> f64 {
        if self.bar_returns.len() < 2 {
            return 0.0;
        }
        let excess: Vec<f64> = self.bar_returns.iter().map(|r| r - daily_rf).collect();
        let mean = excess.iter().sum::<f64>() / excess.len() as f64;
        let variance = excess.iter().map(|r| (r - mean).powi(2)).sum::<f64>()
            / (excess.len() - 1) as f64;
        let std = variance.sqrt();
        if std < 1e-12 { return 0.0; }
        mean / std * TRADING_DAYS_PER_YEAR.sqrt()
    }

    fn compute_sortino(&self, daily_rf: f64) -> f64 {
        if self.bar_returns.len() < 2 {
            return 0.0;
        }
        let excess: Vec<f64> = self.bar_returns.iter().map(|r| r - daily_rf).collect();
        let mean = excess.iter().sum::<f64>() / excess.len() as f64;
        // Downside deviation: only negative excess returns
        let downside_sq: Vec<f64> = excess.iter()
            .filter(|&&r| r < 0.0)
            .map(|r| r.powi(2))
            .collect();
        if downside_sq.is_empty() {
            return if mean > 0.0 { f64::INFINITY } else { 0.0 };
        }
        let downside_std = (downside_sq.iter().sum::<f64>() / downside_sq.len() as f64).sqrt();
        if downside_std < 1e-12 { return 0.0; }
        mean / downside_std * TRADING_DAYS_PER_YEAR.sqrt()
    }

    fn compute_max_drawdown(&self) -> f64 {
        let mut peak = self.initial_capital;
        let mut max_dd = 0.0f64;
        for &eq in &self.equity_curve {
            if eq > peak { peak = eq; }
            let dd = (eq - peak) / peak;
            if dd < max_dd { max_dd = dd; }
        }
        max_dd
    }

    fn compute_profit_factor(&self) -> f64 {
        let gross_profit: f64 = self.trade_pnls.iter().filter(|&&p| p > 0.0).sum();
        let gross_loss: f64 = self.trade_pnls.iter().filter(|&&p| p < 0.0).map(|p| p.abs()).sum();
        if gross_loss < 1e-9 {
            if gross_profit > 0.0 { f64::INFINITY } else { 0.0 }
        } else {
            gross_profit / gross_loss
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use approx::assert_abs_diff_eq;

    #[test]
    fn zero_bars_returns_zeros() {
        let m = MetricsEngine::new(100_000.0);
        let r = m.finalize();
        assert_abs_diff_eq!(r.total_return, 0.0, epsilon = 1e-9);
        assert_eq!(r.total_trades, 0);
        assert_abs_diff_eq!(r.max_drawdown, 0.0, epsilon = 1e-9);
    }

    #[test]
    fn positive_trend_gives_positive_sharpe() {
        // Vary returns slightly (+0.1% ± 0.05%) so std > 0 → Sharpe is defined.
        let mut m = MetricsEngine::new(100_000.0);
        let mut eq = 100_000.0;
        for i in 0..100usize {
            let ret = 0.001 + if i % 2 == 0 { 0.0005 } else { -0.0005 };
            eq *= 1.0 + ret;
            m.record_bar_equity(eq);
        }
        let r = m.finalize();
        assert!(r.sharpe > 0.0, "sharpe={}", r.sharpe);
        assert!(r.total_return > 0.0, "ret={}", r.total_return);
        // Max drawdown: alternating ups/downs with net upward — dd should be small
        assert!(r.max_drawdown >= -0.01, "dd={}", r.max_drawdown);
    }

    #[test]
    fn drawdown_computed_correctly() {
        let mut m = MetricsEngine::new(100_000.0);
        m.record_bar_equity(110_000.0); // peak
        m.record_bar_equity(88_000.0);  // dd = (88-110)/110 ≈ -20%
        m.record_bar_equity(99_000.0);
        let r = m.finalize();
        assert!(r.max_drawdown < -0.19, "dd={}", r.max_drawdown);
        assert!(r.max_drawdown > -0.21, "dd={}", r.max_drawdown);
    }

    #[test]
    fn win_rate_and_profit_factor() {
        let mut m = MetricsEngine::new(100_000.0);
        m.record_trade(1000.0);
        m.record_trade(1000.0);
        m.record_trade(-500.0);
        let r = m.finalize();
        assert_abs_diff_eq!(r.win_rate, 2.0 / 3.0, epsilon = 1e-9);
        assert_abs_diff_eq!(r.profit_factor, 4.0, epsilon = 1e-9); // 2000/500
    }

    #[test]
    fn sortino_infinity_when_no_down_days() {
        let mut m = MetricsEngine::new(100_000.0);
        let mut eq = 100_000.0;
        for _ in 0..20 {
            eq *= 1.002;
            m.record_bar_equity(eq);
        }
        let r = m.finalize();
        assert!(r.sortino.is_infinite() || r.sortino > 100.0, "sortino={}", r.sortino);
    }

    #[test]
    fn consecutive_losses_max_drawdown() {
        let mut m = MetricsEngine::new(100_000.0);
        let mut eq = 100_000.0;
        for _ in 0..10 {
            eq *= 0.99; // -1% each bar → ~10% total DD
            m.record_bar_equity(eq);
        }
        let r = m.finalize();
        assert!(r.max_drawdown < -0.09, "dd={}", r.max_drawdown);
        assert!(r.total_return < -0.09, "ret={}", r.total_return);
    }
}
