"""
gui/settings_dialog.py — 设置对话框
====================================
编辑 API 配置、生成时间、截图开关。
"""
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QSpinBox, QCheckBox, QPushButton,
    QGroupBox, QFormLayout, QDialogButtonBox,
)
from PyQt5.QtCore import Qt

from backend import CONFIG, save_config


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setMinimumWidth(420)
        self._setup_ui()
        self._load()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # ── API 配置 ──────────────────────────────
        api_group = QGroupBox("豆包 API 配置")
        api_layout = QFormLayout()

        self.api_url = QLineEdit()
        self.api_url.setPlaceholderText("https://ark.cn-beijing.volces.com/api/v3")
        api_layout.addRow("Base URL:", self.api_url)

        self.api_key = QLineEdit()
        self.api_key.setPlaceholderText("输入你的 API Key")
        self.api_key.setEchoMode(QLineEdit.Password)
        api_layout.addRow("API Key:", self.api_key)

        self.model_id = QLineEdit()
        self.model_id.setPlaceholderText("ep-2025xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx")
        api_layout.addRow("模型 ID:", self.model_id)

        api_group.setLayout(api_layout)
        layout.addWidget(api_group)

        # ── 检测参数 ────────────────────────────────
        detect_group = QGroupBox("检测参数")
        detect_layout = QFormLayout()

        time_layout = QHBoxLayout()
        self.hour_spin = QSpinBox()
        self.hour_spin.setRange(0, 23)
        self.hour_spin.setPrefix(" ")
        self.minute_spin = QSpinBox()
        self.minute_spin.setRange(0, 59)
        self.minute_spin.setPrefix(" : ")
        self.minute_spin.setSuffix(" ")
        time_layout.addWidget(self.hour_spin)
        time_layout.addWidget(self.minute_spin)
        time_layout.addStretch()
        detect_layout.addRow("日报生成时间:", time_layout)

        self.screenshot_cb = QCheckBox("状态变化时自动截图")
        detect_layout.addRow("", self.screenshot_cb)

        detect_group.setLayout(detect_layout)
        layout.addWidget(detect_group)

        # ── 按钮 ───────────────────────────────────
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _load(self):
        self.api_url.setText(CONFIG["doubao_base_url"])
        self.api_key.setText(CONFIG["doubao_api_key"])
        self.model_id.setText(CONFIG["doubao_model"])
        self.hour_spin.setValue(CONFIG["report_hour"])
        self.minute_spin.setValue(CONFIG["report_minute"])
        self.screenshot_cb.setChecked(CONFIG["screenshot_on_change"])

    def _on_ok(self):
        CONFIG["doubao_base_url"] = self.api_url.text().strip()
        CONFIG["doubao_api_key"] = self.api_key.text().strip()
        CONFIG["doubao_model"] = self.model_id.text().strip()
        CONFIG["report_hour"] = self.hour_spin.value()
        CONFIG["report_minute"] = self.minute_spin.value()
        CONFIG["screenshot_on_change"] = self.screenshot_cb.isChecked()
        save_config()
        self.accept()
