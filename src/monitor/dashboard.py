"""Streamlit main dashboard.

Run via launcher.py or directly:
    streamlit run src/monitor/dashboard.py --server.port 8501

Navigation (sidebar):
    Home | Data | Strategies | Backtest | Live Trading | Risk | Logs | Help
"""
from __future__ import annotations

import importlib
import sys
import threading
import time
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

st.set_page_config(
    page_title="quant_trade",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Sidebar navigation ────────────────────────────────────────────────────────

PAGES = ["Home", "Data", "Strategies", "Backtest", "Live Trading", "Risk", "Logs", "Help"]
page = st.sidebar.radio("Navigation", PAGES, label_visibility="collapsed")
st.sidebar.markdown("---")
st.sidebar.caption("quant_trade v0.1  |  [Live Dashboard](http://localhost:8000)")


# ── Page: Home ────────────────────────────────────────────────────────────────

def page_home():
    st.title("System Status")
    from src.utils.config import get_settings
    cfg = get_settings()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Mode", cfg.system.mode.upper())
    c2.metric("Log Level", cfg.system.log_level)
    c3.metric("Initial Capital", f"¥{cfg.backtest.initial_capital:,.0f}")
    c4.metric("Commission", f"{cfg.backtest.commission_rate*100:.2f}%")

    st.divider()
    st.subheader("Quick Links")
    col1, col2, col3 = st.columns(3)
    col1.markdown("**[Live Dashboard](http://localhost:8000)**  \nReal-time orders/positions (FastAPI)")
    col2.markdown("**[Logs](logs/)**  \nApplication and data quality logs")
    col3.markdown("**[Reports](reports/)**  \nBacktest HTML reports")

    st.divider()
    st.subheader("Directory Structure")
    dirs = {"strategies/": "User strategy files", "data_cache/": "SQLite bar cache",
            "logs/": "Application logs", "reports/": "Backtest reports", "config/": "YAML config"}
    for path, desc in dirs.items():
        exists = (ROOT / path.rstrip("/")).exists()
        icon = "✅" if exists else "❌"
        st.write(f"{icon} `{path}` — {desc}")


# ── Page: Data ────────────────────────────────────────────────────────────────

def page_data():
    st.title("Data Management")
    tab1, tab2 = st.tabs(["A-share / Futures", "Crypto"])

    with tab1:
        st.subheader("Download A-share / Futures Bars")
        col1, col2 = st.columns(2)
        symbol = col1.text_input("Symbol", "000001.SZ", help="e.g. 000001.SZ, IF9999")
        interval = col1.selectbox("Interval", ["daily", "weekly", "monthly"])
        adjust = col2.selectbox("Adjust", ["qfq", "hfq", ""], help="qfq=forward, hfq=backward, blank=raw")
        start = col2.date_input("Start", value=None)
        end = col2.date_input("End", value=None)
        force = col2.checkbox("Force refresh (overwrite cache)")

        if st.button("Download", key="dl_ashare"):
            with st.spinner("Downloading…"):
                try:
                    from src.data.akshare_feed import CachedAkShareFeed
                    feed = CachedAkShareFeed()
                    df, report = feed.get_bars(
                        symbol, interval=interval,
                        start=str(start) if start else "2020-01-01",
                        end=str(end) if end else None,
                        adjust=adjust, force_refresh=force,
                    )
                    badge_color = {"GREEN": "green", "YELLOW": "orange", "RED": "red"}.get(report.badge, "gray")
                    st.success(f"Downloaded {len(df)} bars")
                    st.markdown(f"Validation: :{badge_color}[{report.badge}]  "
                                f"— missing={report.missing_bars}, ohlc_errors={report.ohlc_errors}, "
                                f"anomalies={len(report.price_anomalies)}, zero_vol={report.zero_volume_days}")
                    if not df.empty:
                        st.dataframe(df.tail(10))
                except ImportError as e:
                    st.error(f"Missing dependency: {e}")
                except Exception as e:
                    st.error(f"Error: {e}")

    with tab2:
        st.subheader("Download Crypto Bars")
        col1, col2 = st.columns(2)
        exchange = col1.selectbox("Exchange", ["binance", "okx", "bybit", "gate"])
        crypto_sym = col1.text_input("Symbol", "BTC/USDT")
        crypto_interval = col2.selectbox("Interval", ["1d", "1h", "4h", "15m"])
        crypto_start = col2.date_input("Start", key="crypto_start", value=None)

        if st.button("Download", key="dl_crypto"):
            with st.spinner("Downloading…"):
                try:
                    from src.data.crypto_feed import CryptoFeed
                    feed = CryptoFeed(exchange_id=exchange)
                    df = feed.fetch_bars(
                        crypto_sym, interval=crypto_interval,
                        start=str(crypto_start) if crypto_start else "2023-01-01"
                    )
                    st.success(f"Downloaded {len(df)} bars")
                    if not df.empty:
                        st.dataframe(df.tail(10))
                except ImportError as e:
                    st.error(f"Missing dependency (pip install ccxt): {e}")
                except Exception as e:
                    st.error(f"Error: {e}")

    st.divider()
    st.subheader("Cached Symbols")
    try:
        from src.data.database import BarDatabase
        db = BarDatabase()
        symbols = db.list_symbols()
        if symbols:
            st.dataframe({"symbol_interval": symbols})
        else:
            st.info("No data cached yet.")
    except Exception as e:
        st.warning(f"Could not read cache: {e}")


# ── Page: Strategies ──────────────────────────────────────────────────────────

def page_strategies():
    st.title("Strategy Management")
    strategies_dir = ROOT / "strategies"

    py_files = sorted(p for p in strategies_dir.glob("*.py") if not p.name.startswith("_"))

    tab1, tab2 = st.tabs(["Strategy List", "New / Edit"])

    with tab1:
        if not py_files:
            st.info("No strategies found in strategies/. Copy _template.py to get started.")
        else:
            for f in py_files:
                with st.expander(f"📄 {f.stem}", expanded=False):
                    col1, col2 = st.columns([3, 1])
                    col1.code(f.read_text(encoding="utf-8"), language="python")
                    with col2:
                        if st.button("Delete", key=f"del_{f.stem}"):
                            archived = strategies_dir / "archived"
                            archived.mkdir(exist_ok=True)
                            f.rename(archived / f.name)
                            st.success(f"Archived {f.name}")
                            st.rerun()

    with tab2:
        st.subheader("Create / Edit Strategy")
        existing = ["(new)"] + [f.stem for f in py_files]
        choice = st.selectbox("Based on", existing)

        if choice == "(new)":
            template = (strategies_dir / "_template.py").read_text(encoding="utf-8") \
                if (strategies_dir / "_template.py").exists() else \
                "from src.strategy.base import BaseStrategy\nfrom src.core.object import BarData\n\nclass MyStrategy(BaseStrategy):\n    def on_bar(self, bar: BarData) -> None:\n        pass\n"
            default_name = "my_strategy"
        else:
            template = (strategies_dir / f"{choice}.py").read_text(encoding="utf-8")
            default_name = choice

        filename = st.text_input("Filename (no .py)", default_name)
        code = st.text_area("Code", template, height=400)

        if st.button("Save"):
            target = strategies_dir / f"{filename}.py"
            target.write_text(code, encoding="utf-8")
            st.success(f"Saved {target.name}")
            st.rerun()


# ── Page: Backtest ────────────────────────────────────────────────────────────

def page_backtest():
    st.title("Backtest")
    tab_run, tab_opt = st.tabs(["Run Backtest", "Parameter Optimization"])

    strategies_dir = ROOT / "strategies"
    py_files = sorted(p.stem for p in strategies_dir.glob("*.py") if not p.name.startswith("_"))

    with tab_run:
        col1, col2 = st.columns(2)
        strategy_name = col1.selectbox("Strategy", py_files or ["(no strategies)"])
        symbols_str = col1.text_input("Symbols (comma-separated)", "000001.SZ")
        start_date = col2.date_input("Start", value=None, key="bt_start")
        end_date = col2.date_input("End", value=None, key="bt_end")
        interval = col2.selectbox("Interval", ["daily", "weekly"])
        adjust = col2.selectbox("Adjust", ["qfq", "hfq", ""])

        if st.button("Run Backtest"):
            if not py_files:
                st.error("No strategies available.")
            else:
                with st.spinner("Running backtest…"):
                    try:
                        mod = importlib.import_module(f"strategies.{strategy_name}")
                        # Find strategy class (first class that is a subclass of BaseStrategy)
                        from src.strategy.base import BaseStrategy
                        strategy_cls = next(
                            (v for v in vars(mod).values()
                             if isinstance(v, type) and issubclass(v, BaseStrategy) and v is not BaseStrategy),
                            None
                        )
                        if strategy_cls is None:
                            st.error(f"No BaseStrategy subclass found in strategies/{strategy_name}.py")
                        else:
                            symbols = [s.strip() for s in symbols_str.split(",")]
                            from src.backtest.engine import BacktestEngine
                            engine = BacktestEngine()
                            result = engine.run(
                                strategy_cls(),
                                symbols=symbols,
                                start=str(start_date) if start_date else "2020-01-01",
                                end=str(end_date) if end_date else "2024-12-31",
                                interval=interval,
                                adjust=adjust,
                            )
                            st.success(result.summary())
                            m = result.metrics
                            c1, c2, c3, c4, c5 = st.columns(5)
                            c1.metric("Total Return", f"{m.total_return:.2%}")
                            c2.metric("Sharpe", f"{m.sharpe_ratio:.2f}")
                            c3.metric("Max Drawdown", f"{m.max_drawdown:.2%}")
                            c4.metric("Trades", m.total_trades)
                            c5.metric("Win Rate", f"{m.win_rate:.2%}")

                            # Equity curve chart
                            if not result.equity_curve.empty:
                                st.line_chart(result.equity_curve, use_container_width=True)

                            # Generate HTML report
                            from src.backtest.report import generate_report
                            report_path = generate_report(result, strategy_name)
                            st.info(f"HTML report saved: {report_path}")
                    except Exception as e:
                        st.error(f"Backtest failed: {e}")
                        import traceback
                        st.code(traceback.format_exc())

    with tab_opt:
        st.subheader("Parameter Grid Search")
        opt_strategy = st.selectbox("Strategy", py_files or ["(no strategies)"], key="opt_strat")
        opt_symbols = st.text_input("Symbols", "000001.SZ", key="opt_syms")
        opt_start = st.date_input("Start", value=None, key="opt_start")
        opt_end = st.date_input("End", value=None, key="opt_end")
        opt_metric = st.selectbox("Optimize for", ["sharpe_ratio", "total_return", "win_rate"])
        opt_jobs = st.slider("Parallel workers", 1, 8, 2)

        st.markdown("**Parameter grid** (JSON, e.g. `{\"fast_period\": [3,5,10], \"slow_period\": [15,20,30]}`)")
        param_json = st.text_area("param_grid", '{"fast_period": [3, 5], "slow_period": [15, 20]}', height=80)

        if "opt_result" not in st.session_state:
            st.session_state.opt_result = None
        if "opt_running" not in st.session_state:
            st.session_state.opt_running = False

        if st.button("Start Optimization", disabled=st.session_state.opt_running):
            try:
                import json as _json
                param_grid = _json.loads(param_json)
            except Exception:
                st.error("Invalid JSON for param_grid")
                return

            st.session_state.opt_running = True
            st.session_state.opt_result = None

            def _run_opt():
                try:
                    mod = importlib.import_module(f"strategies.{opt_strategy}")
                    from src.strategy.base import BaseStrategy
                    strategy_cls = next(
                        (v for v in vars(mod).values()
                         if isinstance(v, type) and issubclass(v, BaseStrategy) and v is not BaseStrategy),
                        None
                    )
                    if strategy_cls is None:
                        st.session_state.opt_result = {"error": "Strategy class not found"}
                        return
                    from src.backtest.optimizer import GridOptimizer
                    opt = GridOptimizer()
                    result = opt.optimize(
                        strategy_cls=strategy_cls,
                        param_grid=param_grid,
                        symbols=[s.strip() for s in opt_symbols.split(",")],
                        start=str(opt_start) if opt_start else "2020-01-01",
                        end=str(opt_end) if opt_end else "2024-12-31",
                        metric=opt_metric,
                        n_jobs=opt_jobs,
                    )
                    st.session_state.opt_result = result
                except Exception as e:
                    import traceback
                    st.session_state.opt_result = {"error": str(e), "trace": traceback.format_exc()}
                finally:
                    st.session_state.opt_running = False

            threading.Thread(target=_run_opt, daemon=True).start()
            st.rerun()

        if st.session_state.opt_running:
            st.info("Optimization running in background…")
            time.sleep(2)
            st.rerun()

        if st.session_state.opt_result:
            r = st.session_state.opt_result
            if isinstance(r, dict) and "error" in r:
                st.error(r["error"])
                if "trace" in r:
                    st.code(r["trace"])
            else:
                st.success(f"Best: {r.best_params}  {opt_metric}={r.best_score:.4f}")
                import pandas as pd
                rows = [{"params": str(p), "score": s} for p, s in r.top_n(10)]
                st.dataframe(pd.DataFrame(rows))


# ── Page: Live Trading ────────────────────────────────────────────────────────

def page_live():
    st.title("Live Trading")

    st.subheader("Gateway Configuration")
    gateway = st.selectbox("Gateway", ["paper", "ctp", "crypto"])

    if gateway == "paper":
        st.info("Paper gateway: simulated matching, no real orders.")
        capital = st.number_input("Initial Capital", value=1_000_000.0, step=10_000.0)

    elif gateway == "ctp":
        st.subheader("CTP (Futures)")
        broker_id = st.text_input("Broker ID", help="e.g. 9999 for SimNow")
        user_id = st.text_input("Account")
        td_addr = st.text_input("Trading server", "tcp://180.168.146.187:10201")
        md_addr = st.text_input("Market data server", "tcp://180.168.146.187:10211")
        ctp_pwd = st.text_input("Password", type="password")
        if st.button("Save CTP credentials"):
            if ctp_pwd:
                master = st.text_input("KeyStore master password", type="password", key="ctp_master")
                if master:
                    try:
                        from src.utils.keystore import KeyStore
                        KeyStore().set_key("ctp_password", ctp_pwd, master)
                        st.success("CTP password saved to KeyStore")
                    except Exception as e:
                        st.error(f"KeyStore error: {e}")

    elif gateway == "crypto":
        exchange = st.selectbox("Exchange", ["binance", "okx", "bybit"])
        sandbox = st.checkbox("Sandbox / testnet", value=True)
        api_key_in = st.text_input("API Key", type="password")
        secret_in = st.text_input("Secret", type="password")
        if st.button("Save crypto credentials"):
            master = st.text_input("KeyStore master password", type="password", key="crypto_master")
            if master and api_key_in and secret_in:
                try:
                    from src.utils.keystore import KeyStore
                    ks = KeyStore()
                    ks.set_key("crypto_api_key", api_key_in, master)
                    ks.set_key("crypto_secret",  secret_in,  master)
                    st.success("Crypto credentials saved to KeyStore")
                except Exception as e:
                    st.error(f"KeyStore error: {e}")

    st.divider()
    st.subheader("Strategy")
    strategies_dir = ROOT / "strategies"
    py_files = sorted(p.stem for p in strategies_dir.glob("*.py") if not p.name.startswith("_"))
    live_strategy = st.selectbox("Strategy", py_files or ["(no strategies)"])
    live_symbols = st.text_input("Symbols", "000001.SZ")

    col1, col2 = st.columns(2)
    if col1.button("Start Live Trading", type="primary"):
        st.warning("Live trading is started via CLI: `python run_live.py --gateway paper --strategy MACrossStrategy`  \n"
                   "Or start the full system: `python launcher.py`")

    if col2.button("Open Live Dashboard"):
        st.markdown("[Open in new tab](http://localhost:8000)", unsafe_allow_html=True)

    st.divider()
    st.subheader("Current Positions (from live server)")
    try:
        import urllib.request
        with urllib.request.urlopen("http://localhost:8000/state", timeout=1) as r:
            import json
            state = json.loads(r.read())
        acc = state["account"]
        st.metric("Balance", f"¥{acc['balance']:,.2f}", delta=f"PnL: ¥{acc['total_pnl']:,.2f}")
        pos_data = state.get("positions", {})
        if pos_data:
            import pandas as pd
            st.dataframe(pd.DataFrame(pos_data).T)
        else:
            st.info("No open positions")
    except Exception:
        st.info("Live server not running (start with python launcher.py).")


# ── Page: Risk Settings ───────────────────────────────────────────────────────

def page_risk():
    st.title("Risk Settings")
    from src.utils.config import get_settings
    cfg = get_settings()

    st.subheader("Current Thresholds (from config/settings.yaml)")
    col1, col2 = st.columns(2)
    col1.metric("Max Position %", f"{cfg.risk.max_position_pct*100:.0f}%")
    col1.metric("Daily Loss Limit", f"{cfg.risk.daily_loss_limit*100:.0f}%")
    col2.metric("Max Drawdown", f"{cfg.risk.max_drawdown*100:.0f}%")
    col2.metric("Max Order Volume", f"{cfg.risk.max_order_volume:,.0f}")

    st.divider()
    st.subheader("Edit Risk Config")
    st.info("Edit `config/settings.yaml` and restart to apply changes.")
    cfg_path = ROOT / "config" / "settings.yaml"
    if cfg_path.exists():
        import yaml
        with st.form("risk_form"):
            content = cfg_path.read_text(encoding="utf-8")
            edited = st.text_area("settings.yaml", content, height=400)
            if st.form_submit_button("Save"):
                try:
                    yaml.safe_load(edited)   # validate
                    cfg_path.write_text(edited, encoding="utf-8")
                    from src.utils.config import reload_settings
                    reload_settings()
                    st.success("Saved and reloaded")
                except yaml.YAMLError as e:
                    st.error(f"Invalid YAML: {e}")

    st.divider()
    st.subheader("Validator Thresholds")
    rows = [{"asset_type": k, "threshold": f"{v*100:.0f}%"} for k, v in cfg.validator_thresholds.items()]
    import pandas as pd
    st.dataframe(pd.DataFrame(rows))


# ── Page: Logs ────────────────────────────────────────────────────────────────

def page_logs():
    st.title("Logs & Alerts")
    tab1, tab2 = st.tabs(["Application Logs", "Alert Configuration"])

    with tab1:
        logs_dir = ROOT / "logs"
        log_files = sorted(logs_dir.glob("*.log"), reverse=True) if logs_dir.exists() else []
        if not log_files:
            st.info("No log files found in logs/")
        else:
            selected = st.selectbox("Log file", [f.name for f in log_files])
            log_path = logs_dir / selected
            lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
            tail = st.slider("Last N lines", 20, 500, 100)
            st.code("\n".join(lines[-tail:]), language=None)
            if st.button("Refresh"):
                st.rerun()

    with tab2:
        st.subheader("Email")
        from src.utils.config import get_settings
        cfg = get_settings().notifier.email
        st.text_input("SMTP host", cfg.smtp_host, disabled=True)
        st.text_input("Sender", cfg.sender, disabled=True)
        st.text_input("Receiver", cfg.receiver, disabled=True)
        st.caption("Edit `config/settings.yaml → notifier.email` to change SMTP settings. "
                   "Store email password via KeyStore.")

        st.subheader("WeChat Work Webhook")
        wh = get_settings().notifier.wechat_webhook
        st.text_input("Webhook URL", wh or "(not configured)", disabled=True)
        st.caption("Set `config/settings.yaml → notifier.wechat_webhook`.")

        st.subheader("Test Alert")
        if st.button("Send test alert"):
            try:
                from src.monitor.notifier import Notifier
                n = Notifier.from_settings()
                n.alert("quant_trade test", "This is a test alert from the dashboard.")
                st.success("Alert sent (if channels are configured)")
            except Exception as e:
                st.error(f"Alert failed: {e}")


# ── Page: Help ────────────────────────────────────────────────────────────────

def page_help():
    st.title("Help & Documentation")
    docs_dir = ROOT / "docs"
    doc_files = sorted(docs_dir.glob("*.md")) if docs_dir.exists() else []
    readme = ROOT / "README.md"

    options = ["README"] + [f.stem for f in doc_files]
    choice = st.selectbox("Document", options)

    if choice == "README":
        path = readme
    else:
        path = docs_dir / f"{choice}.md"

    if path.exists():
        st.markdown(path.read_text(encoding="utf-8"))
    else:
        st.info(f"{path.name} not found.")

    st.divider()
    st.subheader("Quick Command Reference")
    st.code("""
# Install / build
setup.bat                          # Windows one-click install
maturin develop --release          # (re)compile Rust extension

# Run
python launcher.py                 # Start Streamlit + FastAPI
python launcher.py --gui-only      # Streamlit only
python launcher.py --live-only     # FastAPI only (after position check)

# CLI backtest
python run_backtest.py --strategy MACrossStrategy --symbol 000001.SZ

# CLI live trading
python run_live.py --gateway paper --strategy MACrossStrategy

# Tests
pytest tests/ -v

# Windows service
python scripts/install_service.py --install
python scripts/scheduler_setup.py --install
""", language="bash")


# ── Router ────────────────────────────────────────────────────────────────────

if page == "Home":
    page_home()
elif page == "Data":
    page_data()
elif page == "Strategies":
    page_strategies()
elif page == "Backtest":
    page_backtest()
elif page == "Live Trading":
    page_live()
elif page == "Risk":
    page_risk()
elif page == "Logs":
    page_logs()
elif page == "Help":
    page_help()
