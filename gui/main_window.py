"""
gui/main_window.py — 主窗口（科技banner风格）
=============================================
浅蓝渐变背景 · 玻璃拟态卡片 · 几何纹理
"""
import os
import cv2
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QListWidget, QListWidgetItem,
    QTextBrowser, QSplitter, QStatusBar, QToolBar,
    QMessageBox, QInputDialog, QAction, qApp,
    QFrame, QSizePolicy, QTabWidget,
)
from PyQt5.QtCore import Qt, QTimer, QSize
from PyQt5.QtGui import QIcon, QFont, QPalette, QColor, QImage, QPixmap

from backend import CONFIG, State
from gui.monitor_thread import MonitorThread
from gui.report_viewer import render_report
from gui.settings_dialog import SettingsDialog


# ──────────────────────────────────────────────
# 状态映射
# ──────────────────────────────────────────────
STATE_EMOJI = {
    State.WORK:    "💻",
    State.PHONE:    "📱",
    State.SLEEP:    "😴",
    State.AWAY:     "🚶",
    State.UNKNOWN:  "❓",
}
STATE_COLOR = {
    State.WORK:    "#10b981",
    State.PHONE:   "#f59e0b",
    State.SLEEP:   "#6366f1",
    State.AWAY:    "#94a3b8",
    State.UNKNOWN: "#cbd5e1",
}
STATE_BG = {
    State.WORK:    "rgba(16,185,129,0.10)",
    State.PHONE:   "rgba(245,158,11,0.10)",
    State.SLEEP:   "rgba(99,102,241,0.10)",
    State.AWAY:    "rgba(148,163,184,0.10)",
    State.UNKNOWN: "rgba(203,213,225,0.10)",
}

# ── CSS 常量 ──────────────────────────────────
BASE_QSS = """
    QWidget {
        font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
    }
"""

CARD_QSS = """
    background: rgba(255,255,255,0.72);
    border: 1px solid rgba(255,255,255,0.85);
    border-radius: 16px;
    padding: 14px;
"""

BTN_PRIMARY_QSS = """
    QPushButton {
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
            stop:0 #3b82f6, stop:1 #2563eb);
        color: white;
        border: none;
        border-radius: 8px;
        padding: 10px 24px;
        font-size: 14px;
        font-weight: 600;
    }
    QPushButton:hover {
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
            stop:0 #2563eb, stop:1 #1d4ed8);
    }
    QPushButton:pressed {
        background: #1d4ed8;
    }
    QPushButton:disabled {
        background: #cbd5e1;
        color: #94a3b8;
    }
"""

BTN_SECONDARY_QSS = """
    QPushButton {
        background: rgba(255,255,255,0.60);
        color: #475569;
        border: 1px solid rgba(203,213,225,0.60);
        border-radius: 8px;
        padding: 8px 18px;
        font-size: 13px;
    }
    QPushButton:hover {
        background: rgba(255,255,255,0.90);
        border-color: #94a3b8;
    }
"""

LIST_QSS = """
    QListWidget {
        background: rgba(255,255,255,0.60);
        border: 1px solid rgba(203,213,225,0.50);
        border-radius: 12px;
        padding: 6px;
        outline: none;
    }
    QListWidget::item {
        padding: 8px 12px;
        border-radius: 8px;
        color: #334155;
        margin: 2px 0;
    }
    QListWidget::item:selected {
        background: #dbeafe;
        color: #1e40af;
        font-weight: 600;
    }
    QListWidget::item:hover {
        background: rgba(59,130,246,0.08);
    }
"""

TEXT_QSS = """
    QTextBrowser {
        background: rgba(255,255,255,0.60);
        border: 1px solid rgba(203,213,225,0.50);
        border-radius: 12px;
        padding: 12px;
        color: #334155;
    }
"""

STATUS_QSS = """
    QStatusBar {
        background: rgba(255,255,255,0.50);
        color: #64748b;
        font-size: 12px;
        border-top: 1px solid rgba(203,213,225,0.40);
    }
"""


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._thread: MonitorThread | None = None
        self._monitoring = False
        self._today_screenshot_count = 0
        self._state_records: list[str] = []
        self._last_analysis: dict = {}
        self._setup_ui()
        self._setup_tray()
        self._load_reports()
        self._refresh_stats()

        self._stats_timer = QTimer(self)
        self._stats_timer.timeout.connect(self._refresh_stats)
        self._stats_timer.start(5000)

        # ── 番茄钟 ──
        self._pomo_running = False
        self._pomo_seconds = 25 * 60
        self._pomo_work_duration = 25 * 60
        self._pomo_break_duration = 5 * 60
        self._pomo_is_work = True
        self._pomo_round = 0
        self._pomo_focus_seconds = 0  # 累计专注秒数
        self._pomo_timer = QTimer(self)
        self._pomo_timer.timeout.connect(self._pomo_tick)

        # ── 桌面通知 ──
        self._notify_cooldown = 0  # 通知冷却秒数（防止刷屏）
        self._last_notify_state = None  # 上次通知时的状态
        self._notify_timer = QTimer(self)
        self._notify_timer.timeout.connect(self._notify_cooldown_tick)

        # ── 状态图表 ──
        self._chart_start_time: float | None = None

    # ── UI 初始化 ──────────────────────────────────

    def _setup_ui(self):
        self.setWindowTitle("智能工作状态监测")
        self.setMinimumSize(1080, 720)
        self.resize(1280, 780)

        # 全局渐变背景
        palette = self.palette()
        gradient = QPalette()
        gradient.setColor(QPalette.Window, QColor("#f0f9ff"))
        self.setPalette(gradient)
        self.setStyleSheet(BASE_QSS)

        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(24, 20, 24, 16)
        outer.setSpacing(16)

        # ═══════ 顶部横幅（科技banner风格）═══════
        banner = QWidget()
        banner.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #e0f2fe, stop:0.5 #f0f9ff, stop:1 #ffffff);
                border-radius: 20px;
                border: 1px solid rgba(59,130,246,0.15);
            }
        """)
        banner_layout = QHBoxLayout(banner)
        banner_layout.setContentsMargins(32, 22, 32, 22)
        banner_layout.setSpacing(28)

        # 左侧文字区
        left_text = QWidget()
        left_lay = QVBoxLayout(left_text)
        left_lay.setSpacing(8)
        left_lay.setContentsMargins(0, 0, 0, 0)

        self._title_label = QLabel("智能工作状态监测")
        self._title_label.setStyleSheet("""
            font-size: 28px; font-weight: 800; color: #0f172a;
            background: transparent; border: none;
        """)
        left_lay.addWidget(self._title_label)

        subtitle = QLabel("AI驱动的实时姿态分析 · 面部表情识别 · 自动化日报")
        subtitle.setStyleSheet("font-size: 13px; color: #64748b; background: transparent; border: none;")
        left_lay.addWidget(subtitle)

        left_lay.addSpacing(12)

        # 按钮行
        btn_row = QWidget()
        btn_row_lay = QHBoxLayout(btn_row)
        btn_row_lay.setSpacing(10)
        btn_row_lay.setContentsMargins(0, 0, 0, 0)

        self._btn_start = QPushButton("▶  开始监测")
        self._btn_start.setStyleSheet(BTN_PRIMARY_QSS)
        self._btn_start.setMinimumWidth(120)
        self._btn_start.clicked.connect(self._start_monitor)
        btn_row_lay.addWidget(self._btn_start)

        self._btn_stop = QPushButton("■  停止监测")
        self._btn_stop.setStyleSheet(BTN_SECONDARY_QSS)
        self._btn_stop.setMinimumWidth(100)
        self._btn_stop.setEnabled(False)
        self._btn_stop.clicked.connect(self._stop_monitor)
        btn_row_lay.addWidget(self._btn_stop)

        btn_settings = QPushButton("⚙  设置")
        btn_settings.setStyleSheet(BTN_SECONDARY_QSS)
        btn_settings.clicked.connect(self._open_settings)
        btn_row_lay.addWidget(btn_settings)

        btn_refresh = QPushButton("🔄  刷新")
        btn_refresh.setStyleSheet(BTN_SECONDARY_QSS)
        btn_refresh.clicked.connect(self._reload_reports)
        btn_row_lay.addWidget(btn_refresh)

        btn_row_lay.addStretch()
        left_lay.addWidget(btn_row)
        left_lay.addStretch()

        # 右侧视觉装饰区（占位用几何图形）
        right_visual = QWidget()
        right_visual.setFixedSize(260, 160)
        right_visual.setStyleSheet("""
            QWidget {
                background: qradialgradient(cx:0.7,cy:0.3,radius:1,
                    stop:0 rgba(59,130,246,0.12),
                    stop:1 rgba(59,130,246,0.02));
                border-radius: 16px;
                border: 1px solid rgba(59,130,246,0.10);
            }
        """)
        right_v_lay = QVBoxLayout(right_visual)
        right_v_lay.setAlignment(Qt.AlignCenter)
        icon_label = QLabel("🤖")
        icon_label.setStyleSheet("font-size: 48px; background: transparent; border: none;")
        icon_label.setAlignment(Qt.AlignCenter)
        right_v_lay.addWidget(icon_label)
        ai_text = QLabel("AI 智能监测引擎")
        ai_text.setStyleSheet("font-size: 12px; color: #94a3b8; background: transparent; border: none;")
        ai_text.setAlignment(Qt.AlignCenter)
        right_v_lay.addWidget(ai_text)

        banner_layout.addWidget(left_text, 3)
        banner_layout.addWidget(right_visual, 1)
        outer.addWidget(banner)

        # ═══════ 主内容区 ═══════
        splitter = QSplitter(Qt.Horizontal)
        splitter.setStyleSheet("QSplitter::handle { background: rgba(203,213,225,0.30); width: 2px; }")

        # ── 左侧：日报列表 ──
        left_card = QWidget()
        left_card.setStyleSheet(CARD_QSS)
        left_l = QVBoxLayout(left_card)
        left_l.setContentsMargins(0, 0, 0, 0)
        left_l.setSpacing(10)

        lbl_reports = QLabel("<b style='color:#1e293b;font-size:14px;'>📅 日报列表</b>")
        lbl_reports.setStyleSheet("background: transparent; border: none;")
        left_l.addWidget(lbl_reports)

        self._report_list = QListWidget()
        self._report_list.setStyleSheet(LIST_QSS)
        self._report_list.setMinimumWidth(180)
        self._report_list.itemClicked.connect(self._on_report_clicked)
        left_l.addWidget(self._report_list)
        splitter.addWidget(left_card)
        splitter.setStretchFactor(0, 2)

        # ── 中间：实时画面 / 日报预览 ──
        center_card = QWidget()
        center_card.setStyleSheet(CARD_QSS)
        center_l = QVBoxLayout(center_card)
        center_l.setContentsMargins(0, 0, 0, 0)
        center_l.setSpacing(10)

        lbl_center = QLabel("<b style='color:#1e293b;font-size:14px;'>📄 实时画面 / 日报预览</b>")
        lbl_center.setStyleSheet("background: transparent; border: none;")
        center_l.addWidget(lbl_center)

        # 视频/占位区域
        self._video_label = QLabel()
        self._video_label.setAlignment(Qt.AlignCenter)
        self._video_label.setMinimumSize(380, 260)
        self._video_label.setStyleSheet("""
            QLabel {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                    stop:0 #0f172a, stop:1 #1e293b);
                border-radius: 14px;
                border: 1px solid rgba(59,130,246,0.20);
                color: #64748b;
            }
        """)
        self._video_label.setText("<br><br>▶ 点击「开始监测」显示实时画面")
        center_l.addWidget(self._video_label)

        self._report_viewer = QTextBrowser()
        self._report_viewer.setStyleSheet(TEXT_QSS)
        self._report_viewer.setOpenExternalLinks(True)
        center_l.addWidget(self._report_viewer)
        splitter.addWidget(center_card)
        splitter.setStretchFactor(1, 4)

        # ── 右侧：Tab 面板 ──
        right_card = QWidget()
        right_card.setStyleSheet(CARD_QSS)
        right_l = QVBoxLayout(right_card)
        right_l.setContentsMargins(10, 10, 10, 10)
        right_l.setSpacing(0)

        tabs = QTabWidget()
        tabs.setStyleSheet("""
            QTabWidget::pane {
                border: none;
                background: transparent;
                top: -1px;
            }
            QTabBar::tab {
                background: rgba(255,255,255,0.50);
                color: #64748b;
                border: none;
                border-radius: 8px;
                padding: 6px 18px;
                margin: 2px 4px;
                font-size: 12px;
                font-weight: 500;
            }
            QTabBar::tab:selected {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #3b82f6, stop:1 #2563eb);
                color: white;
            }
            QTabBar::tab:hover:!selected {
                background: rgba(59,130,246,0.12);
                color: #3b82f6;
            }
        """)
        tabs.setDocumentMode(True)

        # ═══════ Tab 0: 概览 ═══════
        tab_overview = QWidget()
        tab_overview_lay = QVBoxLayout(tab_overview)
        tab_overview_lay.setContentsMargins(8, 10, 8, 8)
        tab_overview_lay.setSpacing(8)

        # 状态徽章
        self._state_label = QLabel(f"{STATE_EMOJI[State.UNKNOWN]}  监测已停止")
        self._state_label.setFont(QFont("Segoe UI", 13, QFont.Bold))
        self._state_label.setAlignment(Qt.AlignCenter)
        self._state_label.setMinimumHeight(52)
        self._state_label.setStyleSheet(
            f"color: {STATE_COLOR[State.UNKNOWN]};"
            f"background: {STATE_BG[State.UNKNOWN]};"
            "border-radius: 12px; padding: 10px 16px; border: 1px solid rgba(0,0,0,0.04);"
        )
        tab_overview_lay.addWidget(self._state_label)

        # 统计卡片
        self._stats_card = QLabel()
        self._stats_card.setStyleSheet("""
            QLabel {
                background: rgba(255,255,255,0.55);
                border: 1px solid rgba(203,213,225,0.45);
                border-radius: 12px;
                padding: 10px;
                color: #334155;
            }
        """)
        self._stats_card.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self._stats_card.setTextFormat(Qt.RichText)
        tab_overview_lay.addWidget(self._stats_card)
        tab_overview_lay.addStretch()

        tabs.addTab(tab_overview, "📊 概览")

        # ═══════ Tab 1: 分析 ═══════
        tab_analysis = QWidget()
        tab_analysis_lay = QVBoxLayout(tab_analysis)
        tab_analysis_lay.setContentsMargins(8, 10, 8, 8)
        tab_analysis_lay.setSpacing(8)

        self._analysis_card = QLabel()
        self._analysis_card.setStyleSheet("""
            QLabel {
                background: rgba(255,255,255,0.55);
                border: 1px solid rgba(203,213,225,0.45);
                border-radius: 12px;
                padding: 10px;
                color: #334155;
            }
        """)
        self._analysis_card.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self._analysis_card.setTextFormat(Qt.RichText)
        self._analysis_card.setText(self._build_analysis_html())
        tab_analysis_lay.addWidget(self._analysis_card)

        self._chart_canvas = self._make_chart_canvas()
        tab_analysis_lay.addWidget(self._chart_canvas)
        tab_analysis_lay.addStretch()

        tabs.addTab(tab_analysis, "🔬 分析")

        # ═══════ Tab 2: 番茄钟 ═══════
        tab_pomo = QWidget()
        tab_pomo_lay = QVBoxLayout(tab_pomo)
        tab_pomo_lay.setContentsMargins(8, 10, 8, 8)
        tab_pomo_lay.setSpacing(8)

        pomodoro_card = QWidget()
        pomodoro_card.setStyleSheet("""
            QWidget {
                background: rgba(255,255,255,0.55);
                border: 1px solid rgba(203,213,225,0.45);
                border-radius: 12px;
                padding: 10px;
            }
        """)
        pomodoro_lay = QVBoxLayout(pomodoro_card)
        pomodoro_lay.setContentsMargins(0, 0, 0, 0)
        pomodoro_lay.setSpacing(8)

        # 倒计时显示
        self._pomo_time_label = QLabel("25:00")
        self._pomo_time_label.setFont(QFont("Segoe UI", 24, QFont.Bold))
        self._pomo_time_label.setAlignment(Qt.AlignCenter)
        self._pomo_time_label.setStyleSheet(
            "color: #0f172a; background: transparent; border: none;"
        )
        pomodoro_lay.addWidget(self._pomo_time_label)

        # 相位标签
        self._pomo_phase_label = QLabel("🍅 专注中")
        self._pomo_phase_label.setAlignment(Qt.AlignCenter)
        self._pomo_phase_label.setStyleSheet(
            "color: #10b981; font-size: 12px; background: rgba(16,185,129,0.10); "
            "border-radius: 6px; padding: 3px 10px;"
        )
        pomodoro_lay.addWidget(self._pomo_phase_label)

        # 轮次计数
        self._pomo_round_label = QLabel("第 0 轮 · 已专注 0 分钟")
        self._pomo_round_label.setAlignment(Qt.AlignCenter)
        self._pomo_round_label.setStyleSheet(
            "color: #64748b; font-size: 11px; background: transparent; border: none;"
        )
        pomodoro_lay.addWidget(self._pomo_round_label)

        # 控制按钮行
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        self._pomo_btn_start = QPushButton("▶")
        self._pomo_btn_start.setFixedWidth(36)
        self._pomo_btn_start.setStyleSheet("""
            QPushButton {
                background: rgba(16,185,129,0.80);
                color: white; border: none; border-radius: 6px;
                padding: 5px; font-size: 13px;
            }
            QPushButton:hover { background: #10b981; }
        """)
        self._pomo_btn_start.clicked.connect(self._pomo_start)

        self._pomo_btn_pause = QPushButton("⏸")
        self._pomo_btn_pause.setFixedWidth(36)
        self._pomo_btn_pause.setEnabled(False)
        self._pomo_btn_pause.setStyleSheet("""
            QPushButton {
                background: rgba(245,158,11,0.80);
                color: white; border: none; border-radius: 6px;
                padding: 5px; font-size: 13px;
            }
            QPushButton:hover { background: #f59e0b; }
        """)
        self._pomo_btn_pause.clicked.connect(self._pomo_pause)

        self._pomo_btn_reset = QPushButton("↺")
        self._pomo_btn_reset.setFixedWidth(36)
        self._pomo_btn_reset.setStyleSheet("""
            QPushButton {
                background: rgba(148,163,184,0.60);
                color: white; border: none; border-radius: 6px;
                padding: 5px; font-size: 13px;
            }
            QPushButton:hover { background: #94a3b8; }
        """)
        self._pomo_btn_reset.clicked.connect(self._pomo_reset)

        btn_row.addStretch()
        btn_row.addWidget(self._pomo_btn_start)
        btn_row.addWidget(self._pomo_btn_pause)
        btn_row.addWidget(self._pomo_btn_reset)
        btn_row.addStretch()
        pomodoro_lay.addLayout(btn_row)

        tab_pomo_lay.addWidget(pomodoro_card)
        tab_pomo_lay.addStretch()

        tabs.addTab(tab_pomo, "🍅 番茄钟")

        right_l.addWidget(tabs)
        splitter.addWidget(right_card)
        splitter.setStretchFactor(2, 2)

        outer.addWidget(splitter, 1)

        # ═══════ 底部状态栏 ═══════
        self._status_bar = QStatusBar()
        self._status_bar.setStyleSheet(STATUS_QSS)
        self.setStatusBar(self._status_bar)
        self._status_bar.showMessage("📍 就绪 · 点击「开始监测」启动 AI 引擎")

    # ── 系统托盘 ───────────────────────────────────

    def _setup_tray(self):
        self._tray = None
        try:
            from PyQt5.QtWidgets import QSystemTrayIcon
            if QSystemTrayIcon.isSystemTrayAvailable():
                self._tray = QSystemTrayIcon(self)
                self._tray.setToolTip("智能工作状态监测")
                self._tray.activated.connect(self._on_tray_activated)
                self._build_tray_menu()
                self._tray.show()
        except Exception:
            pass

    def _build_tray_menu(self):
        from PyQt5.QtWidgets import QMenu
        menu = QMenu()
        menu.addAction("📋 显示主窗口", self.show)
        menu.addAction("▶ 开始监测", self._start_monitor).setEnabled(not self._monitoring)
        menu.addAction("■ 停止监测", self._stop_monitor).setEnabled(self._monitoring)
        menu.addSeparator()
        menu.addAction("❌ 退出", self._on_exit)
        if self._tray:
            self._tray.setContextMenu(menu)

    def _on_tray_activated(self, reason):
        from PyQt5.QtWidgets import QSystemTrayIcon
        if reason == QSystemTrayIcon.Trigger:
            self.show()
            self.activateWindow()

    # ── 监测控制 ───────────────────────────────────

    def _start_monitor(self):
        if self._monitoring:
            return
        self._thread = MonitorThread()
        self._thread.frame_ready.connect(self._update_frame)
        self._thread.state_changed.connect(self._on_state_changed)
        self._thread.analysis_updated.connect(self._on_analysis_updated)
        self._thread.screenshot_taken.connect(self._on_screenshot)
        self._thread.report_ready.connect(self._on_report_generated)
        self._thread.tick.connect(self._on_tick)
        self._thread.error.connect(self._on_error)
        self._thread.started_.connect(self._on_thread_started)
        self._thread.finished.connect(self._on_thread_finished)
        self._thread.start()
        self._btn_start.setEnabled(False)
        self._btn_stop.setEnabled(True)
        self._status_bar.showMessage("🔄 摄像头初始化中...")

    def _stop_monitor(self):
        if self._thread and self._monitoring:
            self._thread.stop()
        self._monitoring = False
        self._btn_start.setEnabled(True)
        self._btn_stop.setEnabled(False)
        self._update_state_display(State.UNKNOWN)
        self._status_bar.showMessage("📍 监测已停止")
        # 恢复日报显示
        self._report_viewer.show()
        self._video_label.setText("<br><br>▶ 点击「开始监测」显示实时画面")
        self._video_label.setStyleSheet("""
            QLabel {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                    stop:0 #0f172a, stop:1 #1e293b);
                border-radius: 14px;
                border: 1px solid rgba(59,130,246,0.20);
                color: #64748b;
            }
        """)

    def _on_thread_started(self):
        self._monitoring = True
        self._build_tray_menu()
        self._status_bar.showMessage("🟢 监测中 · 状态: 初始化")
        self._state_records.clear()
        self._last_analysis = {}
        self._today_screenshot_count = 0
        self._report_viewer.hide()
        self._analysis_card.setText(self._build_analysis_html())
        self._update_chart()

    def _on_thread_finished(self):
        self._monitoring = False
        self._btn_start.setEnabled(True)
        self._btn_stop.setEnabled(False)
        self._build_tray_menu()

    # ── 信号处理 ───────────────────────────────────

    def _update_frame(self, frame):
        try:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb.shape
            img = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
            pixmap = QPixmap.fromImage(img)
            scaled = pixmap.scaled(
                self._video_label.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
            self._video_label.setPixmap(scaled)
        except Exception:
            pass

    def _on_state_changed(self, state: str):
        self._state_records.append(state)
        self._update_state_display(state)
        self._status_bar.showMessage(
            f"🟢 监测中 · 状态: {STATE_EMOJI.get(state,'')} {state}"
        )
        self._refresh_stats()
        self._update_chart()

    def _on_tick(self, state: str, screenshot_count: int):
        self._today_screenshot_count = screenshot_count
        self._refresh_stats()
        self._update_chart()

    def _on_analysis_updated(self, analysis: dict):
        self._last_analysis = analysis
        self._analysis_card.setText(self._build_analysis_html(analysis))
        self._check_notify(analysis)

    def _build_analysis_html(self, analysis: dict = None) -> str:
        from backend import FaceState, PhoneState
        if not analysis:
            return """
            <div style="line-height:1.8;color:#94a3b8;font-size:12px;">
                <i>监测启动后显示...</i>
            </div>"""

        face = analysis.get("face_state", FaceState.NEUTRAL)
        phone = analysis.get("phone_state", PhoneState.NONE)
        drinking = analysis.get("drinking", False)
        env = analysis.get("env", {})

        FACE_EMOJI = {
            FaceState.NEUTRAL:     ("😐", "#64748b", "rgba(100,116,139,0.08)"),
            FaceState.SMILING:     ("😊", "#10b981", "rgba(16,185,129,0.10)"),
            FaceState.YAWNING:     ("🥱", "#f59e0b", "rgba(245,158,11,0.10)"),
            FaceState.FROWNING:    ("😟", "#6366f1", "rgba(99,102,241,0.10)"),
            FaceState.EYES_CLOSED: ("😴", "#8b5cf6", "rgba(139,92,246,0.10)"),
        }
        PHONE_EMOJI = {
            PhoneState.NONE:      ("✅", "#10b981", "rgba(16,185,129,0.08)"),
            PhoneState.HOLDING:   ("📱", "#f59e0b", "rgba(245,158,11,0.10)"),
            PhoneState.SCROLLING: ("👆", "#ef4444", "rgba(239,68,68,0.10)"),
            PhoneState.GAMING:    ("🎮", "#8b5cf6", "rgba(139,92,246,0.10)"),
        }

        fe, fc, fb = FACE_EMOJI.get(face, ("😐", "#64748b", "rgba(100,116,139,0.08)"))
        pe, pc, pb = PHONE_EMOJI.get(phone, ("✅", "#10b981", "rgba(16,185,129,0.08)"))
        de = "💧" if drinking else "🚫"
        dc = "#3b82f6" if drinking else "#94a3b8"
        db = "rgba(59,130,246,0.10)" if drinking else "rgba(148,163,184,0.06)"
        dtext = "检测到喝水" if drinking else "未检测"

        distracted = env.get("distracted", False)
        multi = env.get("multi_person", False)

        lines = [
            f'<div style="background:{fb};border-radius:8px;padding:7px 10px;margin:4px 0;">',
            f'  <span style="color:#64748b;font-size:11px;">表情</span>  '
            f'  <span style="color:{fc};font-weight:600;">{fe} {face}</span>',
            f'</div>',
            f'<div style="background:{pb};border-radius:8px;padding:7px 10px;margin:4px 0;">',
            f'  <span style="color:#64748b;font-size:11px;">手机</span>  '
            f'  <span style="color:{pc};font-weight:600;">{pe} {phone}</span>',
            f'</div>',
            f'<div style="background:{db};border-radius:8px;padding:7px 10px;margin:4px 0;">',
            f'  <span style="color:#64748b;font-size:11px;">饮水</span>  '
            f'  <span style="color:{dc};font-weight:600;">{de} {dtext}</span>',
            f'</div>',
        ]

        if distracted or multi:
            lines += [
                '<div style="border-top:1px solid rgba(203,213,225,0.30);margin-top:6px;padding-top:6px;">',
            ]
            if distracted:
                lines.append('<div style="color:#ef4444;font-size:11px;">⚠️ 检测到分心</div>')
            if multi:
                lines.append('<div style="color:#f59e0b;font-size:11px;">👥 检测到多人</div>')
            lines.append('</div>')

        return f'<div style="line-height:1.6;">{"".join(lines)}</div>'

    def _on_screenshot(self, path: str):
        self._today_screenshot_count += 1
        self._refresh_stats()
        basename = os.path.basename(path)
        self._status_bar.showMessage(f"📸 截图: {basename}")

    def _on_report_generated(self, path: str):
        self._status_bar.showMessage(f"✅ 日报已生成: {os.path.basename(path)}")
        self._load_reports()
        if self._tray:
            self._tray.showMessage("日报生成", "今日工作日报已生成！", msecs=3000)

    def _on_error(self, msg: str):
        self._status_bar.showMessage(f"❌ 错误: {msg}")
        if self._tray:
            self._tray.showMessage("监测错误", msg, msecs=5000)

    # ── 状态显示 ───────────────────────────────────

    def _update_state_display(self, state: str):
        emoji = STATE_EMOJI.get(state, "❓")
        color = STATE_COLOR.get(state, "#cbd5e1")
        bg = STATE_BG.get(state, "rgba(203,213,225,0.10)")
        self._state_label.setText(f"{emoji}  {state}")
        self._state_label.setStyleSheet(
            f"color: {color};"
            f"background: {bg};"
            "border-radius: 12px; padding: 10px 16px;"
            "border: 1px solid rgba(0,0,0,0.04);"
        )

    def _refresh_stats(self):
        today_str = datetime.now().strftime("%Y-%m-%d")

        screenshots = 0
        today_dir = Path(CONFIG["screenshots_dir"]) / today_str
        if today_dir.exists():
            screenshots = (
                len(list(today_dir.glob("*.jpg"))) +
                len(list(today_dir.glob("*.png")))
            )

        work_count = self._state_records.count(State.WORK)
        phone_count = self._state_records.count(State.PHONE)
        away_count = self._state_records.count(State.AWAY)
        sleep_count = self._state_records.count(State.SLEEP)
        total = len(self._state_records) or 1

        work_pct = work_count / total * 100
        phone_pct = phone_count / total * 100

        focus_segments = 0
        in_work = False
        for s in self._state_records:
            if s == State.WORK and not in_work:
                focus_segments += 1
                in_work = True
            elif s != State.WORK:
                in_work = False

        html = f"""
        <div style="line-height:1.7;">
        <b style="font-size:15px;color:#0f172a;">📅 {today_str}</b><br><br>

        <div style="margin-bottom:8px;">
            <span style="color:#64748b;font-size:12px;">专注时长占比</span><br>
            <span style="font-size:22px;font-weight:800;color:#10b981;">{work_pct:.0f}%</span>
        </div>

        <div style="background:rgba(16,185,129,0.08);border-radius:8px;padding:8px 12px;margin:6px 0;">
            💻 专注: {work_count}次
        </div>
        <div style="background:rgba(245,158,11,0.08);border-radius:8px;padding:8px 12px;margin:6px 0;">
            📱 摸鱼: {phone_count}次 ({phone_pct:.0f}%)
        </div>
        <div style="background:rgba(99,102,241,0.08);border-radius:8px;padding:8px 12px;margin:6px 0;">
            😴 休息: {sleep_count}次
        </div>
        <div style="background:rgba(148,163,184,0.08);border-radius:8px;padding:8px 12px;margin:6px 0;">
            🚶 离开: {away_count}次
        </div>

        <div style="margin-top:10px;border-top:1px solid rgba(203,213,225,0.40);padding-top:8px;">
            <span style="color:#64748b;font-size:12px;">📸 截图数:</span>
            <span style="font-weight:700;color:#0f172a;"> {screenshots}</span><br>
            <span style="color:#64748b;font-size:12px;">🔁 专注切换:</span>
            <span style="font-weight:700;color:#0f172a;"> {focus_segments}次</span>
        </div>
        </div>
        """
        self._stats_card.setText(html)

    # ── 日报列表 ───────────────────────────────────

    def _load_reports(self):
        self._report_list.clear()
        reports_dir = Path(CONFIG["reports_dir"])
        if not reports_dir.exists():
            return
        reports = sorted(reports_dir.glob("*.md"), reverse=True)
        for r in reports:
            date_str = r.stem
            item = QListWidgetItem(f"📄 {date_str}")
            item.setData(Qt.UserRole, str(r))
            self._report_list.addItem(item)

        if reports:
            self._report_list.setCurrentRow(0)
            self._load_report(str(reports[0]))

    def _reload_reports(self):
        self._load_reports()
        self._status_bar.showMessage("日报列表已刷新")

    def _on_report_clicked(self, item: QListWidgetItem):
        path = item.data(Qt.UserRole)
        if path:
            self._load_report(path)

    def _load_report(self, path: str):
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            html = render_report(content)
            self._report_viewer.setHtml(html)
        except Exception as e:
            self._report_viewer.setHtml(f"<p style='color:red'>读取失败: {e}</p>")

    # ── 设置 ───────────────────────────────────────

    def _open_settings(self):
        dlg = SettingsDialog(self)
        dlg.exec_()

    # ── 桌面气泡通知 ────────────────────────────────

    def _check_notify(self, analysis: dict):
        """根据实时分析结果，判断是否发送桌面通知"""
        if not self._monitoring:
            return

        from backend import PhoneState, FaceState

        # 冷却中，跳过
        if self._notify_cooldown > 0:
            return

        title = "WorkBuddy 提醒"
        tips = []
        urgency = "normal"

        # 手机使用
        phone = analysis.get("phone_state", PhoneState.NONE)
        if phone == PhoneState.SCROLLING:
            tips.append("检测到你在刷手机 🎮")
            urgency = "critical"
        elif phone == PhoneState.GAMING:
            tips.append("检测到你在玩游戏 🎮 休息一下吧~")
            urgency = "critical"

        # 趴桌/睡觉
        pose = analysis.get("pose_state", State.UNKNOWN)
        if pose == State.SLEEP:
            tips.append("检测到你在趴桌 😴 醒醒！")
            urgency = "critical"

        # 表情
        face = analysis.get("face_state", FaceState.NEUTRAL)
        if face == FaceState.YAWNING:
            tips.append("你好像有点困 🥱 要不要休息一下？")
            urgency = "normal"
        elif face == FaceState.EYES_CLOSED:
            tips.append("眼睛闭着呢 😴 休息够了就起来工作吧")
            urgency = "normal"

        # 分心
        env = analysis.get("env", {})
        if env.get("distracted"):
            tips.append("检测到你在分心 ⚠️ 专注力很重要！")

        if not tips:
            return

        msg = tips[0]

        # 同一状态不重复通知
        notify_key = f"{pose}/{phone}/{face}/{env.get('distracted', False)}"
        if notify_key == self._last_notify_state:
            return

        self._last_notify_state = notify_key
        self._notify_cooldown = 30   # 30秒冷却
        self._notify_timer.start(1000)

        if self._tray:
            self._tray.showMessage(title, msg, msecs=3000)
        self._status_bar.showMessage(f"🔔 {msg}")

    def _notify_cooldown_tick(self):
        self._notify_cooldown -= 1
        if self._notify_cooldown <= 0:
            self._notify_timer.stop()
            self._notify_cooldown = 0
            self._last_notify_state = None

    # ── 退出 ───────────────────────────────────────

    def _on_exit(self):
        if self._thread and self._monitoring:
            self._thread.stop()
            self._thread.wait(3000)
        qApp.quit()

    def closeEvent(self, event):
        if self._tray:
            event.ignore()
            self.hide()
            self._tray.showMessage("最小化到托盘", "双击托盘图标恢复窗口", msecs=2000)
        else:
            self._on_exit()
            event.accept()

    # ── 番茄钟 ─────────────────────────────────────

    def _pomo_start(self):
        if self._pomo_running:
            return
        self._pomo_running = True
        self._pomo_timer.start(1000)
        self._pomo_btn_start.setEnabled(False)
        self._pomo_btn_pause.setEnabled(True)
        self._status_bar.showMessage(
            f"🍅 番茄钟已开始 · {('专注' if self._pomo_is_work else '休息')}模式"
        )

    def _pomo_pause(self):
        if not self._pomo_running:
            return
        self._pomo_running = False
        self._pomo_timer.stop()
        self._pomo_btn_start.setEnabled(True)
        self._pomo_btn_pause.setEnabled(False)
        self._status_bar.showMessage("⏸ 番茄钟已暂停")

    def _pomo_reset(self):
        self._pomo_timer.stop()
        self._pomo_running = False
        self._pomo_seconds = self._pomo_work_duration
        self._pomo_is_work = True
        self._pomo_round = 0
        self._pomo_focus_seconds = 0
        self._pomo_btn_start.setEnabled(True)
        self._pomo_btn_pause.setEnabled(False)
        self._pomo_update_display()
        self._status_bar.showMessage("↺ 番茄钟已重置")

    def _pomo_tick(self):
        if self._pomo_seconds > 0:
            self._pomo_seconds -= 1
            if self._pomo_is_work:
                self._pomo_focus_seconds += 1
            self._pomo_update_display()
        else:
            self._pomo_switch_phase()

    def _pomo_switch_phase(self):
        if self._pomo_is_work:
            # 专注结束，切换休息
            self._pomo_round += 1
            self._pomo_seconds = self._pomo_break_duration
            self._pomo_is_work = False
            msg = f"🎉 第 {self._pomo_round} 轮专注完成！休息 5 分钟吧"
        else:
            # 休息结束，切换专注
            self._pomo_seconds = self._pomo_work_duration
            self._pomo_is_work = True
            msg = "☕ 休息结束！开始新一轮专注"

        self._pomo_update_display()
        self._status_bar.showMessage(msg)
        if self._tray:
            self._tray.showMessage("🍅 番茄钟", msg, msecs=5000)

    def _pomo_update_display(self):
        m, s = divmod(self._pomo_seconds, 60)
        self._pomo_time_label.setText(f"{m:02d}:{s:02d}")

        if self._pomo_is_work:
            self._pomo_phase_label.setText("🍅 专注中")
            self._pomo_phase_label.setStyleSheet(
                "color: #10b981; font-size: 12px; "
                "background: rgba(16,185,129,0.10); border-radius: 6px; padding: 3px 10px;"
            )
            self._pomo_time_label.setStyleSheet(
                "color: #10b981; background: transparent; border: none; font-size: 24px; font-weight: bold;"
            )
        else:
            self._pomo_phase_label.setText("☕ 休息中")
            self._pomo_phase_label.setStyleSheet(
                "color: #f59e0b; font-size: 12px; "
                "background: rgba(245,158,11,0.10); border-radius: 6px; padding: 3px 10px;"
            )
            self._pomo_time_label.setStyleSheet(
                "color: #f59e0b; background: transparent; border: none; font-size: 24px; font-weight: bold;"
            )

        focus_min = self._pomo_focus_seconds // 60
        self._pomo_round_label.setText(f"第 {self._pomo_round} 轮 · 已专注 {focus_min} 分钟")

    # ── 状态时间轴图表 ───────────────────────────────

    def _make_chart_canvas(self) -> FigureCanvas:
        """创建 matplotlib 图表画布（用于嵌入 PyQt5）"""
        fig = Figure(figsize=(3.2, 1.6), dpi=75)
        fig.patch.set_facecolor("#f8fafc")
        ax = fig.add_subplot(111)
        ax.set_facecolor("#f8fafc")
        ax.set_title("今日状态分布", fontsize=9, color="#334155", pad=4)
        ax.set_xlabel("时间", fontsize=8, color="#64748b")
        ax.tick_params(axis="x", labelsize=7, colors="#64748b")
        ax.tick_params(axis="y", labelsize=8, colors="#64748b")
        ax.set_yticks([])
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_color("#e2e8f0")
        ax.spines["bottom"].set_color("#e2e8f0")

        # 初始化空白柱状图
        ax.bar([], [], color="#94a3b8", width=0.6)
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        for t in ax.get_xticklabels():
            t.set_visible(False)

        fig.tight_layout(pad=0.8)
        canvas = FigureCanvas(fig)
        canvas.setStyleSheet("background: rgba(255,255,255,0.55); border: 1px solid rgba(203,213,225,0.45); border-radius: 12px;")
        canvas.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        canvas.setMinimumHeight(130)
        canvas.setMaximumHeight(160)
        canvas._fig = fig
        canvas._ax = ax
        return canvas

    def _update_chart(self):
        """根据当前状态记录更新图表"""
        ax = self._chart_canvas._ax
        ax.clear()

        if not self._state_records:
            ax.set_facecolor("#f8fafc")
            ax.set_title("今日状态分布", fontsize=9, color="#334155", pad=4)
            ax.set_xlabel("暂无数据", fontsize=8, color="#94a3b8")
            ax.set_yticks([])
            ax.set_xlim(0, 1)
            ax.set_ylim(0, 1)
            self._chart_canvas.draw()
            return

        # 统计各状态数量
        states = [State.WORK, State.PHONE, State.SLEEP, State.AWAY]
        colors = {
            State.WORK:  "#10b981",
            State.PHONE: "#f59e0b",
            State.SLEEP: "#6366f1",
            State.AWAY:  "#94a3b8",
        }
        counts = [self._state_records.count(s) for s in states]
        labels = ["💻专注", "📱摸鱼", "😴休息", "🚶离开"]
        total = sum(counts) or 1

        # 过滤零值
        nonzero = [(c, l, colors[s]) for c, l, s in zip(counts, labels, states) if c > 0]
        if not nonzero:
            ax.set_facecolor("#f8fafc")
            ax.set_title("今日状态分布", fontsize=9, color="#334155", pad=4)
            ax.set_yticks([])
            self._chart_canvas.draw()
            return

        vals, lbls, clrs = zip(*nonzero)

        # 水平条形图
        y_pos = range(len(vals))
        bars = ax.barh(list(y_pos), vals, color=clrs, height=0.55, edgecolor="white", linewidth=0.5)

        # 数值标签
        for bar, v, pct in zip(bars, vals, [v / total * 100 for v in vals]):
            ax.text(
                bar.get_width() + 0.3, bar.get_y() + bar.get_height() / 2,
                f"{pct:.0f}%", va="center", fontsize=8, color="#334155"
            )

        ax.set_yticks(list(y_pos))
        ax.set_yticklabels(lbls, fontsize=8)
        ax.set_xlabel("次数", fontsize=8, color="#64748b")
        ax.tick_params(axis="x", labelsize=7, colors="#64748b")
        ax.set_title("今日状态分布", fontsize=9, color="#334155", pad=4)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_color("#e2e8f0")
        ax.spines["bottom"].set_color("#e2e8f0")
        ax.set_xlim(0, max(vals) * 1.25 if max(vals) > 0 else 1)

        self._chart_canvas._fig.tight_layout(pad=0.8)
        self._chart_canvas.draw()


