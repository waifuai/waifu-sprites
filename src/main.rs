use eframe::egui;
use serde::{Deserialize, Serialize};
use std::fs;
use std::path::PathBuf;
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

    fn to_index(&self) -> usize {
        match self {
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
        }
    }

    fn to_uv_rect(&self, frame_count: u32) -> egui::Rect {
        let index = self.to_index();
        
        // Anti-crash safeguard: ensure frames_per_row is never 0
        let frames_per_row = if frame_count == 12 { 4 } else { (frame_count as f32).sqrt() as u32 }.max(1);
        let frames_per_col = (frame_count + frames_per_row - 1) / frames_per_row;

        let col = (index % frames_per_row as usize) as f32;
        let row = (index / frames_per_row as usize) as f32;
        let w = 1.0 / frames_per_row as f32;
        let h = 1.0 / frames_per_col as f32;

        egui::Rect::from_min_max(
            egui::pos2(col * w, row * h),
            egui::pos2((col + 1.0) * w, (row + 1.0) * h),
        )
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct WaifuSet {
    pub name: String,
    pub path: PathBuf,
    pub is_directory: bool,
    pub frame_count: u32,
}

#[derive(Debug, Serialize, Deserialize)]
struct AppConfig {
    selected_waifu: String,
}

impl Default for AppConfig {
    fn default() -> Self {
        Self {
            selected_waifu: "waifu".to_string(),
        }
    }
}

fn get_config_path() -> PathBuf {
    let exe_path = std::env::current_exe().unwrap_or_default();
    let exe_dir = exe_path.parent().unwrap_or(std::path::Path::new("."));
    exe_dir.join("waifu_config.json")
}

fn load_config() -> AppConfig {
    let path = get_config_path();
    if let Ok(contents) = fs::read_to_string(&path) {
        if let Ok(config) = serde_json::from_str(&contents) {
            return config;
        }
    }
    AppConfig::default()
}

fn save_config(config: &AppConfig) {
    let path = get_config_path();
    if let Ok(json) = serde_json::to_string_pretty(config) {
        let _ = fs::write(path, json);
    }
}

fn discover_waifu_sets() -> Vec<WaifuSet> {
    let mut sets = Vec::new();
    let assets_dir = PathBuf::from("assets");

    if let Ok(entries) = fs::read_dir(&assets_dir) {
        for entry in entries.flatten() {
            let path = entry.path();
            let name = path.file_stem().unwrap_or_default().to_string_lossy().to_string();
            
            if path.is_dir() {
                let mut frame_numbers: Vec<u32> = fs::read_dir(&path)
                    .map(|entries| {
                        entries.flatten()
                            .filter(|e| e.path().extension().map_or(false, |ext| ext == "png"))
                            .filter_map(|e| {
                                let name = e.file_name().to_string_lossy().to_string();
                                name.trim_end_matches(".png").parse::<u32>().ok()
                            })
                            .collect()
                    })
                    .unwrap_or_default();
                
                frame_numbers.sort();
                let frame_count = frame_numbers.len() as u32;
                
                if frame_count > 0 {
                    sets.push(WaifuSet {
                        name,
                        path: path.clone(),
                        is_directory: true,
                        frame_count,
                    });
                }
            } else if path.extension().map_or(false, |ext| ext == "png") {
                if let Ok(metadata) = entry.metadata() {
                    if metadata.len() > 1000 {
                        sets.push(WaifuSet {
                            name,
                            path: path.clone(),
                            is_directory: false,
                            frame_count: 12,
                        });
                    }
                }
            }
        }
    }

    sets.sort_by(|a, b| a.name.cmp(&b.name));
    sets
}

#[derive(Debug, Deserialize)]
struct StateRequest {
    state: AgentState,
}

struct AppSharedState {
    current_state: Arc<Mutex<AgentState>>,
    repaint_signal: broadcast::Sender<()>,
}

// FIX: Removed #[tokio::main] to prevent the Windows resize crash
fn main() -> Result<(), eframe::Error> {
    tracing_subscriber::fmt::init();

    // Initialize Tokio runtime manually so it doesn't fight eframe for the main thread
    let rt = tokio::runtime::Runtime::new().expect("Unable to create Runtime");
    let _enter = rt.enter();

    let current_state = Arc::new(Mutex::new(AgentState::Idle));
    let (tx, _) = broadcast::channel(10);

    let shared = Arc::new(AppSharedState {
        current_state: current_state.clone(),
        repaint_signal: tx.clone(),
    });

    let server_shared = shared.clone();
    
    // Because we 'entered' the runtime, we can safely use tokio::spawn
    tokio::spawn(async move {
        let app = Router::new()
            .route("/state", post(update_state_handler))
            .layer(CorsLayer::permissive())
            .with_state(server_shared);

        let listener = tokio::net::TcpListener::bind("0.0.0.0:8000").await.unwrap();
        println!("Server listening on http://0.0.0.0:8000/state");
        axum::serve(listener, app).await.unwrap();
    });

    let config = load_config();
    let waifu_sets = discover_waifu_sets();

    let initial_waifu = config.selected_waifu.clone();
    let initial_set = waifu_sets.iter().find(|s| s.name == initial_waifu).cloned()
        .or_else(|| waifu_sets.first().cloned())
        .unwrap_or_else(|| waifu_sets[0].clone());

    let options = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default()
            .with_inner_size([600.0, 550.0])
            .with_title("Waifu Display")
            .with_transparent(false),
        ..Default::default()
    };

    eframe::run_native(
        "Waifu Display",
        options,
        Box::new(move |cc| {
            egui_extras::install_image_loaders(&cc.egui_ctx);
            
            let mut rx = tx.subscribe();
            let ctx = cc.egui_ctx.clone();
            
            tokio::spawn(async move {
                while rx.recv().await.is_ok() {
                    ctx.request_repaint();
                }
            });

            Box::new(WaifuApp {
                state: current_state,
                waifu_sets: waifu_sets.clone(),
                current_set: initial_set,
                show_debug: true,
            })
        })
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
    waifu_sets: Vec<WaifuSet>,
    current_set: WaifuSet,
    show_debug: bool,
}

impl eframe::App for WaifuApp {
    fn update(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        let current_agent_state = *self.state.lock().unwrap();

        // 1. TOP PANEL: Title and Waifu Selector
        egui::TopBottomPanel::top("top_panel").show(ctx, |ui| {
            ui.vertical_centered(|ui| {
                ui.add_space(10.0);
                ui.heading("Waifu Display");
                ui.add_space(5.0);
            });
            
            ui.horizontal(|ui| {
                ui.add_space(10.0);
                ui.label("Waifu:");
                egui::ComboBox::from_id_source("waifu_selector")
                    .selected_text(&self.current_set.name)
                    .show_ui(ui, |ui| {
                        for set in &self.waifu_sets {
                            let label = if set.is_directory {
                                format!("{} ({} frames)", set.name, set.frame_count)
                            } else {
                                set.name.clone()
                            };
                            
                            if ui.selectable_value(&mut self.current_set, set.clone(), &label).clicked() {
                                let config = AppConfig {
                                    selected_waifu: set.name.clone(),
                                };
                                save_config(&config);
                            }
                        }
                    });
            });
            ui.add_space(10.0);
        });

        // 2. BOTTOM PANEL: State Label and Debug controls
        egui::TopBottomPanel::bottom("bottom_panel").show(ctx, |ui| {
            ui.add_space(10.0);
            ui.vertical_centered(|ui| {
                ui.label(format!("State: {:?} ({}/{})", current_agent_state, current_agent_state.to_index() + 1, self.current_set.frame_count));
            });

            if self.show_debug {
                ui.separator();
                ui.horizontal(|ui| {
                    ui.add_space(10.0);
                    ui.label("State:");
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
            ui.add_space(10.0);
        });

        // 3. CENTRAL PANEL: Image space
        // CentralPanel automatically fills whatever space is left between the Top and Bottom panels.
        egui::CentralPanel::default().show(ctx, |ui| {
            let uv = current_agent_state.to_uv_rect(self.current_set.frame_count);

            let image = if self.current_set.is_directory {
                let frame_index = current_agent_state.to_index() + 1;
                let frame_path = self.current_set.path.join(format!("{}.png", frame_index));
                
                if frame_path.exists() {
                    let frame_str = format!("file://{}", frame_path.display()); 
                    Some(egui::Image::new(frame_str))
                } else {
                    let fallback_path = PathBuf::from("assets").join(&self.current_set.name).join("1.png");
                    if fallback_path.exists() {
                        let fallback_str = format!("file://{}", fallback_path.display());
                        Some(egui::Image::new(fallback_str))
                    } else {
                        None
                    }
                }
            } else {
                let file_str = format!("file://{}", self.current_set.path.display());
                Some(egui::Image::new(file_str).uv(uv))
            };

            let image_widget = image.unwrap_or_else(|| {
                let fallback_path = PathBuf::from("assets").join(&self.current_set.name).join("1.png");
                let fallback_str = format!("file://{}", fallback_path.display());
                egui::Image::new(fallback_str).uv(uv)
            });

            // This perfectly centers the image and scales it up/down to take exactly the available space
            // without stretching the character's face/body (maintains aspect ratio).
            ui.centered_and_justified(|ui| {
                ui.add(image_widget.fit_to_exact_size(ui.available_size()).maintain_aspect_ratio(true));
            });
        });
    }
}