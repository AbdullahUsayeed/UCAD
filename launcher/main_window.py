"""UCAD Assistant Launcher — main window with settings, diagnostics, and launch.

This is the primary user interface. It:
  • Detects / manages the FreeCAD installation
  • Configures API providers, models, and settings
  • Runs pre-launch diagnostics
  • Launches FreeCAD with the UCAD Mod loaded
"""
import json
import os
import sys
import threading
from pathlib import Path

# Ensure launcher package is importable (critical for PyInstaller frozen builds)
_LAUNCHER_DIR = os.path.dirname(os.path.abspath(__file__))
_PARENT_DIR = os.path.dirname(_LAUNCHER_DIR)
if _PARENT_DIR not in sys.path:
    sys.path.insert(0, _PARENT_DIR)

import launcher.paths as paths  # noqa: E402
from launcher.config_manager import load_config, save_config, get_secret, set_secret, delete_secret  # noqa: E402
from launcher.runtime_manager import RuntimeManager  # noqa: E402
from launcher.diagnostics import run_diagnostics  # noqa: E402


try:
    from PySide6 import QtWidgets, QtCore, QtGui
except ImportError:
    from PySide2 import QtWidgets, QtCore, QtGui


# ── Styles ─────────────────────────────────────────────────

DARK_STYLE = """
QWidget { background:#0d1625; color:#e6edf3; font-family: 'Segoe UI', sans-serif; }
QLabel { color:#c8d6e8; font-size:13px; }
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit {
    background:#121c2c; color:#e8f0f9; border:1px solid #2e3e56;
    border-radius:6px; padding:6px 10px; font-size:13px;
}
QLineEdit:focus, QComboBox:focus { border-color:#63a5ff; }
QPushButton {
    background:#1e3a5f; color:#e6f0fc; border:none;
    border-radius:8px; padding:8px 24px; font-size:13px; font-weight:600;
}
QPushButton:hover { background:#2a4d7a; }
QPushButton#launchBtn {
    background:#0078d4; font-size:15px; padding:12px 32px;
}
QPushButton#launchBtn:hover { background:#1a8ae8; }
QPushButton:pressed { background:#005a9e; }
QTabWidget::pane { border:1px solid #2e3e56; border-radius:6px; background:#0d1625; }
QTabBar::tab { background:#121c2c; color:#8b9bb5; padding:8px 18px; margin-right:2px; border-radius:4px 4px 0 0; }
QTabBar::tab:selected { background:#1e3a5f; color:#e6f0fc; }
QGroupBox { border:1px solid #2e3e56; border-radius:6px; margin-top:12px; padding:16px 12px 12px; font-weight:600; }
QGroupBox::title { subcontrol-origin:margin; left:12px; padding:0 6px; }
QProgressBar { border:1px solid #2e3e56; border-radius:4px; text-align:center; background:#121c2c; }
QProgressBar::chunk { background:#0078d4; border-radius:3px; }
QCheckBox { color:#c8d6e8; spacing:8px; }
QCheckBox::indicator { width:16px; height:16px; border-radius:3px;
    border:1px solid #2e3e56; background:#121c2c; }
QCheckBox::indicator:checked { background:#0078d4; border-color:#0078d4; }
QListWidget { background:#121c2c; border:1px solid #2e3e56; border-radius:6px; }
QTextEdit { background:#0a1018; color:#c8d6e8; border:1px solid #2e3e56; border-radius:6px; font-family: 'Cascadia Code', 'Consolas', monospace; font-size:12px; }
"""


# ── Provider presets (mirrors orchestrator/providers.py) ──

PRESET_MODELS = [
    ("[Anthropic] Claude Opus 4", "anthropic", "anthropic/claude-opus-4-20250514"),
    ("[Anthropic] Claude Sonnet 5", "anthropic", "anthropic/claude-sonnet-5-20250514"),
    ("[DeepSeek] DeepSeek Chat", "deepseek", "deepseek/deepseek-chat"),
    ("[OpenAI] GPT-4o", "openai", "openai/gpt-4o"),
    ("[OpenAI] GPT-4o-mini", "openai", "openai/gpt-4o-mini"),
    ("[Google] Gemini 2.5 Pro", "google", "gemini/gemini-2.5-pro-exp-03-25"),
    ("[xAI] Grok 3", "xai", "xai/grok-3-beta"),
    ("[Mistral] Mistral Large", "mistral", "mistral/mistral-large-latest"),
    ("[Local] Ollama", "ollama", ""),
]


class LauncherWindow(QtWidgets.QMainWindow):
    """Main launcher window."""

    def __init__(self):
        super().__init__()
        self._rm = RuntimeManager()
        self._config = load_config()
        self._freecad_found = False
        self._diagnostics_result = None

        self.setWindowTitle("UCAD Assistant")
        self.setMinimumSize(680, 520)
        self.setStyleSheet(DARK_STYLE)

        self._build_ui()
        self._load_config_into_ui()

        # Detect FreeCAD in background
        QtCore.QTimer.singleShot(100, self._detect_freecad)

    def _build_ui(self):
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QVBoxLayout(central)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # ── Header ──
        header = QtWidgets.QLabel("<h1>UCAD Assistant</h1><p style='color:#8b9bb5;'>AI-powered CAD design for FreeCAD</p>")
        layout.addWidget(header)

        # ── FreeCAD status bar ──
        self._status_frame = QtWidgets.QFrame()
        self._status_frame.setStyleSheet("QFrame { background:#121c2c; border:1px solid #2e3e56; border-radius:8px; padding:8px 12px; }")
        status_layout = QtWidgets.QHBoxLayout(self._status_frame)
        status_layout.setContentsMargins(12, 8, 12, 8)

        self._status_icon = QtWidgets.QLabel("⏳")
        self._status_icon.setStyleSheet("font-size:18px;")
        self._status_text = QtWidgets.QLabel("Detecting FreeCAD...")
        self._status_text.setStyleSheet("font-size:13px;")
        self._fc_version = QtWidgets.QLabel("")
        self._fc_version.setStyleSheet("color:#8b9bb5; font-size:12px;")

        status_layout.addWidget(self._status_icon)
        status_layout.addWidget(self._status_text, 1)
        status_layout.addWidget(self._fc_version)
        layout.addWidget(self._status_frame)

        # ── Tabs ──
        self._tabs = QtWidgets.QTabWidget()
        layout.addWidget(self._tabs, 1)

        # Tab 1: Launch
        self._launch_tab = self._build_launch_tab()
        self._tabs.addTab(self._launch_tab, "Launch")

        # Tab 2: Settings
        self._settings_tab = self._build_settings_tab()
        self._tabs.addTab(self._settings_tab, "Settings")

        # Tab 3: Diagnostics
        self._diag_tab = self._build_diagnostics_tab()
        self._tabs.addTab(self._diag_tab, "Diagnostics")

    # ── Launch Tab ────────────────────────────────────────

    def _build_launch_tab(self):
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)
        layout.setSpacing(16)

        # Launch button (big, centered)
        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.addStretch()
        self._launch_btn = QtWidgets.QPushButton("🚀  LAUNCH UCAD ASSISTANT")
        self._launch_btn.setObjectName("launchBtn")
        self._launch_btn.setMinimumHeight(52)
        self._launch_btn.setMinimumWidth(320)
        self._launch_btn.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.PointingHandCursor))
        self._launch_btn.clicked.connect(self._on_launch)
        self._launch_btn.setEnabled(False)
        btn_layout.addWidget(self._launch_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # Quick status
        self._quick_status = QtWidgets.QLabel("Waiting for FreeCAD detection...")
        self._quick_status.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self._quick_status.setStyleSheet("color:#8b9bb5; font-size:12px;")
        layout.addWidget(self._quick_status)

        # Provider summary
        self._summary_group = QtWidgets.QGroupBox("Current Configuration")
        summary_layout = QtWidgets.QFormLayout(self._summary_group)
        self._summary_provider = QtWidgets.QLabel("—")
        self._summary_model = QtWidgets.QLabel("—")
        self._summary_api = QtWidgets.QLabel("—")
        summary_layout.addRow("Provider:", self._summary_provider)
        summary_layout.addRow("Model:", self._summary_model)
        summary_layout.addRow("API Key:", self._summary_api)
        layout.addWidget(self._summary_group)

        layout.addStretch()
        return tab

    # ── Settings Tab ──────────────────────────────────────

    def _build_settings_tab(self):
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)
        layout.setSpacing(8)

        # ── Provider ──
        prov_group = QtWidgets.QGroupBox("AI Provider")
        prov_layout = QtWidgets.QFormLayout(prov_group)

        self._provider_combo = QtWidgets.QComboBox()
        self._provider_combo.addItems([
            "anthropic", "deepseek", "openai", "google",
            "xai", "mistral", "cohere", "perplexity",
            "groq", "openrouter", "together", "fireworks",
            "github", "moonshot", "ollama",
        ])
        self._provider_combo.currentTextChanged.connect(self._on_provider_changed)
        prov_layout.addRow("Provider:", self._provider_combo)

        self._model_combo = QtWidgets.QComboBox()
        self._model_combo.setEditable(True)
        prov_layout.addRow("Model:", self._model_combo)

        self._api_key_input = QtWidgets.QLineEdit()
        self._api_key_input.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        self._api_key_input.setPlaceholderText("Enter your API key...")
        prov_layout.addRow("API Key:", self._api_key_input)

        layout.addWidget(prov_group)

        # ── Connection ──
        conn_group = QtWidgets.QGroupBox("Connection")
        conn_layout = QtWidgets.QFormLayout(conn_group)
        self._url_input = QtWidgets.QLineEdit()
        self._url_input.setPlaceholderText("Custom API URL (optional)")
        conn_layout.addRow("API URL:", self._url_input)

        self._proxy_input = QtWidgets.QLineEdit()
        self._proxy_input.setPlaceholderText("http://proxy:port (optional)")
        conn_layout.addRow("Proxy:", self._proxy_input)

        self._ollama_url_input = QtWidgets.QLineEdit()
        self._ollama_url_input.setPlaceholderText("http://localhost:11434")
        conn_layout.addRow("Ollama URL:", self._ollama_url_input)

        layout.addWidget(conn_group)

        # ── General ──
        gen_group = QtWidgets.QGroupBox("General")
        gen_layout = QtWidgets.QFormLayout(gen_group)

        self._theme_combo = QtWidgets.QComboBox()
        self._theme_combo.addItems(["dark", "light"])
        gen_layout.addRow("Theme:", self._theme_combo)

        self._temp_spin = QtWidgets.QDoubleSpinBox()
        self._temp_spin.setRange(0.0, 2.0)
        self._temp_spin.setSingleStep(0.1)
        gen_layout.addRow("Temperature:", self._temp_spin)

        self._tokens_spin = QtWidgets.QSpinBox()
        self._tokens_spin.setRange(1024, 131072)
        self._tokens_spin.setSingleStep(1024)
        gen_layout.addRow("Max Tokens:", self._tokens_spin)

        self._retries_spin = QtWidgets.QSpinBox()
        self._retries_spin.setRange(0, 20)
        gen_layout.addRow("Retries per step:", self._retries_spin)

        self._mode_combo = QtWidgets.QComboBox()
        self._mode_combo.addItems(["build", "code"])
        gen_layout.addRow("Mode:", self._mode_combo)

        layout.addWidget(gen_group)

        # ── Save ──
        save_btn = QtWidgets.QPushButton("Save Settings")
        save_btn.clicked.connect(self._on_save_settings)
        layout.addWidget(save_btn)

        layout.addStretch()
        return tab

    # ── Diagnostics Tab ───────────────────────────────────

    def _build_diagnostics_tab(self):
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)
        layout.setSpacing(12)

        # Controls
        ctrl_layout = QtWidgets.QHBoxLayout()
        self._run_diag_btn = QtWidgets.QPushButton("Run Diagnostics")
        self._run_diag_btn.clicked.connect(self._on_run_diagnostics)
        ctrl_layout.addWidget(self._run_diag_btn)

        self._copy_diag_btn = QtWidgets.QPushButton("Copy to Clipboard")
        self._copy_diag_btn.clicked.connect(self._on_copy_diagnostics)
        self._copy_diag_btn.setEnabled(False)
        ctrl_layout.addWidget(self._copy_diag_btn)

        ctrl_layout.addStretch()
        layout.addLayout(ctrl_layout)

        # Results
        self._diag_output = QtWidgets.QTextEdit()
        self._diag_output.setReadOnly(True)
        layout.addWidget(self._diag_output, 1)

        return tab

    # ── FreeCAD Detection ─────────────────────────────────

    def _detect_freecad(self):
        exe = self._rm.find_freecad()
        if exe:
            self._freecad_found = True
            self._status_icon.setText("✅")
            self._status_text.setText(f"FreeCAD ready")
            self._fc_version.setText(f"v{self._rm.version_str} at {exe.parent}")
            self._launch_btn.setEnabled(True)
            self._quick_status.setText("Ready to launch")
        else:
            self._freecad_found = False
            self._status_icon.setText("⚠️")
            self._status_text.setText("FreeCAD not found")
            self._fc_version.setText("")

            # Offer to download
            reply = QtWidgets.QMessageBox.question(
                self, "FreeCAD Not Found",
                "FreeCAD is not installed. Would you like to download it?\n\n"
                f"This will download ~400 MB from GitHub.",
                QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
            )
            if reply == QtWidgets.QMessageBox.StandardButton.Yes:
                self._download_freecad()

    def _download_freecad(self):
        self._status_icon.setText("⏳")
        self._status_text.setText("Downloading FreeCAD...")
        self._quick_status.setText("Downloading FreeCAD (this may take a few minutes)...")
        self._launch_btn.setEnabled(False)

        # Progress bar
        self._progress = QtWidgets.QProgressBar()
        self._status_frame.layout().addWidget(self._progress)

        def on_progress(frac):
            self._progress.setValue(int(frac * 100))

        def done():
            exe = self._rm.download_freecad(on_progress=on_progress)
            if exe:
                self._freecad_found = True
                self._status_icon.setText("✅")
                self._status_text.setText("FreeCAD ready")
                self._fc_version.setText(f"v{self._rm.version_str}")
                self._launch_btn.setEnabled(True)
                self._quick_status.setText("Ready to launch")
            else:
                self._status_icon.setText("❌")
                self._status_text.setText("Download failed")
            self._progress.hide()

        threading.Thread(target=done, daemon=True).start()

    # ── Launch ────────────────────────────────────────────

    def _on_launch(self):
        issues = self._rm.validate()
        if issues:
            qm = QtWidgets.QMessageBox(self)
            qm.setWindowTitle("Validation Issues")
            qm.setText("The following issues were found:")
            qm.setInformativeText("\n".join(f"• {i}" for i in issues))
            qm.setStandardButtons(
                QtWidgets.QMessageBox.StandardButton.Launch |
                QtWidgets.QMessageBox.StandardButton.Cancel
            )
            qm.button(QtWidgets.QMessageBox.StandardButton.Launch).setText("Launch Anyway")
            if qm.exec() != QtWidgets.QMessageBox.StandardButton.Launch:
                return

        proc = self._rm.launch()
        if proc:
            self._quick_status.setText("FreeCAD launched! The UCAD workbench will activate automatically.")
            # Minimize launcher to system tray / hide
            self.showMinimized()
            # Wait then close
            def _wait_and_close():
                proc.wait()
                QtCore.QMetaObject.invokeMethod(self, "close", QtCore.Qt.ConnectionType.QueuedConnection)
            threading.Thread(target=_wait_and_close, daemon=True).start()
        else:
            QtWidgets.QMessageBox.critical(self, "Launch Failed", "Could not launch FreeCAD.")

    # ── Settings ──────────────────────────────────────────

    def _load_config_into_ui(self):
        cfg = self._config
        self._provider_combo.setCurrentText(cfg.get("provider", "deepseek"))
        self._url_input.setText(cfg.get("url", ""))
        self._proxy_input.setText(cfg.get("proxy_url", ""))
        self._ollama_url_input.setText(cfg.get("ollama_url", "http://localhost:11434"))
        self._theme_combo.setCurrentText(cfg.get("theme", "dark"))
        self._temp_spin.setValue(cfg.get("temperature", 0.49))
        self._tokens_spin.setValue(cfg.get("max_tokens", 16384) or 16384)
        self._retries_spin.setValue(cfg.get("retries_per_step", 5))
        self._mode_combo.setCurrentText(cfg.get("mode", "build"))

        # Load API key from secrets
        api_key = get_secret("api_key")
        if api_key:
            self._api_key_input.setText(api_key)

        self._on_provider_changed(cfg.get("provider", "deepseek"))
        self._update_summary()

    def _on_provider_changed(self, provider: str):
        self._model_combo.clear()
        is_ollama = provider == "ollama"
        self._model_combo.setVisible(not is_ollama or True)
        self._api_key_input.setVisible(not is_ollama)
        self._url_input.setVisible(not is_ollama)
        self._ollama_url_input.setVisible(is_ollama)

        if is_ollama:
            self._model_combo.addItem("local")
            self._model_combo.setCurrentText("local")
        else:
            for label, prov, model_id in PRESET_MODELS:
                if prov == provider:
                    self._model_combo.addItem(label, model_id)
            if self._config.get("model"):
                idx = self._model_combo.findText(self._config.get("model_label", ""))
                if idx >= 0:
                    self._model_combo.setCurrentIndex(idx)

    def _on_save_settings(self):
        provider = self._provider_combo.currentText()
        model_data = self._model_combo.currentData()
        model_label = self._model_combo.currentText()
        api_key = self._api_key_input.text()

        cfg = {
            "provider": provider,
            "model": model_data or model_label,
            "model_label": model_label,
            "url": self._url_input.text(),
            "proxy_url": self._proxy_input.text(),
            "ollama_url": self._ollama_url_input.text(),
            "theme": self._theme_combo.currentText(),
            "temperature": self._temp_spin.value(),
            "max_tokens": self._tokens_spin.value(),
            "retries_per_step": self._retries_spin.value(),
            "mode": self._mode_combo.currentText(),
        }
        save_config(cfg)
        if api_key:
            set_secret("api_key", api_key)
        else:
            delete_secret("api_key")

        self._config = load_config()
        self._update_summary()

        QtWidgets.QMessageBox.information(self, "Saved", "Settings saved successfully!")

    def _update_summary(self):
        cfg = self._config
        self._summary_provider.setText(cfg.get("provider", "—"))
        self._summary_model.setText(cfg.get("model_label") or cfg.get("model", "—"))
        key = get_secret("api_key")
        self._summary_api.setText("✓ Configured" if key else "⚠ Not set")

    # ── Diagnostics ───────────────────────────────────────

    def _on_run_diagnostics(self):
        self._diag_output.setPlainText("Running diagnostics...\n")
        self._run_diag_btn.setEnabled(False)
        self._copy_diag_btn.setEnabled(False)

        def _run():
            report = run_diagnostics()
            self._diagnostics_result = report
            QtCore.QMetaObject.invokeMethod(
                self, "_show_diagnostics", QtCore.Qt.ConnectionType.QueuedConnection
            )

        threading.Thread(target=_run, daemon=True).start()

    def _show_diagnostics(self):
        report = self._diagnostics_result
        if not report:
            return
        self._diag_output.setPlainText(report.to_text())
        self._run_diag_btn.setEnabled(True)
        self._copy_diag_btn.setEnabled(True)

    def _on_copy_diagnostics(self):
        if self._diagnostics_result:
            clip = QtWidgets.QApplication.clipboard()
            clip.setText(self._diagnostics_result.to_text())
            self._copy_diag_btn.setText("Copied!")
            QtCore.QTimer.singleShot(2000, lambda: self._copy_diag_btn.setText("Copy to Clipboard"))


# ── Entry Point ────────────────────────────────────────────

def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("UCAD Assistant")
    app.setOrganizationName("USAYEED LLC")

    # Ensure directories exist
    paths.ensure_dirs()

    window = LauncherWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
