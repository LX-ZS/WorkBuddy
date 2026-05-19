"""
gui/monitor_thread.py — 后台监测线程
=====================================
在 QThread 中运行监测循环，通过信号向主窗口推送事件。
"""
import time
from PyQt5.QtCore import QThread, pyqtSignal

from backend import (
    CONFIG, init_camera, State, PoseAnalyzer,
    ScreenshotManager, DailyScheduler, DailyReportGenerator,
    get_today_dir, FaceState, PhoneState,
)


class MonitorThread(QThread):
    """
    后台监测线程。
    signals:
        state_changed(str)      — 当前状态变化
        analysis_updated(dict)  — 每次完整分析结果（pose/face/phone/drinking/env）
        screenshot_taken(str)   — 新截图路径
        report_ready(str)       — 日报生成完成（路径）
        tick(str, int)          — 每秒心跳（状态, 截图数）
        error(str)              — 异常信息
        started_                — 线程启动
        stopped_                — 线程停止
    """
    frame_ready = pyqtSignal(object)  # numpy.ndarray, 用于实时画面显示
    state_changed = pyqtSignal(str)
    analysis_updated = pyqtSignal(dict)  # 完整分析结果
    screenshot_taken = pyqtSignal(str)
    report_ready = pyqtSignal(str)
    tick = pyqtSignal(str, int)
    error = pyqtSignal(str)
    started_ = pyqtSignal()
    stopped_ = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._running = True
        self._cap = None
        self._analyzer = None  # 延迟到 run() 中初始化
        self._screenshot_mgr = ScreenshotManager(CONFIG["screenshots_dir"])
        self._scheduler = DailyScheduler(CONFIG["report_hour"], CONFIG["report_minute"])
        self._report_generator = None
        self._last_state = State.UNKNOWN
        self._skip_frames = max(1, int(CONFIG["frame_interval"] * 30))
        self._frame_count = 0
        self._tick_counter = 0

    def _init_report_generator(self):
        if self._report_generator is None:
            self._report_generator = DailyReportGenerator(
                CONFIG["doubao_base_url"],
                CONFIG["doubao_api_key"],
                CONFIG["doubao_model"],
            )

    def _collect_today_screenshots(self):
        today_dir = get_today_dir(CONFIG["screenshots_dir"])
        if not today_dir.exists():
            return []
        return sorted(today_dir.glob("*.jpg")) + sorted(today_dir.glob("*.png"))

    def _trigger_daily_report(self):
        from pathlib import Path
        today_str = self._scheduler._last_date.isoformat()
        if hasattr(self._scheduler, '_last_date') is False:
            from datetime import datetime
            today_str = datetime.now().strftime("%Y-%m-%d")
        report_file = Path(CONFIG["reports_dir"]) / f"{today_str}.md"
        if report_file.exists():
            return
        self._init_report_generator()
        screenshots = [str(p) for p in self._collect_today_screenshots()]
        report_text = self._report_generator.generate(today_str, screenshots)
        with open(report_file, "w", encoding="utf-8") as f:
            f.write(report_text)
        self.report_ready.emit(str(report_file))

    def _process_frame(self, frame):
        """
        完整分析一帧，返回 (pose_state, should_screenshot, analysis_result)。
        analyze_all 会打印控制台输出，内部维护历史缓冲区。
        """
        result = self._analyzer.analyze_all(frame)
        state = result["pose_state"]
        _, should_screenshot = self._analyzer.update_state(state, time.time())
        return state, should_screenshot, result

    def run(self):
        try:
            # 延迟初始化 PoseAnalyzer，避免阻塞主线程
            self._analyzer = PoseAnalyzer()
            self._cap = init_camera(0)
        except Exception as e:
            self.error.emit(f"初始化失败: {e}")
            return

        self.started_.emit()
        last_tick_time = time.time()

        while self._running:
            try:
                success, frame = self._cap.read()
                if not success:
                    self.error.emit("读取帧失败，尝试重连...")
                    try:
                        self._cap.release()
                        self._cap = init_camera(0)
                    except Exception as e2:
                        self.error.emit(f"重连失败: {e2}")
                    time.sleep(1)
                    continue

                self._frame_count += 1

                # 每读一帧就发送一次（用于实时画面，监测分析跳过部分帧）
                self.frame_ready.emit(frame)

                if self._frame_count % self._skip_frames != 0:
                    continue

                state, should_screenshot, analysis = self._process_frame(frame)

                if state != self._last_state:
                    self._last_state = state
                    self.state_changed.emit(state)

                # 每次分析都推送完整结果
                self.analysis_updated.emit(analysis)

                if should_screenshot and CONFIG["screenshot_on_change"]:
                    path = self._screenshot_mgr.save(frame, state)
                    self.screenshot_taken.emit(path)

                # 每秒心跳
                now = time.time()
                if now - last_tick_time >= 1.0:
                    self.tick.emit(state, self._screenshot_mgr.count_today())
                    last_tick_time = now

                # 检查定时任务
                if self._scheduler.check():
                    self._trigger_daily_report()
            except Exception as e:
                import traceback
                self.error.emit(f"处理帧异常: {e}")
                traceback.print_exc()
                time.sleep(1)
                continue

        # 清理
        if self._cap:
            self._cap.release()
        self.stopped_.emit()

    def stop(self):
        self._running = False
