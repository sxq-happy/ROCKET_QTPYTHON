# video_components.py
import sys
import cv2
import numpy as np
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QMessageBox,
    QSizePolicy, QSplitter, QFrame
)
from PyQt6.QtCore import (
    Qt, QThread, pyqtSignal, QTimer, QSize
)
from PyQt6.QtGui import (
    QImage, QPixmap
)


# --- 1. 视频采集线程 ---
class VideoCaptureThread(QThread):
    """
    独立线程，用于从 USB 摄像头捕获视频帧。
    捕获到的帧将通过信号发送给主线程。
    同时，该线程会报告摄像头的状态和发生的错误，并包含其对应摄像头的索引。
    """
    frame_captured = pyqtSignal(np.ndarray)  # 发送 NumPy 数组格式的帧
    camera_ready = pyqtSignal(bool, int)  # 信号：(是否成功打开, 摄像头索引)
    camera_error = pyqtSignal(str, int)  # 信号：(错误信息, 摄像头索引)

    def __init__(self, camera_index=0, parent=None):
        super().__init__(parent)
        self.camera_index = camera_index
        self._running = False
        self.cap = None

    def run(self):
        """
        线程的主执行函数，包含视频捕获循环。
        """
        self._running = True

        # 先尝试打开并配置摄像头格式为MJPEG
        try:
            # 打开带DSHOW后端的摄像头 (Windows平台)
            self.cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)

            if self.cap.isOpened():
                # 重要：设置MJPEG格式 (FourCC编码是'MJPG')
                self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M', 'J', 'P', 'G'))
                # 设置分辨率 (可选，根据摄像头支持情况调整)
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
                # 设置帧率 (可选)
                self.cap.set(cv2.CAP_PROP_FPS, 30)

                # 重新打开以应用设置 (有时是必须的)
                # 某些摄像头在CAP_PROP_FOURCC设置后需要先release再重新open才能生效
                self.cap.release()
                self.cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)

                # 验证是否成功设置了MJPEG格式
                fourcc_int = int(self.cap.get(cv2.CAP_PROP_FOURCC))
                fourcc = "".join([chr((fourcc_int >> 8 * i) & 0xFF) for i in range(4)])
                print(f"摄像头 {self.camera_index} 使用的格式: {fourcc}")

        except Exception as e:
            print(f"配置摄像头 {self.camera_index} 格式时出错: {str(e)}")
            # 如果设置MJPEG失败，尝试使用默认格式
            try:
                if self.cap:
                    self.cap.release()
                self.cap = cv2.VideoCapture(self.camera_index)
            except Exception as e2:
                error_msg = f"打开摄像头 {self.camera_index} 失败: {str(e2)}"
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

        # 主捕获循环
        while self._running and self.cap.isOpened():
            ret, frame = self.cap.read()
            if ret:
                # 检查是否为灰度图像
                if len(frame.shape) == 2 or (len(frame.shape) == 3 and frame.shape[2] == 1):
                    # 如果是灰度图，转换为3通道
                    frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)

                # 确保图像是BGR格式
                # OpenCV默认捕获BGR，无需额外转换除非已知设备输出不同

                self.frame_captured.emit(frame)
            else:
                # 如果没有更多帧（例如摄像头断开），则停止捕获
                print(f"摄像头 {self.camera_index}: 未捕获到帧或摄像头已断开连接。")
                self.camera_error.emit(f"摄像头 {self.camera_index} 无法读取帧，可能已断开。", self.camera_index)
                self._running = False

            # 适当延迟，避免CPU占用过高
            QThread.msleep(5)

        # 确保在退出循环后，摄像头被释放
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
    camera_stopped = pyqtSignal(int)
    camera_started = pyqtSignal(int)

    def __init__(self, camera_index, parent=None):
        super().__init__(parent)
        self.camera_index = camera_index
        self.video_thread = None
        # 使用可调整大小的视频帧
        self.video_frame = ResizableVideoFrame(camera_index)
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout()

        # 视频显示区域
        main_layout.addWidget(self.video_frame)

        # 控制按钮区域
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

    def start_capture(self):
        """启动视频捕获"""
        if self.video_thread and self.video_thread.isRunning():
            print(f"摄像头 {self.camera_index} 已在运行中")
            return

        print(f"正在启动摄像头 {self.camera_index}...")
        self.video_frame.video_label.setText(f"摄像头 {self.camera_index}: 正在启动...")

        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(False)

        self.video_thread = VideoCaptureThread(self.camera_index)
        self.video_thread.frame_captured.connect(self.video_frame.update_frame)
        self.video_thread.camera_ready.connect(self._on_camera_ready)
        self.video_thread.camera_error.connect(self._on_camera_error)
        self.video_thread.start()

    def stop_capture(self):
        """停止视频捕获"""
        if self.video_thread and self.video_thread.isRunning():
            print(f"正在停止摄像头 {self.camera_index}...")
            self.video_thread.stop()
            self.video_thread = None

            self.video_frame.clear_display()
            self.start_button.setEnabled(True)
            self.stop_button.setEnabled(False)
            self.camera_stopped.emit(self.camera_index)
        else:
            print(f"摄像头 {self.camera_index} 未运行")

    def _on_camera_ready(self, is_ready, camera_index):
        """处理摄像头就绪状态变化"""
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
        """处理摄像头错误"""
        print(f"摄像头 {camera_index} 错误: {message}")
        QMessageBox.critical(self, f"摄像头 {camera_index} 错误", message)
        self.stop_capture()

    def cleanup_on_close(self):
        """资源清理"""
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
        top_control_layout.addStretch()
        main_layout.addLayout(top_control_layout)

        # 使用QSplitter的容器
        self.splitter_container = QWidget()
        self.splitter_layout = QVBoxLayout(self.splitter_container)
        self.splitter_layout.setContentsMargins(0, 0, 0, 0)

        main_layout.addWidget(self.splitter_container, 1)  # 1表示伸缩因子
        self.setLayout(main_layout)

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

