#!/usr/bin/env python3
"""
backend.py — 智能工作状态监测系统核心逻辑
=========================================
从 main.py 抽取的业务逻辑，供 GUI 和 CLI 共用。

作者: 三金Dev
"""

import os
import sys
import time
import base64
import logging
import json
from datetime import datetime
from pathlib import Path
from threading import Event
from collections import deque

import cv2
import mediapipe as mp
from mediapipe.tasks.python.vision import FaceLandmarker, PoseLandmarker
from openai import OpenAI

# ─────────────────────────────────────────────
# 配置区
# ─────────────────────────────────────────────
CONFIG = {
    "doubao_base_url": "https://ark.cn-beijing.volces.com/api/v3",
    "doubao_api_key": "YOUR_API_KEY_HERE",
    "doubao_model": "ep-2025xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "frame_interval": 0.5,
    "phone_duration": 5.0,
    "screenshot_on_change": True,
    "screenshots_dir": "screenshots",
    "reports_dir": "daily_reports",
    "log_file": "status_monitor.log",
    "report_hour": 18,
    "report_minute": 0,
}

CONFIG_FILE = "config.json"


def load_config():
    """从 config.json 加载配置（如果存在），覆盖默认值"""
    path = Path(CONFIG_FILE)
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                saved = json.load(f)
            CONFIG.update(saved)
        except Exception:
            pass


def save_config():
    """保存当前配置到 config.json"""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(CONFIG, f, ensure_ascii=False, indent=4)


# ─────────────────────────────────────────────
# 状态枚举
# ─────────────────────────────────────────────
class State:
    AWAY    = "Away"
    PHONE   = "Phone"
    SLEEP   = "Sleep"
    WORK    = "Working"
    UNKNOWN = "Unknown"


class FaceState:
    NEUTRAL       = "Neutral"
    SMILING       = "Smiling"
    YAWNING       = "Yawning"
    FROWNING      = "Frowning"
    EYES_CLOSED   = "Eyes_Closed"


class PhoneState:
    NONE          = "None"
    HOLDING       = "Holding_Phone"
    SCROLLING     = "Scrolling_Phone"
    GAMING        = "Gaming"


# ─────────────────────────────────────────────
# PoseAnalyzer + FaceLandmarker (mediapipe 0.10+)
# ─────────────────────────────────────────────

class PoseAnalyzer:
    """
    增强版姿态 + 表情分析器（mediapipe 0.10+）
    - PoseLandmarker：检测人体骨架 → 工作状态
    - FaceLandmarker：检测面部特征 → 表情状态
    - 历史帧缓冲区：用于多帧联合判断（分心、喝水、游戏等）
    """

    # ── FaceMesh 关键点索引（MediaPipe FaceMesh 468点）─────────────
    # 左眼
    _LEFT_EYE_INNER = 133   # 内角
    _LEFT_EYE_OUTER = 33    # 外角
    _LEFT_EYE_TOP   = 159   # 上睑
    _LEFT_EYE_BOTTOM = 145  # 下睑
    # 右眼
    _RIGHT_EYE_INNER = 362
    _RIGHT_EYE_OUTER = 263
    _RIGHT_EYE_TOP    = 386
    _RIGHT_EYE_BOTTOM = 374
    # 嘴部
    _MOUTH_LEFT   = 61   # 嘴角左
    _MOUTH_RIGHT  = 291  # 嘴角右
    _MOUTH_TOP    = 13   # 上唇中
    _MOUTH_BOTTOM = 14   # 下唇中
    # 眉毛
    _LEFT_BROW_INNER  = 107
    _RIGHT_BROW_INNER = 336
    # 鼻尖（辅助参考）
    _NOSE_TIP = 4

    # ── Pose 关键点索引 ──────────────────────────────────────────
    _NOSE             = 0
    _LEFT_SHOULDER    = 11
    _RIGHT_SHOULDER   = 12
    _LEFT_WRIST       = 15
    _RIGHT_WRIST      = 16
    _LEFT_ELBOW       = 13
    _RIGHT_ELBOW      = 14
    _LEFT_EAR         = 7
    _RIGHT_EAR        = 8

    def __init__(self):
        # Pose 模型
        pose_path = self._model_path('pose_landmarker_full.task')
        self._pose_landmarker = PoseLandmarker.create_from_model_path(pose_path)

        # Face 模型
        face_path = self._model_path('face_landmarker.task')
        self._face_landmarker = FaceLandmarker.create_from_model_path(face_path)

        # 状态追踪
        self._phone_start_time: float | None = None
        self._last_pose_state: str = State.UNKNOWN

        # 历史帧缓冲区（用于多帧联合判断）
        self._pose_history: deque = deque(maxlen=90)   # ~3秒 @30fps
        self._wrist_y_history: deque  = deque(maxlen=30)  # 手腕抖动检测
        self._head_x_history: deque   = deque(maxlen=90)  # 头部偏移检测
        self._wrist_near_mouth_history: deque = deque(maxlen=60)  # 喝水检测 ~2秒

        # 表情持续时间追踪
        self._yawn_start: float | None = None
        self._eyes_closed_start: float | None = None
        self._frown_start: float | None = None

        # 喝水中头后仰持续时间
        self._drink_start: float | None = None

        # 环境状态（多人/对话/分心）
        self._multi_person_count: int = 0
        self._distracted_since: float | None = None
        self._last_face_state: str = FaceState.NEUTRAL

    @staticmethod
    def _model_path(name: str) -> str:
        p = os.path.join(os.path.dirname(__file__), name)
        return p if os.path.exists(p) else name

    # ── 检测 ───────────────────────────────────────────────────

    def detect_pose(self, frame):
        """检测人体骨架，返回 landmarks 列表（可能有多人）或 None"""
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = self._pose_landmarker.detect(img)
        return result.pose_landmarks if result.pose_landmarks else None

    def detect_face(self, frame):
        """检测面部特征，返回 face_landmarks 或 None"""
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = self._face_landmarker.detect(img)
        if result.face_landmarks and len(result.face_landmarks) > 0:
            return result.face_landmarks[0]
        return None

    # ── 姿态分析 ───────────────────────────────────────────────

    def analyze_pose(self, landmarks, frame_shape: tuple) -> str:
        """根据 landmarks 分析工作状态（主状态）"""
        h, w = frame_shape[:2]

        avg_vis = sum(lm.visibility for lm in landmarks) / len(landmarks)
        if avg_vis < 0.5:
            return State.AWAY

        nose   = landmarks[self._NOSE]
        ls     = landmarks[self._LEFT_SHOULDER]
        rs     = landmarks[self._RIGHT_SHOULDER]
        lw     = landmarks[self._LEFT_WRIST]
        rw     = landmarks[self._RIGHT_WRIST]

        nose_x, nose_y = nose.x * w, nose.y * h
        ls_x, ls_y     = ls.x * w, ls.y * h
        rs_x, rs_y     = rs.x * w, rs.y * h

        mid_shoulder_y  = (ls_y + rs_y) / 2
        shoulder_width  = abs(rs_x - ls_x)
        head_diff       = nose_y - mid_shoulder_y

        # 低头 → 睡眠
        if head_diff < shoulder_width * 0.5:
            return State.SLEEP

        lw_y = lw.y * h
        rw_y = rw.y * h

        wrist_low = (lw_y > mid_shoulder_y + shoulder_width * 0.3 or
                     rw_y > mid_shoulder_y + shoulder_width * 0.3)
        mid_shoulder_x = (ls_x + rs_x) / 2
        head_fwd = abs(nose_x - mid_shoulder_x)

        if wrist_low and head_fwd > shoulder_width * 0.3:
            return State.PHONE

        return State.WORK

    def update_state(self, new_state: str, current_time: float) -> tuple:
        is_changed = new_state != self._last_pose_state
        if is_changed:
            self._last_pose_state = new_state
            self._phone_start_time = None
            return True, True

        if new_state == State.PHONE:
            if self._phone_start_time is None:
                self._phone_start_time = current_time
            elif (current_time - self._phone_start_time) >= CONFIG["phone_duration"]:
                self._phone_start_time = current_time
                return True, True

        return False, False

    # ── 表情分析 ───────────────────────────────────────────────

    def analyze_face(self, face_landmarks, frame_shape: tuple) -> str:
        """
        基于 FaceMesh 关键点分析表情。
        返回：Smiling / Yawning / Frowning / Eyes_Closed / Neutral
        """
        h, w = frame_shape[:2]
        now = time.time()

        def pt(idx):
            lm = face_landmarks[idx]
            return lm.x * w, lm.y * h

        # ── 眼睛 EAR（Eye Aspect Ratio）────────────────────────
        def eye_ear(inner, outer, top, bottom):
            _,   inner_y = pt(inner)
            _,   outer_y = pt(outer)
            _,   top_y   = pt(top)
            _,   bottom_y= pt(bottom)
            ear = abs(top_y - bottom_y) / (abs(inner_y - outer_y) + 1e-6)
            return ear

        left_ear  = eye_ear(self._LEFT_EYE_INNER,  self._LEFT_EYE_OUTER,
                             self._LEFT_EYE_TOP,    self._LEFT_EYE_BOTTOM)
        right_ear = eye_ear(self._RIGHT_EYE_INNER, self._RIGHT_EYE_OUTER,
                             self._RIGHT_EYE_TOP,   self._RIGHT_EYE_BOTTOM)
        avg_ear   = (left_ear + right_ear) / 2

        # EAR < 0.2 持续 → 闭眼
        if avg_ear < 0.2:
            if self._eyes_closed_start is None:
                self._eyes_closed_start = now
            elif now - self._eyes_closed_start > 1.0:   # 持续1秒
                self._yawn_start = None
                self._frown_start = None
                return FaceState.EYES_CLOSED
        else:
            self._eyes_closed_start = None

        # ── 嘴部 MAR（Mar Aspect Ratio）─────────────────────────
        ml_x,  ml_y  = pt(self._MOUTH_LEFT)
        mr_x,  mr_y  = pt(self._MOUTH_RIGHT)
        mt_x,  mt_y  = pt(self._MOUTH_TOP)
        mb_x,  mb_y  = pt(self._MOUTH_BOTTOM)

        mouth_width = abs(mr_x - ml_x)
        mouth_height = abs(mb_y - mt_y)
        mar = mouth_height / (mouth_width + 1e-6)

        # MAR > 0.5 持续 → 打哈欠
        if mar > 0.5:
            if self._yawn_start is None:
                self._yawn_start = now
            elif now - self._yawn_start > 1.5:   # 持续1.5秒
                self._eyes_closed_start = None
                self._frown_start = None
                return FaceState.YAWNING
        else:
            self._yawn_start = None

        # ── 眉毛倾斜度 ──────────────────────────────────────────
        lbi_x, lbi_y = pt(self._LEFT_BROW_INNER)
        rbi_x, rbi_y = pt(self._RIGHT_BROW_INNER)
        brow_diff = (lbi_y - rbi_y) / (abs(lbi_x - rbi_x) + 1e-6)

        # 眉毛明显下压 → 皱眉
        if brow_diff > 0.15:
            if self._frown_start is None:
                self._frown_start = now
            elif now - self._frown_start > 1.0:
                return FaceState.FROWNING
        else:
            self._frown_start = None

        # ── 微笑检测：嘴角上扬 + 嘴宽比 ─────────────────────────
        nose_x, nose_y = pt(self._NOSE_TIP)
        mouth_center_x = (ml_x + mr_x) / 2
        mouth_center_y = (mt_y + mb_y) / 2
        nose_to_mouth  = mouth_center_y - nose_y

        # 嘴宽较大且居中 → 微笑（简化判断）
        if mouth_width > w * 0.25 and nose_to_mouth > h * 0.05:
            return FaceState.SMILING

        return FaceState.NEUTRAL

    # ── 手机使用分析 ───────────────────────────────────────────

    def analyze_phone_usage(self, landmarks, frame_shape: tuple) -> str:
        """
        结合手腕、肘部、头部关键点，分析手机使用姿态。
        返回：None / Holding_Phone / Scrolling_Phone / Gaming
        """
        h, w = frame_shape[:2]

        def py(idx): return landmarks[idx].y * h
        def px(idx): return landmarks[idx].x * w

        lw_y, rw_y = py(self._LEFT_WRIST),  py(self._RIGHT_WRIST)
        le_y,  re_y = py(self._LEFT_ELBOW), py(self._RIGHT_ELBOW)
        nose_y      = py(self._NOSE)
        nose_x      = px(self._NOSE)

        # 手腕是否低于肩膀附近（拿手机姿势）
        shoulder_mid_y = (py(self._LEFT_SHOULDER) + py(self._RIGHT_SHOULDER)) / 2
        wrist_near_shoulder = (lw_y > shoulder_mid_y - h * 0.15 or
                                rw_y > shoulder_mid_y - h * 0.15)

        # 手腕靠近头部（手机在面前）
        wrist_near_head = (abs(lw_y - nose_y) < h * 0.25 or
                           abs(rw_y - nose_y) < h * 0.25)

        if not (wrist_near_shoulder and wrist_near_head):
            self._wrist_y_history.clear()
            return PhoneState.NONE

        # ── 手腕抖动检测（连续帧间 y 方向快速变化）───────────────
        self._wrist_y_history.append((lw_y, rw_y, time.time()))
        if len(self._wrist_y_history) >= 10:
            deltas = []
            history = list(self._wrist_y_history)
            for i in range(1, len(history)):
                prev_y = (history[i-1][0] + history[i-1][1]) / 2
                curr_y = (history[i][0]   + history[i][1])   / 2
                dt = history[i][2] - history[i-1][2]
                if dt > 0:
                    deltas.append(abs(curr_y - prev_y) / dt)

            avg_delta = sum(deltas) / len(deltas) if deltas else 0
            shake_threshold = h * 0.02   # 帧间抖动 > 2% 高度

            if avg_delta > shake_threshold:
                # ── 游戏检测：横屏快速滑动 ──────────────────────
                # 游戏时手部靠近屏幕中央，且高频抖动
                screen_center_x = w / 2
                wrist_x = (px(self._LEFT_WRIST) + px(self._RIGHT_WRIST)) / 2
                if abs(wrist_x - screen_center_x) < w * 0.3:
                    return PhoneState.GAMING
                return PhoneState.SCROLLING

        return PhoneState.HOLDING

    # ── 环境分析 ──────────────────────────────────────────────

    def analyze_environment(self, all_pose_landmarks, frame_shape: tuple) -> dict:
        """
        多人体骨架分析。
        - 检测人数 → someone_passed_by / talking
        - 头部偏转 → distracted
        """
        result = {
            "multi_person": False,
            "someone_passed_by": False,
            "talking": False,
            "distracted": False,
        }
        h, w = frame_shape[:2]
        now = time.time()

        # ── 多人检测 ─────────────────────────────────────────────
        person_count = len(all_pose_landmarks)
        if person_count > 1:
            result["multi_person"] = True
            result["someone_passed_by"] = True
            self._multi_person_count = person_count

        # ── 头部偏转（分心）─── 记录历史 ─────────────────────────
        if all_pose_landmarks:
            main = all_pose_landmarks[0]  # 以主用户为准
            if len(main) > self._RIGHT_EAR:
                nose_x = main[self._NOSE].x * w
                ls_x   = main[self._LEFT_SHOULDER].x * w
                rs_x   = main[self._RIGHT_SHOULDER].x * w
                mid_shoulder_x = (ls_x + rs_x) / 2
                head_offset = abs(nose_x - mid_shoulder_x)
                shoulder_width = abs(rs_x - ls_x)
                self._head_x_history.append(head_offset)
            else:
                self._head_x_history.clear()
        else:
            self._head_x_history.clear()
            self._distracted_since = None

        # 持续 3 秒以上头部偏转 > 30% 肩宽 → 分心
        if len(self._head_x_history) >= self._head_x_history.maxlen * 0.7:
            avg_offset = sum(self._head_x_history) / len(self._head_x_history)
            if hasattr(self, '_last_shoulder_width') and self._last_shoulder_width > 0:
                ratio = avg_offset / max(self._last_shoulder_width, 1)
                if ratio > 0.3:
                    if self._distracted_since is None:
                        self._distracted_since = now
                    elif now - self._distracted_since > 3.0:
                        result["distracted"] = True
                else:
                    self._distracted_since = None

        return result

    # ── 喝水检测 ───────────────────────────────────────────────

    def check_drinking(self, landmarks, frame_shape: tuple) -> bool:
        """
        检测手部靠近嘴部 + 头部轻微后仰。
        持续 2 秒判定为喝水。
        返回：True（正在喝水）/ False
        """
        h, w = frame_shape[:2]
        now = time.time()

        def pt(idx):
            lm = landmarks[idx]
            return lm.x * w, lm.y * h

        lw_x, lw_y = pt(self._LEFT_WRIST)
        rw_x, rw_y = pt(self._RIGHT_WRIST)
        mt_x, mt_y = pt(self._MOUTH_TOP)
        mb_x, mb_y = pt(self._MOUTH_BOTTOM)
        nose_x, nose_y = pt(self._NOSE)
        ls_x, ls_y = pt(self._LEFT_SHOULDER)
        rs_x, rs_y = pt(self._RIGHT_SHOULDER)

        mouth_center_x = (mt_x + mb_x) / 2
        mouth_center_y = (mt_y + mb_y) / 2
        mid_shoulder_y  = (ls_y + rs_y) / 2

        # 手腕靠近嘴边（x,y 均接近）
        dist_l = ((lw_x - mouth_center_x)**2 + (lw_y - mouth_center_y)**2) ** 0.5
        dist_r = ((rw_x - mouth_center_x)**2 + (rw_y - mouth_center_y)**2) ** 0.5
        min_dist = min(dist_l, dist_r)

        # 头部后仰：鼻尖 y < 肩部 y（即头部向上抬起）
        head_tilted = nose_y < mid_shoulder_y - h * 0.05

        # 手腕在嘴边附近 且 有后仰动作
        near_mouth = min_dist < w * 0.15
        self._wrist_near_mouth_history.append(1 if (near_mouth and head_tilted) else 0)

        # 持续 2 秒
        recent = list(self._wrist_near_mouth_history)
        if len(recent) >= 60:   # 约2秒@30fps
            window = recent[-60:]
            if sum(window) / len(window) > 0.7:  # 70%以上帧符合
                return True

        return False

    # ── 全量分析（主入口）──────────────────────────────────────

    def analyze_all(self, frame) -> dict:
        """
        对一帧执行全部分析，返回汇总字典。
        调用顺序：姿态 → 表情 → 手机 → 环境 → 喝水
        """
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w = rgb.shape[:2]

        result = {
            "pose_state":   State.UNKNOWN,
            "face_state":   FaceState.NEUTRAL,
            "phone_state":  PhoneState.NONE,
            "drinking":     False,
            "env": {
                "multi_person":     False,
                "someone_passed_by": False,
                "talking":          False,
                "distracted":       False,
            },
            "timestamp":    datetime.now().strftime("%H:%M:%S"),
        }

        # 姿态检测（可能多人）
        pose_landmarks = self.detect_pose(frame)
        if pose_landmarks:
            main_landmarks = pose_landmarks[0]
            result["pose_state"] = self.analyze_pose(main_landmarks, frame.shape)
        else:
            main_landmarks = None

        # 表情检测
        face_landmarks = self.detect_face(frame)
        if face_landmarks:
            result["face_state"] = self.analyze_face(face_landmarks, frame.shape)

        # 手机使用
        if main_landmarks:
            result["phone_state"] = self.analyze_phone_usage(main_landmarks, frame.shape)

        # 环境分析（多人 + 分心）
        if pose_landmarks:
            result["env"] = self.analyze_environment(pose_landmarks, frame.shape)

        # 喝水检测
        if main_landmarks:
            result["drinking"] = self.check_drinking(main_landmarks, frame.shape)

        # 控制台输出
        ts = result["timestamp"]
        print(f"[{ts}] State: {result['pose_state']}, "
              f"Face: {result['face_state']}, "
              f"Phone: {result['phone_state']}, "
              f"Drink: {result['drinking']}", flush=True)

        return result


# ─────────────────────────────────────────────
# 日志
# ─────────────────────────────────────────────
def setup_logging():
    Path(CONFIG["screenshots_dir"]).mkdir(parents=True, exist_ok=True)
    Path(CONFIG["reports_dir"]).mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(CONFIG["log_file"], encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    return logging.getLogger(__name__)

logger = setup_logging()


# ─────────────────────────────────────────────
# 工具函数
# ─────────────────────────────────────────────
def get_today_dir(base_dir: str) -> Path:
    today = datetime.now().strftime("%Y-%m-%d")
    p = Path(base_dir) / today
    p.mkdir(parents=True, exist_ok=True)
    return p


def ensure_dirs():
    for d in [CONFIG["screenshots_dir"], CONFIG["reports_dir"]]:
        Path(d).mkdir(parents=True, exist_ok=True)


def image_to_base64(image_path: str) -> str:
    with open(image_path, "rb") as f:
        data = base64.b64encode(f.read()).decode("utf-8")
    ext = os.path.splitext(image_path)[1].lower().lstrip(".")
    mime = f"image/{ext}" if ext in ("jpg", "jpeg", "png", "webp") else "image/jpeg"
    return f"data:{mime};base64,{data}"


def select_representative_screenshots(screenshot_paths: list, max_count: int = 10) -> list:
    if len(screenshot_paths) <= max_count:
        return screenshot_paths
    sorted_paths = sorted(screenshot_paths, key=lambda p: os.path.basename(p))
    step = max(1, len(sorted_paths) // max_count)
    return sorted_paths[:max(1, max_count)][::step or 1][:max_count]


def init_camera(camera_index: int = 0) -> cv2.VideoCapture:
    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        raise RuntimeError("Cannot open camera")
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    return cap



# ─────────────────────────────────────────────
# ScreenshotManager
# ─────────────────────────────────────────────
class ScreenshotManager:
    def __init__(self, base_dir: str):
        self.base_dir = base_dir
        self.today_dir = get_today_dir(base_dir)

    def refresh_today_dir(self):
        new_dir = get_today_dir(self.base_dir)
        if new_dir != self.today_dir:
            self.today_dir = new_dir

    def save(self, frame, state: str) -> str:
        self.refresh_today_dir()
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"{ts}_{state}.jpg"
        filepath = self.today_dir / filename
        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 90]
        cv2.imwrite(str(filepath), frame, encode_param)
        return str(filepath)

    def count_today(self) -> int:
        self.refresh_today_dir()
        return len(list(self.today_dir.glob("*.jpg"))) + len(list(self.today_dir.glob("*.png")))


# ─────────────────────────────────────────────
# DailyReportGenerator
# ─────────────────────────────────────────────
class DailyReportGenerator:
    SYSTEM_PROMPT = (
        "你是一个幽默的私人助理。我会给你我今天的几张工作状态截图。"
        "请根据这些图片，帮我生成一份简短、风趣的中文工作日报（Markdown格式）。"
        "包含：\n"
        "1. 今日工作总览（根据图片推断）。\n"
        "2. 一个有趣的观察和槽点。\n"
        "3. 明日改进小建议。\n"
        "只输出日报内容，不要添加额外解释。\n"
        "语气要轻松、幽默、接地气，像朋友在调侃一样。"
    )

    def __init__(self, base_url: str, api_key: str, model: str):
        self.client = OpenAI(base_url=base_url, api_key=api_key, timeout=120.0)
        self.model = model

    def generate(self, date_str: str, screenshot_paths: list) -> str:
        if not screenshot_paths:
            return self._empty_report(date_str)

        selected = select_representative_screenshots(screenshot_paths, max_count=10)
        content = [{"type": "text", "text": f"请分析以下 {len(selected)} 张图片，日期：{date_str}"}]
        for path in selected:
            try:
                content.append({"type": "image_url", "image_url": {"url": image_to_base64(path)}})
            except Exception as e:
                logger.warning(f"无法读取截图 {path}: {e}")

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": content},
                ],
                max_tokens=2048,
                temperature=0.8,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"调用大模型失败: {e}")
            return self._error_report(date_str, str(e))

    @staticmethod
    def _empty_report(date_str: str) -> str:
        return f"""# 📋 工作日报 — {date_str}

## 今日总览
今日未检测到明显状态变化，可能是休息日或者摄像头没对准人 🎯

## 有趣观察
今天的状态数据少得像...我找不到任何梗，因为真的什么都没有 😴

## 明日建议
试试把摄像头对准自己？
"""

    @staticmethod
    def _error_report(date_str: str, error: str) -> str:
        return f"""# 📋 工作日报 — {date_str}

## 生成状态
⚠️ 日报生成遇到问题：{error}

## 今日总览
今日截图分析失败，可能是 API 额度用尽或网络问题。

## 有趣观察
今天的日报比我的理解能力还难懂 🐛

## 明日建议
检查 API Key 是否有效，网络是否畅通。
"""


# ─────────────────────────────────────────────
# DailyScheduler
# ─────────────────────────────────────────────
class DailyScheduler:
    def __init__(self, hour: int, minute: int):
        self.hour = hour
        self.minute = minute
        self.triggered_today = False
        self._check_and_reset()

    def _check_and_reset(self):
        now = datetime.now()
        today_key = now.date()
        if hasattr(self, "_last_date") and self._last_date != today_key:
            self.triggered_today = False
        self._last_date = today_key

    def check(self) -> bool:
        self._check_and_reset()
        if self.triggered_today:
            return False
        now = datetime.now()
        if now.hour == self.hour and now.minute == self.minute:
            self.triggered_today = True
            return True
        return False


# ─────────────────────────────────────────────
# WorkStatusMonitor（CLI 入口用）
# ─────────────────────────────────────────────
class WorkStatusMonitor:
    def __init__(self, cfg: dict | None = None):
        if cfg:
            CONFIG.update(cfg)
        load_config()
        ensure_dirs()
        self.cap: cv2.VideoCapture | None = None
        self.analyzer = PoseAnalyzer()
        self.screenshot_mgr = ScreenshotManager(CONFIG["screenshots_dir"])
        self.scheduler = DailyScheduler(CONFIG["report_hour"], CONFIG["report_minute"])
        self.report_generator: DailyReportGenerator | None = None
        self._running = Event()
        self._current_state = State.UNKNOWN
        self._screenshot_count = 0

    @property
    def current_state(self) -> str:
        return self._current_state

    @property
    def screenshot_count(self) -> int:
        return self.screenshot_mgr.count_today()

    def _init_report_generator(self):
        if self.report_generator is None:
            self.report_generator = DailyReportGenerator(
                CONFIG["doubao_base_url"],
                CONFIG["doubao_api_key"],
                CONFIG["doubao_model"],
            )

    def _collect_today_screenshots(self) -> list:
        today_dir = get_today_dir(CONFIG["screenshots_dir"])
        if not today_dir.exists():
            return []
        return sorted(today_dir.glob("*.jpg")) + sorted(today_dir.glob("*.png"))

    def _trigger_daily_report(self):
        today_str = datetime.now().strftime("%Y-%m-%d")
        report_file = Path(CONFIG["reports_dir"]) / f"{today_str}.md"
        if report_file.exists():
            logger.info(f"今日日报已存在: {report_file}，跳过生成")
            return
        self._init_report_generator()
        screenshots = [str(p) for p in self._collect_today_screenshots()]
        report_text = self.report_generator.generate(today_str, screenshots)
        with open(report_file, "w", encoding="utf-8") as f:
            f.write(report_text)
        logger.info(f"日报已保存: {report_file}")

    def process_frame(self, frame) -> tuple:
        """处理单帧，返回 (state, should_screenshot)"""
        result = self.analyzer.analyze_all(frame)
        state = result["pose_state"]
        self._current_state = state
        _, should_screenshot = self.analyzer.update_state(state, time.time())
        return state, should_screenshot

    def run(self):
        """CLI 主循环（阻塞）"""
        self._running.set()
        try:
            self.cap = init_camera(0)
        except Exception as e:
            logger.error(f"摄像头初始化失败: {e}")
            return

        logger.info("智能工作状态监测系统已启动（CLI模式）")
        logger.info(f"日报生成时间: {CONFIG['report_hour']:02d}:{CONFIG['report_minute']:02d}")
        logger.info("按 Ctrl+C 退出")

        frame_count = 0
        skip_frames = max(1, int(CONFIG["frame_interval"] * 30))

        try:
            while self._running.is_set():
                success, frame = self.cap.read()
                if not success:
                    time.sleep(1)
                    self.cap.release()
                    self.cap = init_camera(0)
                    continue

                frame_count += 1
                if frame_count % skip_frames != 0:
                    continue

                state, should_screenshot = self.process_frame(frame)
                ts = datetime.now().strftime("%H:%M:%S")
                print(f"\r{ts} {state}", end="", flush=True)

                if should_screenshot and CONFIG["screenshot_on_change"]:
                    self.screenshot_mgr.save(frame, state)

                if self.scheduler.check():
                    print()
                    self._trigger_daily_report()

        except KeyboardInterrupt:
            pass
        finally:
            self._cleanup()

    def _cleanup(self):
        if self.cap:
            self.cap.release()
        logger.info("程序结束")

    def stop(self):
        self._running.clear()
