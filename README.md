# WorkBuddy · 智能工作状态监测

> 摄像头实时监测工作状态 → 本地 AI 分析 + 云端幽默日报生成，附带图形界面。

[![Python 3.8+](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/)
[![PyQt5](https://img.shields.io/badge/GUI-PyQt5-green.svg)](https://pypi.org/project/PyQt5/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

---

## ✨ 功能特性

| 模块 | 说明 |
|------|------|
| 🎥 实时监测 | MediaPipe 姿态/面部识别，本地处理，不上传摄像头数据 |
| 📊 状态分析 | 自动识别 💻 工作 / 📱 玩手机 / 😴 趴桌 / 🚶 离开 |
| 📝 AI 日报 | 调用豆包 API 生成每日工作日报（幽默风格） |
| 🍅 番茄钟 | 内置 25 分钟专注 + 5 分钟休息计时器 |
| 🖥️ 系统托盘 | 最小化到托盘，后台持续监测 |
| 📈 数据可视化 | 专注时长统计图、状态时间轴 |

---

## 📦 项目结构

```
WorkBuddy/
├── main_gui.py            # GUI 入口（推荐）⭐
├── main.py                # CLI 入口（后台静默运行）
├── backend.py             # 核心逻辑（GUI 与 CLI 共用）
├── config.json            # 配置文件（首次运行自动生成）
├── requirements.txt        # Python 依赖
├── gui/
│   ├── main_window.py     # 主窗口（三栏布局 + Tab 分页）
│   ├── monitor_thread.py  # 后台摄像头监测线程
│   ├── report_viewer.py   # Markdown 日报渲染
│   └── settings_dialog.py # 设置对话框
├── face_landmarker.task   # MediaPipe 面部 landmark 模型（已内含）
├── pose_landmarker_full.task  # MediaPipe 姿态 landmark 模型（已内含）
├── screenshots/           # 状态截图（运行时自动创建）
└── daily_reports/        # 日报输出（运行时自动创建）
```

---

## 🚀 快速开始

### 环境要求

| 依赖 | 版本要求 |
|------|---------|
| Python | 3.8 及以上 |
| 摄像头 | 内置或外接均可 |
| 系统 | Windows / macOS / Linux |

> **Linux 用户注意**：PyQt5 需要系统图形库支持，Ubuntu/Debian 请先运行：
> ```bash
> sudo apt install python3-pyqt5 python3-opencv libxcb-xinerama0
> ```

### 安装步骤

**1. 克隆仓库**

```bash
git clone https://github.com/LX-ZS/WorkBuddy.git
cd WorkBuddy
```

**2. 安装 Python 依赖**

```bash
pip install -r requirements.txt
```

> 依赖说明：`opencv-python` · `mediapipe` · `openai` · `PyQt5` · `matplotlib`
> 安装耗时约 2~5 分钟，取决于网络速度。

**3. 配置豆包 API（可选，日报功能需要）**

首次运行后会自动生成 `config.json`，也可以点击界面右上角 **⚙ 设置** 填写：

```json
{
    "doubao_base_url": "https://ark.cn-beijing.volces.com/api/v3",
    "doubao_api_key": " YOUR_API_KEY_HERE ",
    "doubao_model": "ep-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "report_hour": 18,
    "report_minute": 0,
    "screenshot_on_change": true
}
```

> **获取豆包 API Key**：登录 [火山引擎控制台](https://console.volceengine.com/)，创建方舟推理接入点，获取 API Key 和 Model ID。

**4. 运行**

```bash
python main_gui.py
```

---

## 🖥️ 使用说明

启动后界面分为三栏：

```
┌──────────────────────────────────────────────────────┐
│  ▶ 开始监测    ■ 停止        ⚙ 设置    🔄 刷新日报      │
├──────────┬──────────────────────┬───────────────────┤
│  📅 日报列表 │ 📄 日报内容预览      │ 📊 概览 | 🔬 分析 | 🍅 番茄钟 │
│           │                      │                   │
│  (日报日期)  │  (Markdown 渲染)     │  (Tab 分页右侧)   │
├──────────┴──────────────────────┴───────────────────┤
│  🟢 监测中...  状态: 💻 Working      📅 2026-05-19     │
└──────────────────────────────────────────────────────┘
```

### 右侧面板三个 Tab

| Tab | 功能 |
|-----|------|
| 📊 概览 | 实时状态徽章 + 今日统计卡片 |
| 🔬 分析 | 实时分析详情 + 状态时间轴图表 |
| 🍅 番茄钟 | 25 分钟专注 / 5 分钟休息，到期桌面通知 |

### 系统托盘

关闭窗口后会最小化到系统托盘，右键托盘图标可：
- 快速开始/停止监测
- 查看当前状态
- 退出程序

---

## 🎯 状态说明

| 状态 | 含义 | 触发条件 |
|------|------|---------|
| 💻 Working | 专注工作 | 坐姿端正，面对摄像头 |
| 📱 Phone | 玩手机 | 手部区域靠近头部，姿态异常 |
| 😴 Sleep | 趴桌/睡觉 | 头部位置偏低，姿态倾斜 |
| 🚶 Away | 离开座位 | 未检测到人体 |
| ❓ Unknown | 未知 | 初始化或检测失败 |

---

## ⚙️ 配置参数说明

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `doubao_api_key` | 豆包 API Key（日报功能必填） | 空 |
| `doubao_model` | 豆包模型 ID | 空 |
| `report_hour` | 日报生成小时（24小时制） | 18 |
| `report_minute` | 日报生成分钟 | 0 |
| `screenshot_on_change` | 状态改变时自动截图 | true |

---

## 🔒 隐私说明

- **摄像头数据完全本地处理**，不上传任何原始视频/图像到服务器
- 日报生成仅使用**状态标签和截图**，不包含原始摄像头画面
- 所有数据存储在本地 `screenshots/` 和 `daily_reports/` 目录
- 建议在工位使用时**告知同事**或设置明显标识

---

## ❓ 常见问题

**Q: 摄像头打不开？**
> 确保摄像头未被其他程序（微信、QQ、浏览器）占用。
> 若仍无法打开，修改 `backend.py` 中 `init_camera(0)` 的索引值，尝试 `1`、`2` 等。

**Q: 安装 mediapipe 失败？**
> MediaPipe 需要 Python 3.8~3.11（部分版本不支持 3.12+）。
> 建议使用 Python 3.10：
> ```bash
> conda create -n workbuddy python=3.10
> conda activate workbuddy
> pip install -r requirements.txt
> ```

**Q: GUI 界面没有反应？**
> 检查 PyQt5 是否安装成功：
> ```bash
> python -c "import PyQt5; print(PyQt5.QtCore.PYQT_VERSION_STR)"
> ```
> Linux 用户可能需要安装额外系统包（见上方「环境要求」）。

**Q: 日报没有生成？**
> 检查：① `config.json` 中 API Key 是否正确；② 火山引擎账号额度是否充足；③ 查看 `status_monitor.log` 错误日志。

**Q: MediaPipe 模型文件太大，克隆很慢？**
> `face_landmarker.task` 和 `pose_landmarker_full.task` 已包含在仓库中（约 10MB 合计）。
> 若不需要重新下载，也可从 [MediaPipe 官网](https://developers.google.com/mediapipe/solutions/vision/face_landmarker) 自行下载后放入项目根目录。

---

## 📄 License

MIT License —— 欢迎 Fork、修改、二次发布。

---

## 🙏 致谢

- [MediaPipe](https://developers.google.com/mediapipe) —— 姿态与面部识别
- [PyQt5](https://pypi.org/project/PyQt5/) —— GUI 框架
- [火山引擎·豆包](https://www.volceengine.com/) —— AI 日报生成
