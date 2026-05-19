#!/usr/bin/env python3
"""
main_gui.py — GUI 入口
======================
启动 PyQt5 桌面应用，替代 CLI 方式运行监测系统。
"""
import sys
import os
import warnings

# 禁用 TensorFlow/MediaPipe 日志
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
warnings.filterwarnings('ignore')

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt

from backend import load_config, ensure_dirs
from gui.main_window import MainWindow


def main():
    # 加载配置
    load_config()
    ensure_dirs()

    # Qt 应用
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("智能工作状态监测")
    app.setApplicationVersion("1.0")
    app.setStyle("Fusion")  # 统一风格

    # 启动主窗口
    window = MainWindow()
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
