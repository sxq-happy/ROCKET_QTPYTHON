# main.py - 程序入口点与主窗口
import sys
import os
import argparse
import json
import time
import queue
import threading
import subprocess
import random
from datetime import datetime
from pathlib import Path
import serial
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QStackedWidget, QPushButton, QLabel,
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QFrame,
    QMessageBox, QStatusBar, QDialog, QComboBox, QDockWidget, QFileDialog
)
from PySide6.QtCore import Qt, QSize, QTimer, QObject, Signal
from PySide6.QtGui import QIcon, QAction, QFont, QPixmap


# 导入自定义组件
# 假设 video_components.py 和 serial_components.py 文件存在且内容正确
from video_components import MultiCameraViewer
from control_components import ControlPanel, RocketControlConsole
from serial_components import SerialManager, SerialConfigDialog, SensorControlDialog, SensorDataDialog
from hmi_components import HMIPanel

# ═══════════════════════════════════════════════════════════════════════════
# 回放控制面板 (Replay Control Panel) —— 底部控制条
# ═══════════════════════════════════════════════════════════════════════════

class ReplayControlPanel(QWidget):
    """回放控制条：播放/暂停、重置、倍速切换"""

    play_requested = Signal()
    pause_requested = Signal()
    reset_requested = Signal()
    speed_changed = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._playing = False
        self._init_ui()

    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)

        self.play_pause_btn = QPushButton("▶ 播放")
        self.play_pause_btn.setMinimumWidth(90)
        self.play_pause_btn.setStyleSheet("""
            QPushButton {
                background-color: #27AE60;
                color: white;
                font-weight: bold;
                font-size: 12px;
                padding: 6px 12px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #2ECC71; }
            QPushButton:disabled { background-color: #BDC3C7; color: #7F8C8D; }
        """)
        self.play_pause_btn.clicked.connect(self._on_play_pause)
        layout.addWidget(self.play_pause_btn)

        self.reset_btn = QPushButton("⟲ 重置")
        self.reset_btn.setMinimumWidth(80)
        self.reset_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498DB;
                color: white;
                font-weight: bold;
                font-size: 12px;
                padding: 6px 12px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #2980B9; }
        """)
        self.reset_btn.clicked.connect(self._on_reset)
        layout.addWidget(self.reset_btn)

        speed_label = QLabel("倍速:")
        speed_label.setStyleSheet("font-weight: bold; color: #ECF0F1;")
        layout.addWidget(speed_label)

        self.speed_combo = QComboBox()
        self.speed_combo.addItems(["0.125x", "0.25x", "0.5x", "1.0x"])
        self.speed_combo.setCurrentIndex(3)
        self.speed_combo.setMinimumWidth(70)
        self.speed_combo.setStyleSheet("""
            QComboBox {
                background-color: #2C3E50;
                color: #ECF0F1;
                border: 1px solid #7F8C8D;
                border-radius: 3px;
                padding: 3px 6px;
            }
            QComboBox:hover { border-color: #3498DB; }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox QAbstractItemView {
                background-color: #2C3E50;
                color: #ECF0F1;
                selection-background-color: #3498DB;
                border: 1px solid #7F8C8D;
            }
        """)
        self.speed_combo.currentTextChanged.connect(self._on_speed_changed)
        layout.addWidget(self.speed_combo)

        layout.addStretch(1)

    def set_playing(self, playing):
        self._playing = playing
        if playing:
            self.play_pause_btn.setText("⏸ 暂停")
            self.play_pause_btn.setStyleSheet(self.play_pause_btn.styleSheet().replace(
                "background-color: #27AE60;", "background-color: #E67E22;"))
        else:
            self.play_pause_btn.setText("▶ 播放")
            self.play_pause_btn.setStyleSheet("""
                QPushButton {
                    background-color: #27AE60;
                    color: white;
                    font-weight: bold;
                    font-size: 12px;
                    padding: 6px 12px;
                    border-radius: 4px;
                }
                QPushButton:hover { background-color: #2ECC71; }
                QPushButton:disabled { background-color: #BDC3C7; color: #7F8C8D; }
            """)

    def _on_play_pause(self):
        if self._playing:
            self.set_playing(False)
            self.pause_requested.emit()
        else:
            self.set_playing(True)
            self.play_requested.emit()

    def _on_reset(self):
        self.set_playing(False)
        self.reset_requested.emit()

    def _on_speed_changed(self, text):
        try:
            multiplier = float(text.replace("x", ""))
            self.speed_changed.emit(multiplier)
        except ValueError:
            pass


# ═══════════════════════════════════════════════════════════════════════════
# 遥测数据记录器 (Telemetry Logger) —— JSONL 格式，非阻塞 I/O
# ═══════════════════════════════════════════════════════════════════════════

class TelemetryLogger:
    """航天级遥测数据记录器。"""

    def __init__(self, log_dir="logs"):
        self._log_dir = Path(log_dir)
        self._queue = queue.Queue()
        self._thread = None
        self._file = None
        self._running = False
        self._start_wall = None
        self._log_path = None

    def start(self):
        if self._running:
            return
        self._log_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._log_path = self._log_dir / f"telemetry_{ts}.jsonl"
        self._file = open(self._log_path, "w", encoding="utf-8")
        self._running = True
        self._start_wall = time.monotonic()
        self._thread = threading.Thread(target=self._writer_loop, daemon=True)
        self._thread.start()
        print(f"[LOGGER] 遥测记录已启动 → {self._log_path}")

    def stop(self):
        if not self._running:
            return
        self._queue.put(None)
        self._thread.join(timeout=3.0)
        self._running = False
        if self._file:
            self._file.close()
            self._file = None
        print(f"[LOGGER] 遥测记录已停止 → {self._log_path}")

    def record_valve(self, device, is_open, t=None):
        self._enqueue({
            "t": self._resolve_t(t),
            "device": device,
            "type": "valve",
            "val": bool(is_open),
        })

    def record_sensor(self, device, value, t=None):
        self._enqueue({
            "t": self._resolve_t(t),
            "device": device,
            "type": "sensor",
            "val": value,
        })

    def record_timeline(self, desc, t=None):
        self._enqueue({
            "t": self._resolve_t(t),
            "device": "timeline",
            "type": "timeline",
            "val": desc,
        })

    def _resolve_t(self, t):
        if t is not None:
            return round(float(t), 3)
        if self._start_wall is None:
            return 0.0
        return round(time.monotonic() - self._start_wall, 3)

    def _enqueue(self, record):
        if self._running:
            self._queue.put(record)

    def _writer_loop(self):
        while True:
            record = self._queue.get()
            if record is None:
                break
            try:
                line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
                self._file.write(line + "\n")
                self._file.flush()
            except Exception:
                pass


# ═══════════════════════════════════════════════════════════════════════════
# 遥测数据回放器 (Telemetry Replayer) —— QTimer 驱动，50ms 精确定序派发
# ═══════════════════════════════════════════════════════════════════════════

class TelemetryReplayer(QObject):
    """航天级遥测回放引擎。"""

    valve_changed = Signal(str, bool)
    timeline_update = Signal(float, str, float)
    sensor_batch = Signal(dict)
    finished = Signal()
    progress = Signal(float)

    TICK_MS = 50

    def __init__(self, filepath, parent=None):
        super().__init__(parent)
        self._filepath = filepath
        self._events = []
        self._cursor = 0
        self._total_duration = 0.0
        self._elapsed = 0.0
        self._speed = 1.0
        self._paused = False
        self._last_desc = "回放中..."
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    def load(self):
        if not self._load(self._filepath):
            return False
        print(f"[REPLAY] 已加载 {len(self._events)} 条记录, "
              f"总时长 {self._total_duration:.1f}s")
        return True

    def start(self):
        if not self._events:
            print("[REPLAY] 无数据，请先调用 load()")
            return
        self._cursor = 0
        self._elapsed = 0.0
        self._paused = False
        self._timer.start(self.TICK_MS)
        print("[REPLAY] 开始回放")

    def stop(self):
        self._timer.stop()
        self._paused = False
        print("[REPLAY] 回放已停止")

    def pause(self):
        if not self._paused:
            self._timer.stop()
            self._paused = True
            print(f"[REPLAY] 已暂停 @ {self._elapsed:.1f}s")

    def resume(self):
        if self._paused:
            self._timer.start(self.TICK_MS)
            self._paused = False
            print(f"[REPLAY] 继续回放 @ {self._elapsed:.1f}s")

    def reset(self):
        self._timer.stop()
        self._paused = False
        self._cursor = 0
        self._elapsed = 0.0
        self._last_desc = "回放中..."
        print("[REPLAY] 回放已重置")

    def is_paused(self):
        return self._paused

    def is_running(self):
        return self._timer.isActive()

    def set_speed(self, multiplier):
        self._speed = max(0.1, min(10.0, multiplier))

    def _load(self, filepath):
        self._events.clear()
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                        t = float(record.get("t", 0))
                        self._events.append((t, record))
                    except (json.JSONDecodeError, ValueError, TypeError):
                        continue
        except FileNotFoundError:
            print(f"[REPLAY] 文件不存在: {filepath}")
            return False
        except Exception as e:
            print(f"[REPLAY] 加载文件失败: {e}")
            return False

        if not self._events:
            print("[REPLAY] 日志文件为空")
            return False

        self._events.sort(key=lambda x: x[0])
        self._total_duration = self._events[-1][0]
        return True

    def _tick(self):
        step = (self.TICK_MS / 1000.0) * self._speed
        self._elapsed += step

        sensor_patch = {}
        while self._cursor < len(self._events):
            t, record = self._events[self._cursor]
            if t > self._elapsed:
                break
            self._cursor += 1
            self._dispatch(record, sensor_patch)

        if sensor_patch:
            self.sensor_batch.emit(sensor_patch)

        if self._total_duration > 0:
            self.progress.emit(min(self._elapsed / self._total_duration, 1.0))

        self.timeline_update.emit(
            min(self._elapsed, self._total_duration),
            self._last_desc,
            self._total_duration,
        )

        if self._cursor >= len(self._events):
            self._timer.stop()
            self.timeline_update.emit(self._total_duration, "回放完成", self._total_duration)
            print("[REPLAY] 回放完成")
            self.finished.emit()

    def _dispatch(self, record, sensor_patch):
        typ = record.get("type")
        device = record.get("device", "")
        val = record.get("val")

        if typ == "valve":
            self.valve_changed.emit(device, bool(val))
        elif typ == "sensor":
            sensor_patch[device] = val
        elif typ == "timeline":
            self._last_desc = str(val)


# 设置高DPI缩放
QApplication.setHighDpiScaleFactorRoundingPolicy(
    Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"
os.environ["QT_SCALE_FACTOR"] = "1"

# test reset function. remember: do not !!!merge!!!.

class NavButton(QPushButton):
    """自定义导航按钮，带有选中效果"""

    def __init__(self, text, icon_path=None, parent=None):
        super().__init__(text, parent)
        self.setCheckable(True)  # 允许按钮可选中
        self.setFixedHeight(50)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        if icon_path and os.path.exists(icon_path):
            self.setIcon(QIcon(icon_path))
            self.setIconSize(QSize(24, 24))

        font = QFont()
        font.setPointSize(10)
        self.setFont(font)

        # 简化样式设置
        self.setStyleSheet("""
            QPushButton {
                border: none;
                text-align: left;
                padding-left: 15px;
                background-color: #2C3E50;
                color: white;
            }
            QPushButton:hover {
                background-color: #34495E;
            }
            QPushButton:checked {
                background-color: #34495E;
                border-left: 5px solid #3498DB;
                font-weight: bold;
            }
        """)


class RocketGroundStation(QMainWindow):
    """火箭上位机主窗口"""

    def __init__(self, mock_mode=False, replay_file=None, record_enabled=False):
        super().__init__()
        self.mock_mode = mock_mode
        self.replay_mode = replay_file is not None
        self.record_enabled = record_enabled

        title = "小火炬实验点火软件V1.0"
        if self.replay_mode:
            title += " [遥测回放模式]"
        elif self.mock_mode:
            title += " [SIL 仿真模式]"
        self.setWindowTitle(title)
        self.setGeometry(100, 100, 1280, 720)
        self.setMinimumSize(800, 600)

        # 遥测记录器
        self.telemetry_logger = None
        if record_enabled and not self.replay_mode:
            self.telemetry_logger = TelemetryLogger()
            self.telemetry_logger.start()

        # 创建共享的串口管理器 (回放模式下不连接物理串口)
        self.serial_manager = SerialManager()
        self.serial_manager.error_occurred.connect(self._handle_serial_error)

        # 初始化界面
        self.init_ui()

        # 回放引擎 / Mock 引擎初始化
        if self.replay_mode:
            self._lock_controls_for_replay()
            self._init_replay_engine(replay_file)
            self._init_replay_control_panel()
            self.statusBar().showMessage(f"[REPLAY 模式] 回放文件: {replay_file}", 0)
        elif self.mock_mode:
            self._init_mock_engine()
            self.statusBar().showMessage("[MOCK 模式] 仿真数据已启用 - 未连接真实硬件", 0)
        else:
            self.statusBar().showMessage("系统启动完成，欢迎使用火箭上位机系统", 5000)

    def init_ui(self):
        """初始化主界面"""
        # 创建中心部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 创建左侧导航面板
        self.nav_panel = self.create_nav_panel()

        # 创建右侧内容区
        self.content_stack = QStackedWidget()

        # 创建视频监控页面
        self.video_page = MultiCameraViewer()
        self.content_stack.addWidget(self.video_page)

        # 创建控制面板页面
        self.control_page = ControlPanel(self.serial_manager)
        self.content_stack.addWidget(self.control_page)
        
        # 创建点火控制台页面
        self.ignition_console_page = RocketControlConsole(self.serial_manager)
        self.content_stack.addWidget(self.ignition_console_page)

        # 桥接：序列执行 → HMI 面板
        self.ignition_console_page.sequence_valve_changed.connect(
            self._on_seq_valve_changed)
        self.ignition_console_page.sequence_timeline_update.connect(
            self._on_seq_timeline_update)

        # 创建传感器数据页面


        # 添加到主布局
        main_layout.addWidget(self.nav_panel)
        main_layout.addWidget(self.content_stack)

        # 设置比例 (导航栏占1份宽度，内容区占5份宽度)
        main_layout.setStretch(0, 1)
        main_layout.setStretch(1, 5)

        # 初始化菜单栏
        self.init_menu_bar()

        # 初始化状态栏
        self.statusBar().showMessage("就绪")
        
        # 连接串口状态信号
        self.connect_serial_status_signals()

    def open_sensor_data_dialog(self):
        """打开传感器数据对话框"""
        dialog = SensorDataDialog(self.serial_manager, self)
        dialog.setWindowFlag(Qt.WindowType.Window, True)
        dialog.setStyleSheet(self.styleSheet())
        dialog.show()
        return dialog

    def create_nav_panel(self):
        """创建左侧导航面板"""
        nav_panel = QFrame()
        nav_panel.setObjectName("navPanel")
        nav_panel.setStyleSheet("""
            #navPanel {
                background-color: #2C3E50;
                min-width: 200px;
                max-width: 250px;
            }
        """)

        nav_layout = QVBoxLayout(nav_panel)
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.setSpacing(0)

        # 添加顶部标题
        header = QLabel("小火炬实验点火软件")
        header.setStyleSheet("""
            color: white;
            background-color: #3498DB;
            padding: 15px;
            font-size: 16px;
            font-weight: bold;
        """)
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        nav_layout.addWidget(header)

        # 添加间隔
        nav_layout.addSpacing(10)
        
        # 串口设置按钮 - 移到最顶部
        self.btn_serial = NavButton("串口设置", "icons/serial.png")
        self.btn_serial.clicked.connect(self.open_serial_dialog)
        self.btn_serial.setStyleSheet("""
            QPushButton {
                border: none;
                text-align: left;
                padding-left: 15px;
                background-color: #16A085;  /* 绿色背景突出显示 */
                color: white;
                font-weight: bold;          /* 加粗显示 */
            }
            QPushButton:hover {
                background-color: #1ABC9C;
            }
            QPushButton:checked {
                background-color: #1ABC9C;
                border-left: 5px solid #3498DB;
                font-weight: bold;
            }
        """)
        nav_layout.addWidget(self.btn_serial)
        
        # 额外的间隔，分隔串口设置与其他按钮
        nav_layout.addSpacing(8)
        
        # 添加串口状态显示区域
        self.create_serial_status_panel(nav_layout)

        # 视频监控按钮
        self.btn_video = NavButton("视频监控", "icons/camera.png")
        self.btn_video.setChecked(True)  # 默认选中
        self.btn_video.clicked.connect(lambda: self.switch_page(0))
        nav_layout.addWidget(self.btn_video)

        # 控制面板按钮
        self.btn_control = NavButton("控制面板", "icons/control.png")
        self.btn_control.clicked.connect(lambda: self.switch_page(1))
        nav_layout.addWidget(self.btn_control)

        # 点火控制台按钮
        self.btn_ignition = NavButton("点火控制台", "icons/fire.png")
        self.btn_ignition.clicked.connect(lambda: self.switch_page(2))
        nav_layout.addWidget(self.btn_ignition)

        # 传感器数据按钮
        self.btn_sensor_data = NavButton("传感器数据", "icons/sensor.png")
        self.btn_sensor_data.clicked.connect(self.open_sensor_data_dialog) 
        nav_layout.addWidget(self.btn_sensor_data)

        self.btn_sensor = NavButton("传感器测试", "icons/fire.png")
        self.btn_sensor.clicked.connect(self.open_sensor_dialog)
        nav_layout.addWidget(self.btn_sensor)

        # HMI 实时监控看板按钮（弹窗模式）
        self.btn_hmi = NavButton("HMI 监控看板", "icons/dashboard.png")
        self.btn_hmi.clicked.connect(self.open_hmi_dialog)
        nav_layout.addWidget(self.btn_hmi)

        # 回放模式入口
        self.btn_replay_entry = NavButton("回放模式", "icons/replay.png")
        self.btn_replay_entry.clicked.connect(self.open_replay_selector)
        self.btn_replay_entry.setStyleSheet("""
            QPushButton {
                border: none;
                text-align: left;
                padding-left: 15px;
                background-color: #8E44AD;
                color: white;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #9B59B6;
            }
            QPushButton:checked {
                background-color: #9B59B6;
                border-left: 5px solid #F39C12;
                font-weight: bold;
            }
        """)
        nav_layout.addWidget(self.btn_replay_entry)



        # 添加弹性空间
        nav_layout.addStretch(1)

        # 紧急停止按钮(放在导航栏底部)
        self.btn_emergency = QPushButton("紧急停止")
        self.btn_emergency.setStyleSheet("""
            QPushButton {
                background-color: #E74C3C;
                color: white;
                font-weight: bold;
                font-size: 12px;
                padding: 10px;
                border: none;
                margin: 10px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #C0392B;
            }
            QPushButton:pressed {
                background-color: #922B21;
            }
        """)
        self.btn_emergency.clicked.connect(self.send_emergency_stop)
        # 更新工具提示，按新协议描述灭火序列
        self.btn_emergency.setToolTip("将发送命令: 0xEE000000000000000000 (强制停止)\n执行完整灭火序列，分批关闭所有设备")
        nav_layout.addWidget(self.btn_emergency)

        # 在串口状态标签下方添加刷新按钮
        refresh_btn = QPushButton("🔄 刷新状态")
        refresh_btn.setStyleSheet("""
               QPushButton {
                   background-color: #3498DB;
                   color: white;
                   padding: 10px 8px;
                   font-size: 9px;
                   border-radius: 3px;
                   margin: 5px 10px;
               }
               QPushButton:hover {
                   background-color: #2980B9;
               }
               QPushButton:pressed {
                   background-color: #1F618D;
               }
           """)
        refresh_btn.clicked.connect(self.refresh_serial_status)
        nav_layout.addWidget(refresh_btn)

        nav_layout.addSpacing(10)

        return nav_panel

    def refresh_serial_status(self):
        """手动刷新串口连接状态，检测物理断开"""
        print("🔄 手动刷新串口状态...")

        # 检查串口1
        port1_physical_connected = self._check_physical_connection(1)
        port1_logic_connected = self.serial_manager.is_port1_connected()

        if port1_logic_connected and not port1_physical_connected:
            # 逻辑上连接但物理已断开
            print("⚠️ 检测到串口1物理断开")
            self.serial_manager.disconnect_port1()  # 强制清理资源
            self._on_main_port1_disconnected()
            self.statusBar().showMessage("串口1已断开连接", 3000)
        elif port1_logic_connected and port1_physical_connected:
            # 获取当前串口信息
            try:
                port_name = self.serial_manager._serial_port1.name
                baud_rate = self.serial_manager._serial_port1.baudrate
                self._on_main_port1_connected(port_name, baud_rate)
                self.statusBar().showMessage(f"串口1正常: {port_name} @ {baud_rate}", 2000)
            except:
                self.statusBar().showMessage("串口1状态正常", 2000)

        # 检查串口2
        port2_physical_connected = self._check_physical_connection(2)
        port2_logic_connected = self.serial_manager.is_port2_connected()

        if port2_logic_connected and not port2_physical_connected:
            print("⚠️ 检测到串口2物理断开")
            self.serial_manager.disconnect_port2()
            self._on_main_port2_disconnected()
            self.statusBar().showMessage("串口2已断开连接", 3000)
        elif port2_logic_connected and port2_physical_connected:
            try:
                port_name = self.serial_manager._serial_port2.name
                baud_rate = self.serial_manager._serial_port2.baudrate
                self._on_main_port2_connected(port_name, baud_rate)
                self.statusBar().showMessage(f"串口2正常: {port_name} @ {baud_rate}", 2000)
            except:
                self.statusBar().showMessage("串口2状态正常", 2000)

        # 如果都未连接
        if not port1_logic_connected and not port2_logic_connected:
            self.statusBar().showMessage("所有串口均未连接", 2000)

    def _check_physical_connection(self, port_num):
        """
        检查物理连接是否真实存在
        通过访问 in_waiting 属性来测试（会触发底层IO检查）
        """
        try:
            if port_num == 1:
                serial_port = self.serial_manager._serial_port1
            else:
                serial_port = self.serial_manager._serial_port2

            if serial_port is None:
                return False

            # 关键测试：尝试访问 in_waiting
            # 如果USB被拔出，这里会抛出 OSError 或 SerialException
            _ = serial_port.in_waiting

            # 额外检查：尝试获取控制线状态（更严格）
            # 如果设备支持CTS检测，这能进一步确认连接
            if hasattr(serial_port, 'cts'):
                _ = serial_port.cts

            return True

        except (OSError, serial.SerialException, AttributeError):
            return False

    def create_serial_status_panel(self, nav_layout):
        """创建串口状态显示面板"""
        # 串口状态标题
        status_title = QLabel("串口状态")
        status_title.setStyleSheet("""
            color: white;
            background-color: #34495E;
            padding: 8px 15px;
            font-size: 12px;
            font-weight: bold;
            border-radius: 3px;
            margin: 5px 10px;
        """)
        #nav_layout.addWidget(status_title)
        
        # 串口1状态
        self.port1_status_label = QLabel("串口1: ❌ 未连接")
        self.port1_status_label.setStyleSheet("""
            color: #e74c3c;
            background-color: #fdf2f2;
            padding: 6px 12px;
            font-size: 10px;
            font-weight: bold;
            border-radius: 3px;
            margin: 2px 10px;
            border: 1px solid #e74c3c;
        """)
        nav_layout.addWidget(self.port1_status_label)
        
        # 串口2状态
        self.port2_status_label = QLabel("串口2: ❌ 未连接")
        self.port2_status_label.setStyleSheet("""
            color: #e74c3c;
            background-color: #fdf2f2;
            padding: 6px 12px;
            font-size: 10px;
            font-weight: bold;
            border-radius: 3px;
            margin: 2px 10px;
            border: 1px solid #e74c3c;
        """)
        nav_layout.addWidget(self.port2_status_label)
        
        # 添加间隔
        nav_layout.addSpacing(10)

    def connect_serial_status_signals(self):
        """连接串口状态信号"""
        # 连接双串口专用信号
        if hasattr(self.serial_manager, 'port1_connected'):
            self.serial_manager.port1_connected.connect(self._on_main_port1_connected)
            self.serial_manager.port2_connected.connect(self._on_main_port2_connected)
        if hasattr(self.serial_manager, 'port1_disconnected'):
            self.serial_manager.port1_disconnected.connect(self._on_main_port1_disconnected)
            self.serial_manager.port2_disconnected.connect(self._on_main_port2_disconnected)

    def _on_main_port1_connected(self, port_name, baud_rate):
        """主界面串口1连接成功"""
        self.port1_status_label.setText(f"串口1: ✅ {port_name}")
        self.port1_status_label.setStyleSheet("""
            color: #27ae60;
            background-color: #d5f4e6;
            padding: 6px 12px;
            font-size: 10px;
            font-weight: bold;
            border-radius: 3px;
            margin: 2px 10px;
            border: 1px solid #27ae60;
        """)

    def _on_main_port2_connected(self, port_name, baud_rate):
        """主界面串口2连接成功"""
        self.port2_status_label.setText(f"串口2: ✅ {port_name}")
        self.port2_status_label.setStyleSheet("""
            color: #27ae60;
            background-color: #d5f4e6;
            padding: 6px 12px;
            font-size: 10px;
            font-weight: bold;
            border-radius: 3px;
            margin: 2px 10px;
            border: 1px solid #27ae60;
        """)

    def _on_main_port1_disconnected(self):
        """主界面串口1断开连接"""
        self.port1_status_label.setText("串口1: ❌ 未连接")
        self.port1_status_label.setStyleSheet("""
            color: #e74c3c;
            background-color: #fdf2f2;
            padding: 6px 12px;
            font-size: 10px;
            font-weight: bold;
            border-radius: 3px;
            margin: 2px 10px;
            border: 1px solid #e74c3c;
        """)

    def _on_main_port2_disconnected(self):
        """主界面串口2断开连接"""
        self.port2_status_label.setText("串口2: ❌ 未连接")
        self.port2_status_label.setStyleSheet("""
            color: #e74c3c;
            background-color: #fdf2f2;
            padding: 6px 12px;
            font-size: 10px;
            font-weight: bold;
            border-radius: 3px;
            margin: 2px 10px;
            border: 1px solid #e74c3c;
        """)


    def init_menu_bar(self):
        """初始化菜单栏"""
        menu_bar = self.menuBar()

        # 文件菜单
        file_menu = menu_bar.addMenu("文件")

        exit_action = QAction("退出", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # 设置菜单
        settings_menu = menu_bar.addMenu("设置")

        serial_action = QAction("串口配置", self)
        serial_action.setShortcut("Ctrl+S")
        serial_action.triggered.connect(self.open_serial_dialog)
        settings_menu.addAction(serial_action)

        # 帮助菜单
        help_menu = menu_bar.addMenu("帮助")

        about_action = QAction("关于", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

    def switch_page(self, index):
        """切换内容页面"""
        self.content_stack.setCurrentIndex(index)

        # 更新按钮状态
        self.btn_video.setChecked(index == 0)
        self.btn_control.setChecked(index == 1)
        self.btn_ignition.setChecked(index == 2)
     
        self.btn_serial.setChecked(False)  # 串口设置是弹窗，不改变主内容区

    def open_serial_dialog(self):
        """打开串口设置对话框"""
        dialog = SerialConfigDialog(self.serial_manager, self)
        dialog.setStyleSheet(self.styleSheet())  # 继承主窗口样式
        dialog.show()


    def open_sensor_dialog(self):
        """打开传感器设置对话框"""
        dialog = SensorControlDialog(self.serial_manager,self)
        # 设置为独立窗口，不跟随主窗口最小化/隐藏
        dialog.setWindowFlag(Qt.WindowType.Window, True)
        dialog.setStyleSheet(self.styleSheet())

        # 连接关闭信号，在对话框关闭时取消按钮选中状态
        dialog.finished.connect(lambda: self.btn_sensor.setChecked(False))

        # 非模态显示
        dialog.show()



    def send_emergency_stop(self):
        """发送紧急停止命令"""
        if not self.serial_manager.is_connected():
            self.statusBar().showMessage("错误: 串口未连接，无法发送紧急停止命令", 3000)
            print("❌ 紧急停止失败: 串口未连接")
            return

        # 强制停止命令(灭火序列)：0xEE + 保留字节(9字节)
        command = bytes([0xEE] + [0x00] * 9)
        
        try:
            success = self.serial_manager.send_data(command)
            if success:
                message = "已发送: 强制停止命令(灭火序列) (0x{})".format(command.hex().upper())
                # 确保 control_page 已创建且可用
                if self.control_page:
                    self.control_page.log_message(message)
                # 确保点火控制台页面已创建且可用
                if hasattr(self, 'ignition_console_page'):
                    self.ignition_console_page._log_task("强制停止命令(灭火序列)已发送")
                
                # 使用状态栏显示，不阻塞主线程
                self.statusBar().showMessage("强制停止命令(灭火序列)已发送！", 5000)
                print(f"✅ {message}")
            else:
                error_message = "发送失败: 强制停止命令 (0x{})".format(command.hex().upper())
                if self.control_page:
                    self.control_page.log_message(error_message)
                if hasattr(self, 'ignition_console_page'):
                    self.ignition_console_page._log_task("强制停止命令发送失败")
                
                # 使用状态栏显示错误
                self.statusBar().showMessage("强制停止命令发送失败！", 5000)
                print(f"❌ {error_message}")
                
        except Exception as e:
            error_message = f"强制停止命令发送异常: {e}"
            if self.control_page:
                self.control_page.log_message(error_message)
            if hasattr(self, 'ignition_console_page'):
                self.ignition_console_page._log_task(error_message)
            
            # 使用状态栏显示异常
            self.statusBar().showMessage("强制停止命令发送异常！", 5000)
            print(f"❌ {error_message}")
            import traceback
            traceback.print_exc()

    def show_about(self):
        """显示关于对话框"""
        QMessageBox.about(
            self,
            "关于小火炬实验点火软件",
            "小火炬实验点火软件 V1.0\n\n"
            "集成了视频监控和设备控制功能的上位机软件。\n"
            "可用于火箭点火系统远程控制和监测。\n\n"
            "开发者: 冕巢航天"
        )

    def _handle_serial_error(self, message):
        """处理串口错误"""
        self.statusBar().showMessage("串口错误: {}".format(message), 5000)

    # ── 序列执行 → HMI 桥接 ────────────────────────────────────────────────
    def _on_seq_valve_changed(self, hmi_valve_name, is_open):
        """点火控制台序列执行时通知 HMI 更新阀门颜色"""
        hmi = getattr(self, '_hmi_panel', None)
        if hmi:
            hmi.set_valve_state(hmi_valve_name, is_open)
        if self.telemetry_logger:
            self.telemetry_logger.record_valve(hmi_valve_name, is_open)

    def _on_seq_timeline_update(self, elapsed, desc, total_duration):
        """点火控制台序列执行时通知 HMI 更新进度条"""
        hmi = getattr(self, '_hmi_panel', None)
        if hmi:
            hmi.update_timeline(elapsed, desc, total_duration)
        if self.telemetry_logger:
            self.telemetry_logger.record_timeline(desc, elapsed)

    def open_hmi_dialog(self):
        """打开 HMI 实时监控看板弹窗"""
        if hasattr(self, '_hmi_dialog') and self._hmi_dialog and self._hmi_dialog.isVisible():
            self._hmi_dialog.raise_()
            self._hmi_dialog.activateWindow()
            return self._hmi_dialog

        dialog = QDialog(self)
        dialog.setWindowTitle("HMI 实时监控看板 - 2KN 推力供给系统")
        dialog.setMinimumSize(1280, 720)
        dialog.resize(1600, 900)
        dialog.setWindowFlag(Qt.WindowType.Window, True)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(0, 0, 0, 0)

        hmi = HMIPanel(self.serial_manager, dialog)
        self._hmi_panel = hmi
        layout.addWidget(hmi)

        def on_close():
            self.btn_hmi.setChecked(False)
            if hasattr(self, '_hmi_dialog'):
                self._hmi_dialog = None
            if hasattr(self, '_hmi_panel'):
                self._hmi_panel = None

        dialog.finished.connect(on_close)
        dialog.setStyleSheet(self.styleSheet())

        self._hmi_dialog = dialog
        self.btn_hmi.setChecked(True)
        dialog.show()
        return dialog

    def open_replay_selector(self):
        """打开遥测记录文件选择器，选中后重启进入回放模式"""
        self.btn_replay_entry.setChecked(False)

        start_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
        if not os.path.isdir(start_dir):
            start_dir = os.path.expanduser("~")

        filepath, _ = QFileDialog.getOpenFileName(
            self, "选择遥测记录文件", start_dir,
            "JSONL 遥测日志 (*.jsonl);;所有文件 (*)",
        )
        if not filepath:
            return

        print(f"[REPLAY ENTRY] 用户选择回放文件: {filepath}")
        subprocess.Popen(
            [sys.executable, sys.argv[0], "--replay", filepath],
            start_new_session=True,
        )
        QApplication.quit()

    # ── 遥测回放引擎 ──────────────────────────────────────────────────────
    def _init_replay_engine(self, replay_file):
        """初始化遥测回放引擎，加载文件但不自动播放"""
        self._replayer = TelemetryReplayer(replay_file)
        self._replayer.valve_changed.connect(self._on_seq_valve_changed)
        self._replayer.timeline_update.connect(self._on_seq_timeline_update)
        self._replayer.sensor_batch.connect(self._on_replay_sensor_batch)
        self._replayer.finished.connect(self._on_replay_finished)
        if not self._replayer.load():
            self.statusBar().showMessage("[REPLAY] 加载日志文件失败!", 5000)

    def _on_replay_sensor_batch(self, sensor_dict):
        """回放时批量更新 HMI 传感器数值"""
        hmi = getattr(self, '_hmi_panel', None)
        if hmi:
            for key, val in sensor_dict.items():
                hmi.sensor_values[key] = val
            hmi.plc_connected = True
            hmi._mark_dirty()

    def _on_replay_finished(self):
        """回放完成"""
        self.statusBar().showMessage("[REPLAY] 遥测数据回放已完成", 5000)
        if hasattr(self, '_replay_control'):
            self._replay_control.set_playing(False)
        print("[REPLAY] 回放结束")

    # ── 回放安全锁 & 控制面板 ──────────────────────────────────────────────
    def _lock_controls_for_replay(self):
        """回放模式下禁用所有串口指令按钮 (物理安全锁)"""
        if hasattr(self, 'btn_emergency'):
            self.btn_emergency.setEnabled(False)
        if hasattr(self, 'control_page'):
            self.control_page.set_replay_mode(True)
        if hasattr(self, 'ignition_console_page'):
            self.ignition_console_page.set_replay_mode(True)

    def _init_replay_control_panel(self):
        """回放模式：状态标签留在主窗口，控制按钮悬浮"""

        status_bar = QWidget()
        status_layout = QHBoxLayout(status_bar)
        status_layout.setContentsMargins(8, 4, 8, 4)

        self._replay_status_label = QLabel("回放模式")
        self._replay_status_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self._replay_status_label.setStyleSheet("""
            background-color: #F39C12;
            color: #000000;
            font-weight: bold;
            font-size: 13px;
            padding: 5px 12px;
            border-radius: 4px;
        """)
        self._replay_status_label.setToolTip("点击打开回放控制台")
        status_layout.addWidget(self._replay_status_label)
        status_layout.addStretch(1)

        dock = QDockWidget("", self)
        dock.setWidget(status_bar)
        dock.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        dock.setTitleBarWidget(QWidget())
        self.addDockWidget(Qt.DockWidgetArea.TopDockWidgetArea, dock)
        self._replay_status_dock = dock

        self._replay_control = ReplayControlPanel()

        self._replay_control.play_requested.connect(self._on_replay_play)
        self._replay_control.pause_requested.connect(self._on_replay_pause)
        self._replay_control.reset_requested.connect(self._on_replay_reset)
        self._replay_control.speed_changed.connect(self._on_replay_speed)

        dialog = QDialog(self)
        dialog.setWindowTitle("回放控制台")
        dialog.setWindowFlag(Qt.WindowType.Window, True)
        dialog.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._replay_control)
        dialog.adjustSize()

        def on_close():
            dialog.hide()

        dialog.rejected.connect(on_close)
        dialog.setStyleSheet(self.styleSheet())
        dialog.show()
        self._replay_dialog = dialog

        self._replay_status_label.mousePressEvent = lambda e: dialog.show()

    def _on_replay_play(self):
        if hasattr(self, '_replayer'):
            if self._replayer.is_paused():
                self._replayer.resume()
            else:
                self._replayer.start()

    def _on_replay_pause(self):
        if hasattr(self, '_replayer'):
            self._replayer.pause()

    def _on_replay_reset(self):
        if hasattr(self, '_replayer'):
            self._replayer.reset()
            hmi = getattr(self, '_hmi_panel', None)
            if hmi:
                for v in list(hmi._valve_state_set):
                    hmi.valve_states[v] = False
                hmi._valve_state_set.clear()
                hmi.update_timeline(0.0, "等待回放...",
                                    self._replayer._total_duration)
                hmi._mark_dirty()

    def _on_replay_speed(self, multiplier):
        if hasattr(self, '_replayer'):
            self._replayer.set_speed(multiplier)

    # ── SIL Mock 引擎 ──────────────────────────────────────────────────────
    AEROSPIKE_TIMELINE = [
        {"t": -5.0, "desc": "前吹扫开始",
         "actions": {"purge_valve": True}},
        {"t": -2.0, "desc": "火花塞建压",
         "actions": {"spark_plug": True, "purge_valve": False}},
        {"t": -1.5, "desc": "火炬点火",
         "actions": {"propane_valve": True, "torch_o2_valve": True}},
        {"t":  0.0, "desc": "主级点火 (爆燃瞬间)",
         "actions": {"main_lox_valve": True, "main_ethanol_valve": True, "spark_plug": False}},
        {"t":  0.5, "desc": "进入自持燃烧",
         "actions": {"propane_valve": False, "torch_o2_valve": False}},
        {"t":  2.0, "desc": "主发动机关机并开启后吹扫",
         "actions": {"main_ethanol_valve": False, "main_lox_valve": False, "purge_valve": True}},
        {"t":  5.0, "desc": "试车彻底结束",
         "actions": {"purge_valve": False}},
    ]

    TIMELINE_VALVE_MAP = {
        "purge_valve":       ["XV-302"],
        "propane_valve":     ["XV-401"],
        "torch_o2_valve":    ["XV-402"],
        "main_lox_valve":    ["XV-202", "XV-205", "XV-206"],
        "main_ethanol_valve":["XV-102", "XV-104"],
    }

    def _init_mock_engine(self):
        """初始化试车时序仿真引擎 —— 每 50ms 推进一次时间轴"""
        self._mock_elapsed = -5.0
        self._mock_phase_index = 0
        self._mock_phase_desc = "等待试车..."
        self._mock_cycle_complete = False
        self._mock_timer = QTimer(self)
        self._mock_timer.timeout.connect(self._mock_tick)
        self._mock_timer.start(50)
        print("[MOCK] 试车时序仿真引擎已启动 (2KN Aerospike 时序, 50ms/帧)")

    def _mock_tick(self):
        """每个 tick 推进 0.05s，驱动阀门帧 & 传感器 & 进度条"""
        hmi = getattr(self, '_hmi_panel', None)
        if hmi is None:
            return

        self._mock_elapsed += 0.05

        # 1) 执行当前时刻之前的时序帧（阀门状态翻转）
        for frame in self.AEROSPIKE_TIMELINE[self._mock_phase_index:]:
            if frame["t"] > self._mock_elapsed:
                break
            self._mock_phase_index += 1
            self._mock_phase_desc = frame["desc"]
            print(f"  [MOCK] t={frame['t']:+.1f}s {frame['desc']}")
            for logical_name, state in frame["actions"].items():
                for hmi_name in self.TIMELINE_VALVE_MAP.get(logical_name, []):
                    hmi.set_valve_state(hmi_name, state)
                    if self.telemetry_logger:
                        self.telemetry_logger.record_valve(hmi_name, state, frame["t"])

        # 2) 传感器数据（按当前时相）
        t = self._mock_elapsed
        if t < 0:
            thrust = 0.0
            chamber_temp = 25.0
            chamber_press = 0.0
            ethanol_temp = 20.0
            lox_temp = -183.0
            press = 0.5 + random.uniform(-0.05, 0.05)
        elif 0 <= t < 2.0:
            thrust = 1800.0 + random.uniform(-100, 100)
            chamber_temp = 2800.0 + random.uniform(-150, 150)
            chamber_press = 2.0 + random.uniform(-0.1, 0.1)
            ethanol_temp = 35.0 + random.uniform(-2, 2)
            lox_temp = -170.0 + random.uniform(-3, 3)
            press = 2.0 + random.uniform(-0.1, 0.1)
        else:
            decay = max(0.0, (5.0 - t) / 3.0)
            thrust = 0.0
            chamber_temp = 25.0 + 2775.0 * decay
            chamber_press = 2.0 * decay
            ethanol_temp = 20.0 + 15.0 * decay
            lox_temp = -183.0 + 13.0 * (1 - decay)
            press = 0.5 + 1.5 * decay

        hmi.sensor_values["value_ZT_301"]           = round(thrust, 1)
        hmi.sensor_values["value_TT_303"]           = round(chamber_temp, 1)
        hmi.sensor_values["value_PT_303"]           = round(chamber_press, 2)
        hmi.sensor_values["value_TI_ethanol_tank"]  = round(ethanol_temp, 1)
        hmi.sensor_values["value_TT_301"]           = round(ethanol_temp + random.uniform(-1, 1), 1)
        hmi.sensor_values["value_TT_302"]           = round(lox_temp + random.uniform(-1, 1), 1)
        hmi.sensor_values["value_PT_301"]           = round(press, 2)
        hmi.sensor_values["value_PT_302"]           = round(press * 0.95, 2)
        hmi.sensor_values["value_PT_ethanol_tank"]  = round(press * 1.1, 2)
        hmi.sensor_values["value_PT_LOX_tank"]      = round(press * 1.05, 2)

        # 3) 时序进度条（每帧更新，游标丝滑移动）
        hmi.update_timeline(self._mock_elapsed, self._mock_phase_desc)

        # 4) 遥测记录
        if self.telemetry_logger:
            t = self._mock_elapsed
            self.telemetry_logger.record_timeline(self._mock_phase_desc, t)
            for key, val in hmi.sensor_values.items():
                if val is not None:
                    self.telemetry_logger.record_sensor(key, val, t)

        # 5) 到达 t=5.0s 后循环
        if self._mock_elapsed >= 5.0 and not self._mock_cycle_complete:
            self._mock_cycle_complete = True
            print("[MOCK] 试车时序完成，2s 后重新开始...")
            QTimer.singleShot(2000, self._reset_mock_cycle)

        hmi.plc_connected = True
        hmi._mark_dirty()

    def _reset_mock_cycle(self):
        """复位试车时序到 t=-5.0，清空阀门状态"""
        hmi = getattr(self, '_hmi_panel', None)
        if hmi:
            for valve_name in list(hmi._valve_state_set):
                hmi.valve_states[valve_name] = False
            hmi._valve_state_set.clear()
            hmi.update_timeline(-5.0, "等待试车...")
            hmi._mark_dirty()
        self._mock_elapsed = -5.0
        self._mock_phase_index = 0
        self._mock_phase_desc = "等待试车..."
        self._mock_cycle_complete = False
        print("[MOCK] 时序已复位，开始新循环")

    def closeEvent(self, event):
        """关闭窗口时的处理"""
        try:
            # 停止遥测记录器
            if hasattr(self, 'telemetry_logger') and self.telemetry_logger:
                self.telemetry_logger.stop()
            # 停止回放器
            if hasattr(self, '_replayer') and self._replayer:
                self._replayer.stop()
            # 关闭回放控制悬浮窗
            if hasattr(self, '_replay_dialog') and self._replay_dialog:
                self._replay_dialog.close()
            # 关闭 HMI 弹窗
            if hasattr(self, '_hmi_dialog') and self._hmi_dialog:
                self._hmi_dialog.close()
            # 清理串口资源
            if hasattr(self, 'serial_manager') and self.serial_manager:
                self.serial_manager.disconnect_serial()

            # 清理视频资源
            if hasattr(self, 'video_page') and self.video_page:
                self.video_page.cleanup_on_close()

            # 确保所有子组件正确清理
            if hasattr(self, 'control_page'):
                self.control_page.deleteLater()
            if hasattr(self, 'ignition_console_page'):
                self.ignition_console_page.deleteLater()
            if hasattr(self, 'sensor_data_page'):
                self.sensor_data_page.deleteLater()

            # 延迟一点时间确保清理完成
            from PySide6.QtCore import QTimer
            QTimer.singleShot(100, lambda: None)

        except Exception as e:
            print(f"关闭窗口时发生错误: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # 接受关闭事件
            event.accept()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="小火炬实验点火软件 - 火箭上位机系统")
    parser.add_argument(
        "--mock", action="store_true",
        help="启用 SIL 仿真模式：使用随机假数据驱动 UI，无需连接真实硬件串口"
    )
    parser.add_argument(
        "--replay", type=str, default=None, metavar="FILE",
        help="遥测回放模式：加载 JSONL 日志文件进行数据复盘 (屏蔽串口/Mock)"
    )
    parser.add_argument(
        "--record", action="store_true",
        help="启用遥测记录：将阀门/传感器/时间轴数据写入 JSONL 日志"
    )
    args = parser.parse_args()

    app = QApplication(sys.argv)

    # 应用全局样式
    app.setStyle("Fusion")

    # 设置全局样式表 - 统一按钮颜色和样式
    # 在设置背景时，只修改 QMainWindow 的背景
    app.setStyleSheet("""
        QMainWindow {
        QPushButton {
            padding: 2px 5px;
            border-radius: 4px;
            background-color: #3498DB;
            color: white;
            border: none;
        }
        QPushButton:hover {
            background-color: #2980B9;
        }
        QPushButton:pressed {
            background-color: #1F618D;
        }
        QPushButton:disabled {
            background-color: #BDC3C7;
            color: #7F8C8D;
        }
        QComboBox, QLineEdit, QSpinBox {
            padding: 5px;
            border: 1px solid #BDC3C7;
            border-radius: 3px;
            background-color: white;
        }
        QLabel {
            color: #2C3E50;
        }
        QGroupBox {
            font-weight: bold;
            border: 1px solid #BDC3C7;
            border-radius: 5px;
            margin-top: 10px;
            padding-top: 15px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 5px;
        }
        QTabWidget::pane {
            border: 1px solid #BDC3C7;
            background-color: white;
        }
        QTabBar::tab {
            background-color: #ECF0F1;
            border: 1px solid #BDC3C7;
            padding: 8px 16px;
            margin-right: 2px;
        }
        QTabBar::tab:selected {
            background-color: white;
            border-bottom-color: white;
            font-weight: bold;
        }
        QTabBar::tab:hover:!selected {
            background-color: #D6EAF8;
        }
    """)

    main_window = RocketGroundStation(
        mock_mode=args.mock,
        replay_file=args.replay,
        record_enabled=args.record,
    )
    main_window.show()

    sys.exit(app.exec())
