# video_components.py
import sys
import cv2
import numpy as np
import os
import time
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QMessageBox,
    QSizePolicy, QSplitter, QFrame
)
from PySide6.QtCore import (
    Qt, QThread, Signal, QTimer, QSize
)
from PySide6.QtGui import (
    QImage, QPixmap
)


# --- 1. 视频采集线程 ---
class VideoCaptureThread(QThread):
    """
    独立线程，用于从 USB 摄像头捕获视频帧。
    捕获到的帧将通过信号发送给主线程。
    同时，该线程会报告摄像头的状态和发生的错误，并包含其对应摄像头的索引。
    """
    frame_captured = Signal(np.ndarray)  # 发送 NumPy 数组格式的帧
    camera_ready = Signal(bool, int)  # 信号：(是否成功打开, 摄像头索引)
    camera_error = Signal(str, int)  # 信号：(错误信息, 摄像头索引)

    def __init__(self, camera_index=0, parent=None):
        super().__init__(parent)
        self.camera_index = camera_index
        self._running = False
        self.cap = None

        # ▼▼▼ 新增：让后台线程拥有录像控制权 ▼▼▼
        self.is_recording = False
        self._pending_recording = False
        self.save_folder = ""
        self.video_writer = None
        # ▲▲▲ 新增结束 ▲▲▲

    # ▼▼▼ 新增：控制录像的开关方法 ▼▼▼
    def start_recording(self, save_folder):
        self.save_folder = save_folder
        self._pending_recording = True
        self.is_recording = True

    def stop_recording(self):
        self.is_recording = False
    # ▲▲▲ 新增结束 ▲▲▲

    def run(self):
        """
        线程的主执行函数，包含视频捕获循环。
        """
        self._running = True

        try:
            # 尝试使用 MSMF 后端打开摄像头
            self.cap = cv2.VideoCapture(self.camera_index, cv2.CAP_MSMF)

            if self.cap.isOpened():
                # 强制设置 MJPEG 格式！极大地节省 USB 带宽！
                self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M', 'J', 'P', 'G'))
                
                # 设置保守分辨率，确保多路并发
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                self.cap.set(cv2.CAP_PROP_FPS, 30)

                # 获取并验证实际生效的格式
                fourcc_int = int(self.cap.get(cv2.CAP_PROP_FOURCC))
                try:
                    # 尝试将数字解码为4个字母的格式代码
                    fourcc = "".join([chr((fourcc_int >> 8 * i) & 0xFF) for i in range(4)])
                except Exception:
                    # 如果解码失败，直接显示代号，防止程序崩溃
                    fourcc = f"未知代号: {fourcc_int}"
                    
                w = self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)
                h = self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
                print(f"✅ 摄像头 {self.camera_index} 实际参数: 格式={fourcc}, 尺寸={w}x{h}")

        except Exception as e:
            error_msg = f"打开摄像头 {self.camera_index} 失败: {str(e)}"
            print(f"Error: {error_msg}")
            self.camera_error.emit(error_msg, self.camera_index)
            self.camera_ready.emit(False, self.camera_index)
            self._running = False
            return

        # 检查摄像头是否成功打开
        if not self.cap.isOpened():
            error_msg = f"无法打开摄像头 {self.camera_index}。请确保摄像头已连接且未被占用。"
            print(f"Error: {error_msg}")
            self.camera_error.emit(error_msg, self.camera_index)
            self.camera_ready.emit(False, self.camera_index)
            self._running = False
            return

        # 摄像头成功打开
        print(f"摄像头 {self.camera_index} 已成功打开，开始捕获...")
        self.camera_ready.emit(True, self.camera_index)

        # ▼▼▼ 核心优化点：添加计数器用于抽帧 ▼▼▼
        frame_counter = 0

        # 主捕获循环
        while self._running and self.cap.isOpened():
            ret, frame = self.cap.read()
            if ret:
                frame_counter += 1

                # --- 1. 录像分支：最高画质，不抽帧 ---
                if self._pending_recording:
                    h, w = frame.shape[:2]
                    filename = time.strftime(f"摄像头{self.camera_index}_%Y%m%d_%H%M%S.mp4")
                    filepath = os.path.join(self.save_folder, filename)
                    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                    self.video_writer = cv2.VideoWriter(filepath, fourcc, 30.0, (w, h))
                    self._pending_recording = False
                    print(f"🔴 后台录像启动: {filepath}")

                if self.is_recording and self.video_writer is not None:
                    self.video_writer.write(frame) # 将原始的高清画面写入硬盘
                elif not self.is_recording and self.video_writer is not None:
                    # 收到停止指令，安全释放文件
                    self.video_writer.release()
                    self.video_writer = None
                    print(f"⏹️ 摄像头 {self.camera_index} 后台录像已安全保存。")

                # --- 2. 预览分支：抽帧 + 瘦身（UI 减负绝招） ---
                # 只有偶数帧才发给界面 (相当于 UI 只处理 15 FPS 的画面)
                if frame_counter % 2 == 0:
                    # 检查是否为灰度图像
                    if len(frame.shape) == 2 or (len(frame.shape) == 3 and frame.shape[2] == 1):
                        frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)

                    # 核心优化：把发给 UI 的图片缩小一半
                    preview_frame = cv2.resize(frame, (320, 240))
                    
                    self.frame_captured.emit(preview_frame)

            else:
                # 如果没有更多帧（例如摄像头断开），则停止捕获
                print(f"摄像头 {self.camera_index}: 未捕获到帧或摄像头已断开连接。")
                self.camera_error.emit(f"摄像头 {self.camera_index} 无法读取帧，可能已断开。", self.camera_index)
                self._running = False

            # 适当延迟，避免CPU占用过高
            QThread.msleep(5)

        # ▼▼▼ 安全的统一退出清理 ▼▼▼
        if self.video_writer is not None:
            self.video_writer.release()
            self.video_writer = None
            
        if self.cap and self.cap.isOpened():
            self.cap.release()
            print(f"摄像头 {self.camera_index} 已释放。")

        self.camera_ready.emit(False, self.camera_index)  # 摄像头关闭

    def stop(self):
        """
        停止捕获线程。
        """
        self._running = False
        self.wait()  # 等待线程完全结束，确保资源释放

    def is_running(self):
        return self._running
        
# --- 2. 可调整大小的视频显示区域组件 ---
class ResizableVideoFrame(QFrame):
    """
    可调整大小的视频帧显示区域。
    继承自QFrame以便获得边框和鼠标事件支持。
    """

    def __init__(self, camera_id, parent=None):
        super().__init__(parent)
        self.camera_id = camera_id
        self._current_frame = None
        self.init_ui()

        # 启用鼠标追踪，以便在未点击时也能接收鼠标移动事件
        self.setMouseTracking(True)

        # 设置框架样式，使其具有可见边框
        self.setFrameShape(QFrame.Shape.Box)
        self.setFrameShadow(QFrame.Shadow.Raised)
        self.setLineWidth(2)

        # 添加一个标签，显示"可拖拽调整大小"的提示
        self.resize_hint = QLabel("拖拽边缘调整大小", self)
        self.resize_hint.setStyleSheet("background-color: rgba(0, 0, 0, 120); color: white; padding: 3px;")
        self.resize_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.resize_hint.hide()  # 默认隐藏，鼠标悬停时显示

    def init_ui(self):
        layout = QVBoxLayout()

        # 视频显示标签
        self.video_label = QLabel(f"摄像头 {self.camera_id}: 等待视频流...")
        self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_label.setStyleSheet("background-color: black; border: none;")
        self.video_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        layout.addWidget(self.video_label)
        self.setLayout(layout)

        # 设置最小尺寸和默认大小
        self.setMinimumSize(240, 180)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def update_frame(self, frame):
        """
        更新视频帧，并确保颜色正确显示
        """
        if frame is None:
            return

        self._current_frame = frame.copy()  # 存储一份副本，用于resize时重绘

        # 确保图像是BGR格式，然后转换为RGB显示
        if len(frame.shape) == 2:  # 灰度图像
            # 如果是灰度图像，转换为3通道
            rgb_image = cv2.cvtColor(frame, cv2.COLOR_GRAY2RGB)
        else:  # 彩色图像
            # OpenCV默认使用BGR顺序，需要转换为RGB
            rgb_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        h, w, ch = rgb_image.shape
        bytes_per_line = ch * w

        # 创建QImage
        qt_image = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)

        # 获取label当前大小进行缩放
        target_size = self.video_label.size()
        if target_size.width() <= 0 or target_size.height() <= 0:
            return

        # 缩放并保持宽高比
        pixmap = QPixmap.fromImage(qt_image)
        scaled_pixmap = pixmap.scaled(
            target_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )

        self.video_label.setPixmap(scaled_pixmap)

    def clear_display(self):
        """清空视频显示"""
        self._current_frame = None
        self.video_label.clear()
        self.video_label.setText(f"摄像头 {self.camera_id}: 视频已停止")

    def resizeEvent(self, event):
        """当视频区域大小改变时，重新调整视频图像"""
        super().resizeEvent(event)
        if self._current_frame is not None:
            self.update_frame(self._current_frame)

        # 更新提示标签位置
        if hasattr(self, 'resize_hint'):
            self.resize_hint.move(
                (self.width() - self.resize_hint.width()) // 2,
                self.height() - self.resize_hint.height() - 10
            )

    def enterEvent(self, event):
        """鼠标进入时显示提示"""
        if hasattr(self, 'resize_hint'):
            self.resize_hint.show()

    def leaveEvent(self, event):
        """鼠标离开时隐藏提示"""
        if hasattr(self, 'resize_hint'):
            self.resize_hint.hide()


# --- 3. 单个摄像头控制和显示组件 ---
class CameraControlWidget(QWidget):
    """
    管理一个特定摄像头的视频采集、显示和其控制按钮的独立组件。
    """
    camera_stopped = Signal(int)
    camera_started = Signal(int)

    def __init__(self, camera_index, parent=None):
        super().__init__(parent)
        self.camera_index = camera_index
        self.video_thread = None
        self.video_frame = ResizableVideoFrame(camera_index)
        
        # 只需要保留保存路径即可，录像对象(writer)交给后台线程管理
        self.save_folder = "视频录像"
        import os
        os.makedirs(self.save_folder, exist_ok=True)

        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout()
        main_layout.addWidget(self.video_frame)

        control_layout = QHBoxLayout()
        self.camera_info_label = QLabel(f"摄像头 {self.camera_index} ")
        control_layout.addWidget(self.camera_info_label)

        self.start_button = QPushButton("启动")
        self.start_button.clicked.connect(self.start_capture)
        control_layout.addWidget(self.start_button)

        self.stop_button = QPushButton("停止")
        self.stop_button.clicked.connect(self.stop_capture)
        self.stop_button.setEnabled(False)
        control_layout.addWidget(self.stop_button)

        main_layout.addLayout(control_layout)
        self.setLayout(main_layout)

    # ▼▼▼ 核心减负：主界面现在只负责把画面画出来 ▼▼▼
    def handle_new_frame(self, frame):
        """主界面现在很轻松，只负责刷新显示，不再去写硬盘了"""
        self.video_frame.update_frame(frame)

    # ▼▼▼ 供总管调用的录像开关控制，直接委派给后台线程 ▼▼▼
    def start_recording(self):
        if not self.video_thread or not self.video_thread.is_running():
            return False 
        if getattr(self.video_thread, 'is_recording', False):
            return True # 已经在录了
        
        import os
        os.makedirs(self.save_folder, exist_ok=True)
        # 让后台线程自己去录像
        self.video_thread.start_recording(self.save_folder)
        return True

    def stop_recording(self):
        if self.video_thread and self.video_thread.is_running():
            self.video_thread.stop_recording()

    def start_capture(self):
        if self.video_thread and self.video_thread.isRunning():
            return

        self.video_frame.video_label.setText(f"摄像头 {self.camera_index}: 正在启动...")
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(False)

        self.video_thread = VideoCaptureThread(self.camera_index)
        
        # 将画面信号连接到极简版的 handle_new_frame
        self.video_thread.frame_captured.connect(self.handle_new_frame)
        self.video_thread.camera_ready.connect(self._on_camera_ready)
        self.video_thread.camera_error.connect(self._on_camera_error)
        self.video_thread.start()

    def stop_capture(self):
        if self.video_thread and self.video_thread.isRunning():
            # 关闭摄像头时，自动停止录像
            self.stop_recording()
            
            self.video_thread.stop()
            self.video_thread = None

            self.video_frame.clear_display()
            self.start_button.setEnabled(True)
            self.stop_button.setEnabled(False)
            self.camera_stopped.emit(self.camera_index)

    def _on_camera_ready(self, is_ready, camera_index):
        if is_ready:
            self.start_button.setEnabled(False)
            self.stop_button.setEnabled(True)
            self.camera_info_label.setText(f"摄像头 {camera_index} (运行中)")
            self.camera_started.emit(camera_index)
        else:
            self.start_button.setEnabled(True)
            self.stop_button.setEnabled(False)
            self.camera_info_label.setText(f"摄像头 {camera_index} (已停止)")
            if self.video_thread and not self.video_thread.isRunning():
                self.video_thread = None

    def _on_camera_error(self, message, camera_index):
        QMessageBox.critical(self, f"摄像头 {camera_index} 错误", message)
        self.stop_capture()

    def cleanup_on_close(self):
        self.stop_recording() # 关闭软件时确保视频保存完好
        self.stop_capture()


# --- 4. 多摄像头视图管理器 ---
class MultiCameraViewer(QWidget):
    """
    使用QSplitter管理多个摄像头视图，允许用户通过拖动分隔线调整每个视图的大小。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.camera_widgets = {}  # 存储 CameraControlWidget 实例
        self.init_ui()
        self.probe_and_add_cameras()

    def init_ui(self):
        main_layout = QVBoxLayout()

        # 顶部控制区域
        top_control_layout = QHBoxLayout()
        refresh_button = QPushButton("刷新摄像头")
        refresh_button.clicked.connect(self.probe_and_add_cameras)
        top_control_layout.addWidget(refresh_button)

        # ▼▼▼ 新增：全局录像控制按钮 ▼▼▼
        self.btn_start_record = QPushButton("全部开始录屏")
        self.btn_start_record.setStyleSheet("background-color: #E74C3C; color: white; font-weight: bold;")
        self.btn_start_record.clicked.connect(self.start_all_recording)
        
        self.btn_stop_record = QPushButton("全部停止录屏")
        self.btn_stop_record.setStyleSheet("background-color: #7F8C8D; color: white; font-weight: bold;")
        self.btn_stop_record.setEnabled(False)
        self.btn_stop_record.clicked.connect(self.stop_all_recording)
        
        top_control_layout.addWidget(self.btn_start_record)
        top_control_layout.addWidget(self.btn_stop_record)
        # ▲▲▲ 新增结束 ▲▲▲

        top_control_layout.addStretch()
        main_layout.addLayout(top_control_layout)

        # 使用QSplitter的容器
        self.splitter_container = QWidget()
        self.splitter_layout = QVBoxLayout(self.splitter_container)
        self.splitter_layout.setContentsMargins(0, 0, 0, 0)

        main_layout.addWidget(self.splitter_container, 1)  # 1表示伸缩因子
        self.setLayout(main_layout)

        # ▼▼▼ 新增：遍历并控制所有摄像头录像的方法 ▼▼▼
    def start_all_recording(self):
        started_any = False
        for idx, widget in self.camera_widgets.items():
            if widget.start_recording():
                started_any = True
                
        if started_any:
            self.btn_start_record.setEnabled(False)
            self.btn_stop_record.setEnabled(True)
            self.btn_stop_record.setStyleSheet("background-color: #2ECC71; color: white; font-weight: bold;")
            QMessageBox.information(self, "录像开启", "已开始录制所有正在运行的摄像头！")
        else:
            QMessageBox.warning(self, "操作无效", "当前没有任何正在运行的摄像头，无法开始录制。")

    def stop_all_recording(self):
        for idx, widget in self.camera_widgets.items():
            widget.stop_recording()
            
        self.btn_start_record.setEnabled(True)
        self.btn_stop_record.setEnabled(False)
        self.btn_stop_record.setStyleSheet("background-color: #7F8C8D; color: white; font-weight: bold;")
        QMessageBox.information(self, "录像完成", "所有录像已结束，文件已保存至项目目录下的「视频录像」文件夹中。")
    # ▲▲▲ 新增结束 ▲▲▲

    def probe_and_add_cameras(self):
        """探测并添加摄像头"""
        print("正在探测可用摄像头...")
        self.clear_all_camera_widgets()  # 清理旧的摄像头widget

        # 探测可用摄像头
        available_camera_indices = self._detect_cameras()

        if not available_camera_indices:
            self._show_no_cameras_message()
            return

        self._create_camera_widgets(available_camera_indices)

    def _detect_cameras(self):
        """探测系统中可用的摄像头"""
        available_indices = []
        for i in range(10):  # 尝试前10个索引
            try:
                # 尝试使用DSHOW后端(Windows)
                cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
                if cap.isOpened():
                    ret, _ = cap.read()
                    if ret:
                        available_indices.append(i)
                        print(f"发现摄像头: {i}")
                    cap.release()
            except Exception as e:
                print(f"探测摄像头 {i} 时出错: {str(e)}")
                if 'cap' in locals() and cap:
                    cap.release()

        return available_indices

    def _show_no_cameras_message(self):
        """显示无摄像头的消息"""
        print("未发现任何摄像头")
        # 清空现有布局
        self._clear_splitter_layout()

        # 添加提示标签
        no_camera_label = QLabel("未发现任何摄像头。\n请确保摄像头已连接并尝试刷新。")
        no_camera_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        no_camera_label.setStyleSheet("font-size: 16px; color: #666;")
        self.splitter_layout.addWidget(no_camera_label)

    def _create_camera_widgets(self, camera_indices):
        """为每个摄像头创建控制组件并布局"""
        # 清空现有布局
        self._clear_splitter_layout()

        # 根据摄像头数量选择布局方式
        if len(camera_indices) == 1:
            # 单个摄像头，直接添加
            camera_widget = CameraControlWidget(camera_indices[0])
            self.camera_widgets[camera_indices[0]] = camera_widget
            self.splitter_layout.addWidget(camera_widget)
        else:
            # 多个摄像头，使用垂直和水平分割器
            main_splitter = QSplitter(Qt.Orientation.Vertical)

            # 将摄像头索引分组，每两个一组
            paired_indices = []
            for i in range(0, len(camera_indices), 2):
                if i + 1 < len(camera_indices):
                    paired_indices.append((camera_indices[i], camera_indices[i + 1]))
                else:
                    paired_indices.append((camera_indices[i],))

            # 为每一组创建水平分割器
            for row_indices in paired_indices:
                row_splitter = QSplitter(Qt.Orientation.Horizontal)

                # 添加该行的摄像头
                for idx in row_indices:
                    camera_widget = CameraControlWidget(idx)
                    self.camera_widgets[idx] = camera_widget
                    row_splitter.addWidget(camera_widget)

                # 设置均匀的初始尺寸
                sizes = [100] * len(row_indices)  # 初始分配比例
                row_splitter.setSizes(sizes)

                # 将行分割器添加到主分割器
                main_splitter.addWidget(row_splitter)

            # 设置均匀的垂直尺寸
            main_splitter.setSizes([100] * len(paired_indices))

            # 添加主分割器到布局
            self.splitter_layout.addWidget(main_splitter)

    def _clear_splitter_layout(self):
        """清空分割器布局内的所有控件"""
        while self.splitter_layout.count():
            item = self.splitter_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
                item.widget().deleteLater()

    def clear_all_camera_widgets(self):
        """停止所有摄像头并清理资源"""
        for index, widget in list(self.camera_widgets.items()):
            widget.cleanup_on_close()
            del self.camera_widgets[index]

        self._clear_splitter_layout()

    def cleanup_on_close(self):
        """程序关闭时的清理工作"""
        self.clear_all_camera_widgets()

