#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
紧急停止功能测试脚本
专门测试紧急停止按钮是否会导致程序闪退
"""

import sys
import time
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, 
    QPushButton, QLabel, QGroupBox, QWidget, QTextEdit,
    QMessageBox
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont

# 模拟串口管理器
class MockSerialManager:
    def __init__(self):
        self.connected = False
        
    def is_connected(self):
        return self.connected
        
    def connect_serial(self, port, baud):
        self.connected = True
        return True
        
    def disconnect_serial(self):
        self.connected = False
        
    def send_data(self, data):
        # 模拟发送数据
        print(f"模拟发送数据: {data.hex().upper()}")
        return True

class EmergencyStopTestWindow(QMainWindow):
    """紧急停止测试窗口"""
    
    def __init__(self):
        super().__init__()
        self.serial_manager = MockSerialManager()
        self.init_ui()
        
    def init_ui(self):
        self.setWindowTitle("紧急停止功能测试")
        self.setGeometry(100, 100, 800, 600)
        
        # 主布局
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        # 标题
        title_label = QLabel("紧急停止功能测试工具")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet("""
            font-size: 18px;
            font-weight: bold;
            color: #2C3E50;
            margin: 10px;
        """)
        main_layout.addWidget(title_label)
        
        # 说明文字
        desc_label = QLabel("此工具用于测试紧急停止按钮是否会导致程序闪退")
        desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc_label.setStyleSheet("color: #7F8C8D; margin: 5px;")
        main_layout.addWidget(desc_label)
        
        # 串口状态控制
        serial_group = QGroupBox("串口状态控制")
        serial_layout = QHBoxLayout(serial_group)
        
        self.connect_btn = QPushButton("连接串口")
        self.connect_btn.clicked.connect(self.connect_serial)
        self.disconnect_btn = QPushButton("断开串口")
        self.disconnect_btn.clicked.connect(self.disconnect_serial)
        self.disconnect_btn.setEnabled(False)
        
        serial_layout.addWidget(self.connect_btn)
        serial_layout.addWidget(self.disconnect_btn)
        serial_layout.addStretch()
        
        main_layout.addWidget(serial_group)
        
        # 紧急停止测试区域
        test_group = QGroupBox("紧急停止测试")
        test_layout = QVBoxLayout(test_group)
        
        # 紧急停止按钮（模拟主程序中的按钮）
        self.emergency_btn = QPushButton("紧急停止")
        self.emergency_btn.setStyleSheet("""
            QPushButton {
                background-color: #E74C3C;
                color: white;
                font-weight: bold;
                font-size: 16px;
                padding: 15px;
                border: none;
                border-radius: 8px;
                margin: 10px;
            }
            QPushButton:hover {
                background-color: #C0392B;
            }
            QPushButton:pressed {
                background-color: #922B21;
            }
        """)
        self.emergency_btn.clicked.connect(self.send_emergency_stop)
        test_layout.addWidget(self.emergency_btn)
        
        # 测试控制按钮
        test_buttons_layout = QHBoxLayout()
        
        self.single_test_btn = QPushButton("单次测试")
        self.single_test_btn.clicked.connect(self.single_test)
        test_buttons_layout.addWidget(self.single_test_btn)
        
        self.multiple_test_btn = QPushButton("连续测试(10次)")
        self.multiple_test_btn.clicked.connect(self.multiple_test)
        test_buttons_layout.addWidget(self.multiple_test_btn)
        
        self.clear_log_btn = QPushButton("清空日志")
        self.clear_log_btn.clicked.connect(self.clear_log)
        test_buttons_layout.addWidget(self.clear_log_btn)
        
        test_layout.addLayout(test_buttons_layout)
        main_layout.addWidget(test_group)
        
        # 日志区域
        log_group = QGroupBox("测试日志")
        log_layout = QVBoxLayout(log_group)
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("""
            QTextEdit {
                background-color: #2C3E50;
                color: #ECF0F1;
                border: 1px solid #34495E;
                border-radius: 4px;
                font-family: 'Courier New', monospace;
                font-size: 11px;
                padding: 8px;
            }
        """)
        log_layout.addWidget(self.log_text)
        
        main_layout.addWidget(log_group)
        
        # 状态栏
        self.statusBar().showMessage("准备就绪")
        
        # 初始日志
        self.log_message("紧急停止功能测试工具已启动")
        self.log_message("请先连接串口，然后进行测试")
        
    def connect_serial(self):
        """连接串口"""
        if self.serial_manager.connect_serial("COM1", 9600):
            self.connect_btn.setEnabled(False)
            self.disconnect_btn.setEnabled(True)
            self.log_message("串口已连接")
            self.statusBar().showMessage("串口已连接", 3000)
        else:
            self.log_message("串口连接失败")
            
    def disconnect_serial(self):
        """断开串口"""
        self.serial_manager.disconnect_serial()
        self.connect_btn.setEnabled(True)
        self.disconnect_btn.setEnabled(False)
        self.log_message("串口已断开")
        self.statusBar().showMessage("串口已断开", 3000)
        
    def send_emergency_stop(self):
        """发送紧急停止命令（修复后的版本）"""
        if not self.serial_manager.is_connected():
            self.statusBar().showMessage("错误: 串口未连接，无法发送紧急停止命令", 3000)
            self.log_message("错误: 串口未连接，无法发送紧急停止命令")
            print("❌ 紧急停止失败: 串口未连接")
            return

        # 紧急停止命令扩展为10字节，后面补0
        command = bytes([0xEE, 0x00, 0x00, 0x00] + [0x00] * 6)
        
        try:
            success = self.serial_manager.send_data(command)
            if success:
                message = "已发送: 紧急停止命令 ({})".format(command.hex().upper())
                self.log_message(message)
                
                # 使用状态栏显示，不阻塞主线程
                self.statusBar().showMessage("紧急停止命令已发送！", 5000)
                print(f"✅ {message}")
            else:
                error_message = "发送失败: 紧急停止命令 ({})".format(command.hex().upper())
                self.log_message(error_message)
                
                # 使用状态栏显示错误
                self.statusBar().showMessage("紧急停止命令发送失败！", 5000)
                print(f"❌ {error_message}")
                
        except Exception as e:
            error_message = f"紧急停止命令发送异常: {e}"
            self.log_message(error_message)
            
            # 使用状态栏显示异常
            self.statusBar().showMessage("紧急停止命令发送异常！", 5000)
            print(f"❌ {error_message}")
            import traceback
            traceback.print_exc()
            
    def single_test(self):
        """单次测试"""
        self.log_message("执行单次紧急停止测试...")
        self.send_emergency_stop()
        self.log_message("单次测试完成")
        
    def multiple_test(self):
        """连续测试"""
        self.log_message("开始连续紧急停止测试（10次）...")
        
        for i in range(10):
            self.log_message(f"第 {i+1} 次测试")
            self.send_emergency_stop()
            # 短暂延时
            QTimer.singleShot(100, lambda: None)
            time.sleep(0.1)
            
        self.log_message("连续测试完成")
        
    def clear_log(self):
        """清空日志"""
        self.log_text.clear()
        self.log_message("日志已清空")
        
    def log_message(self, message):
        """记录日志消息"""
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        formatted_message = f"[{timestamp}] {message}"
        self.log_text.append(formatted_message)
        
        # 滚动到底部
        sb = self.log_text.verticalScrollBar()
        sb.setValue(sb.maximum())


def main():
    app = QApplication(sys.argv)
    
    # 设置应用样式
    app.setStyle("Fusion")
    
    # 创建测试窗口
    window = EmergencyStopTestWindow()
    window.show()
    
    print("紧急停止功能测试工具")
    print("用于验证紧急停止按钮是否会导致程序闪退")
    print("测试步骤：")
    print("1. 点击'连接串口'")
    print("2. 点击'紧急停止'按钮")
    print("3. 观察程序是否闪退")
    print("4. 可以尝试连续测试")
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
