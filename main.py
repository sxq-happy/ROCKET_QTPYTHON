# main.py - 程序入口点与主窗口
import sys
import os
import serial
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QStackedWidget, QPushButton, QLabel,
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QFrame,
    QMessageBox, QStatusBar
)
from PyQt6.QtCore import Qt, QSize, QTimer
from PyQt6.QtGui import QIcon, QAction, QFont, QPixmap


# 导入自定义组件
# 假设 video_components.py 和 serial_components.py 文件存在且内容正确
from video_components import MultiCameraViewer
from control_components import ControlPanel, RocketControlConsole
from serial_components import SerialManager, SerialConfigDialog, SensorControlDialog, SensorDataDialog

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

    def __init__(self):
        super().__init__()
        self.setWindowTitle("小火炬实验点火软件V1.0")
        self.setGeometry(100, 100, 1280, 720)
        self.setMinimumSize(800, 600)


        # 创建共享的串口管理器
        self.serial_manager = SerialManager()
        self.serial_manager.error_occurred.connect(self._handle_serial_error)

        # 初始化界面
        self.init_ui()

        # 在状态栏显示欢迎信息
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

    def closeEvent(self, event):
        """关闭窗口时的处理"""
        try:
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
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(100, lambda: None)
            
        except Exception as e:
            print(f"关闭窗口时发生错误: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # 接受关闭事件
            event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)

    # 应用全局样式
    app.setStyle("Fusion")

    # 设置全局样式表 - 统一按钮颜色和样式
    # 在设置背景时，只修改 QMainWindow 的背景
    app.setStyleSheet("""
        QMainWindow {
            background-image: url(r"D:\desk_file\电控\shangweijiv2.2\logo_white.png");
            background-repeat: no-repeat;
            background-position: center;
            background-size: 1px auto; /* 可以根据需要调整数值 */
        }
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

    main_window = RocketGroundStation()
    main_window.show()

    sys.exit(app.exec())
