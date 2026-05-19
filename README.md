# 智能工作状态监测与日报系统

> 摄像头实时监测工作状态 → 本地分析 + 云端幽默日报生成，支持图形界面查看。

## 界面预览

```
┌──────────────────────────────────────────────────────┐
│ ▶ 开始监测  ■ 停止      ⚙ 设置  🔄 刷新日报           │
├──────────┬──────────────────────┬───────────────────┤
│ 📅 日报列表 │ 📄 日报预览            │ 📊 今日统计        │
│ 📄 2025-05-18 │ # 📋 工作日报      │ 💻 专注时长: 65%   │
│ 📄 2025-05-17 │ ## 今日总览        │ 📱 摸鱼占比: 20%   │
│ 📄 2025-05-16 │ ...                │ 😴 休息: 3次       │
│           │                      │ 📸 截图数: 12     │
├──────────┴──────────────────────┴───────────────────┤
│ 🟢 监测中...  状态: 💻 Working   📅 2025-05-18        │
└──────────────────────────────────────────────────────┘
```

## 项目结构

```
.
├── main_gui.py          # GUI 入口（推荐）⭐
├── main.py              # CLI 入口（后台静默运行）
├── backend.py           # 核心逻辑（GUI 与 CLI 共用）
├── gui/
│   ├── main_window.py   # 主窗口
│   ├── monitor_thread.py # 后台监测线程
│   ├── report_viewer.py  # Markdown 日报渲染
│   └── settings_dialog.py # 设置对话框
├── config.json          # 配置文件（首次运行后自动生成）
├── screenshots/         # 状态截图（自动创建）
├── daily_reports/       # 日报输出（自动创建）
└── requirements.txt     # 依赖
```

## 安装依赖

```bash
pip install -r requirements.txt
```

## 运行

### 方式一：图形界面（推荐）⭐
```bash
python main_gui.py
```
- 三栏窗口：日报列表 | 日报预览 | 今日统计
- 系统托盘：最小化到托盘，后台持续监测
- 点击日报日期查看详情，支持 Markdown 渲染

### 方式二：命令行
```bash
python main.py
```

## 配置

首次运行后会自动生成 `config.json`，或点击界面右上角「⚙ 设置」。

```json
{
    "doubao_base_url": "https://ark.cn-beijing.volces.com/api/v3",
    "doubao_api_key": "YOUR_API_KEY_HERE",
    "doubao_model": "ep-2025xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "report_hour": 18,
    "report_minute": 0,
    "screenshot_on_change": true
}
```

**获取豆包 API Key：** 登录[火山引擎控制台](https://console.volceengine.com/)，创建方舟推理接入点。

## 状态说明

| 状态 | 含义 | 颜色 |
|---|---|---|
| 💻 Working | 专注工作 | 🟢 绿 |
| 📱 Phone | 玩手机 | 🔴 红 |
| 😴 Sleep | 趴桌/睡觉 | 🟠 橙 |
| 🚶 Away | 离开座位 | ⚪ 灰 |
| ❓ Unknown | 未检测到人 | 灰 |

## 隐私说明

- **摄像头流完全在本地处理**，不上传到任何服务器
- 每日日报仅上传**已保存的本地截图**（用户可控）
- 建议工位使用时告知同事或设置明显标识

## 常见问题

**Q: 摄像头打不开？**
> 确保摄像头未被其他程序占用，或修改 `backend.py` 中 `init_camera(0)` 的索引值。

**Q: 界面没有反应？**
> 检查是否缺少 `PyQt5`，运行 `pip install PyQt5`。

**Q: 日报没有生成？**
> 检查 API Key 是否正确、额度是否充足，查看 `status_monitor.log`。
