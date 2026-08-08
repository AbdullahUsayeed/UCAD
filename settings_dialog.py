"""General AI Companion settings — retries, local LLM, theme, advanced options."""
import json
import os
from compat import QtWidgets, QtCore, QtGui, Qt
from secret_store import load_json_file
from orchestrator.providers import _provider_tuning
from telemetry import has_consent, record_consent

SETTINGS_KEYS = [
    "retries_per_step", "auto_replan", "sandbox_mode", "max_defer_attempts",
    "theme", "chat_font_size", "code_font_size",
    "temperature", "max_history_length", "max_tokens",
]

DEFAULT_SETTINGS = {
    "retries_per_step": 5,
    "auto_replan": False,
    "sandbox_mode": True,
    "max_defer_attempts": 15,
    "theme": "dark",
    "chat_font_size": 13,
    "code_font_size": 12,
    "temperature": 0.7,
    "max_history_length": 50,
    "max_tokens": 16384,
}


def load_settings(cfg):
    return {k: cfg.get(k, DEFAULT_SETTINGS[k]) for k in SETTINGS_KEYS}


def _section(title):
    lbl = QtWidgets.QLabel(f"<b>{title}</b>")
    lbl.setStyleSheet("font-size:12px;color:#00f0ff;padding-top:8px;")
    return lbl


def show_settings_dialog(sidebar):
    d = QtWidgets.QDialog(sidebar)
    d.setWindowTitle("\u2699 UCAD Assistant Settings")
    d.setMinimumWidth(520)

    # Detect current provider for per-provider default hints
    _current_prov = getattr(sidebar, '_current_provider', lambda: "deepseek")()
    _prov_tuning = _provider_tuning(_current_prov)
    _prov_default_temp = _prov_tuning["temperature"]
    _prov_default_tokens = _prov_tuning["max_tokens"] or 0
    d.setStyleSheet("""
        QDialog { background:#0d1625; color:#e6edf3; }
        QLabel { color:#c8d6e8; font-size:12px; }
        QLineEdit, QSpinBox, QDoubleSpinBox {
            background:#121c2c; color:#e8f0f9; border:1px solid #2e3e56;
            border-radius:6px; padding:6px 10px; font-size:12px;
        }
        QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus { border-color:#63a5ff; }
        QCheckBox { color:#c8d6e8; font-size:12px; spacing:8px; }
        QCheckBox::indicator { width:16px; height:16px; border-radius:3px;
            border:1px solid #2e3e56; background:#121c2c; }
        QCheckBox::indicator:checked { background:#00f0ff; border-color:#00f0ff; }
        QComboBox {
            background:#121c2c; color:#e8f0f9; border:1px solid #2e3e56;
            border-radius:6px; padding:4px 8px; font-size:12px;
        }
        QComboBox:hover { border-color:#63a5ff; }
        QComboBox::drop-down { border:none; width:16px; }
        QSlider::groove:horizontal { height:4px; background:#2e3e56; border-radius:2px; }
        QSlider::handle:horizontal { background:#00f0ff; width:14px; height:14px;
            margin:-5px 0; border-radius:7px; }
        QSlider::sub-page:horizontal { background:#00f0ff; border-radius:2px; }
        QPushButton {
            background:#1e3a5f; color:#e6f0fc; border:none;
            border-radius:8px; padding:8px 24px; font-size:12px; font-weight:600;
        }
        QPushButton:hover { background:#2a4d7a; }
    """)

    l = QtWidgets.QVBoxLayout(d)
    l.setSpacing(6)

    title = QtWidgets.QLabel("<b>\u2699 Settings</b>")
    title.setStyleSheet("font-size:14px;color:#e6edf3;")
    l.addWidget(title)

    # Read current config
    p = os.path.join(os.path.dirname(__file__), "config.json")
    cfg = load_json_file(p)
    s = {}
    for k in SETTINGS_KEYS:
        v = cfg.get(k)
        s[k] = v if v is not None else DEFAULT_SETTINGS[k]

    # ── BEHAVIOR ────────────────────────────────────────────
    l.addWidget(_section("\U0001f504 Behavior"))

    r1 = QtWidgets.QHBoxLayout()
    r1.setSpacing(8)
    retry_spin = QtWidgets.QSpinBox()
    retry_spin.setRange(1, 20)
    retry_spin.setValue(int(s["retries_per_step"]))
    retry_spin.setFixedWidth(80)
    r1.addWidget(QtWidgets.QLabel("Retries per step:"))
    r1.addWidget(retry_spin)
    r1.addWidget(QtWidgets.QLabel("(how many times AI retries on error)"))
    r1.addStretch()
    l.addLayout(r1)

    auto_replan_cb = QtWidgets.QCheckBox("Auto-replan on persistent failure")
    auto_replan_cb.setChecked(bool(s["auto_replan"]))
    l.addWidget(auto_replan_cb)

    sandbox_cb = QtWidgets.QCheckBox("Sandbox mode (run code in subprocess)")
    sandbox_cb.setChecked(bool(s["sandbox_mode"]))
    l.addWidget(sandbox_cb)

    telemetry_cb = QtWidgets.QCheckBox(
        "Share anonymous usage statistics to improve UCAD Assistant"
    )
    telemetry_cb.setChecked(has_consent() is True)
    telemetry_cb.setToolTip(
        "Sends anonymized CAD commands and AI-generated scripts to our server "
        "to train better models. No document or personal data is collected."
    )
    l.addWidget(telemetry_cb)

    r2 = QtWidgets.QHBoxLayout()
    r2.setSpacing(8)
    defer_spin = QtWidgets.QSpinBox()
    defer_spin.setRange(1, 100)
    defer_spin.setValue(int(s["max_defer_attempts"]))
    defer_spin.setFixedWidth(80)
    r2.addWidget(QtWidgets.QLabel("Max defer attempts:"))
    r2.addWidget(defer_spin)
    r2.addWidget(QtWidgets.QLabel("(retry scheduling attempts)"))
    r2.addStretch()
    l.addLayout(r2)

    # ── APPEARANCE ──────────────────────────────────────────
    l.addWidget(_section("\U0001f3a8 Appearance"))

    r5 = QtWidgets.QHBoxLayout()
    r5.setSpacing(8)
    theme_combo = QtWidgets.QComboBox()
    theme_combo.addItem("Dark Glass", "dark")
    theme_combo.addItem("Light", "light")
    idx = theme_combo.findData(s.get("theme", "dark"))
    theme_combo.setCurrentIndex(idx if idx >= 0 else 0)
    r5.addWidget(QtWidgets.QLabel("Theme:"))
    r5.addWidget(theme_combo)
    r5.addStretch()
    l.addLayout(r5)

    r6 = QtWidgets.QHBoxLayout()
    r6.setSpacing(8)
    chat_font_spin = QtWidgets.QSpinBox()
    chat_font_spin.setRange(8, 24)
    chat_font_spin.setValue(int(s["chat_font_size"]))
    chat_font_spin.setFixedWidth(70)
    r6.addWidget(QtWidgets.QLabel("Chat font size:"))
    r6.addWidget(chat_font_spin)
    r6.addStretch()
    l.addLayout(r6)

    r7 = QtWidgets.QHBoxLayout()
    r7.setSpacing(8)
    code_font_spin = QtWidgets.QSpinBox()
    code_font_spin.setRange(8, 24)
    code_font_spin.setValue(int(s["code_font_size"]))
    code_font_spin.setFixedWidth(70)
    r7.addWidget(QtWidgets.QLabel("Code font size:"))
    r7.addWidget(code_font_spin)
    r7.addStretch()
    l.addLayout(r7)

    # ── ADVANCED ────────────────────────────────────────────
    l.addWidget(_section("\U0001f9ea Advanced"))

    temp_hint = QtWidgets.QLabel(f"(Provider default: {_prov_default_temp:.1f})")
    temp_hint.setStyleSheet("font-size:10px; color:#888;")
    r8 = QtWidgets.QHBoxLayout()
    r8.setSpacing(8)
    temp_slider = QtWidgets.QSlider(Qt.Horizontal)
    temp_slider.setRange(0, 200)
    temp_slider.setValue(int(float(s["temperature"]) * 100))
    temp_label = QtWidgets.QLabel(f"{float(s['temperature']):.1f}")
    temp_label.setFixedWidth(30)
    temp_slider.valueChanged.connect(lambda v: temp_label.setText(f"{v / 100:.1f}"))
    r8.addWidget(QtWidgets.QLabel("AI Temperature:"))
    r8.addWidget(temp_slider, 1)
    r8.addWidget(temp_label)
    r8.addWidget(temp_hint)
    l.addLayout(r8)

    r9 = QtWidgets.QHBoxLayout()
    r9.setSpacing(8)
    history_spin = QtWidgets.QSpinBox()
    history_spin.setRange(0, 500)
    history_spin.setValue(int(s["max_history_length"]))
    history_spin.setFixedWidth(80)
    r9.addWidget(QtWidgets.QLabel("Max chat history:"))
    r9.addWidget(history_spin)
    r9.addWidget(QtWidgets.QLabel("messages (0 = unlimited)"))
    r9.addStretch()
    l.addLayout(r9)

    r10 = QtWidgets.QHBoxLayout()
    r10.setSpacing(8)
    tokens_hint = QtWidgets.QLabel(f"(Provider default: {_prov_default_tokens:,})" if _prov_default_tokens else "(Provider default: none)")
    tokens_hint.setStyleSheet("font-size:10px; color:#888;")
    tokens_spin = QtWidgets.QSpinBox()
    tokens_spin.setRange(0, 131072)
    tokens_spin.setSingleStep(1024)
    tokens_spin.setValue(int(s.get("max_tokens", _prov_default_tokens or 16384)))
    tokens_spin.setFixedWidth(100)
    r10.addWidget(QtWidgets.QLabel("Max output tokens:"))
    r10.addWidget(tokens_spin)
    r10.addWidget(QtWidgets.QLabel("(0 = no cap)"))
    r10.addWidget(tokens_hint)
    r10.addStretch()
    l.addLayout(r10)

    l.addStretch()

    # ── Buttons ─────────────────────────────────────────────
    btns = QtWidgets.QDialogButtonBox(
        QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
    )

    def _apply_telemetry_consent(enabled):
        record_consent(enabled)
        try:
            import FreeCADGui
            collector = getattr(FreeCADGui, "_telemetry", None)
            if enabled and collector is None:
                from telemetry import TelemetryCollector
                tc = TelemetryCollector()
                FreeCADGui._telemetry = tc
                tc.install_do_command_hook()
                tc.install_run_command_hook()
                tc.install_report_view_hook()
                tc._hook_python_console()
            elif not enabled and collector is not None:
                try:
                    collector.shutdown()
                except Exception:
                    pass
                FreeCADGui._telemetry = None
        except Exception:
            pass

    def _accept():
        s["retries_per_step"] = retry_spin.value()
        s["auto_replan"] = auto_replan_cb.isChecked()
        s["sandbox_mode"] = sandbox_cb.isChecked()
        s["max_defer_attempts"] = defer_spin.value()
        s["theme"] = theme_combo.currentData() or "dark"
        s["chat_font_size"] = chat_font_spin.value()
        s["code_font_size"] = code_font_spin.value()
        s["temperature"] = temp_slider.value() / 100
        s["max_history_length"] = history_spin.value()
        s["max_tokens"] = tokens_spin.value()
        _apply_telemetry_consent(telemetry_cb.isChecked())
        sidebar._apply_settings(s)
        d.accept()

    btns.accepted.connect(_accept)
    btns.rejected.connect(d.reject)
    l.addWidget(btns)

    d.exec()
