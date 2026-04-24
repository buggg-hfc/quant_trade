use crate::object::{Bar, Tick};

pub struct BarBuilder {
    symbol_id: u32,
    period_secs: i64,
    current_bar: Option<Bar>,
    bar_start: i64,
}

impl BarBuilder {
    pub fn new(symbol_id: u32, period_secs: i64) -> Self {
        BarBuilder { symbol_id, period_secs, current_bar: None, bar_start: 0 }
    }

    /// Feed a tick; returns a completed Bar when the period boundary is crossed.
    pub fn update(&mut self, tick: &Tick) -> Option<Bar> {
        let period_start = (tick.datetime / self.period_secs) * self.period_secs;
        let mut completed = None;

        if let Some(ref bar) = self.current_bar {
            if period_start != self.bar_start {
                completed = Some(*bar);
                self.current_bar = None;
            }
        }

        self.bar_start = period_start;
        let price = tick.last_price;
        let vol = tick.volume;

        self.current_bar = Some(match self.current_bar {
            None => Bar {
                symbol_id: self.symbol_id,
                datetime: period_start,
                open: price,
                high: price,
                low: price,
                close: price,
                volume: vol,
            },
            Some(b) => Bar {
                high: b.high.max(price),
                low: b.low.min(price),
                close: price,
                volume: b.volume + vol,
                ..b
            },
        });

        completed
    }

    /// Force-close whatever is in progress (e.g. end of trading session).
    pub fn flush(&mut self) -> Option<Bar> {
        self.current_bar.take()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn tick(ts: i64, price: f64, vol: f64) -> Tick {
        Tick { symbol_id: 0, datetime: ts, last_price: price, bid_price: price - 0.01, ask_price: price + 0.01, volume: vol }
    }

    #[test]
    fn builds_bar_on_boundary() {
        let mut bb = BarBuilder::new(0, 60);
        // 4 ticks in minute 0
        assert!(bb.update(&tick(0, 10.0, 100.0)).is_none());
        assert!(bb.update(&tick(10, 10.5, 200.0)).is_none());
        assert!(bb.update(&tick(20, 9.8, 150.0)).is_none());
        assert!(bb.update(&tick(55, 10.2, 50.0)).is_none());
        // first tick of minute 1 → returns minute-0 bar
        let bar = bb.update(&tick(60, 10.3, 100.0)).unwrap();
        assert_eq!(bar.open, 10.0);
        assert_eq!(bar.high, 10.5);
        assert_eq!(bar.low, 9.8);
        assert_eq!(bar.close, 10.2);
        assert_eq!(bar.volume, 500.0);
    }

    #[test]
    fn flush_returns_incomplete_bar() {
        let mut bb = BarBuilder::new(0, 60);
        bb.update(&tick(0, 10.0, 100.0));
        let bar = bb.flush().unwrap();
        assert_eq!(bar.open, 10.0);
    }
}
