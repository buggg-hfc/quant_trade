use crossbeam::channel::{self, Receiver, Sender};
use pyo3::prelude::*;
use std::collections::HashMap;
use std::sync::{Arc, RwLock};
use std::thread;

use crate::object::Bar;

#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub enum EventType {
    Bar,
    Tick,
    Order,
    Trade,
    Position,
    Account,
    Timer,
}

pub enum EventData {
    Bar(Bar),
    Raw(Vec<u8>),
}

pub struct Event {
    pub event_type: EventType,
    pub data: EventData,
}

type HandlerFn = Arc<dyn Fn(&Event) + Send + Sync>;

#[pyclass]
pub struct EventEngine {
    sender: Sender<Event>,
    receiver: Arc<Receiver<Event>>,
    handlers: Arc<RwLock<HashMap<EventType, Vec<HandlerFn>>>>,
    running: Arc<std::sync::atomic::AtomicBool>,
}

#[pymethods]
impl EventEngine {
    #[new]
    pub fn new() -> Self {
        let (sender, receiver) = channel::unbounded();
        EventEngine {
            sender,
            receiver: Arc::new(receiver),
            handlers: Arc::new(RwLock::new(HashMap::new())),
            running: Arc::new(std::sync::atomic::AtomicBool::new(false)),
        }
    }

    pub fn start(&self) {
        self.running.store(true, std::sync::atomic::Ordering::SeqCst);
        let receiver = Arc::clone(&self.receiver);
        let handlers = Arc::clone(&self.handlers);
        let running = Arc::clone(&self.running);

        thread::spawn(move || {
            while running.load(std::sync::atomic::Ordering::SeqCst) {
                match receiver.recv_timeout(std::time::Duration::from_millis(100)) {
                    Ok(event) => {
                        let map = handlers.read().unwrap();
                        if let Some(fns) = map.get(&event.event_type) {
                            for f in fns {
                                f(&event);
                            }
                        }
                    }
                    Err(_) => {}
                }
            }
        });
    }

    pub fn stop(&self) {
        self.running.store(false, std::sync::atomic::Ordering::SeqCst);
    }

    pub fn put_bar(&self, bar: Bar) -> PyResult<()> {
        self.sender
            .send(Event { event_type: EventType::Bar, data: EventData::Bar(bar) })
            .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))
    }
}
