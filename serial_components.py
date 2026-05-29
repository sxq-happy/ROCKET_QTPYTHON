# serial_components.py
import os
import serial
import serial.tools.list_ports
import threading
import time
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton, QLabel, QMessageBox, QTabWidget,
    QComboBox, QLineEdit, QTextEdit, QDialog, QFormLayout, QSlider, QSpinBox, QGroupBox, QRadioButton, QApplication
)
from PySide6.QtCore import (
    Qt, QThread, Signal, QTimer, QSize, QIODevice, QObject
)
import pyqtgraph as pg
import csv
from datetime import datetime

from openpyxl.workbook import Workbook

def calculate_crc16(data: bytes) -> bytes:
    """计算 Modbus RTU CRC16 校验码"""
    crc = 0xFFFF
    for pos in data:
        crc ^= pos
        for i in range(8):
            if (crc & 1) != 0:
                crc >>= 1
                crc ^= 0xA001
            else:
                crc >>= 1
    return crc.to_bytes(2, byteorder='little')

# --- 串口读取线程 (作为SerialManager的内部类) ---
class SerialReaderThread(QThread):
    data_received = Signal(bytes)
    error_occurred = Signal(str)

    def __init__(self, serial_port, parent=None):
        super().__init__(parent)
        self.serial_port = serial_port
        self._running = True
        self._stop_requested = False

    def run(self):  # <-- 修正：这个方法需要在类内部正确缩进
        consecutive_errors = 0
        max_consecutive_errors = 5

        while self._running and not self._stop_requested:
            try:
                # 检查串口对象是否仍然有效
                if not self.serial_port or not hasattr(self.serial_port, 'is_open'):
                    break

                if not self.serial_port.is_open:
                    break

                # 安全地检查是否有数据可读
                try:
                    bytes_available = self.serial_port.in_waiting
                except (OSError, AttributeError):
                    # 串口可能已经被关闭
                    break

                if bytes_available > 0:
                    # 限制单次读取的数据量，防止内存问题
                    bytes_to_read = min(bytes_available, 1024)
                    try:
                        data = self.serial_port.read(bytes_to_read)
                        if data and len(data) > 0:
                            self.data_received.emit(data)
                            consecutive_errors = 0  # 重置错误计数
                    except (OSError, serial.SerialException):
                        # 串口读取错误，可能设备已断开，不弹窗只记录
                        consecutive_errors += 1
                        if consecutive_errors >= max_consecutive_errors:
                            self.error_occurred.emit(f"串口读取连续错误")
                            break
                        else:
                            self.msleep(100)
                        continue

                # 使用msleep而不是time.sleep，更适合QThread
                self.msleep(10)  # 10ms延迟

            except Exception as e:
                consecutive_errors += 1
                if consecutive_errors >= max_consecutive_errors:
                    self.error_occurred.emit(f"串口读取错误: {str(e)[:50]}")
                    break
                else:
                    # 短暂等待后重试
                    self.msleep(100)

    def stop(self):
        self._stop_requested = True
        self._running = False
        # 等待线程结束，但不要无限等待
        if not self.wait(3000):  # 等待最多3秒
            # 如果线程没有正常结束，强制终止
            self.terminate()
            self.wait(1000)  # 再等待1秒确保终止

# --- 双串口管理中心 ---
class SerialManager(QObject):
    # 定义信号
    connected = Signal(str, int)  # (port_name, baud_rate) - 兼容性信号
    disconnected = Signal()
    data_received = Signal(bytes)
    error_occurred = Signal(str)

    # 双串口专用信号
    port1_connected = Signal(str, int)  # 串口1连接
    port2_connected = Signal(str, int)  # 串口2连接
    port1_disconnected = Signal()  # 串口1断开
    port2_disconnected = Signal()  # 串口2断开
    port1_data_received = Signal(bytes)  # 串口1数据
    port2_data_received = Signal(bytes)  # 串口2数据

    def __init__(self, parent=None):
        super().__init__(parent)
        # 串口1 - 用于点火/灭火
        self._serial_port1 = None
        self._reader_thread1 = None
        self._is_connected1 = False

        # 串口2 - 用于其他控制
        self._serial_port2 = None
        self._reader_thread2 = None
        self._is_connected2 = False

    def is_connected(self):
        """返回是否有任一串口处于连接状态（兼容性方法）"""
        return self.is_port1_connected() or self.is_port2_connected()

    def is_port1_connected(self):
        """返回串口1是否处于连接状态"""
        return self._is_connected1 and self._serial_port1 is not None and self._serial_port1.is_open

    def is_port2_connected(self):
        """返回串口2是否处于连接状态"""
        return self._is_connected2 and self._serial_port2 is not None and self._serial_port2.is_open

    def connect_port1(self, port_name, baud_rate, data_bits, parity, stop_bits, rtscts, xonxoff):
        """连接串口1（点火/灭火专用）"""
        if self.is_port1_connected():
            self.error_occurred.emit("串口1已连接，请先断开。")
            return False

        return self._connect_port(1, port_name, baud_rate, data_bits, parity, stop_bits, rtscts, xonxoff)

    def connect_port2(self, port_name, baud_rate, data_bits, parity, stop_bits, rtscts, xonxoff):
        """连接串口2（其他控制专用）"""
        if self.is_port2_connected():
            self.error_occurred.emit("串口2已连接，请先断开。")
            return False

        return self._connect_port(2, port_name, baud_rate, data_bits, parity, stop_bits, rtscts, xonxoff)

    def connect_serial(self, port_name, baud_rate, data_bits, parity, stop_bits, rtscts, xonxoff):
        """兼容性方法：连接串口1"""
        return self.connect_port1(port_name, baud_rate, data_bits, parity, stop_bits, rtscts, xonxoff)

    def _connect_port(self, port_num, port_name, baud_rate, data_bits, parity, stop_bits, rtscts, xonxoff):
        """内部方法：连接指定串口"""
        try:
            # 创建串口对象
            serial_port = serial.Serial(
                port=port_name,
                baudrate=baud_rate,
                bytesize=data_bits,
                parity=parity,
                stopbits=stop_bits,
                timeout=0.1,  # 读取超时时间，非阻塞读取
                write_timeout=0.1,  # 写入超时时间
                rtscts=rtscts,
                xonxoff=xonxoff
            )

            if serial_port.is_open:
                # 根据端口号设置对应的变量
                if port_num == 1:
                    self._serial_port1 = serial_port
                    self._is_connected1 = True

                    # 启动读取线程
                    try:
                        self._reader_thread1 = SerialReaderThread(serial_port, self)
                        self._reader_thread1.data_received.connect(self.port1_data_received.emit)
                        self._reader_thread1.data_received.connect(self.data_received.emit)  # 兼容性
                        self._reader_thread1.error_occurred.connect(self.error_occurred.emit)
                        self._reader_thread1.finished.connect(lambda: self._reader_thread_finished(1))
                        self._reader_thread1.start()

                        # 发出连接信号
                        self.port1_connected.emit(port_name, baud_rate)
                        self.connected.emit(port_name, baud_rate)  # 兼容性
                        return True
                    except Exception as e:
                        # 线程创建失败，清理资源
                        self._is_connected1 = False
                        if self._serial_port1:
                            try:
                                self._serial_port1.close()
                            except:
                                pass
                            self._serial_port1 = None
                        self.error_occurred.emit(f"创建串口1读取线程失败：{e}")
                        return False

                elif port_num == 2:
                    self._serial_port2 = serial_port
                    self._is_connected2 = True

                    # 启动读取线程
                    try:
                        self._reader_thread2 = SerialReaderThread(serial_port, self)
                        self._reader_thread2.data_received.connect(self.port2_data_received.emit)
                        self._reader_thread2.data_received.connect(self.data_received.emit)  # 兼容性
                        self._reader_thread2.error_occurred.connect(self.error_occurred.emit)
                        self._reader_thread2.finished.connect(lambda: self._reader_thread_finished(2))
                        self._reader_thread2.start()

                        # 发出连接信号
                        self.port2_connected.emit(port_name, baud_rate)
                        self.connected.emit(port_name, baud_rate)  # 兼容性
                        return True
                    except Exception as e:
                        # 线程创建失败，清理资源
                        self._is_connected2 = False
                        if self._serial_port2:
                            try:
                                self._serial_port2.close()
                            except:
                                pass
                            self._serial_port2 = None
                        self.error_occurred.emit(f"创建串口2读取线程失败：{e}")
                        return False
            else:
                self.error_occurred.emit(f"无法打开串口{port_num} {port_name}。")
                return False

        except serial.SerialException as e:
            self.error_occurred.emit(f"串口{port_num}连接错误: {e}")
            return False
        except Exception as e:
            self.error_occurred.emit(f"串口{port_num}发生未知错误: {e}")
            return False

    def disconnect_port1(self):
        """断开串口1连接"""
        return self._disconnect_port(1)

    def disconnect_port2(self):
        """断开串口2连接"""
        return self._disconnect_port(2)

    def disconnect_serial(self):
        """兼容性方法：断开所有串口连接"""
        self.disconnect_port1()
        self.disconnect_port2()

    def _disconnect_port(self, port_num):
        """内部方法：断开指定串口"""
        if port_num == 1:
            was_connected = self._is_connected1
            self._is_connected1 = False

            # 停止读取线程
            if self._reader_thread1 and self._reader_thread1.isRunning():
                try:
                    self._reader_thread1.data_received.disconnect()
                    self._reader_thread1.error_occurred.disconnect()
                    self._reader_thread1.finished.disconnect()
                except:
                    pass

                self._reader_thread1.stop()
                if not self._reader_thread1.wait(3000):
                    self._reader_thread1.terminate()
                    self._reader_thread1.wait(1000)

            # 关闭串口
            if self._serial_port1:
                try:
                    if hasattr(self._serial_port1, 'is_open') and self._serial_port1.is_open:
                        try:
                            self._serial_port1.reset_input_buffer()
                            self._serial_port1.reset_output_buffer()
                        except:
                            pass
                        self._serial_port1.close()
                except Exception as e:
                    print(f"关闭串口1时发生错误：{e}")
                finally:
                    self._serial_port1 = None

            # 清理线程引用
            self._reader_thread1 = None

            # 发出断开信号
            if was_connected:
                try:
                    self.port1_disconnected.emit()
                    self.disconnected.emit()  # 兼容性
                except:
                    pass

        elif port_num == 2:
            was_connected = self._is_connected2
            self._is_connected2 = False

            # 停止读取线程
            if self._reader_thread2 and self._reader_thread2.isRunning():
                try:
                    self._reader_thread2.data_received.disconnect()
                    self._reader_thread2.error_occurred.disconnect()
                    self._reader_thread2.finished.disconnect()
                except:
                    pass

                self._reader_thread2.stop()
                if not self._reader_thread2.wait(3000):
                    self._reader_thread2.terminate()
                    self._reader_thread2.wait(1000)

            # 关闭串口
            if self._serial_port2:
                try:
                    if hasattr(self._serial_port2, 'is_open') and self._serial_port2.is_open:
                        try:
                            self._serial_port2.reset_input_buffer()
                            self._serial_port2.reset_output_buffer()
                        except:
                            pass
                        self._serial_port2.close()
                except Exception as e:
                    print(f"关闭串口2时发生错误：{e}")
                finally:
                    self._serial_port2 = None

            # 清理线程引用
            self._reader_thread2 = None

            # 发出断开信号
            if was_connected:
                try:
                    self.port2_disconnected.emit()
                except:
                    pass

    def _reader_thread_finished(self, port_num):
        """当读取线程结束时调用，处理异常断开或正常终止。"""
        try:
            if port_num == 1:
                # 检查串口1是否是异常断开
                if self._is_connected1 and (self._serial_port1 is None or not hasattr(self._serial_port1,
                                                                                      'is_open') or not self._serial_port1.is_open):
                    self._is_connected1 = False
                    try:
                        self.error_occurred.emit("串口1读取线程异常终止，连接可能已断开。")
                        self.port1_disconnected.emit()
                        self.disconnected.emit()  # 兼容性
                    except:
                        pass
                # 清除对已结束线程的引用
                self._reader_thread1 = None

            elif port_num == 2:
                # 检查串口2是否是异常断开
                if self._is_connected2 and (self._serial_port2 is None or not hasattr(self._serial_port2,
                                                                                      'is_open') or not self._serial_port2.is_open):
                    self._is_connected2 = False
                    try:
                        self.error_occurred.emit("串口2读取线程异常终止，连接可能已断开。")
                        self.port2_disconnected.emit()
                    except:
                        pass
                # 清除对已结束线程的引用
                self._reader_thread2 = None

        except Exception as e:
            # 防止在清理过程中出现新的错误
            print(f"串口{port_num}线程清理时发生错误: {e}")
            if port_num == 1:
                self._reader_thread1 = None
            elif port_num == 2:
                self._reader_thread2 = None

    def send_ignition_command(self, data: bytes):
        """发送点火/灭火命令（使用串口1）"""
        return self.send_to_port1(data)

    def send_control_command(self, data: bytes):
        """发送其他控制命令（使用串口2）"""
        return self.send_to_port2(data)

    def send_sequence_command(self, data: bytes):
        """发送序列命令（真正同时发送到两个串口，最小化延时）"""

        # 检查连接状态
        port1_available = self.is_port1_connected()
        port2_available = self.is_port2_connected()

        if not port1_available and not port2_available:
            self.error_occurred.emit("两个串口都未连接，无法发送序列命令。")
            return False

        # 用于存储发送结果
        results = {'port1': False, 'port2': False}
        exceptions = {'port1': None, 'port2': None}

        def send_to_port1_thread():
            """串口1发送线程"""
            try:
                if port1_available:
                    results['port1'] = self._send_to_port(1, data)
                else:
                    results['port1'] = False
            except Exception as e:
                exceptions['port1'] = e
                results['port1'] = False

        def send_to_port2_thread():
            """串口2发送线程"""
            try:
                if port2_available:
                    results['port2'] = self._send_to_port(2, data)
                else:
                    results['port2'] = False
            except Exception as e:
                exceptions['port2'] = e
                results['port2'] = False

        # 记录开始时间（用于延时分析）
        start_time = time.perf_counter()

        # 使用事件同步，确保真正"同时"启动
        sync_event = threading.Event()

        # 修改线程函数，等待同步事件
        def synchronized_send_to_port1():
            sync_event.wait()  # 等待同步信号
            send_to_port1_thread()

        def synchronized_send_to_port2():
            sync_event.wait()  # 等待同步信号
            send_to_port2_thread()

        # 创建同步线程
        thread1 = threading.Thread(target=synchronized_send_to_port1, name="SerialPort1Send")
        thread2 = threading.Thread(target=synchronized_send_to_port2, name="SerialPort2Send")

        # 启动线程（但它们会等待同步事件）
        thread1.start()
        thread2.start()

        # 短暂延时确保线程都已启动并等待
        time.sleep(0.001)  # 1ms确保线程就绪

        # 发出同步信号，让两个线程真正同时开始执行
        sync_event.set()

        # 等待两个线程完成，设置超时防止死锁
        thread1.join(timeout=1.0)  # 1秒超时
        thread2.join(timeout=1.0)  # 1秒超时

        # 计算总用时
        end_time = time.perf_counter()  
        total_time_ms = (end_time - start_time) * 1000

        # 检查是否有线程超时
        if thread1.is_alive():
            self.error_occurred.emit("串口1发送超时")
            results['port1'] = False
        if thread2.is_alive():
            self.error_occurred.emit("串口2发送超时")
            results['port2'] = False

        # 记录发送时间（用于调试）
        print(f"双串口序列命令发送完成，用时: {total_time_ms:.2f}ms")

        # 处理异常
        if exceptions['port1']:
            self.error_occurred.emit(f"串口1发送异常: {exceptions['port1']}")
        if exceptions['port2']:
            self.error_occurred.emit(f"串口2发送异常: {exceptions['port2']}")

        # 返回结果：至少一个端口发送成功就算成功
        success = results['port1'] or results['port2']

        if success:
            success_ports = []
            if results['port1'] and port1_available:
                success_ports.append("串口1")
            if results['port2'] and port2_available:
                success_ports.append("串口2")
            print(f"✅ 序列命令发送成功: {', '.join(success_ports)}")
        else:
            print("❌ 序列命令发送失败: 所有串口都失败")

        return success

    def send_sequence_command_ultra_sync(self, data: bytes):
        """超高精度同步发送（微秒级同步，适用于对时序要求极高的场景）"""

        # 检查连接状态
        port1_available = self.is_port1_connected()
        port2_available = self.is_port2_connected()

        if not port1_available and not port2_available:
            self.error_occurred.emit("两个串口都未连接，无法发送序列命令。")
            return False

        # 预先准备串口写入
        serial_port1 = self._serial_port1 if port1_available else None
        serial_port2 = self._serial_port2 if port2_available else None

        # 记录开始时间
        start_time = time.perf_counter()

        try:
            # 方法1: 直接在主线程中快速连续发送（延时最小）
            success1 = True
            success2 = True

            if serial_port1 and serial_port1.is_open:
                try:
                    bytes_written1 = serial_port1.write(data)
                    success1 = (bytes_written1 == len(data))
                except Exception as e:
                    self.error_occurred.emit(f"串口1发送异常: {e}")
                    success1 = False

            # 立即发送到串口2（延时最小化）
            if serial_port2 and serial_port2.is_open:
                try:
                    bytes_written2 = serial_port2.write(data)
                    success2 = (bytes_written2 == len(data))
                except Exception as e:
                    self.error_occurred.emit(f"串口2发送异常: {e}")
                    success2 = False

            # 计算用时
            end_time = time.perf_counter()
            total_time_us = (end_time - start_time) * 1000000  # 微秒

            print(f"超高精度序列命令发送完成，用时: {total_time_us:.1f}μs")

            # 返回结果
            overall_success = success1 or success2
            if overall_success:
                success_ports = []
                if success1 and port1_available:
                    success_ports.append("串口1")
                if success2 and port2_available:
                    success_ports.append("串口2")
                print(f"✅ 超高精度序列命令发送成功: {', '.join(success_ports)}")
            else:
                print("❌ 超高精度序列命令发送失败")

            return overall_success

        except Exception as e:
            self.error_occurred.emit(f"超高精度发送异常: {e}")
            return False

    def send_to_port1(self, data: bytes):
        """向串口1发送数据"""
        if not self.is_port1_connected():
            self.error_occurred.emit("串口1未连接，无法发送数据。")
            return False
        return self._send_to_port(1, data)

    def send_to_port2(self, data: bytes):
        """向串口2发送数据"""
        if not self.is_port2_connected():
            self.error_occurred.emit("串口2未连接，无法发送数据。")
            return False
        return self._send_to_port(2, data)

    def send_data(self, data: bytes):
        """兼容性方法：智能路由数据到合适的串口"""

        # 根据命令类型智能选择串口
        if len(data) > 0:
            command = data[0]
            if (command in (0x01, 0x02) or 0x03 <= command <= 0x07) and len(data) > 1:
                return self.send_to_port2(data)
            return self.send_to_port1(data)
        return False

    def _send_to_port(self, port_num, data: bytes):
        try:
            serial_port = self._serial_port1 if port_num == 1 else self._serial_port2

        # 检查串口状态
            if not serial_port or not serial_port.is_open:
                self.error_occurred.emit(f"串口{port_num}已断开")
                return False

        # 只在输出缓冲区有大量积压时才清理
            if serial_port.out_waiting > 100:
                serial_port.reset_output_buffer()

        # 发送数据
            bytes_written = serial_port.write(data)

        # 验证发送的字节数
            if bytes_written != len(data):
                self.error_occurred.emit(
                    f"串口{port_num}数据发送不完整：期望{len(data)}字节，实际发送{bytes_written}字节")
                return False

            return True

        except serial.SerialTimeoutException:
        # 改为发射错误信号但不弹窗，让主界面显示状态栏消息
            self.error_occurred.emit(f"串口{port_num}发送数据超时")
            return False
        except serial.SerialException as e:
            error_msg = str(e)
            self.error_occurred.emit(f"串口{port_num}错误：{e}")
        # 只在严重串口错误时断开连接
            if "device" in error_msg.lower() or "disconnected" in error_msg.lower():
                if port_num == 1:
                    self.disconnect_port1()
                else:
                    self.disconnect_port2()
            return False
        except Exception as e:
            self.error_occurred.emit(f"串口{port_num}发送数据时发生未知错误：{e}")
            return False


class SensorControlDialog(QDialog):
    def __init__(self, serial_manager: SerialManager, parent=None):
        super().__init__(parent)
        self.serial_manager = serial_manager  # 保存引用，槽函数里要用
        self.setWindowTitle("传感器设置")
        self.setGeometry(200, 200, 600, 700)

        self.init_ui()  # 调用初始化界面
        import time
        self.start_time = time.time()
        self.temp1_history = []
        self.temp2_history = []
        self.temp3_history = []
        self.thr_history = []
        self.pressure_history = []

        self.temp1_all_data = []
        self.temp2_all_data = []
        self.temp3_all_data = []
        self.thr_all_data = []
        self.pressure_all_data = []

        self.pressure_info = {}
        for addr in range(3, 8):
            self.pressure_info[addr] = {
                'history': [],
                'all_data': [],
                'zero': 0.0,
                'org': 0.0,
                'is_tare': False,
                'display': None,
                'curve': None,
                'indicator': None,
                'tab_widget': None,
                'plot_widget': None,
                'timer': None,
            }

        self.pressure_org = 0.0
        self.pressure_zero = 0.0
        self.thr_org = 0.0
        self.time_counter = 0
        self.temp1_zero = 0.0
        self.temp2_zero = 0.0
        self.temp3_zero = 0.0
        self.thr_zero = 0.0
        self.is_tare = False
        self.is_calibrated = False
        self.is_pressure_tare = False
        self._current_pressure_addr = 3
        self._serial_buffer = bytearray()
        # 连接信号
        self.serial_manager.port2_data_received.connect(self.on_data)

    def on_data(self, data: bytes):
        if len(data) == 0 or not self.is_collecting:
            return

        self._serial_buffer.extend(data)

        while len(self._serial_buffer) >= 5:
            addr = self._serial_buffer[0]
            func = self._serial_buffer[1]

            if addr not in (0x01, 0x02) and not (0x03 <= addr <= 0x07):
                self._serial_buffer.pop(0)
                continue
            if func not in (0x03, 0x04):
                self._serial_buffer.pop(0)
                continue

            byte_count = self._serial_buffer[2]
            expected_len = 3 + byte_count + 2
            if len(self._serial_buffer) < expected_len:
                break

            frame = bytes(self._serial_buffer[:expected_len])
            if frame[-2:] == calculate_crc16(frame[:-2]):
                self._dispatch_frame(frame)
                del self._serial_buffer[:expected_len]
            else:
                self._serial_buffer.pop(0)

        if len(self._serial_buffer) > 512:
            self._serial_buffer.clear()

    def _dispatch_frame(self, frame: bytes):
        current_time = time.time() - self.start_time
        addr = frame[0]

        if addr == 0x01:
            thrust = int.from_bytes(frame[3:5], 'big', signed=True) / 1000.0 * 9.8 - self.thr_zero

            self.current_sample = {
                'time': current_time,
                'thrust': thrust,
                'pressure': self.last_pressure if hasattr(self, 'last_pressure') else None,
                'temp1': self.last_temp1 if hasattr(self, 'last_temp1') else None,
                'temp2': self.last_temp2 if hasattr(self, 'last_temp2') else None
            }
            self.samples.append(self.current_sample.copy())

            self.thr_history.append((current_time, thrust))
            self.thrust_display.setText(f"{thrust:.2f} N")

            if len(self.thr_history) > 100:
                self.thr_history.pop(0)
            x, y = zip(*self.thr_history)
            self.curve.setData(x, y)
            self.thr_all_data.append((current_time, thrust))

        elif addr == 0x02:
            if frame[2] < 6:
                return
            temp1 = int.from_bytes(frame[3:5], 'big', signed=True) / 10.0
            temp2 = int.from_bytes(frame[5:7], 'big', signed=True) / 10.0
            temp3 = int.from_bytes(frame[7:9], 'big', signed=True) / 10.0 if len(frame) >= 10 else 0.0

            self.last_temp1 = temp1
            self.last_temp2 = temp2

            self.time_counter += 1
            self.temp1_history.append((current_time, temp1))
            self.temp2_history.append((current_time, temp2))
            self.temp3_history.append((current_time, temp3))
            self.temp1_display.setText(f"{temp1:.1f} °C")
            self.temp2_display.setText(f"{temp2:.1f} °C")
            self.temp3_display.setText(f"{temp3:.1f} °C")

            if len(self.temp1_history) > 100:
                self.temp1_history.pop(0)
                self.temp2_history.pop(0)
                self.temp3_history.pop(0)

            x1, y1 = zip(*self.temp1_history)
            x2, y2 = zip(*self.temp2_history)
            x3, y3 = zip(*self.temp3_history)

            self.temp1_curve.setData(x1, y1)
            self.temp2_curve.setData(x2, y2)
            self.temp3_curve.setData(x3, y3)

            self.temp1_all_data.append((current_time, temp1))
            self.temp2_all_data.append((current_time, temp2))
            self.temp3_all_data.append((current_time, temp3))

        elif 0x03 <= addr <= 0x07:
            if frame[2] < 2:
                return
            info = self.pressure_info[addr]
            pressure = int.from_bytes(frame[3:5], 'big', signed=True) / 100.0 - info['zero']
            info['org'] = int.from_bytes(frame[3:5], 'big', signed=True) / 100.0

            if addr == 0x03:
                self.last_pressure = pressure

            self.time_counter += 1
            info['history'].append((current_time, pressure))
            if info['display'] is not None:
                info['display'].setText(f"{pressure:.2f} MPa")

            if len(info['history']) > 100:
                info['history'].pop(0)
            if info['curve'] is not None and len(info['history']) >= 2:
                x, y = zip(*info['history'])
                info['curve'].setData(x, y)
            info['all_data'].append((current_time, pressure))

    def init_ui(self):
        # 主布局：上下分割
        main_layout = QVBoxLayout()

        # ========== 上半部分：推力传感器控制 ==========
        top_group = QGroupBox("推力传感器控制")
        top_layout = QVBoxLayout()

        # 第一行：标题 + 三个按钮
        row1_layout = QHBoxLayout()

        title_label = QLabel("推力传感器")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold;")

        # 添加状态指示灯
        self.thrust_indicator = QLabel()
        self.thrust_indicator.setFixedSize(20, 20)
        self.thrust_indicator.setStyleSheet("""
            QLabel {
                background-color: #7f8c8d;
                border-radius: 10px;
                border: 1px solid #555;
            }
        """)

        self.btn_open = QPushButton("开")
        self.btn_close = QPushButton("关")
        self.btn_tare = QPushButton("去皮")
        self.save_btn = QPushButton("下载数据")
        self.clear_btn = QPushButton("清空数据")

        # 连接槽函数
        self.btn_open.clicked.connect(self.on_thrust_open)
        self.btn_close.clicked.connect(self.on_thrust_close)
        self.btn_tare.clicked.connect(self.on_thrust_tare)
        self.save_btn.clicked.connect(self.save_all_thr_data)
        self.clear_btn.clicked.connect(self.clear_all_thr_data)

        row1_layout.addWidget(title_label)
        row1_layout.addWidget(self.thrust_indicator)
        row1_layout.addStretch()  # 弹簧，把按钮推到右边
        row1_layout.addWidget(self.btn_open)
        row1_layout.addWidget(self.btn_close)
        row1_layout.addWidget(self.btn_tare)
        row1_layout.addWidget(self.save_btn)
        row1_layout.addWidget(self.clear_btn)

        top_layout.addLayout(row1_layout)

        # 第二行：实时读数
        row2_layout = QHBoxLayout()

        readout_label = QLabel("实时读数:")
        readout_label.setStyleSheet("font-size: 14px;")

        self.thrust_display = QLabel("0.00 N")
        self.thrust_display.setStyleSheet("""
               font-size: 24px; 
               font-weight: bold; 
               color: #2ECC71;
               background-color: #2C3E50;
               padding: 10px;
               border-radius: 5px;
           """)
        self.thrust_display.setMinimumWidth(150)
        self.thrust_display.setAlignment(Qt.AlignmentFlag.AlignCenter)

        row2_layout.addWidget(readout_label)
        row2_layout.addWidget(self.thrust_display)
        row2_layout.addStretch()

        top_layout.addLayout(row2_layout)

        # 第三行：曲线图
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground('#34495E')
        self.plot_widget.setMaximumHeight(350)
        self.plot_widget.setLabel('left', '推力', units='N')
        self.plot_widget.setLabel('bottom', '时间', units='s')
        self.plot_widget.showGrid(x=True, y=True)

        # 创建曲线
        self.curve = self.plot_widget.plot(pen=pg.mkPen(color='#2ECC71', width=2))

        top_layout.addWidget(self.plot_widget)

        top_group.setLayout(top_layout)
        main_layout.addWidget(top_group, stretch=2)  # 上面占2份

        # ========== 中间部分：压力传感器控制 (地址3-7) ==========
        pressure_group = QGroupBox("压力传感器控制")
        pressure_layout = QVBoxLayout()

        pressure_title_label = QLabel("压力传感器 (地址 #3 ~ #7)")
        pressure_title_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        pressure_layout.addWidget(pressure_title_label)

        pressure_colors = {3: '#9B59B6', 4: '#E74C3C', 5: '#3498DB', 6: '#2ECC71', 7: '#F39C12'}

        self.pressure_tabs = QTabWidget()
        self.pressure_tabs.currentChanged.connect(self._on_pressure_tab_changed)
        for addr in range(3, 8):
            tab = QWidget()
            tab_layout = QVBoxLayout(tab)
            tab_layout.setContentsMargins(10, 10, 10, 10)

            display = QLabel("0.00 MPa")
            color = pressure_colors[addr]
            display.setStyleSheet(f"""
                font-size: 24px;
                font-weight: bold;
                color: {color};
                background-color: #2C3E50;
                padding: 10px;
                border-radius: 5px;
            """)
            display.setMinimumWidth(150)
            display.setAlignment(Qt.AlignmentFlag.AlignCenter)
            tab_layout.addWidget(display)

            plot_widget = pg.PlotWidget()
            plot_widget.setBackground('#34495E')
            plot_widget.setMaximumHeight(300)
            plot_widget.setLabel('left', '压力', units='MPa')
            plot_widget.setLabel('bottom', '时间', units='s')
            plot_widget.showGrid(x=True, y=True)
            curve = plot_widget.plot(pen=pg.mkPen(color=color, width=2))
            tab_layout.addWidget(plot_widget)

            self.pressure_info[addr]['display'] = display
            self.pressure_info[addr]['curve'] = curve
            self.pressure_info[addr]['plot_widget'] = plot_widget
            self.pressure_info[addr]['tab_widget'] = tab

            self.pressure_tabs.addTab(tab, f"压力 #{addr}")

        pressure_layout.addWidget(self.pressure_tabs)

        indicator_label = QLabel("传感器状态:")
        indicator_label.setStyleSheet("font-size: 12px; font-weight: bold;")

        control_row = QHBoxLayout()
        self.pressure_indicator = QLabel()
        self.pressure_indicator.setFixedSize(20, 20)
        self.pressure_indicator.setStyleSheet("""
            QLabel {
                background-color: #7f8c8d;
                border-radius: 10px;
                border: 1px solid #555;
            }
        """)

        self.btn_pressure_open = QPushButton("开")
        self.btn_pressure_close = QPushButton("关")
        self.btn_pressure_tare = QPushButton("去皮")
        self.save_btn_pressure = QPushButton("下载数据")
        self.clear_btn_pressure = QPushButton("清空数据")

        self.btn_pressure_open.clicked.connect(self.on_pressure_open)
        self.btn_pressure_close.clicked.connect(self.on_pressure_close)
        self.btn_pressure_tare.clicked.connect(self.on_pressure_tare)
        self.save_btn_pressure.clicked.connect(self.save_all_pressure_data)
        self.clear_btn_pressure.clicked.connect(self.clear_all_pressure_data)

        control_row.addWidget(indicator_label)
        control_row.addWidget(self.pressure_indicator)
        control_row.addStretch()
        control_row.addWidget(self.btn_pressure_open)
        control_row.addWidget(self.btn_pressure_close)
        control_row.addWidget(self.btn_pressure_tare)
        control_row.addWidget(self.save_btn_pressure)
        control_row.addWidget(self.clear_btn_pressure)
        pressure_layout.addLayout(control_row)

        pressure_group.setLayout(pressure_layout)
        main_layout.addWidget(pressure_group, stretch=2)

        # ========== 下半部分：温度传感器控制 ==========
        bottom_group = QGroupBox("温度传感器控制")
        bottom_layout = QVBoxLayout()

        # 第一行：标题 + 三个按钮
        temp_row1_layout = QHBoxLayout()

        temp_title_label = QLabel("温度传感器")
        temp_title_label.setStyleSheet("font-size: 16px; font-weight: bold;")

        self.temp_indicator = QLabel()
        self.temp_indicator.setFixedSize(20, 20)
        self.temp_indicator.setStyleSheet("""
                QLabel {
                    background-color: #7f8c8d;
                    border-radius: 10px;
                    border: 1px solid #555;
                }
            """)

        self.btn_temp_open = QPushButton("开")
        self.btn_temp_close = QPushButton("关")
        self.btn_temp_calibrate = QPushButton("校准")
        self.save_btn_temp = QPushButton("下载数据")
        self.clear_btn_temp = QPushButton("清空数据")

        # 连接槽函数
        self.btn_temp_open.clicked.connect(self.on_temp_open)
        self.btn_temp_close.clicked.connect(self.on_temp_close)
        self.btn_temp_calibrate.clicked.connect(self.on_temp_calibrate)
        self.save_btn_temp.clicked.connect(self.save_all_temp_data)
        self.clear_btn_temp.clicked.connect(self.clear_all_temp_data)

        temp_row1_layout.addWidget(temp_title_label)
        temp_row1_layout.addStretch()
        temp_row1_layout.addWidget(self.temp_indicator)
        temp_row1_layout.addWidget(self.btn_temp_open)
        temp_row1_layout.addWidget(self.btn_temp_close)
        temp_row1_layout.addWidget(self.btn_temp_calibrate)
        temp_row1_layout.addWidget(self.save_btn_temp)
        temp_row1_layout.addWidget(self.clear_btn_temp)

        bottom_layout.addLayout(temp_row1_layout)

        # 第二行：三个实时温度显示
        temp_row2_layout = QHBoxLayout()

        self.temp1_display = QLabel("25.0 °C")
        self.temp1_display.setStyleSheet("""
               font-size: 18px;
               font-weight: bold;
               color: #E74C3C;
               background-color: #2C3E50;
               padding: 6px;
               border-radius: 5px;
           """)
        self.temp1_display.setMinimumWidth(120)
        self.temp1_display.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.temp2_display = QLabel("25.0 °C")
        self.temp2_display.setStyleSheet("""
               font-size: 18px;
               font-weight: bold;
               color: #3498DB;
               background-color: #2C3E50;
               padding: 6px;
               border-radius: 5px;
           """)
        self.temp2_display.setMinimumWidth(120)
        self.temp2_display.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.temp3_display = QLabel("25.0 °C")
        self.temp3_display.setStyleSheet("""
               font-size: 18px;
               font-weight: bold;
               color: #F39C12;
               background-color: #2C3E50;
               padding: 6px;
               border-radius: 5px;
           """)
        self.temp3_display.setMinimumWidth(120)
        self.temp3_display.setAlignment(Qt.AlignmentFlag.AlignCenter)

        temp_row2_layout.addWidget(QLabel("温度 1:"))
        temp_row2_layout.addWidget(self.temp1_display)
        temp_row2_layout.addSpacing(10)
        temp_row2_layout.addWidget(QLabel("温度 2:"))
        temp_row2_layout.addWidget(self.temp2_display)
        temp_row2_layout.addSpacing(10)
        temp_row2_layout.addWidget(QLabel("温度 3:"))
        temp_row2_layout.addWidget(self.temp3_display)
        temp_row2_layout.addStretch()

        bottom_layout.addLayout(temp_row2_layout)

        # 第三行：温度曲线图 (三条曲线)
        self.temp_plot_widget = pg.PlotWidget()
        self.temp_plot_widget.setBackground('#34495E')
        self.temp_plot_widget.setMaximumHeight(350)
        self.temp_plot_widget.setLabel('left', '温度', units='°C')
        self.temp_plot_widget.setLabel('bottom', '时间', units='s')
        self.temp_plot_widget.showGrid(x=True, y=True)
        self.temp_plot_widget.addLegend()

        self.temp1_curve = self.temp_plot_widget.plot(
            pen=pg.mkPen(color='#E74C3C', width=2),
            name='温度1'
        )
        self.temp2_curve = self.temp_plot_widget.plot(
            pen=pg.mkPen(color='#3498DB', width=2),
            name='温度2'
        )
        self.temp3_curve = self.temp_plot_widget.plot(
            pen=pg.mkPen(color='#F39C12', width=2),
            name='温度3'
        )

        bottom_layout.addWidget(self.temp_plot_widget)

        bottom_group.setLayout(bottom_layout)
        main_layout.addWidget(bottom_group, stretch=2)  # 下面也占2份

        self.setLayout(main_layout)

    def on_thrust_open(self):
        command = 0x010300000002C40B
        command_bytes = command.to_bytes(8, byteorder='big')
        if not hasattr(self, 'thrust_timer'):
            self.thrust_timer = QTimer(self)
            self.thrust_timer.timeout.connect(lambda: self.serial_manager.send_data(command_bytes))
            # 每100ms发送一次（可改）
        self.thrust_timer.start(100)
        # 点亮绿灯
        self.thrust_indicator.setStyleSheet("""
                QLabel {
                    background-color: #2ecc71;
                    border-radius: 10px;
                    border: 1px solid #27ae60;
                    box-shadow: 0 0 10px #2ecc71;
                }
            """)

        print("推力传感器开")

    def on_thrust_close(self):
        if hasattr(self, 'thrust_timer'):
            self.thrust_timer.stop()

            # 熄灭指示灯（灰色）
        self.thrust_indicator.setStyleSheet("""
               QLabel {
                   background-color: #7f8c8d;
                   border-radius: 10px;
                   border: 1px solid #555;
               }
           """)

        print("推力传感器关")

    def on_thrust_tare(self):
        if self.thr_all_data:
            # 取最后一个值
            self.thr_zero = self.thr_org
            self.is_tare = True
            print(f"去皮完成: 推力零点={self.thr_zero:.2f}")
        else:
            print("没有数据，无法去皮")

    def on_temp_open(self):
        """开按钮 - 启动定时发送 (3路温度)"""
        data = bytes([0x02, 0x04, 0x00, 0x00, 0x00, 0x03])
        crc = calculate_crc16(data)
        command_bytes = data + crc

        if not hasattr(self, 'temp_timer'):
            self.temp_timer = QTimer(self)
            self.temp_timer.timeout.connect(lambda: self.serial_manager.send_data(command_bytes))

        self.temp_timer.start(100)

        self.temp_indicator.setStyleSheet("""
            QLabel {
                background-color: #2ecc71;
                border-radius: 10px;
                border: 1px solid #27ae60;
                box-shadow: 0 0 10px #2ecc71;
            }
        """)
        print("温度传感器开")

    def on_temp_close(self):
        if hasattr(self, 'temp_timer'):
            self.temp_timer.stop()

        self.temp_indicator.setStyleSheet("""
                 QLabel {
                     background-color: #7f8c8d;
                     border-radius: 10px;
                     border: 1px solid #555;
                 }
             """)
        print("温度传感器关")

    def on_temp_calibrate(self):
        if self.temp1_all_data:
            self.temp1_zero = self.temp1_all_data[-1][1]
            self.temp2_zero = self.temp2_all_data[-1][1]
            self.temp3_zero = self.temp3_all_data[-1][1] if self.temp3_all_data else 0.0
            self.is_calibrated = True
            print(f"校准完成: 温度1零点={self.temp1_zero:.2f}, 温度2零点={self.temp2_zero:.2f}, 温度3零点={self.temp3_zero:.2f}")
        else:
            print("没有数据，无法校准")

    def save_all_temp_data(self):
        if not self.temp1_all_data:
            print("没有数据可保存")
            return

        folder = "传感器数据"
        os.makedirs(folder, exist_ok=True)

        filename = f"温度数据_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        filepath = os.path.join(folder, filename)

        wb = Workbook()
        ws = wb.active
        ws.title = "温度数据"
        ws.append(['时间(s)', '温度1(°C)', '温度2(°C)', '温度3(°C)'])

        count = min(len(self.temp1_all_data), len(self.temp2_all_data), len(self.temp3_all_data))
        for i in range(count):
            t1, y1 = self.temp1_all_data[i]
            _, y2 = self.temp2_all_data[i]
            _, y3 = self.temp3_all_data[i]
            ws.append([round(t1, 3), round(y1, 2), round(y2, 2), round(y3, 2)])

        wb.save(filepath)
        print(f"已保存 {count} 条数据到: {filename}")

    def clear_all_temp_data(self):
        self.temp1_all_data.clear()
        self.temp2_all_data.clear()
        self.temp3_all_data.clear()
        self.temp1_history.clear()
        self.temp2_history.clear()
        self.temp3_history.clear()
        self.time_counter = 0
        print("数据已清空")

    def save_all_thr_data(self):
        """下载所有历史数据为 Excel 文件"""
        if not self.thr_all_data:
            print("没有数据可保存")
            return

        # 创建文件夹（如果不存在）
        folder = "传感器数据"
        os.makedirs(folder, exist_ok=True)

        # 完整路径
        filename = f"推力数据_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        filepath = os.path.join(folder, filename)

        # 创建工作簿
        wb = Workbook()
        ws = wb.active
        ws.title = "推力数据"

        # 写入表头
        headers = ['时间(s)', '推力(N)']
        ws.append(headers)

        # 写入数据
        for (t, y) in self.thr_all_data:
            ws.append([round(t, 3), round(y, 2)])


        # 保存文件
        wb.save(filepath)
        print(f"已保存 {len(self.thr_all_data)} 条数据到: {filename}")




    def clear_all_thr_data(self):
        """清空所有历史数据"""
        self.thr_all_data.clear()
        self.thr_history.clear()
        self.time_counter = 0
        print("数据已清空")

    # ========== 压力传感器控制方法 ==========
    def _pressure_cmd_bytes(self, addr):
        data = bytes([addr, 0x03, 0x00, 0x04, 0x00, 0x01])
        crc = calculate_crc16(data)
        return int.from_bytes(data + crc, 'big').to_bytes(8, 'big')

    def _on_pressure_tab_changed(self, index):
        self._current_pressure_addr = index + 3

    def on_pressure_open(self):
        addr = self._current_pressure_addr
        info = self.pressure_info[addr]
        command_bytes = self._pressure_cmd_bytes(addr)

        if info['timer'] is None:
            info['timer'] = QTimer(self)
            info['timer'].timeout.connect(lambda b=command_bytes: self.serial_manager.send_data(b))

        info['timer'].start(100)

        self.pressure_indicator.setStyleSheet("""
            QLabel {
                background-color: #2ecc71;
                border-radius: 10px;
                border: 1px solid #27ae60;
                box-shadow: 0 0 10px #2ecc71;
            }
        """)
        print(f"压力传感器 #{addr} 开")

    def on_pressure_close(self):
        addr = self._current_pressure_addr
        info = self.pressure_info[addr]
        if info['timer'] is not None:
            info['timer'].stop()

        self.pressure_indicator.setStyleSheet("""
            QLabel {
                background-color: #7f8c8d;
                border-radius: 10px;
                border: 2px solid #555;
            }
        """)
        print(f"压力传感器 #{addr} 关")

    def on_pressure_tare(self):
        addr = self._current_pressure_addr
        info = self.pressure_info[addr]
        if info['all_data']:
            info['zero'] = info['org']
            info['is_tare'] = True
            print(f"压力 #{addr} 去皮完成: 零点={info['zero']:.2f}")
        else:
            print(f"压力 #{addr} 没有数据，无法去皮")

    def save_all_pressure_data(self):
        addr = self._current_pressure_addr
        info = self.pressure_info[addr]
        if not info['all_data']:
            print(f"压力 #{addr} 没有数据可保存")
            return

        folder = "传感器数据"
        os.makedirs(folder, exist_ok=True)

        filename = f"压力数据_addr{addr}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        filepath = os.path.join(folder, filename)

        wb = Workbook()
        ws = wb.active
        ws.title = f"压力数据_addr{addr}"

        headers = ['时间(s)', '压力(MPa)']
        ws.append(headers)

        for (t, y) in info['all_data']:
            ws.append([round(t, 3), round(y, 2)])

        wb.save(filepath)
        print(f"已保存 {len(info['all_data'])} 条数据到: {filename}")

    def clear_all_pressure_data(self):
        addr = self._current_pressure_addr
        info = self.pressure_info[addr]
        info['all_data'].clear()
        info['history'].clear()
        if info['curve'] is not None:
            info['curve'].setData([], [])
        self.time_counter = 0
        print(f"压力 #{addr} 数据已清空")


# --- 串口配置对话框 ---
class SerialConfigDialog(QDialog):
    def __init__(self, serial_manager: SerialManager, parent=None):
        super().__init__(parent)
        self.setWindowTitle("双串口设置")
        self.setGeometry(200, 200, 600, 700)
 
        self.serial_manager = serial_manager  # 接收共享的SerialManager实例

        self.init_ui()
        self._connect_signals()  # 连接SerialManager的信号
        self.populate_ports()  # 填充可用串口 (在update_ui_state之前调用)
        self.update_ui_state()  # 初始状态根据SerialManager判断


    def init_ui(self):
        main_layout = QVBoxLayout()

        # 说明标签
        info_label = QLabel("双串口配置：串口1用于点火/灭火，串口2用于其他控制")
        info_label.setStyleSheet("font-weight: bold; color: #2980B9; padding: 10px;")
        main_layout.addWidget(info_label)

        # 使用标签页来分别配置两个串口

        tab_widget = QTabWidget()

        # 串口1配置页
        port1_widget = QWidget()
        port1_layout = QFormLayout()

        # 串口1选择
        self.port1_combo = QComboBox()
        self.refresh1_button = QPushButton("刷新")
        self.refresh1_button.clicked.connect(self.populate_ports)
        port1_h_layout = QHBoxLayout()
        port1_h_layout.addWidget(self.port1_combo)
        port1_h_layout.addWidget(self.refresh1_button)
        port1_layout.addRow("串口号:", port1_h_layout)

        # 串口1波特率
        self.baud1_combo = QComboBox()
        self.baud1_combo.addItems(["9600", "19200", "38400", "57600", "115200", "230400", "460800", "921600"])
        self.baud1_combo.setCurrentText("115200")
        port1_layout.addRow("波特率:", self.baud1_combo)

        # 串口1数据位
        self.data_bits1_combo = QComboBox()
        self.data_bits1_combo.addItems(["5", "6", "7", "8"])
        self.data_bits1_combo.setCurrentText("8")
        port1_layout.addRow("数据位:", self.data_bits1_combo)

        # 串口1校验位
        self.parity1_combo = QComboBox()
        self.parity1_combo.addItems(["无", "奇校验", "偶校验", "Mark", "Space"])
        self.parity1_combo.setCurrentIndex(0)
        port1_layout.addRow("校验位:", self.parity1_combo)

        # 串口1停止位
        self.stop_bits1_combo = QComboBox()
        self.stop_bits1_combo.addItems(["1", "1.5", "2"])
        self.stop_bits1_combo.setCurrentIndex(0)
        port1_layout.addRow("停止位:", self.stop_bits1_combo)

        # 串口1流控制
        self.flow_control1_combo = QComboBox()
        self.flow_control1_combo.addItems(["无", "硬件 (RTS/CTS)", "软件 (XON/XOFF)"])
        self.flow_control1_combo.setCurrentIndex(0)
        port1_layout.addRow("流控制:", self.flow_control1_combo)

        # 串口1连接按钮
        self.connect1_button = QPushButton("连接串口1")
        self.connect1_button.clicked.connect(self._handle_connect_port1)
        self.disconnect1_button = QPushButton("断开串口1")
        self.disconnect1_button.clicked.connect(self.serial_manager.disconnect_port1)
        button1_h_layout = QHBoxLayout()
        button1_h_layout.addWidget(self.connect1_button)
        button1_h_layout.addWidget(self.disconnect1_button)
        port1_layout.addRow(button1_h_layout)

        # 串口1状态显示
        self.status1_label = QLabel("状态: ❌ 未连接")
        self.status1_label.setStyleSheet(
            "color: #e74c3c; font-weight: bold; padding: 5px; background-color: #fdf2f2; border-radius: 3px; border: 1px solid #e74c3c;")
        port1_layout.addRow("连接状态:", self.status1_label)

        port1_widget.setLayout(port1_layout)
        tab_widget.addTab(port1_widget, "串口1 (控制阀门)")

        # 串口2配置页
        port2_widget = QWidget()
        port2_layout = QFormLayout()

        # 串口2选择
        self.port2_combo = QComboBox()
        self.refresh2_button = QPushButton("刷新")
        self.refresh2_button.clicked.connect(self.populate_ports)
        port2_h_layout = QHBoxLayout()
        port2_h_layout.addWidget(self.port2_combo)
        port2_h_layout.addWidget(self.refresh2_button)
        port2_layout.addRow("串口号:", port2_h_layout)

        # 串口2波特率
        self.baud2_combo = QComboBox()
        self.baud2_combo.addItems(["9600", "19200", "38400", "57600", "115200", "230400", "460800", "921600"])
        self.baud2_combo.setCurrentText("115200")
        port2_layout.addRow("波特率:", self.baud2_combo)

        # 串口2数据位
        self.data_bits2_combo = QComboBox()
        self.data_bits2_combo.addItems(["5", "6", "7", "8"])
        self.data_bits2_combo.setCurrentText("8")
        port2_layout.addRow("数据位:", self.data_bits2_combo)

        # 串口2校验位
        self.parity2_combo = QComboBox()
        self.parity2_combo.addItems(["无", "奇校验", "偶校验", "Mark", "Space"])
        self.parity2_combo.setCurrentIndex(0)
        port2_layout.addRow("校验位:", self.parity2_combo)

        # 串口2停止位
        self.stop_bits2_combo = QComboBox()
        self.stop_bits2_combo.addItems(["1", "1.5", "2"])
        self.stop_bits2_combo.setCurrentIndex(0)
        port2_layout.addRow("停止位:", self.stop_bits2_combo)

        # 串口2流控制
        self.flow_control2_combo = QComboBox()
        self.flow_control2_combo.addItems(["无", "硬件 (RTS/CTS)", "软件 (XON/XOFF)"])
        self.flow_control2_combo.setCurrentIndex(0)
        port2_layout.addRow("流控制:", self.flow_control2_combo)

        # 串口2连接按钮
        self.connect2_button = QPushButton("连接串口2")
        self.connect2_button.clicked.connect(self._handle_connect_port2)
        self.disconnect2_button = QPushButton("断开串口2")
        self.disconnect2_button.clicked.connect(self.serial_manager.disconnect_port2)
        button2_h_layout = QHBoxLayout()
        button2_h_layout.addWidget(self.connect2_button)
        button2_h_layout.addWidget(self.disconnect2_button)
        port2_layout.addRow(button2_h_layout)

        # 检测串口2状态
        is_connected2 = self.serial_manager.is_port2_connected()

        if is_connected2:
            status_text = "状态: ✅ 已连接"
            status_style = ("color: #27ae60; font-weight: bold; padding: 5px; "
                            "background-color: #eafaf1; border-radius: 3px; border: 1px solid #27ae60;")
        else:
            status_text = "状态: ❌ 未连接"
            status_style = ("color: #e74c3c; font-weight: bold; padding: 5px; "
                            "background-color: #fdf2f2; border-radius: 3px; border: 1px solid #e74c3c;")

        self.status2_label = QLabel(status_text)
        self.status2_label.setStyleSheet(status_style)
        port2_layout.addRow("连接状态:", self.status2_label)

        port2_widget.setLayout(port2_layout)
        tab_widget.addTab(port2_widget, "串口2 (控制传感器)")

        main_layout.addWidget(tab_widget)
        # main_layout.addStretch(1) # 增加弹性空间，但form_layout下可能不太需要

        # 数据发送测试区域
        test_group = QGroupBox("数据发送测试")
        test_layout = QVBoxLayout()

        send_layout = QHBoxLayout()
        self.send_line_edit = QLineEdit()
        self.send_line_edit.setPlaceholderText("输入HEX数据，例如: FE01")

        self.send_port_combo = QComboBox()
        self.send_port_combo.addItems(["串口1", "串口2", "双串口"])
        self.send_port_combo.setCurrentText("串口1")

        self.send_button = QPushButton("发送数据")
        self.send_button.clicked.connect(self._handle_send_data)

        send_layout.addWidget(QLabel("数据:"))
        send_layout.addWidget(self.send_line_edit)
        send_layout.addWidget(QLabel("发送到:"))
        send_layout.addWidget(self.send_port_combo)
        send_layout.addWidget(self.send_button)
        test_layout.addLayout(send_layout)

        # 数据接收区域
        self.receive_text_edit = QTextEdit()
        self.receive_text_edit.setReadOnly(True)
        self.receive_text_edit.setMaximumHeight(150)
        self.clear_receive_button = QPushButton("清空接收区")
        self.clear_receive_button.clicked.connect(self.receive_text_edit.clear)

        test_layout.addWidget(QLabel("接收数据:"))
        test_layout.addWidget(self.receive_text_edit)
        test_layout.addWidget(self.clear_receive_button)

        test_group.setLayout(test_layout)
        main_layout.addWidget(test_group)

        self.setLayout(main_layout)

    def _connect_signals(self):
        # 连接SerialManager的信号到本对话框的槽函数
        self.serial_manager.connected.connect(self._on_serial_connected)
        self.serial_manager.disconnected.connect(self._on_serial_disconnected)
        self.serial_manager.data_received.connect(self.append_received_data)
        self.serial_manager.error_occurred.connect(self._on_serial_error)

        # 连接双串口专用信号（分别处理）
        if hasattr(self.serial_manager, 'port1_connected'):
            self.serial_manager.port1_connected.connect(self._on_port1_connected)
            self.serial_manager.port2_connected.connect(self._on_port2_connected)
        if hasattr(self.serial_manager, 'port1_disconnected'):
            self.serial_manager.port1_disconnected.connect(self._on_port1_disconnected)
            self.serial_manager.port2_disconnected.connect(self._on_port2_disconnected)
        if hasattr(self.serial_manager, 'port1_data_received'):
            self.serial_manager.port1_data_received.connect(self.append_received_data)
        if hasattr(self.serial_manager, 'port2_data_received'):
            self.serial_manager.port2_data_received.connect(self.append_received_data)

    def populate_ports(self):
        """填充可用串口列表"""
        self.port1_combo.clear()
        self.port2_combo.clear()
        ports = serial.tools.list_ports.comports()

        if not ports:
            self.port1_combo.addItem("无可用串口")
            self.port2_combo.addItem("无可用串口")
        else:
            for port_info in sorted(ports):
                port_item = f"{port_info.device} - {port_info.description}"
                self.port1_combo.addItem(port_item)
                self.port2_combo.addItem(port_item)

        # 更新UI状态
        self.update_ui_state()

    def _handle_connect_port1(self):
        """处理串口1连接按钮点击事件"""
        selected_port_text = self.port1_combo.currentText()
        if not selected_port_text or "无可用串口" in selected_port_text:
            QMessageBox.warning(self, "连接失败", "未选择有效的串口或无可用串口。")
            return

        port_name = selected_port_text.split(' ')[0]
        baud_rate = int(self.baud1_combo.currentText())
        data_bits = int(self.data_bits1_combo.currentText())

        parity_map = {"无": serial.PARITY_NONE, "奇校验": serial.PARITY_ODD,
                      "偶校验": serial.PARITY_EVEN, "Mark": serial.PARITY_MARK,
                      "Space": serial.PARITY_SPACE}
        parity = parity_map[self.parity1_combo.currentText()]

        stop_bits_map = {"1": serial.STOPBITS_ONE, "1.5": serial.STOPBITS_ONE_POINT_FIVE,
                         "2": serial.STOPBITS_TWO}
        stop_bits_str = self.stop_bits1_combo.currentText()
        stop_bits = stop_bits_map[stop_bits_str]

        rtscts = False  # 硬件
        xonxoff = False  # 软件
        flow_control_text = self.flow_control1_combo.currentText()
        if "硬件" in flow_control_text:
            rtscts = True
        elif "软件" in flow_control_text:
            xonxoff = True

        self.serial_manager.connect_port1(
            port_name, baud_rate, data_bits, parity, stop_bits, rtscts, xonxoff
        )

    def _handle_connect_port2(self):
        """处理串口2连接按钮点击事件"""
        selected_port_text = self.port2_combo.currentText()
        if not selected_port_text or "无可用串口" in selected_port_text:
            QMessageBox.warning(self, "连接失败", "未选择有效的串口或无可用串口。")
            return

        port_name = selected_port_text.split(' ')[0]
        baud_rate = int(self.baud2_combo.currentText())
        data_bits = int(self.data_bits2_combo.currentText())

        parity_map = {"无": serial.PARITY_NONE, "奇校验": serial.PARITY_ODD,
                      "偶校验": serial.PARITY_EVEN, "Mark": serial.PARITY_MARK,
                      "Space": serial.PARITY_SPACE}
        parity = parity_map[self.parity2_combo.currentText()]

        stop_bits_map = {"1": serial.STOPBITS_ONE, "1.5": serial.STOPBITS_ONE_POINT_FIVE,
                         "2": serial.STOPBITS_TWO}
        stop_bits_str = self.stop_bits2_combo.currentText()
        stop_bits = stop_bits_map[stop_bits_str]

        rtscts = False  # 硬件
        xonxoff = False  # 软件
        flow_control_text = self.flow_control2_combo.currentText()
        if "硬件" in flow_control_text:
            rtscts = True
        elif "软件" in flow_control_text:
            xonxoff = True

        self.serial_manager.connect_port2(
            port_name, baud_rate, data_bits, parity, stop_bits, rtscts, xonxoff
        )

    def _on_port1_connected(self, port_name, baud_rate):
        """串口1连接成功时调用"""
        if hasattr(self, 'status1_label'):
            self.status1_label.setText(f"状态: ✅ 已连接到 {port_name} @ {baud_rate}")
            self.status1_label.setStyleSheet(
                "color: #27ae60; font-weight: bold; padding: 5px; background-color: #d5f4e6; border-radius: 3px; border: 1px solid #27ae60;")
        self.update_ui_state()

    def _on_port2_connected(self, port_name, baud_rate):
        """串口2连接成功时调用"""
        if hasattr(self, 'status2_label'):
            self.status2_label.setText(f"状态: ✅ 已连接到 {port_name} @ {baud_rate}")
            self.status2_label.setStyleSheet(
                "color: #27ae60; font-weight: bold; padding: 5px; background-color: #d5f4e6; border-radius: 3px; border: 1px solid #27ae60;")
        self.update_ui_state()

    def _on_port1_disconnected(self):
        """串口1断开连接时调用"""
        if hasattr(self, 'status1_label'):
            self.status1_label.setText("状态: ❌ 已断开连接")
            self.status1_label.setStyleSheet(
                "color: #e74c3c; font-weight: bold; padding: 5px; background-color: #fdf2f2; border-radius: 3px; border: 1px solid #e74c3c;")
        self.update_ui_state()

    def _on_port2_disconnected(self):
        """串口2断开连接时调用"""
        if hasattr(self, 'status2_label'):
            self.status2_label.setText("状态: ❌ 已断开连接")
            self.status2_label.setStyleSheet(
                "color: #e74c3c; font-weight: bold; padding: 5px; background-color: #fdf2f2; border-radius: 3px; border: 1px solid #e74c3c;")
        self.update_ui_state()

    def _on_serial_connected(self, port_name, baud_rate):
        """SerialManager连接成功时调用（兼容模式）"""
        # 单串口界面（兼容模式）
        if hasattr(self, 'status_label'):
            self.status_label.setText(f"状态: 连接成功到 {port_name} @ {baud_rate}")
            self.status_label.setStyleSheet("color: green;")
        self.update_ui_state()

    def _on_serial_disconnected(self):
        """SerialManager断开连接时调用（兼容模式）"""
        # 单串口界面（兼容模式）
        if hasattr(self, 'status_label'):
            self.status_label.setText("状态: 已断开连接")
            self.status_label.setStyleSheet("color: red;")
        self.update_ui_state()

    def _on_serial_error(self, message):
        """SerialManager报告错误时调用"""
    
        # 根据界面类型更新状态标签
        if hasattr(self, 'status_label'):
            self.receive_text_edit.append(f"[错误]: {message}")
    # 根据界面类型更新状态标签
        if hasattr(self, 'status_label'):
            self.status_label.setText(f"状态: 错误发生")
            self.status_label.setStyleSheet("color: red;")
        self.update_ui_state()
    def _handle_send_data(self):
        """发送数据到串口"""
        hex_string = self.send_line_edit.text().strip()
        if not hex_string:
            QMessageBox.warning(self, "发送警告", "请输入要发送的十六进制数据。")
            return

        try:
            # 将十六进制字符串转换为字节数组
            # 允许奇数长度，会补齐
            if len(hex_string) % 2 != 0:
                hex_string = '0' + hex_string
            data_to_send = bytes.fromhex(hex_string)
        except ValueError:
            QMessageBox.warning(self, "发送错误", "请输入有效的十六进制字符串。")
            return

        # 根据选择的端口发送数据
        send_target = self.send_port_combo.currentText()
        success = False

        if send_target == "串口1":
            success = self.serial_manager.send_to_port1(data_to_send)
            target_info = "串口1"
        elif send_target == "串口2":
            success = self.serial_manager.send_to_port2(data_to_send)
            target_info = "串口2"
        elif send_target == "双串口":
            success = self.serial_manager.send_sequence_command(data_to_send)
            target_info = "双串口"

        if success:
            self.receive_text_edit.append(f"[发送到{target_info}]: {data_to_send.hex().upper()}")
            self.send_line_edit.clear()
        else:
            QMessageBox.warning(self, "发送失败", f"数据发送到{target_info}失败，请检查连接状态。")

    def append_received_data(self, data):
        """将接收到的数据追加到文本框"""

        """
        #默认改为字节显示
        try:
            decoded_data = data.decode('utf-8', errors='replace')
        except UnicodeDecodeError:
            decoded_data = data.hex().upper()  
        """
        # 显示十六进制表示
        decoded_data = data.hex().upper()
        self.receive_text_edit.append(f"[接收]: {decoded_data}")
        # 自动滚动到底部
        self.receive_text_edit.verticalScrollBar().setValue(self.receive_text_edit.verticalScrollBar().maximum())

    def update_ui_state(self, connected=None):
        """更新UI元素的可交互状态"""
        # 检查是否是双串口界面
        if hasattr(self, 'port1_combo') and hasattr(self, 'port2_combo'):
            # 双串口界面
            port1_connected = self.serial_manager.is_port1_connected()
            port2_connected = self.serial_manager.is_port2_connected()

            # 更新串口1 UI状态
            self.port1_combo.setEnabled(not port1_connected)
            self.baud1_combo.setEnabled(not port1_connected)
            self.data_bits1_combo.setEnabled(not port1_connected)
            self.parity1_combo.setEnabled(not port1_connected)
            self.stop_bits1_combo.setEnabled(not port1_connected)
            self.flow_control1_combo.setEnabled(not port1_connected)
            self.refresh1_button.setEnabled(not port1_connected)

            # 串口1连接按钮状态
            can_connect1 = (self.port1_combo.count() > 0 and
                            "无可用串口" not in self.port1_combo.currentText() and
                            not port1_connected)
            self.connect1_button.setEnabled(can_connect1)
            self.disconnect1_button.setEnabled(port1_connected)

            # 更新串口2 UI状态
            self.port2_combo.setEnabled(not port2_connected)
            self.baud2_combo.setEnabled(not port2_connected)
            self.data_bits2_combo.setEnabled(not port2_connected)
            self.parity2_combo.setEnabled(not port2_connected)
            self.stop_bits2_combo.setEnabled(not port2_connected)
            self.flow_control2_combo.setEnabled(not port2_connected)
            self.refresh2_button.setEnabled(not port2_connected)

            # 串口2连接按钮状态
            can_connect2 = (self.port2_combo.count() > 0 and
                            "无可用串口" not in self.port2_combo.currentText() and
                            not port2_connected)
            self.connect2_button.setEnabled(can_connect2)
            self.disconnect2_button.setEnabled(port2_connected)

            # 发送数据区域状态（任一串口连接即可发送）
            any_connected = port1_connected or port2_connected
            self.send_line_edit.setEnabled(any_connected)
            self.send_button.setEnabled(any_connected)
            self.receive_text_edit.setEnabled(any_connected)
            self.clear_receive_button.setEnabled(any_connected)

            # 更新发送端口选择器状态
            if hasattr(self, 'send_port_combo'):
                self.send_port_combo.clear()
                if port1_connected and port2_connected:
                    self.send_port_combo.addItems(["串口1", "串口2", "双串口"])
                elif port1_connected:
                    self.send_port_combo.addItems(["串口1"])
                elif port2_connected:
                    self.send_port_combo.addItems(["串口2"])
                else:
                    self.send_port_combo.addItems(["无可用连接"])
                    self.send_port_combo.setEnabled(False)
                    return

                self.send_port_combo.setEnabled(True)

        elif hasattr(self, 'port_combo'):
            # 单串口界面（兼容模式）
            is_connected = connected if connected is not None else self.serial_manager.is_connected()

            self.port_combo.setEnabled(not is_connected)
            if hasattr(self, 'baud_combo'):
                self.baud_combo.setEnabled(not is_connected)
            if hasattr(self, 'data_bits_combo'):
                self.data_bits_combo.setEnabled(not is_connected)
            if hasattr(self, 'parity_combo'):
                self.parity_combo.setEnabled(not is_connected)
            if hasattr(self, 'stop_bits_combo'):
                self.stop_bits_combo.setEnabled(not is_connected)
            if hasattr(self, 'flow_control_combo'):
                self.flow_control_combo.setEnabled(not is_connected)
            if hasattr(self, 'refresh_button'):
                self.refresh_button.setEnabled(not is_connected)

            # 连接按钮状态
            if hasattr(self, 'connect_button') and hasattr(self, 'disconnect_button'):
                can_connect = (self.port_combo.count() > 0 and
                               "无可用串口" not in self.port_combo.currentText() and
                               not is_connected)
                self.connect_button.setEnabled(can_connect)
                self.disconnect_button.setEnabled(is_connected)

            # 发送数据区域状态
            if hasattr(self, 'send_line_edit'):
                self.send_line_edit.setEnabled(is_connected)
            if hasattr(self, 'send_button'):
                self.send_button.setEnabled(is_connected)
            if hasattr(self, 'receive_text_edit'):
                self.receive_text_edit.setEnabled(is_connected)
            if hasattr(self, 'clear_receive_button'):
                self.clear_receive_button.setEnabled(is_connected)

    def closeEvent(self, event):
        """在对话框关闭时，不需断开串口，因为SerialManager是共享的。"""
        print("串口配置对话框关闭。")
        super().closeEvent(event)


# --- 控制面板对话框 ---
class ControlPanelDialog(QDialog):  # 作为一个独立的QDialog来显示
    def __init__(self, serial_manager: SerialManager, parent=None):
        super().__init__(parent)
        self.setWindowTitle("控制面板")
        self.setGeometry(250, 250, 600, 700)  # 调整窗口大小

        self.serial_manager = serial_manager
        self.init_ui()
        self._connect_signals()
        self.update_control_state()  # 根据当前串口状态初始化UI

    def init_ui(self):
        main_layout = QVBoxLayout()
        grid_layout = QGridLayout()  # 使用网格布局更整齐

        # --- 1. 电机控制 (0xAA) ---
        motor_group = QGroupBox("电机控制 (指令: 0xAA)")
        motor_layout = QFormLayout()

        # 方向
        self.motor_dir_reset_rb = QRadioButton("复位")
        self.motor_dir_out_rb = QRadioButton("出液")
        self.motor_dir_reset_rb.setChecked(True)  # 默认复位
        dir_h_layout = QHBoxLayout()
        dir_h_layout.addWidget(self.motor_dir_reset_rb)
        dir_h_layout.addWidget(self.motor_dir_out_rb)
        motor_layout.addRow("操作方向:", dir_h_layout)

        # 连接方向按钮信号
        self.motor_dir_reset_rb.toggled.connect(self.update_motor_preview)
        self.motor_dir_out_rb.toggled.connect(self.update_motor_preview)

        # 速度 - 固定值
        speed_label = QLabel("速度: 固定值 (00 00 00 3F)")
        speed_label.setStyleSheet("color: #7F8C8D; font-style: italic;")
        motor_layout.addRow("速度设置:", speed_label)

        # 圈数选择 - 15个按钮
        circle_group = QGroupBox("圈数选择")
        circle_layout = QGridLayout()

        # 定义10个圈数选项
        circle_options = [
            {"text": "1s 0.5圈", "data": [0x00, 0x00, 0x00, 0x3F]},
            {"text": "2s 1圈", "data": [0x00, 0x00, 0x80, 0x3F]},
            {"text": "3s 1.5圈", "data": [0x00, 0x00, 0xC0, 0x3F]},
            {"text": "4s 2圈", "data": [0x00, 0x00, 0x00, 0x40]},
            {"text": "5s 2.5圈", "data": [0x00, 0x00, 0x20, 0x30]},
            {"text": "6s 3圈", "data": [0x00, 0x00, 0x40, 0x40]},
            {"text": "7s 3.5圈", "data": [0x00, 0x00, 0x60, 0x40]},
            {"text": "8s 4圈", "data": [0x00, 0x00, 0x80, 0x40]},
            {"text": "9s 4.5圈", "data": [0x00, 0x00, 0x90, 0x40]},
            {"text": "10s 5圈", "data": [0x00, 0x00, 0xA0, 0x40]}
        ]

        self.circle_buttons = {}
        row, col = 0, 0
        for i, option in enumerate(circle_options):
            btn = QPushButton(option["text"])
            btn.setCheckable(True)
            btn.setMinimumSize(80, 40)
            btn.clicked.connect(lambda _, idx=i: self._on_circle_button_clicked(idx))
            circle_layout.addWidget(btn, row, col)
            self.circle_buttons[i] = {"button": btn, "data": option["data"]}

            col += 1
            if col > 4:  # 每行5个按钮
                col = 0
                row += 1

        # 默认选中第一个
        if self.circle_buttons:
            self.circle_buttons[0]["button"].setChecked(True)
            self.selected_circle_index = 0

        circle_group.setLayout(circle_layout)
        motor_layout.addRow(circle_group)

        # 添加预览标签
        self.motor_preview_label = QLabel("预览: ")
        self.motor_preview_label.setStyleSheet("""
            QLabel {
                color: #2C3E50;
                font-family: 'Courier New', monospace;
                font-size: 12px;
                padding: 5px;
                background-color: #ECF0F1;
                border: 1px solid #BDC3C7;
                border-radius: 3px;
            }
        """)
        motor_layout.addRow("数据预览:", self.motor_preview_label)

        self.motor_send_button = QPushButton("发送电机指令")
        self.motor_send_button.clicked.connect(self._send_motor_command)
        motor_layout.addRow(self.motor_send_button)

        motor_group.setLayout(motor_layout)
        grid_layout.addWidget(motor_group, 0, 0, 1, 2)  # Row 0, spanning 2 columns

        # --- 2. 电磁阀控制 (0xBB) ---
        valve_group = QGroupBox("电磁阀控制 (指令: 0xBB)")
        valve_layout = QGridLayout()

        # 使用字典存储按钮，方便管理
        self.valve_buttons = {}
        valve_data = {
            1: {"id": "1", "close": 0x11, "open": 0x12},
            2: {"id": "2", "close": 0x13, "open": 0x14},
            3: {"id": "3", "close": 0x15, "open": 0x16},
            4: {"id": "4", "close": 0x17, "open": 0x18}
        }

        for i in range(1, 5):
            valve_label = QLabel(f"电磁阀 {i}:")
            btn_open = QPushButton("打开")
            btn_close = QPushButton("关闭")

            # 使用partial or lambda to pass arguments
            btn_open.clicked.connect(lambda _, val_byte=valve_data[i]["open"]: self._send_valve_command(val_byte))
            btn_close.clicked.connect(lambda _, val_byte=valve_data[i]["close"]: self._send_valve_command(val_byte))

            valve_layout.addWidget(valve_label, i - 1, 0)
            valve_layout.addWidget(btn_open, i - 1, 1)
            valve_layout.addWidget(btn_close, i - 1, 2)
            self.valve_buttons[i] = {"open": btn_open, "close": btn_close}

        valve_group.setLayout(valve_layout)
        grid_layout.addWidget(valve_group, 1, 0, 1, 2)  # Row 1, spanning 2 columns

        # --- 3. 点火控制 (0xCC) ---
        ignition_group = QGroupBox("点火控制 (指令: 0xCC)")
        ignition_layout = QGridLayout()

        ignition_data = {
            "关电火花": 0x20, "开电火花": 0x21,
            "避险程序": 0x22,
            "持续点火": 0x24, "间断点火": 0x25
        }

        self.ignition_buttons = {}  # Initialize the dictionary
        row, col = 0, 0
        for text, value in ignition_data.items():
            button = QPushButton(text)
            button.clicked.connect(lambda _, val_byte=value: self._send_ignition_command(val_byte))
            ignition_layout.addWidget(button, row, col)
            self.ignition_buttons[text] = button  # Store the button
            col += 1
            if col > 2:  # 每行最多3个按钮
                col = 0
                row += 1

        ignition_group.setLayout(ignition_layout)
        grid_layout.addWidget(ignition_group, 2, 0, 1, 2)  # Row 2, spanning 2 columns

        main_layout.addLayout(grid_layout)
        self.setLayout(main_layout)

    def _connect_signals(self):
        self.serial_manager.connected.connect(self.update_control_state)
        self.serial_manager.disconnected.connect(self.update_control_state)
        self.serial_manager.error_occurred.connect(self.update_control_state)  # 错误可能导致断开

        # 初始化预览
        self.update_motor_preview()

    def _on_circle_button_clicked(self, index):
        """圈数按钮点击处理"""
        # 取消其他按钮的选中状态
        for i, btn_data in self.circle_buttons.items():
            if i != index:
                btn_data["button"].setChecked(False)

        self.selected_circle_index = index
        self.update_motor_preview()

    def update_control_state(self):
        """根据串口连接状态更新所有控制的启用禁用状态"""
        connected = self.serial_manager.is_connected()

        # 电机控制
        self.motor_dir_reset_rb.setEnabled(connected)
        self.motor_dir_out_rb.setEnabled(connected)

        # 启用/禁用所有圈数按钮
        for btn_data in self.circle_buttons.values():
            btn_data["button"].setEnabled(connected)

        self.motor_send_button.setEnabled(connected)

        # 电磁阀控制
        for valve_num in self.valve_buttons:
            self.valve_buttons[valve_num]["open"].setEnabled(connected)
            self.valve_buttons[valve_num]["close"].setEnabled(connected)

        # 点火控制
        for text in self.ignition_buttons:
            self.ignition_buttons[text].setEnabled(connected)

    def update_motor_preview(self):
        """更新电机控制预览"""
        motor_dir = 0x00 if self.motor_dir_reset_rb.isChecked() else 0x01
        speed_data = [0x00, 0x00, 0x00, 0x3F]  # 固定速度值
        circle_data = self.circle_buttons[self.selected_circle_index]["data"]

        # 创建命令: [0xAA, 方向, 速度(4字节), 圈数(4-5字节)]
        command = bytes([0xAA, motor_dir] + speed_data + circle_data)

        # 更新预览标签
        direction_text = "复位" if motor_dir == 0x00 else "出液"
        circle_text = self.circle_buttons[self.selected_circle_index]["button"].text()
        preview_text = "预览: {} + {} = {} ({}字节)".format(
            direction_text,
            circle_text,
            command.hex().upper(),
            len(command)
        )
        self.motor_preview_label.setText(preview_text)

    def _send_motor_command(self):
        """发送电机控制指令"""
        motor_dir = 0x00 if self.motor_dir_reset_rb.isChecked() else 0x01  # 0x00 for 复位, 0x01 for 出液
        speed_data = [0x00, 0x00, 0x00, 0x3F]  # 固定速度值
        circle_data = self.circle_buttons[self.selected_circle_index]["data"]

        # 创建命令: [0xAA, 方向, 速度(4字节), 圈数(4-5字节)]
        command = bytes([0xAA, motor_dir] + speed_data + circle_data)

        if self.serial_manager.send_data(command):
            print(f"发送电机指令: {command.hex().upper()}")
        else:
            QMessageBox.warning(self, "发送失败", "串口未连接或发送失败，请检查串口设置。")

    def _send_valve_command(self, value_byte):
        """发送电磁阀控制指令"""
        # 创建10字节命令，后面补0
        command = bytes([0xBB, value_byte] + [0x00] * 8)
        if self.serial_manager.send_data(command):
            print(f"发送电磁阀指令: {command.hex().upper()}")
        else:
            QMessageBox.warning(self, "发送失败", "串口未连接或发送失败，请检查串口设置。")

    def _send_ignition_command(self, value_byte):
        """发送点火控制指令"""
        # 创建10字节命令，后面补0
        command = bytes([0xCC, value_byte] + [0x00] * 8)
        if self.serial_manager.send_data(command):
            print(f"发送点火指令: {command.hex().upper()}")
        else:
            QMessageBox.warning(self, "发送失败", "串口未连接或发送失败，请检查串口设置。")

    def closeEvent(self, event):
        """对话框关闭时，不需要断开串口，因为SerialManager是共享的。"""
        print("控制面板对话框关闭。")
        super().closeEvent(event)


class SensorDataDialog(QDialog):  # 改为 QDialog
    """传感器数据采集对话框 - 弹出式窗口"""

    def __init__(self, serial_manager: SerialManager, parent=None):
        super().__init__(parent)
        self.serial_manager = serial_manager
        # 设置窗口属性
        self.setWindowTitle("传感器数据采集")
        self.setGeometry(200, 200, 900, 700)
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.WindowMaximizeButtonHint |
            Qt.WindowType.WindowMinimizeButtonHint |
            Qt.WindowType.WindowCloseButtonHint
        )
        self.setMinimumSize(600, 500)

        # 初始化数据存储
        import time
        self.start_time = time.time()
        self.time_counter = 0

        self.samples = []  # 存储同步后的采样数据
        self.last_pressure = None  # 缓存最后收到的压力值
        self.last_temp1 = None  # 缓存最后收到的温度1值
        self.last_temp2 = None  # 缓存最后收到的温度2值
        
        # 传感器数据历史
        self.thr_history = []
        self.pressure_history = []
        self.temp1_history = []
        self.temp2_history = []
        self.temp3_history = []

        # 完整数据存储
        self.thr_all_data = []
        self.pressure_all_data = []
        self.temp1_all_data = []
        self.temp2_all_data = []

        #添加缓冲区和状态字典
        self.serial_buffer = bytearray()
        self.current_state = {
            "thrust": 0.0,
            "pressure": 0.0,
            "pressure_4": 0.0,
            "pressure_5": 0.0,
            "pressure_6": 0.0,
            "pressure_7": 0.0,
            "temp1": 25.0,
            "temp2": 25.0,
            "temp3": 25.0,
        }
        self.all_samples = []

        self.thr_zero = 0.0
        self.pressure_zero = {addr: 0.0 for addr in range(3, 8)}
        self.temp1_zero = 0.0
        self.temp2_zero = 0.0
        self.temp3_zero = 0.0

        self.thr_max = float('-inf')
        self.pressure_max = float('-inf')
        self.temp1_max = float('-inf')
        self.temp2_max = float('-inf')
        self.temp3_max = float('-inf')

        # 状态
        self.is_collecting = False
        self.is_tare = False

        # 连接信号
        self.serial_manager.port2_data_received.connect(self.on_data)

        self.init_ui()

    def init_ui(self):
        """初始化界面"""
        main_layout = QVBoxLayout(self)

        # ========== 控制按钮区域 ==========
        control_group = QGroupBox("传感器数据采集控制")
        control_layout = QHBoxLayout()

        self.btn_start = QPushButton("开")
        self.btn_start.setStyleSheet("""
            QPushButton {
                background-color: #2ECC71;
                color: white;
                font-weight: bold;
                font-size: 14px;
                padding: 10px 20px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #27AE60;
            }
        """)
        self.btn_start.clicked.connect(self.on_start_collection)

        self.btn_stop = QPushButton("关")
        self.btn_stop.setStyleSheet("""
            QPushButton {
                background-color: #E74C3C;
                color: white;
                font-weight: bold;
                font-size: 14px;
                padding: 10px 20px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #C0392B;
            }
        """)
        self.btn_stop.clicked.connect(self.on_stop_collection)
        self.btn_stop.setEnabled(False)

        self.btn_tare = QPushButton("推力去皮")
        self.btn_tare.setStyleSheet("""
            QPushButton {
                background-color: #F39C12;
                color: white;
                font-weight: bold;
                font-size: 14px;
                padding: 10px 20px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #E67E22;
            }
        """)
        self.btn_tare.clicked.connect(self.on_tare)

        self.btn_save = QPushButton("保存数据")
        self.btn_save.setStyleSheet("""
            QPushButton {
                background-color: #3498DB;
                color: white;
                font-weight: bold;
                font-size: 14px;
                padding: 10px 20px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #2980B9;
            }
        """)
        self.btn_save.clicked.connect(self.on_save_data)

        control_layout.addWidget(self.btn_start)
        control_layout.addWidget(self.btn_stop)
        control_layout.addWidget(self.btn_tare)
        control_layout.addWidget(self.btn_save)
        control_layout.addStretch()

        control_group.setLayout(control_layout)
        main_layout.addWidget(control_group)

        # ========== 数据显示区域 ==========
        display_group = QGroupBox("传感器数据")
        display_layout = QVBoxLayout()
        display_layout.setSpacing(2)

        label_base = "font-size: 12px;"
        title_base = label_base + "font-weight: bold;"

        # ---- 第一行: 推力 | 压力#3 | 温度1 | 温度2 | 温度3 ----
        row1_grid = QGridLayout()
        row1_grid.setHorizontalSpacing(8)

        def _add_sensor(grid, col, title, color, unit, init_val):
            tl = QLabel(title)
            tl.setStyleSheet(f"{title_base}color: {color};")
            grid.addWidget(tl, 0, col)

            cl = QLabel(f"实时值: {init_val}")
            cl.setStyleSheet(label_base)
            grid.addWidget(cl, 1, col)

            ml = QLabel(f"最大值: {init_val}")
            ml.setStyleSheet(label_base)
            grid.addWidget(ml, 2, col)
            return cl, ml

        self.thrust_current_label, self.thrust_max_label = \
            _add_sensor(row1_grid, 0, "推力传感器", "#2ECC71", "N", "0.00 N")
        self.pressure_current_label, self.pressure_max_label = \
            _add_sensor(row1_grid, 1, "压力传感器#3", "#9B59B6", "MPa", "0.00 MPa")
        self.temp1_current_label, self.temp1_max_label = \
            _add_sensor(row1_grid, 2, "温度传感器1", "#E74C3C", "°C", "25.0 °C")
        self.temp2_current_label, self.temp2_max_label = \
            _add_sensor(row1_grid, 3, "温度传感器2", "#3498DB", "°C", "25.0 °C")
        self.temp3_current_label, self.temp3_max_label = \
            _add_sensor(row1_grid, 4, "温度传感器3", "#F39C12", "°C", "25.0 °C")

        display_layout.addLayout(row1_grid)

        # ---- 第二行: 压力#4 | 压力#5 | 压力#6 | 压力#7 ----
        row2_grid = QGridLayout()
        row2_grid.setHorizontalSpacing(8)

        pressure_colors = {4: '#E74C3C', 5: '#3498DB', 6: '#2ECC71', 7: '#F39C12'}
        for col_idx, addr in enumerate(range(4, 8)):
            color = pressure_colors[addr]
            tl = QLabel(f"压力传感器#{addr}")
            tl.setStyleSheet(f"{title_base}color: {color};")
            row2_grid.addWidget(tl, 0, col_idx)

            cl = QLabel(f"压力#{addr}: -- MPa")
            cl.setStyleSheet(label_base)
            row2_grid.addWidget(cl, 1, col_idx)
            setattr(self, f"pressure_{addr}_label", cl)

        display_layout.addLayout(row2_grid)
        display_group.setLayout(display_layout)
        main_layout.addWidget(display_group)

        # ========== 图表区域 ==========
        chart_group = QGroupBox("数据图表")
        chart_layout = QVBoxLayout(chart_group)
        chart_layout.setSpacing(4)

        pressure_extra_colors = {3: '#9B59B6', 4: '#E74C3C', 5: '#3498DB', 6: '#2ECC71', 7: '#F39C12'}

        chart_style = """
            QLabel {
                font-size: 11px;
                font-weight: bold;
                padding: 1px 6px;
                color: #ECF0F1;
            }
        """

        # --- 推力图表 ---
        thrust_label = QLabel("▪ 推力")
        thrust_label.setStyleSheet(chart_style + "QLabel { background-color: #2ECC71; border-radius: 2px; }")
        chart_layout.addWidget(thrust_label)

        self.thrust_plot = pg.PlotWidget()
        self.thrust_plot.setBackground('#34495E')
        self.thrust_plot.setMaximumHeight(140)
        self.thrust_plot.setLabel('left', '推力', units='N')
        self.thrust_plot.setLabel('bottom', '时间', units='s')
        self.thrust_plot.showGrid(x=True, y=True)
        self.thrust_curve = self.thrust_plot.plot(
            pen=pg.mkPen(color='#2ECC71', width=2),
            name='推力 (N)'
        )
        _legend = self.thrust_plot.addLegend()
        _legend.anchor(itemPos=(1, 0), parentPos=(1, 0), offset=(-5, 5))
        chart_layout.addWidget(self.thrust_plot)

        # --- 温度图表 ---
        temp_label = QLabel("▪ 温度")
        temp_label.setStyleSheet(chart_style + "QLabel { background-color: #E74C3C; border-radius: 2px; }")
        chart_layout.addWidget(temp_label)

        self.temp_plot = pg.PlotWidget()
        self.temp_plot.setBackground('#34495E')
        self.temp_plot.setMaximumHeight(140)
        self.temp_plot.setLabel('left', '温度', units='°C')
        self.temp_plot.setLabel('bottom', '时间', units='s')
        self.temp_plot.showGrid(x=True, y=True)
        self.temp1_curve = self.temp_plot.plot(
            pen=pg.mkPen(color='#E74C3C', width=2),
            name='温度1 (°C)'
        )
        self.temp2_curve = self.temp_plot.plot(
            pen=pg.mkPen(color='#3498DB', width=2),
            name='温度2 (°C)'
        )
        self.temp3_curve = self.temp_plot.plot(
            pen=pg.mkPen(color='#F39C12', width=2),
            name='温度3 (°C)'
        )
        _legend = self.temp_plot.addLegend()
        _legend.anchor(itemPos=(1, 0), parentPos=(1, 0), offset=(-5, 5))
        chart_layout.addWidget(self.temp_plot)

        # --- 压力图表 ---
        pressure_label = QLabel("▪ 压力")
        pressure_label.setStyleSheet(chart_style + "QLabel { background-color: #9B59B6; border-radius: 2px; }")
        chart_layout.addWidget(pressure_label)

        self.pressure_plot = pg.PlotWidget()
        self.pressure_plot.setBackground('#34495E')
        self.pressure_plot.setMaximumHeight(140)
        self.pressure_plot.setLabel('left', '压力', units='MPa')
        self.pressure_plot.setLabel('bottom', '时间', units='s')
        self.pressure_plot.showGrid(x=True, y=True)
        self.pressure_curve = self.pressure_plot.plot(
            pen=pg.mkPen(color=pressure_extra_colors[3], width=2),
            name='压力#3 (MPa)'
        )
        self.pressure_extra_curves = {}
        for addr in range(4, 8):
            self.pressure_extra_curves[addr] = self.pressure_plot.plot(
                pen=pg.mkPen(color=pressure_extra_colors[addr], width=2),
                name=f'压力#{addr} (MPa)'
            )
        _legend = self.pressure_plot.addLegend()
        _legend.anchor(itemPos=(1, 0), parentPos=(1, 0), offset=(-5, 5))
        chart_layout.addWidget(self.pressure_plot)

        main_layout.addWidget(chart_group, stretch=1)

    def on_data(self, data: bytes):
        """安检员：负责接收、拼包、校验，过滤错误数据"""
        if len(data) == 0 or not self.is_collecting:
            return

        # 1. 将新到的碎片数据存入缓冲区
        self.serial_buffer.extend(data)

        # 2. 循环检查缓冲区，处理所有完整的帧
        while len(self.serial_buffer) >= 3:
            addr = self.serial_buffer[0]
            # 检查地址是否为 0x01(推力), 0x02(温度), 或 0x03(压力)
            if addr not in [0x01, 0x02] and not (0x03 <= addr <= 0x07):
                self.serial_buffer.pop(0) # 丢弃开头不对的脏数据
                continue

            # 根据协议，第3个字节代表后续有效数据长度
            data_len = self.serial_buffer[2]
            expected_len = 3 + data_len + 2 # 总长度 = 头(3) + 数据(N) + 校验(2)

            if len(self.serial_buffer) < expected_len:
                break # 长度不够，说明包被截断了，等下一个串口切片过来再拼

            # 3. 提取完整的一帧
            frame = self.serial_buffer[:expected_len]
            
            # 4. 校验 CRC (调用你放在文件最顶部的 calculate_crc16 函数)
            if frame[-2:] == calculate_crc16(frame[:-2]):
                # ▼▼▼ 添加这行拦截打印代码 ▼▼▼
                print(f"✅ 成功收到一帧数据: {frame.hex().upper()}")
                # ▲▲▲ 添加这行拦截打印代码 ▲▲▲
                self.process_sensor_frame(frame) # 校验通过，交给处理员更新UI
            else:
                print(f"CRC校验失败，丢弃干扰包: {frame.hex().upper()}")
            
            # 5. 清理缓冲区，把刚才处理完的包删掉，准备处理下一个
            del self.serial_buffer[:expected_len]

    def process_sensor_frame(self, frame: bytes):
        """处理员：负责解析数值、更新UI、绘制图表、同步数据记录"""
        t = time.time() - self.start_time
        addr = frame[0]
        
        updated = False # 标记是否需要记录一行新的对齐数据

        if addr == 0x01:  # 推力传感器
            thrust = int.from_bytes(frame[3:5], 'big', signed=True) / 1000.0 * 9.8 - self.thr_zero
            self.current_state["thrust"] = thrust

            if thrust > self.thr_max:
                self.thr_max = thrust

            self.thrust_current_label.setText(f"实时值: {thrust:.2f} N")
            self.thrust_max_label.setText(f"最大值: {self.thr_max:.2f} N")

            self.thr_history.append((t, thrust))
            display_data = self.thr_history[-500:] if len(self.thr_history) > 500 else self.thr_history
            x, y = zip(*display_data)
            self.thrust_curve.setData(x, y)

            updated = True

        elif addr == 0x02:  # 温度传感器 (3路)
            temp1 = int.from_bytes(frame[3:5], 'big', signed=True) / 10.0
            temp2 = int.from_bytes(frame[5:7], 'big', signed=True) / 10.0
            temp3 = int.from_bytes(frame[7:9], 'big', signed=True) / 10.0 if len(frame) >= 10 else 0.0
            self.current_state["temp1"] = temp1
            self.current_state["temp2"] = temp2
            self.current_state["temp3"] = temp3

            if temp1 > self.temp1_max: self.temp1_max = temp1
            if temp2 > self.temp2_max: self.temp2_max = temp2
            if temp3 > self.temp3_max: self.temp3_max = temp3

            self.temp1_current_label.setText(f"实时值: {temp1:.1f} °C")
            self.temp1_max_label.setText(f"最大值: {self.temp1_max:.1f} °C")
            self.temp2_current_label.setText(f"实时值: {temp2:.1f} °C")
            self.temp2_max_label.setText(f"最大值: {self.temp2_max:.1f} °C")
            self.temp3_current_label.setText(f"实时值: {temp3:.1f} °C")
            self.temp3_max_label.setText(f"最大值: {self.temp3_max:.1f} °C")

            self.temp1_history.append((t, temp1))
            self.temp2_history.append((t, temp2))
            self.temp3_history.append((t, temp3))
            display_data1 = self.temp1_history[-500:] if len(self.temp1_history) > 500 else self.temp1_history
            display_data2 = self.temp2_history[-500:] if len(self.temp2_history) > 500 else self.temp2_history
            display_data3 = self.temp3_history[-500:] if len(self.temp3_history) > 500 else self.temp3_history
            x1, y1 = zip(*display_data1)
            x2, y2 = zip(*display_data2)
            x3, y3 = zip(*display_data3)
            self.temp1_curve.setData(x1, y1)
            self.temp2_curve.setData(x2, y2)
            self.temp3_curve.setData(x3, y3)

            updated = True

        # 压力传感器地址 0x03-0x07, 读取[3:5]
        elif 0x03 <= addr <= 0x07:
            pressure = int.from_bytes(frame[3:5], 'big', signed=True) / 100.0 - self.pressure_zero.get(addr, 0.0)
            if addr == 0x03:
                self.current_state["pressure"] = pressure
                self.current_state["pressure_3"] = pressure
                if pressure > self.pressure_max:
                    self.pressure_max = pressure
                self.pressure_current_label.setText(f"实时值: {pressure:.2f} MPa")
                self.pressure_max_label.setText(f"最大值: {self.pressure_max:.2f} MPa")

                self.pressure_history.append((t, pressure))
                display_data = self.pressure_history[-500:] if len(self.pressure_history) > 500 else self.pressure_history
                x, y = zip(*display_data)
                self.pressure_curve.setData(x, y)
            else:
                self.current_state[f"pressure_{addr}"] = pressure

                attr_name = f"pressure_{addr}_history"
                if not hasattr(self, attr_name):
                    setattr(self, attr_name, [])
                hist = getattr(self, attr_name)
                hist.append((t, pressure))
                if len(hist) > 500:
                    hist.pop(0)
                if addr in getattr(self, 'pressure_extra_curves', {}):
                    x, y = zip(*hist[-500:])
                    self.pressure_extra_curves[addr].setData(x, y)

                label_attr = f"pressure_{addr}_label"
                if hasattr(self, label_attr):
                    getattr(self, label_attr).setText(f"压力#{addr}: {pressure:.2f} MPa")

            updated = True

        # 任一传感器更新时，把当前快照存入 all_samples
        if updated:
            self.all_samples.append((
                t,
                self.current_state["thrust"],
                self.current_state["pressure"],
                self.current_state["pressure_4"],
                self.current_state["pressure_5"],
                self.current_state["pressure_6"],
                self.current_state["pressure_7"],
                self.current_state["temp1"],
                self.current_state["temp2"],
                self.current_state["temp3"],
            ))

    def on_start_collection(self):
        """开始数据采集"""
        if not self.serial_manager.is_port2_connected():
            QMessageBox.warning(self, "连接错误", "串口2未连接，无法启动数据采集。请先在串口设置中连接串口2。")
            return

        if not hasattr(self, 'collection_timer'):
            self.collection_timer = QTimer(self)
            self.collection_timer.timeout.connect(self.send_sensor_commands)
            self.collection_timer.start(200)

        self.is_collecting = True
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        print("传感器数据采集已启动")

    def on_stop_collection(self):
        """停止数据采集"""
        if hasattr(self, 'collection_timer'):
            self.collection_timer.stop()
            del self.collection_timer

        self.is_collecting = False
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        print("传感器数据采集已停止")

    def send_sensor_commands(self):
        thrust_command = 0x010300000002C40B
        temp_data = bytes([0x02, 0x04, 0x00, 0x00, 0x00, 0x03])
        temp_bytes = temp_data + calculate_crc16(temp_data)

        thrust_bytes = thrust_command.to_bytes(8, byteorder='big')

        self.serial_manager.send_data(thrust_bytes)
        QApplication.processEvents()
        QThread.msleep(50)

        self.serial_manager.send_data(temp_bytes)
        QApplication.processEvents()
        QThread.msleep(50)

        for addr in range(3, 8):
            data = bytes([addr, 0x03, 0x00, 0x04, 0x00, 0x01])
            crc = calculate_crc16(data)
            cmd_bytes = int.from_bytes(data + crc, 'big').to_bytes(8, 'big')
            self.serial_manager.send_data(cmd_bytes)
            QApplication.processEvents()
            QThread.msleep(20)

    def on_tare(self):
        """推力去皮"""
        if self.thr_history:
            _, current_thrust = self.thr_history[-1]
            self.thr_zero += current_thrust
            self.is_tare = True
            print(f"推力去皮完成，零点调整为: {self.thr_zero:.2f} N")
        else:
            print("没有推力数据，无法去皮")


    def on_save_data(self):
        """保存对齐后的统一数据为 Excel 文件"""
        # 1. 检查有没有数据 (现在只需要检查 all_samples 这一个列表即可)
        if getattr(self, 'all_samples', None) is None or len(self.all_samples) == 0:
            print("没有数据可保存")
            return

        folder = "传感器数据"
        os.makedirs(folder, exist_ok=True)

        filename = f"传感器数据_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        filepath = os.path.join(folder, filename)

        wb = Workbook()
        ws = wb.active
        ws.title = "传感器数据"

        # 写入表头
        ws.append(['时间(s)', '推力(N)', '压力#3(MPa)', '压力#4(MPa)', '压力#5(MPa)',
                    '压力#6(MPa)', '压力#7(MPa)', '温度1(°C)', '温度2(°C)', '温度3(°C)'])

        for sample in self.all_samples:
            ws.append([
                round(sample[0], 3),
                round(sample[1], 2) if sample[1] is not None else '',
                round(sample[2], 3) if sample[2] is not None else '',
                round(sample[3], 3) if sample[3] is not None else '',
                round(sample[4], 3) if sample[4] is not None else '',
                round(sample[5], 3) if sample[5] is not None else '',
                round(sample[6], 3) if sample[6] is not None else '',
                round(sample[7], 2) if sample[7] is not None else '',
                round(sample[8], 2) if sample[8] is not None else '',
                round(sample[9], 2) if sample[9] is not None else '',
            ])

        wb.save(filepath)
        print(f"已保存 {len(self.all_samples)} 条对齐数据到: {filename}")

def closeEvent(self, event):
        """关闭对话框时停止采集"""
        self.on_stop_collection()
        try:
            self.serial_manager.port2_data_received.disconnect(self.on_data)
        except:
            pass
        super().closeEvent(event)