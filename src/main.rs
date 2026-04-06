use eframe::egui;
use serde::{Deserialize, Serialize};
use std::sync::{Arc, Mutex};
use tokio::sync::broadcast;
use axum::{
    extract::State,
    routing::post,
    Json, Router,
};
use tower_http::cors::CorsLayer;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum AgentState {
    Idle,
    Listening,
    Speaking,
    Thinking,
    Typing,
    Searching,
    Calculating,
    Fixing,
    Success,
    Error,
    Alert,
    Sleeping,
}

impl AgentState {
    fn all() -> Vec<AgentState> {
        vec![
            AgentState::Idle,
            AgentState::Listening,
            AgentState::Speaking,
            AgentState::Thinking,
            AgentState::Typing,
            AgentState::Searching,
            AgentState::Calculating,
            AgentState::Fixing,
            AgentState::Success,
            AgentState::Error,
            AgentState::Alert,
            AgentState::Sleeping,
        ]
    }

    fn to_uv_rect(&self) -> egui::Rect {
        let index = match self {
            AgentState::Idle => 0,
            AgentState::Listening => 1,
            AgentState::Speaking => 2,
            AgentState::Thinking => 3,
            AgentState::Typing => 4,
            AgentState::Searching => 5,
            AgentState::Calculating => 6,
            AgentState::Fixing => 7,
            AgentState::Success => 8,
            AgentState::Error => 9,
            AgentState::Alert => 10,
            AgentState::Sleeping => 11,
        };

        let col = (index % 4) as f32;
        let row = (index / 4) as f32;
        let w = 1.0 / 4.0;
        let h = 1.0 / 3.0;

        egui::Rect::from_min_max(
            egui::pos2(col * w, row * h),
            egui::pos2((col + 1.0) * w, (row + 1.0) * h),
        )
    }
}

#[derive(Debug, Deserialize)]
struct StateRequest {
    state: AgentState,
}

struct AppSharedState {
    current_state: Arc<Mutex<AgentState>>,
    repaint_signal: broadcast::Sender<()>,
}

#[tokio::main]
async fn main() -> Result<(), eframe::Error> {
    // Setup tracing for debugging
    tracing_subscriber::fmt::init();

    // Shared state between Axum and egui
    let current_state = Arc::new(Mutex::new(AgentState::Idle));
    // Broadcast channel to signal egui to repaint when state changes
    let (tx, _) = broadcast::channel(10);

    let shared = Arc::new(AppSharedState {
        current_state: current_state.clone(),
        repaint_signal: tx.clone(),
    });

    // Spawn Background HTTP Server
    let server_shared = shared.clone();
    tokio::spawn(async move {
        let app = Router::new()
            .route("/state", post(update_state_handler))
            .layer(CorsLayer::permissive())
            .with_state(server_shared);

        let listener = tokio::net::TcpListener::bind("0.0.0.0:8000").await.unwrap();
        println!("Server listening on http://0.0.0.0:8000/state");
        axum::serve(listener, app).await.unwrap();
    });

    // Run egui
    let options = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default()
            .with_inner_size([600.0, 500.0])
            .with_title("Waifu Display")
            .with_transparent(false),
        ..Default::default()
    };

    eframe::run_native(
        "Waifu Display",
        options,
        Box::new(move |cc| {
            // Install image loaders for PNG support
            egui_extras::install_image_loaders(&cc.egui_ctx);
            
            let mut rx = tx.subscribe();
            let ctx = cc.egui_ctx.clone();
            
            // Listen for repaint signals in a background thread
            tokio::spawn(async move {
                while rx.recv().await.is_ok() {
                    ctx.request_repaint();
                }
            });

            Box::new(WaifuApp {
                state: current_state,
                show_debug: true,
            })
        }),
    )
}

async fn update_state_handler(
    State(shared): State<Arc<AppSharedState>>,
    Json(payload): Json<StateRequest>,
) -> &'static str {
    let mut state = shared.current_state.lock().unwrap();
    *state = payload.state;
    let _ = shared.repaint_signal.send(());
    println!("State updated to: {:?}", payload.state);
    "OK"
}

struct WaifuApp {
    state: Arc<Mutex<AgentState>>,
    show_debug: bool,
}

impl eframe::App for WaifuApp {
    fn update(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        let current_agent_state = *self.state.lock().unwrap();

        egui::CentralPanel::default().show(ctx, |ui| {
            ui.vertical_centered(|ui| {
                ui.add_space(20.0);
                ui.heading("Waifu Display");
                
                // Display the image
                let image_size = ui.available_size() * 0.8;
                let uv = current_agent_state.to_uv_rect();

                // Load the texture from assets/waifu.png
                let image = egui::Image::new(egui::include_image!("../assets/waifu.png"))
                    .uv(uv)
                    .fit_to_exact_size(image_size);

                ui.add(image);
                
                ui.add_space(10.0);
                ui.label(format!("Current State: {:?}", current_agent_state));

                // Debug UI
                if self.show_debug {
                    ui.separator();
                    ui.horizontal(|ui| {
                        ui.label("Manual Test:");
                        egui::ComboBox::from_id_source("state_selector")
                            .selected_text(format!("{:?}", current_agent_state))
                            .show_ui(ui, |ui| {
                                for s in AgentState::all() {
                                    let mut temp_state = current_agent_state;
                                    if ui.selectable_value(&mut temp_state, s, format!("{:?}", s)).clicked() {
                                        let mut state_lock = self.state.lock().unwrap();
                                        *state_lock = s;
                                    }
                                }
                            });
                    });
                }
            });
        });
    }
}
