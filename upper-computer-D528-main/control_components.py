# control_components.py - 控制面板界面组件

import struct
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout,
    QPushButton, QLabel, QRadioButton, QSlider, QGroupBox,
    QTabWidget, QFrame, QTextEdit, QSplitter,
    QDoubleSpinBox, QSpinBox, QCheckBox, QButtonGroup, QScrollArea,
    QSizePolicy, QListWidget, QListWidgetItem, QMessageBox,QMenu,QFileDialog, QMessageBox, QInputDialog,QLineEdit
)
from PySide6.QtCore import Qt, QSize, Signal, QMimeData, QTimer
from PySide6.QtGui import QFont, QIcon, QPalette, QColor, QDragEnterEvent, QDropEvent, QDrag, QAction, QBrush
import json
import os
from datetime import datetime
from serial_components import SensorDataDialog

class SequenceManager:
    """序列管理器 - 负责保存和加载序列"""

    def __init__(self, sequences_dir="sequences"):
        self.sequences_dir = sequences_dir
        # 确保目录存在
        if not os.path.exists(sequences_dir):
            os.makedirs(sequences_dir)

    def save_sequence(self, sequence_list, name=None):
        """保存序列到文件"""
        if name is None:
            # 自动生成带时间戳的名称
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            name = f"实验序列_{timestamp}"

        # 确保文件名合法
        filename = self._sanitize_filename(name) + ".json"
        filepath = os.path.join(self.sequences_dir, filename)

        # 转换序列为可序列化格式
        sequence_data = []
        for i in range(sequence_list.count()):
            item = sequence_list.item(i)
            data = item.data(Qt.ItemDataRole.UserRole)
            # 确保所有数据都是JSON可序列化的
            serializable_data = self._make_serializable(data)
            sequence_data.append({
                "index": i,
                "text": item.text(),
                "data": serializable_data
            })

        # 保存为JSON
        save_data = {
            "name": name,
            "created_at": datetime.now().isoformat(),
            "version": "1.0",
            "sequence": sequence_data
        }

        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(save_data, f, ensure_ascii=False, indent=2)
            return True, filepath
        except Exception as e:
            return False, str(e)

    def load_sequence(self, filepath):
        """从文件加载序列"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                save_data = json.load(f)

            # 验证版本
            version = save_data.get("version", "1.0")
            sequence_data = save_data.get("sequence", [])

            # 转换为SequenceItem可用的格式
            items_data = []
            for item_data in sequence_data:
                data = item_data.get("data", {})
                items_data.append({
                    "text": item_data.get("text", "未知命令"),
                    "data": data
                })

            return True, items_data, save_data.get("name", "未命名序列")
        except Exception as e:
            return False, str(e), None

    def list_saved_sequences(self):
        """列出所有保存的序列"""
        sequences = []
        if os.path.exists(self.sequences_dir):
            for filename in sorted(os.listdir(self.sequences_dir)):
                if filename.endswith(".json"):
                    filepath = os.path.join(self.sequences_dir, filename)
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        sequences.append({
                            "filename": filename,
                            "name": data.get("name", filename),
                            "created_at": data.get("created_at", "未知"),
                            "filepath": filepath
                        })
                    except:
                        pass
        return sequences

    def delete_sequence(self, filepath):
        """删除序列文件"""
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
                return True, None
            return False, "文件不存在"
        except Exception as e:
            return False, str(e)

    def _sanitize_filename(self, name):
        """清理文件名中的非法字符"""
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            name = name.replace(char, '_')
        return name.strip()

    def _make_serializable(self, data):
        """确保数据可JSON序列化（处理Qt类型）"""
        if isinstance(data, dict):
            return {k: self._make_serializable(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._make_serializable(i) for i in data]
        elif isinstance(data, (int, float, str, bool, type(None))):
            return data
        else:
            # 其他类型转为字符串
            return str(data)


from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QLabel, QMessageBox, QGroupBox, QSplitter
)


class SequenceSelectorDialog(QDialog):
    """序列选择对话框 - 用于导入已保存的序列"""

    def __init__(self, sequence_manager, parent=None):
        super().__init__(parent)
        self.sequence_manager = sequence_manager
        self.selected_filepath = None
        self.selected_name = None

        self.setWindowTitle("导入实验序列")
        self.setMinimumSize(500, 400)
        self.init_ui()
        self.refresh_list()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(15, 15, 15, 15)

        # 标题
        title = QLabel("选择要导入的实验序列")
        title.setStyleSheet("font-weight: bold; font-size: 14px; color: #2C3E50;")
        layout.addWidget(title)

        # 序列列表
        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet("""
             QListWidget {
                 border: 2px solid #3498DB;
                 border-radius: 6px;
                 padding: 5px;
                 font-size: 12px;
             }
             QListWidget::item {
                 padding: 8px;
                 border-bottom: 1px solid #ECF0F1;
             }
             QListWidget::item:selected {
                 background-color: #3498DB;
                 color: white;
             }
             QListWidget::item:hover {
                 background-color: #D6EAF8;
             }
         """)
        self.list_widget.itemDoubleClicked.connect(self.accept)
        layout.addWidget(self.list_widget)

        # 详情显示
        self.detail_label = QLabel("选择一个序列查看详情")
        self.detail_label.setStyleSheet("""
             color: #7F8C8D;
             font-size: 11px;
             padding: 8px;
             background-color: #F8F9FA;
             border-radius: 4px;
             min-height: 60px;
         """)
        self.detail_label.setWordWrap(True)
        layout.addWidget(self.detail_label)

        # 按钮区域
        button_layout = QHBoxLayout()

        self.refresh_btn = QPushButton("🔄 刷新列表")
        self.refresh_btn.setStyleSheet("""
             QPushButton {
                 background-color: #95A5A6;
                 color: white;
                 border: none;
                 border-radius: 4px;
                 padding: 8px 15px;
                 font-weight: bold;
             }
             QPushButton:hover {
                 background-color: #7F8C8D;
             }
         """)
        self.refresh_btn.clicked.connect(self.refresh_list)
        button_layout.addWidget(self.refresh_btn)

        button_layout.addStretch()

        self.delete_btn = QPushButton("删除")
        self.delete_btn.setStyleSheet("""
             QPushButton {
                 background-color: #E74C3C;
                 color: white;
                 border: none;
                 border-radius: 4px;
                 padding: 8px 15px;
                 font-weight: bold;
             }
             QPushButton:hover {
                 background-color: #C0392B;
             }
         """)
        self.delete_btn.clicked.connect(self.delete_selected)
        button_layout.addWidget(self.delete_btn)

        button_layout.addSpacing(20)

        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_btn)

        self.import_btn = QPushButton("✓ 导入选中")
        self.import_btn.setStyleSheet("""
             QPushButton {
                 background-color: #27AE60;
                 color: white;
                 border: none;
                 border-radius: 4px;
                 padding: 8px 20px;
                 font-weight: bold;
                 font-size: 13px;
             }
             QPushButton:hover {
                 background-color: #229954;
             }
         """)
        self.import_btn.clicked.connect(self.accept)
        button_layout.addWidget(self.import_btn)

        layout.addLayout(button_layout)

        # 连接信号
        self.list_widget.currentItemChanged.connect(self.on_selection_changed)

    def refresh_list(self):
        """刷新序列列表"""
        self.list_widget.clear()
        sequences = self.sequence_manager.list_saved_sequences()

        if not sequences:
            item = QListWidgetItem("暂无保存的序列")
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            item.setForeground(QColor("#95A5A6"))
            self.list_widget.addItem(item)
            self.import_btn.setEnabled(False)
            self.delete_btn.setEnabled(False)
            return

        self.import_btn.setEnabled(True)
        self.delete_btn.setEnabled(True)

        for seq in sequences:
            display_text = f"{seq['name']}\n    创建于: {seq['created_at'][:19].replace('T', ' ')}"
            item = QListWidgetItem(display_text)
            item.setData(Qt.ItemDataRole.UserRole, seq)  # 存储完整数据
            self.list_widget.addItem(item)

    def on_selection_changed(self, current, previous):
        """选择改变时更新详情"""
        if not current:
            self.detail_label.setText("选择一个序列查看详情")
            return

        seq_data = current.data(Qt.ItemDataRole.UserRole)
        if not seq_data:
            return

        # 读取文件获取详细内容
        success, items_data, name = self.sequence_manager.load_sequence(seq_data['filepath'])
        if success:
            # 生成详情文本
            detail_text = f"<b>序列名称:</b> {name}<br>"
            detail_text += f"<b>文件:</b> {seq_data['filename']}<br>"
            detail_text += f"<b>包含命令:</b> {len(items_data)} 项<br><br>"

            # 显示前5个命令
            preview_count = min(5, len(items_data))
            detail_text += "<b>命令预览:</b><br>"
            for i in range(preview_count):
                text = items_data[i]['text']
                detail_text += f"  {i + 1}. {text}<br>"

            if len(items_data) > 5:
                detail_text += f"  ... 还有 {len(items_data) - 5} 项"

            self.detail_label.setText(detail_text)
        else:
            self.detail_label.setText(f"<span style='color: #E74C3C;'>无法读取文件: {items_data}</span>")

    def delete_selected(self):
        """删除选中的序列"""
        current = self.list_widget.currentItem()
        if not current:
            return

        seq_data = current.data(Qt.ItemDataRole.UserRole)
        if not seq_data:
            return

        # 确认对话框
        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定要删除序列 \"{seq_data['name']}\" 吗？\n此操作不可恢复。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            success, error = self.sequence_manager.delete_sequence(seq_data['filepath'])
            if success:
                QMessageBox.information(self, "成功", "序列已删除")
                self.refresh_list()
            else:
                QMessageBox.warning(self, "错误", f"删除失败: {error}")

    def accept(self):
        """确认导入"""
        current = self.list_widget.currentItem()
        if not current:
            QMessageBox.warning(self, "提示", "请先选择一个序列")
            return

        seq_data = current.data(Qt.ItemDataRole.UserRole)
        if not seq_data:
            return

        self.selected_filepath = seq_data['filepath']
        self.selected_name = seq_data['name']
        super().accept()

    def get_selection(self):
        """获取选择结果"""
        return self.selected_filepath, self.selected_name

class SequenceListWidget(QListWidget):
    """序列列表控件 - 支持键盘上下移动和删除"""
    item_deleted = Signal(int)  # 信号：项目被删除（-1表示移动）
    item_moved = Signal(int, int)  # 信号：从from_row移动到to_row（新增）

    def __init__(self, parent=None):
        super().__init__(parent)

        # 基本设置
        self.setDragDropMode(QListWidget.DragDropMode.NoDragDrop)  # 禁用拖拽
        self.setDragEnabled(False)
        self.setAcceptDrops(False)
        self.setSelectionMode(QListWidget.SelectionMode.SingleSelection)  # 单选，方便键盘操作
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        # 清除样式
        self.setStyleSheet("")

        # 启用焦点，这样才能接收键盘事件
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # 提示标签
        self.setToolTip("操作提示：↑↓键移动选中项，Delete键删除，右键菜单更多操作")

    def keyPressEvent(self, event):
        """处理键盘事件"""
        key = event.key()

        # 获取当前选中行
        current_row = self.currentRow()

        # Delete键删除
        if key == Qt.Key.Key_Delete:
            self._delete_selected_items()
            return

        # ↑键上移
        elif key == Qt.Key.Key_Up:
            if current_row > 0:
                # Shift+↑ 移到最顶
                if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                    self._move_item_to(current_row, 0)
                else:
                    self._move_item_up(current_row)
            else:
                # 已经在顶部，只是向上选择（如果有上一项）
                super().keyPressEvent(event)
            return

        # ↓键下移
        elif key == Qt.Key.Key_Down:
            if current_row < self.count() - 1 and current_row >= 0:
                # Shift+↓ 移到底部
                if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                    self._move_item_to(current_row, self.count() - 1)
                else:
                    self._move_item_down(current_row)
            else:
                # 已经在底部或没选中，默认处理
                super().keyPressEvent(event)
            return

        # Ctrl+Home 移到顶部
        elif key == Qt.Key.Key_Home and (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            if current_row > 0:
                self._move_item_to(current_row, 0)
            return

        # Ctrl+End 移到底部
        elif key == Qt.Key.Key_End and (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            if current_row < self.count() - 1 and current_row >= 0:
                self._move_item_to(current_row, self.count() - 1)
            return

        # 空格键或Enter执行（可选功能）
        elif key in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            # 可以触发执行当前项，或只是选中
            super().keyPressEvent(event)
            return

        else:
            super().keyPressEvent(event)

    def _move_item_up(self, row):
        """上移一个项目（与上一项交换位置）"""
        if row <= 0 or row >= self.count():
            return

        # 获取当前项和上一项
        current_item = self.item(row)
        above_item = self.item(row - 1)

        if not current_item or not above_item:
            return

        # 交换数据（保留所有UserRole数据）
        self._swap_items_data(current_item, above_item)

        # 保持选中状态（选中上移后的位置，即原来的上一行）
        self.setCurrentRow(row - 1)

        # 发送信号
        self.item_moved.emit(row, row - 1)
        self.item_deleted.emit(-1)  # 兼容旧信号

    def _move_item_down(self, row):
        """下移一个项目（与下一项交换位置）"""
        if row < 0 or row >= self.count() - 1:
            return

        # 获取当前项和下一项
        current_item = self.item(row)
        below_item = self.item(row + 1)

        if not current_item or not below_item:
            return

        # 交换数据
        self._swap_items_data(current_item, below_item)

        # 保持选中状态（选中下移后的位置，即原来的下一行）
        self.setCurrentRow(row + 1)

        # 发送信号
        self.item_moved.emit(row, row + 1)
        self.item_deleted.emit(-1)

    def _move_item_to(self, from_row, to_row):
        """将项目移动到指定位置（用于Shift+方向键或Ctrl+Home/End）"""
        if from_row == to_row or from_row < 0 or to_row < 0:
            return
        if from_row >= self.count() or to_row >= self.count():
            return

        # 取出项目
        item = self.takeItem(from_row)
        if not item:
            return

        # 插入到新位置
        self.insertItem(to_row, item)
        self.setCurrentItem(item)

        # 发送信号
        self.item_moved.emit(from_row, to_row)
        self.item_deleted.emit(-1)

    def _swap_items_data(self, item1, item2):
        """交换两个项目的所有数据（文本、UserRole数据、背景色等）"""
        # 交换文本
        text1 = item1.text()
        text2 = item2.text()
        item1.setText(text2)
        item2.setText(text1)

        # 交换UserRole数据（核心：包含action_type和所有参数）
        data1 = item1.data(Qt.ItemDataRole.UserRole)
        data2 = item2.data(Qt.ItemDataRole.UserRole)
        item1.setData(Qt.ItemDataRole.UserRole, data2)
        item2.setData(Qt.ItemDataRole.UserRole, data1)

        # 交换背景色
        bg1 = item1.background()
        bg2 = item2.background()
        item1.setBackground(bg2)
        item2.setBackground(bg1)

        # 交换前景色（文字颜色）
        fg1 = item1.foreground()
        fg2 = item2.foreground()
        item1.setForeground(fg2)
        item2.setForeground(fg1)

        # 交换字体
        font1 = item1.font()
        font2 = item2.font()
        item1.setFont(font2)
        item2.setFont(font1)

        # 交换工具提示
        tip1 = item1.toolTip()
        tip2 = item2.toolTip()
        item1.setToolTip(tip2)
        item2.setToolTip(tip1)

    def _show_context_menu(self, position):
        """显示右键菜单"""
        menu = QMenu(self)
        current_row = self.currentRow()

        # 选中项相关操作
        if current_row >= 0:
            # 删除
            delete_action = QAction("删除 (Delete)", self)
            delete_action.triggered.connect(self._delete_selected_items)
            menu.addAction(delete_action)

            menu.addSeparator()

            # 移动操作
            move_menu = QMenu("移动", self)

            # 移到顶部
            if current_row > 0:
                top_action = QAction("移到顶部 (Ctrl+Home)", self)
                top_action.triggered.connect(lambda: self._move_item_to(current_row, 0))
                move_menu.addAction(top_action)

                up_action = QAction("上移 (↑)", self)
                up_action.triggered.connect(lambda: self._move_item_up(current_row))
                move_menu.addAction(up_action)

            # 移到底部
            if current_row < self.count() - 1:
                down_action = QAction("下移 (↓)", self)
                down_action.triggered.connect(lambda: self._move_item_down(current_row))
                move_menu.addAction(down_action)

                bottom_action = QAction("移到底部 (Ctrl+End)", self)
                bottom_action.triggered.connect(lambda: self._move_item_to(current_row, self.count() - 1))
                move_menu.addAction(bottom_action)

            if move_menu.actions():
                menu.addMenu(move_menu)

            menu.addSeparator()

        # 全局操作
        if self.count() > 0:
            clear_action = QAction("清空所有", self)
            clear_action.triggered.connect(self.clear)
            menu.addAction(clear_action)

        if menu.actions():
            menu.exec(self.mapToGlobal(position))

    def _delete_selected_items(self):
        """删除选中的项目"""
        current_row = self.currentRow()
        if current_row < 0:
            return

        # 删除当前项
        item = self.takeItem(current_row)
        if item:
            self.item_deleted.emit(current_row)

            # 自动选中下一项（或上一项）
            if current_row < self.count():
                self.setCurrentRow(current_row)
            elif self.count() > 0:
                self.setCurrentRow(current_row - 1)


    def dragEnterEvent(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()

    def dropEvent(self, event):
        action_type = event.mimeData().text()
        if action_type in ["motor", "valve_open", "valve_close", "ignition_on", "ignition_off", "delay"]:
            # 创建序列项目
            if action_type == "delay":
                item = SequenceItem("延时", action_type, 1000)  # 默认1秒延时
            else:
                item = SequenceItem(self._get_action_name(action_type), action_type)
            
            self.addItem(item)
            event.acceptProposedAction()

    def _get_action_name(self, action_type):
        names = {
            "motor": "电机控制",
            "valve_open": "开阀",
            "valve_close": "关阀", 
            "ignition_on": "点火",
            "ignition_off": "熄火",
            "delay": "延时"
        }
        return names.get(action_type, action_type)

class SequenceItem(QListWidgetItem):
    """序列项目"""
    def __init__(self, name, action_type, delay_ms=0):
        super().__init__()
        self.action_type = action_type
        self.delay_ms = delay_ms
        self.setData(Qt.ItemDataRole.UserRole, {"action_type": action_type, "delay_ms": delay_ms})
        
        # 设置不同操作类型的马卡龙色系 - 更柔和的颜色
        colors = {
            "motor": "#95C7F0",  # 柔和的蓝色 - 电机控制
            "valve_open": "#F2A7A7",  # 柔和的红色 - 电磁阀控制
            "valve_close": "#F2A7A7",  # 柔和的红色 - 电磁阀控制
            "ignition_on": "#FFD699",  # 柔和的黄色 - 点火控制
            "ignition_off": "#FFD699",  # 柔和的黄色 - 点火控制
            "delay": "#99D8CA",# 柔和的绿色 - 延时控制
            "all_valves_open": "#F2A7A7",  
            "all_valves_close": "#F2A7A7"
        }
        
        # 设置显示文本，不添加图标前缀
        if action_type == "motor":
            display_text = "电机控制 - " + name
        elif action_type == "valve_open":
            display_text = "开启 - " + name
        elif action_type == "valve_close":
            display_text = "关闭 - " + name
        elif action_type == "ignition_on":
            display_text = "点火 - " + name
        elif action_type == "ignition_off":
            display_text = "熄火 - " + name
        elif action_type == "delay":
            display_text = f"延时 ({delay_ms}ms)"
        else:
            display_text = name
            
        self.setText(display_text)
        
        # 设置颜色 - 添加适当的透明度
        if action_type in colors:
            # 创建特定颜色的背景刷，添加透明度
            color = QColor(colors[action_type])
            color.setAlpha(180)  # 设置透明度为180（约70%不透明）
            
            brush = QBrush(color)
            brush.setStyle(Qt.BrushStyle.SolidPattern)
            self.setBackground(brush)
            
            # 强制设置前景色，确保文本清晰可见
            dark_text_brush = QBrush(QColor("#000000"))  # 黑色
            self.setForeground(dark_text_brush)
            
            # 添加字体粗体
            font = QFont()
            font.setBold(True)
            self.setFont(font)
            
            # 设置提示信息
            color_names = {
                "motor": "蓝色 - 电机控制",
                "valve_open": "红色 - 电磁阀控制",
                "valve_close": "红色 - 电磁阀控制",
                "ignition_on": "黄色 - 点火控制",
                "ignition_off": "黄色 - 点火控制",
                "delay": "绿色 - 延时控制"
            }
            self.setToolTip(f"{display_text}\n类型: {color_names.get(action_type, '')}")

from serial_components import SerialManager


class ControlPanel(QWidget):
    """主控制面板，集成电机、阀门和点火控制"""

    def __init__(self, serial_manager, parent=None):
        super().__init__(parent)
        self.serial_manager = serial_manager

        self.init_ui()

        # 连接信号
        self.serial_manager.connected.connect(self.update_control_state)
        self.serial_manager.disconnected.connect(self.update_control_state)
        self.serial_manager.error_occurred.connect(self.update_control_state)
        self.serial_manager.error_occurred.connect(self.log_message)
        self.serial_manager.connected.connect(self._on_serial_connected)
        self.serial_manager.disconnected.connect(self._on_serial_disconnected)
        self.serial_manager.data_received.connect(self._on_data_received)

        # 初始更新控件状态
        self.update_control_state()

        # 初始化电机控制预览
        if hasattr(self, 'speed_slider') and hasattr(self, 'circles_slider'):
            self._update_motor_preview()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(5)

        # 使用分割器，上方是控制面板，下方是日志区域
        splitter = QSplitter(Qt.Orientation.Vertical)

        # 上半部分 - 控制区域
        control_widget = QWidget()
        control_layout = QVBoxLayout(control_widget)
        control_layout.setContentsMargins(5, 5, 5, 5)
        control_layout.setSpacing(5)

        # 状态指示器和紧急停止按钮
        status_bar = QHBoxLayout()

        # 连接状态指示
        self.connection_status = QLabel("串口状态：未连接")
        self.connection_status.setStyleSheet("""
            padding: 5px;
            border-radius: 3px;
            background-color: #E74C3C;
            color: white;
            font-weight: bold;
        """)
        status_bar.addWidget(self.connection_status)

        status_bar.addStretch(1)  # 弹性间隔

        # 紧急停止按钮
        emergency_btn = QPushButton("紧急停止")
        emergency_btn.setMinimumSize(120, 40)
        emergency_btn.setStyleSheet("""
            background-color: #E74C3C;
            color: white;
            font-weight: bold;
            font-size: 14px;
        """)
        emergency_btn.clicked.connect(self._send_emergency_stop)
        emergency_btn.setToolTip("将发送命令: 0xEE000000000000000000 (强制停止)\n执行完整灭火序列，分批关闭所有设备")  # 更新工具提示
        status_bar.addWidget(emergency_btn)

        control_layout.addLayout(status_bar)

        # 创建统一的控制界面（三列布局）
        unified_control_layout = QHBoxLayout()
        unified_control_layout.setSpacing(8)
        unified_control_layout.setContentsMargins(0, 0, 0, 0)

        # 1. 在左侧添加弹簧
        unified_control_layout.addStretch(1)

        # 2. 中列 - 电磁阀控制 (将拉伸系数从 1 改为 3 或 4，使其更宽大)
        valve_control = self._create_valve_control_section()
        if valve_control:
            unified_control_layout.addWidget(valve_control, 7) 
        
        # (点火控制保持注释状态...)
        
        # 3. 在右侧添加弹簧
        unified_control_layout.addStretch(1)

        
        # 中列 - 电磁阀控制
        #valve_control = self._create_valve_control_section()
        #if valve_control:
        #    unified_control_layout.addWidget(valve_control, 1)
        
        # 右列 - 点火控制
        #ignition_control = self._create_ignition_control_section()
        #if ignition_control:
        #    unified_control_layout.addWidget(ignition_control, 1)

        # 补充一个占位弹簧，维持原有的视觉比例，防止电磁阀框过度拉伸
        #unified_control_layout.addStretch(1)
        # ==========================================

        control_layout.addLayout(unified_control_layout)

        # 下半部分 - 日志区域
        self.log_widget = QWidget()
        log_layout = QVBoxLayout(self.log_widget)

        log_header = QHBoxLayout()
        log_label = QLabel("通信日志")
        log_label.setStyleSheet("font-weight: bold;")
        log_header.addWidget(log_label)

        log_header.addStretch()

        clear_log_btn = QPushButton("清空日志")
        clear_log_btn.clicked.connect(self.clear_log)
        log_header.addWidget(clear_log_btn)

        log_layout.addLayout(log_header)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("""
            background-color: #2C3E50;
            color: #ECF0F1;
            border-radius: 3px;
        """)
        log_layout.addWidget(self.log_text)

        # 将两个部件添加到分割器
        splitter.addWidget(control_widget)
        splitter.addWidget(self.log_widget)

        # 设置初始大小比例（控制区域占50%，日志区域占50%）
        splitter.setSizes([500, 500])

        main_layout.addWidget(splitter)

    def _create_valve_control_section(self):
        """创建电磁阀控制区域"""
        valve_group = QGroupBox("电磁阀控制")
        valve_group.setMinimumWidth(180)
        valve_group.setMinimumHeight(220)
        valve_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 13px;
                border: 2px solid #E74C3C;
                border-radius: 6px;
                margin-top: 8px;
                padding-top: 8px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px;
                color: #E74C3C;
            }
        """)
        valve_layout = QVBoxLayout(valve_group)
        valve_layout.setContentsMargins(8, 12, 8, 8)
        valve_layout.setSpacing(8)  # 增加组件间距

        # 电磁阀控制按钮
        self.valve_buttons = {}
        valve_data = {
            1: {"id": "1", "valve_id": 0x01, "name": "小火炬丙烷通断阀"},
            2: {"id": "2", "valve_id": 0x02, "name": "小火炬氧气通断阀"},
            3: {"id": "3", "valve_id": 0x03, "name": "乙醇通断阀"},
            4: {"id": "4", "valve_id": 0x04, "name": "液氧通断阀"},
            5: {"id": "5", "valve_id": 0x05, "name": "吹扫阀"},
            6: {"id": "6", "valve_id": 0x06, "name": "乙醇加压通断阀"},
            7: {"id": "7", "valve_id": 0x07, "name": "液氧加压通断阀"},
            8: {"id": "8", "valve_id": 0x08, "name": "火花塞"}


        }

        # 阀门控制区域 - 直接显示，无滚动
        valve_grid = QGridLayout()
        valve_grid.setSpacing(8)  # 增加间距
        valve_grid.setContentsMargins(2, 2, 2, 2)

        # 添加表头
        valve_grid.addWidget(QLabel("<b>阀门</b>"), 0, 0)
        valve_grid.addWidget(QLabel("<b>状态</b>"), 0, 1)
        valve_grid.addWidget(QLabel("<b>操作</b>"), 0, 2, 1, 2)

        row = 1
        valve_ids = [1, 2, 3, 4, 5, 6,7,8]
        for i in valve_ids:
            # 阀门名称（简化）
            #name_parts = valve_data[i]["name"].split("通断阀")
            #short_name = name_parts[0] if name_parts else valve_data[i]["name"]
            # 进一步简化名称
            #if "小火炬" in short_name:
            #    short_name = short_name.replace("小火炬", "小")
            #if "燃烧室" in short_name:
            #    short_name = short_name.replace("燃烧室", "室")
            
            #valve_label = QLabel(short_name)
            #valve_label.setStyleSheet("font-size: 9px; font-weight: bold;")
            # 直接使用字典中的完整名称
            valve_label = QLabel(valve_data[i]["name"])
            
            # 适当调大一点字体以适应全称，保持加粗
            valve_label.setStyleSheet("font-size: 11px; font-weight: bold;")
            valve_label.setWordWrap(True)  # 允许换行
            valve_grid.addWidget(valve_label, row, 0)

            # 状态指示
            status_label = QLabel("关")
            status_label.setStyleSheet("""
                color: white;
                background-color: #E74C3C;
                border-radius: 2px;
                padding: 2px;
                font-size: 9px;
                min-width: 20px;
                text-align: center;
            """)
            status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            valve_grid.addWidget(status_label, row, 1)

            # 操作按钮
            open_btn = QPushButton("开")
            close_btn = QPushButton("关")
            for btn in [open_btn, close_btn]:
                btn.setMinimumSize(40, 30)  # 调整按钮尺寸
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #3498DB;
                        color: white;
                        border: none;
                        border-radius: 4px;
                        font-size: 10px;
                        font-weight: bold;
                        padding: 3px;
                        margin: 3px;
                    }
                    QPushButton:hover {
                        background-color: #2980B9;
                    }
                """)

            # 使用functools.partial避免lambda闭包问题
            from functools import partial
            open_btn.clicked.connect(partial(self._handle_valve_open, i, valve_data[i]["valve_id"], status_label))
            close_btn.clicked.connect(partial(self._handle_valve_close, i, valve_data[i]["valve_id"], status_label))

            valve_grid.addWidget(open_btn, row, 2)
            valve_grid.addWidget(close_btn, row, 3)

            # 保存按钮引用
            self.valve_buttons[i] = {
                "open": open_btn,
                "close": close_btn,
                "status": status_label
            }

            row += 1

        valve_layout.addLayout(valve_grid)

        # 批量控制
        bulk_layout = QHBoxLayout()
        bulk_layout.setSpacing(8)
        open_all_btn = QPushButton("全开")
        close_all_btn = QPushButton("全关")
        for btn in [open_all_btn, close_all_btn]:
            btn.setMinimumHeight(35)  # 设置最小高度
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #3498DB;
                    color: white;
                    font-weight: bold;
                    padding: 8px;
                    border: none;
                    border-radius: 5px;
                    font-size: 12px;
                    margin: 3px;
                }
                QPushButton:hover {
                    background-color: #2980B9;
                }
            """)
        
        open_all_btn.clicked.connect(self._open_all_valves)
        close_all_btn.clicked.connect(self._close_all_valves)
        bulk_layout.addWidget(open_all_btn)
        bulk_layout.addWidget(close_all_btn)
        valve_layout.addLayout(bulk_layout)

        self.bulk_buttons = [open_all_btn, close_all_btn]

        return valve_group

    def _create_ignition_control_section(self):
        """创建点火控制区域"""
        ignition_group = QGroupBox("点火控制")
        ignition_group.setMinimumWidth(180)
        ignition_group.setMinimumHeight(220)
        ignition_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 13px;
                border: 2px solid #F39C12;
                border-radius: 6px;
                margin-top: 8px;
                padding-top: 8px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px;
                color: #F39C12;
            }
        """)
        ignition_layout = QVBoxLayout(ignition_group)
        ignition_layout.setContentsMargins(8, 12, 8, 8)
        ignition_layout.setSpacing(8)  # 增加组件间距

        # 基本点火控制
        basic_layout = QHBoxLayout()
        self.fire_on_btn = QPushButton("🔥 点火")
        self.fire_off_btn = QPushButton("❄️ 关火")
        
        for btn in [self.fire_on_btn, self.fire_off_btn]:
            btn.setMinimumSize(90, 55)  # 进一步增大按钮尺寸
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #E74C3C;
                    color: white;
                    font-weight: bold;
                    font-size: 13px;
                    border: none;
                    border-radius: 6px;
                    margin: 3px;
                    padding: 5px;
                }
                QPushButton:hover {
                    background-color: #C0392B;
                }
            """)
        
        self.fire_off_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498DB;
                color: white;
                font-weight: bold;
                font-size: 13px;
                border: none;
                border-radius: 6px;
                margin: 3px;
                padding: 5px;
            }
            QPushButton:hover {
                background-color: #2980B9;
            }
        """)

        self.fire_on_btn.clicked.connect(self._handle_fire_on)
        self.fire_off_btn.clicked.connect(self._handle_fire_off)
        
        basic_layout.addWidget(self.fire_on_btn)
        basic_layout.addWidget(self.fire_off_btn)
        ignition_layout.addLayout(basic_layout)

        # 高级点火控制
        advanced_layout = QVBoxLayout()
        advanced_layout.setSpacing(5)  # 增加间距
        advanced_layout.addWidget(QLabel("高级模式:"))
        
        self.advanced_buttons = {}
        ignition_data = [
            {"text": "避险程序", "code": 0x22, "icon": "🛡️"},
            {"text": "同步点火", "code": 0x24, "icon": "🔄"},
            {"text": "分段点火", "code": 0x25, "icon": "⏱️"}
        ]

        for item in ignition_data:
            btn = QPushButton(f"{item['icon']} {item['text']}")
            btn.setMinimumSize(120, 40)  # 调整按钮尺寸适应较小框架
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #3498DB;
                    color: white;
                    font-weight: bold;
                    font-size: 12px;
                    border: none;
                    border-radius: 5px;
                    padding: 6px;
                    margin: 3px;
                }
                QPushButton:hover {
                    background-color: #2980B9;
                }
            """)
            # 使用functools.partial避免lambda闭包问题
            from functools import partial
            btn.clicked.connect(partial(self._handle_advanced_ignition, item["code"], item["text"]))
            
            advanced_layout.addWidget(btn)
            self.advanced_buttons[item["text"]] = btn

        ignition_layout.addLayout(advanced_layout)

        return ignition_group

    def log_message(self, message):
        """记录消息到日志窗口"""
        # 获取当前时间
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")

        # 添加带时间戳的消息
        formatted_message = "[{}] {}".format(timestamp, message)
        self.log_text.append(formatted_message)

        # 滚动到底部
        sb = self.log_text.verticalScrollBar()
        sb.setValue(sb.maximum())

    def clear_log(self):
        """清空日志窗口"""
        self.log_text.clear()

    def _on_serial_connected(self, port, baud):
        """串口连接成功回调"""
        self.log_message("已连接到串口 {} (波特率: {})".format(port, baud))

    def _on_serial_disconnected(self):
        """串口断开连接回调"""
        self.log_message("串口已断开连接")

    def _on_data_received(self, data):
        """接收到数据回调"""
        self.log_message("接收: {}".format(data.hex().upper()))

    def _handle_valve_open(self, valve_id, valve_hw_id, status_label):
        """处理阀门打开"""
        self._send_valve_command(valve_id, valve_hw_id, status_label, True)

    def _handle_valve_close(self, valve_id, valve_hw_id, status_label):
        """处理阀门关闭"""
        self._send_valve_command(valve_id, valve_hw_id, status_label, False)

    def _handle_fire_on(self):
        """处理点火开启"""
        self._send_ignition_command(0x21, "开启点火")

    def _handle_fire_off(self):
        """处理点火关闭"""
        self._send_ignition_command(0x20, "关闭点火")

    def _handle_advanced_ignition(self, code, text):
        """处理高级点火功能"""
        self._send_ignition_command(code, text)

    def update_control_state(self):
        """更新控件状态"""
        if self.serial_manager.is_connected():
            self.connection_status.setText("串口状态：已连接")
            self.connection_status.setStyleSheet("""
                padding: 5px;
                border-radius: 3px;
                background-color: #27AE60;  /* 绿色 */
                color: white;
                font-weight: bold;
            """)
        else:
            self.connection_status.setText("串口状态：未连接")
            self.connection_status.setStyleSheet("""
                padding: 5px;
                border-radius: 3px;
                background-color: #E74C3C;  /* 红色 */
                color: white;
                font-weight: bold;
            """)

        # 更新合并后界面的控件状态
        enabled = self.serial_manager.is_connected()
        self._update_valve_controls(enabled)
        self._update_ignition_controls(enabled)
        
    def _update_valve_controls(self, enabled):
        """更新电磁阀控制状态"""
        if hasattr(self, 'valve_buttons'):
            for i in self.valve_buttons:
                self.valve_buttons[i]["open"].setEnabled(enabled)
                self.valve_buttons[i]["close"].setEnabled(enabled)
            
            for btn in self.bulk_buttons:
                btn.setEnabled(enabled)

    def _update_ignition_controls(self, enabled):
        """更新点火控制状态"""
        if hasattr(self, 'fire_on_btn'):
            self.fire_on_btn.setEnabled(enabled)
            self.fire_off_btn.setEnabled(enabled)

            for btn_name in self.advanced_buttons:
                self.advanced_buttons[btn_name].setEnabled(enabled)
    # 电磁阀控制相关方法
    def _send_valve_command(self, valve_id, valve_hw_id, status_label, is_open):
        """发送电磁阀控制命令 - 按新协议格式"""
        if not self.serial_manager.is_connected():
            self.log_message("错误: 串口未连接，无法发送命令")
            return

        # 按新协议: 0xBB + valve_id + valve_state + 保留字节(7字节)
        valve_state = 0x01 if is_open else 0x00
        command = bytes([0xBB, valve_hw_id, valve_state] + [0x00] * 7)

        if self.serial_manager.send_data(command):
            # 更新UI状态
            if is_open:
                status_label.setText("开")
                status_label.setStyleSheet("""
                    color: white;
                    background-color: #27AE60;
                    border-radius: 2px;
                    padding: 2px;
                    font-size: 9px;
                    min-width: 20px;
                    text-align: center;
                """)
                self.log_message("已发送: 打开电磁阀{}命令 (0x{})".format(valve_id, command.hex().upper()))
            else:
                status_label.setText("关")
                status_label.setStyleSheet("""
                    color: white;
                    background-color: #E74C3C;
                    border-radius: 2px;
                    padding: 2px;
                    font-size: 9px;
                    min-width: 20px;
                    text-align: center;
                """)
                self.log_message("已发送: 关闭电磁阀{}命令 (0x{})".format(valve_id, command.hex().upper()))
        else:
            self.log_message("发送失败: 电磁阀{}控制命令".format(valve_id))

    def _open_all_valves(self):
        """打开所有电磁阀 - 使用批量命令"""
        if not self.serial_manager.is_connected():
            self._log_task("错误: 串口未连接")
            return

        # 批量命令：0xBB + 0xFF(所有阀门) + 0x01(打开) + 保留字节
        command = bytes([0xBB, 0xFF, 0x01] + [0x00] * 7)
        
        if self.serial_manager.send_data(command):
            self._log_task("已发送: 打开所有电磁阀 (批量命令)")
            # 更新所有阀门的状态显示
            for hw_id in [0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08]:
                self._update_valve_status(hw_id, True)
        else:
            self._log_task("发送失败: 打开所有电磁阀")

    def _close_all_valves(self):
        """关闭所有电磁阀 - 使用批量命令"""
        if not self.serial_manager.is_connected():
            self._log_task("错误: 串口未连接")
            return

        # 批量命令：0xBB + 0xFF(所有阀门) + 0x00(关闭) + 保留字节
        command = bytes([0xBB, 0xFF, 0x00] + [0x00] * 7)
        
        if self.serial_manager.send_data(command):
            self._log_task("已发送: 关闭所有电磁阀 (批量命令)")
            # 更新所有阀门的状态显示
            for hw_id in [0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08]:
                self._update_valve_status(hw_id, False)
        else:
            self._log_task("发送失败: 关闭所有电磁阀")

    # 点火控制相关方法
    def _send_ignition_command(self, value_byte, operation_name):
        """发送点火控制命令 - 按新协议格式"""
        if not self.serial_manager.is_connected():
            self.log_message("错误: 串口未连接，无法发送命令")
            return

        # 点火命令按新协议: 0xCC + ignition_cmd + 保留字节(8字节)
        command = bytes([0xCC, value_byte] + [0x00] * 8)

        if self.serial_manager.send_data(command):
            self.log_message("已发送: 点火控制命令 \"{}\" (0x{})".format(operation_name, command.hex().upper()))
        else:
            self.log_message("发送失败: 点火控制命令 \"{}\"".format(operation_name))

    def _send_emergency_stop(self):
        """发送强制停止命令(灭火序列)"""
        if not self.serial_manager.is_connected():
            self.log_message("错误: 串口未连接，无法发送强制停止命令")
            print("❌ 强制停止失败: 串口未连接")
            return

        # 强制停止命令(灭火序列): 0xEE + 保留字节(9字节)
        command = bytes([0xEE] + [0x00] * 9)

        try:
            success = self.serial_manager.send_data(command)
            if success:
                message = "已发送: 强制停止命令(灭火序列) (0x{})".format(command.hex().upper())
                self.log_message(message)
                print(f"✅ {message}")
                # 不使用阻塞性消息框，改为状态栏显示
                if hasattr(self, 'connection_status'):
                    self.connection_status.setText("强制停止命令已发送！")
                    self.connection_status.setStyleSheet("color: red; font-weight: bold;")
                    # 3秒后恢复正常状态显示
                    QTimer.singleShot(3000, self._restore_status_display)
            else:
                message = "发送失败: 强制停止命令 (0x{})".format(command.hex().upper())
                self.log_message(message)
                print(f"❌ {message}")

        except Exception as e:
            error_message = f"强制停止命令发送异常: {e}"
            self.log_message(error_message)
            print(f"❌ {error_message}")
            import traceback
            traceback.print_exc()
    def set_replay_mode(self, enabled):
        """回放模式下禁用所有串口指令按钮 (物理安全锁)"""
        self._update_valve_controls(not enabled)
        self._update_ignition_controls(not enabled)

    def _log_task(self, message):
        """记录任务消息（兼容方法）"""
        self.log_message(message)

    def _update_valve_status(self, hw_id, is_open):
        """更新阀门状态显示"""
        valve_id_map = {
            0x01: 1, 0x02: 2, 0x03: 3, 0x04: 4,
            0x05: 5, 0x06: 6, 0x07: 7, 0x08: 8
        }
        
        valve_id = valve_id_map.get(hw_id)
        if valve_id is not None and valve_id in self.valve_buttons:
            status_label = self.valve_buttons[valve_id]["status"]
            if is_open:
                status_label.setText("开")
                status_label.setStyleSheet("""
                    color: white;
                    background-color: #27AE60;
                    border-radius: 2px;
                    padding: 2px;
                    font-size: 9px;
                    min-width: 20px;
                    text-align: center;
                """)
            else:
                status_label.setText("关")
                status_label.setStyleSheet("""
                    color: white;
                    background-color: #E74C3C;
                    border-radius: 2px;
                    padding: 2px;
                    font-size: 9px;
                    min-width: 20px;
                    text-align: center;
                """)

    def _restore_status_display(self):
        """恢复状态显示"""
        if hasattr(self, 'connection_status'):
            if self.serial_manager.is_connected():
                self.connection_status.setText("串口状态：已连接")
                self.connection_status.setStyleSheet("color: green; font-weight: bold;")
            else:
                self.connection_status.setText("串口状态：未连接")
                self.connection_status.setStyleSheet("color: red; font-weight: bold;")



class ValveControlTab(QWidget):
    """电磁阀控制选项卡"""
    command_sent = Signal(str)  # 信号：发送了命令的消息

    def __init__(self, serial_manager, parent=None):
        super().__init__(parent)
        self.serial_manager = serial_manager
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)

        # 电磁阀控制组
        valve_group = QGroupBox("电磁阀控制")
        valve_layout = QGridLayout(valve_group)

        # 电磁阀控制按钮
        self.valve_buttons = {}

        valve_data = {
            1: {"id": "1", "valve_id": 0x01, "name": "小火炬乙醇通断阀"},
            2: {"id": "2", "valve_id": 0x02, "name": "小火炬氧气通断阀"},
            3: {"id": "3", "valve_id": 0x03, "name": "燃烧室乙醇通断阀"},
            4: {"id": "4", "valve_id": 0x04, "name": "燃烧室氧气通断阀"},
            5: {"id": "5", "valve_id": 0x05, "name": "氮气通断阀"},
            6: {"id": "6", "valve_id": 0x06, "name": "水泵"},
            7: {"id": "7", "valve_id": 0x07, "name": "灭火通断阀"},
            8: {"id": "8", "valve_id": 0x08, "name": "火花塞"}
        }

        # 添加标签行
        valve_layout.addWidget(QLabel("电磁阀"), 0, 0)
        valve_layout.addWidget(QLabel("状态"), 0, 1)
        valve_layout.addWidget(QLabel("操作"), 0, 2)

        row = 1
        valve_ids = [1, 2, 3, 4, 5,6, 7,8]  # 按新协议的阀门ID
        for i in valve_ids:
            # 电磁阀标签
            valve_label = QLabel("{}".format(valve_data[i]["name"]))
            valve_label.setStyleSheet("font-weight: bold;")
            valve_layout.addWidget(valve_label, row, 0)

            # 状态指示
            status_label = QLabel("关闭")
            status_label.setStyleSheet("""
                color: white;
                background-color: #E74C3C;
                border-radius: 3px;
                padding: 3px;
                min-width: 60px;
                text-align: center;
            """)
            valve_layout.addWidget(status_label, row, 1)

            # 操作按钮
            button_layout = QHBoxLayout()

            open_btn = QPushButton("打开")
            open_btn.clicked.connect(lambda _, valve_id=i, vid=valve_data[i]["valve_id"], status=status_label:
                                     self._send_valve_command(valve_id, vid, status, True))
            # 设置工具提示，按新协议格式
            open_btn.setToolTip("将发送命令: 0xBB{:02X}010000000000000000\n标志位: 0xBB (电磁阀控制)\n阀门ID: 0x{:02X}\n状态: 0x01 (打开)".format(
                valve_data[i]["valve_id"],
                valve_data[i]["valve_id"]
            ))

            close_btn = QPushButton("关闭")
            close_btn.clicked.connect(lambda _, valve_id=i, vid=valve_data[i]["valve_id"], status=status_label:
                                      self._send_valve_command(valve_id, vid, status, False))
            # 设置工具提示，按新协议格式
            close_btn.setToolTip("将发送命令: 0xBB{:02X}000000000000000000\n标志位: 0xBB (电磁阀控制)\n阀门ID: 0x{:02X}\n状态: 0x00 (关闭)".format(
                valve_data[i]["valve_id"],
                valve_data[i]["valve_id"]
            ))

            button_layout.addWidget(open_btn)
            button_layout.addWidget(close_btn)
            valve_layout.addLayout(button_layout, row, 2)

            # 保存按钮引用
            self.valve_buttons[i] = {
                "open": open_btn,
                "close": close_btn,
                "status": status_label
            }

            row += 1

        main_layout.addWidget(valve_group)

        # 批量控制
        bulk_control_group = QGroupBox("批量控制")
        bulk_layout = QHBoxLayout(bulk_control_group)

        open_all_btn = QPushButton("打开所有电磁阀")
        open_all_btn.clicked.connect(self._open_all_valves)
        # 更新批量操作的ToolTip，按新协议格式
        open_all_btn.setToolTip("将依次发送6个命令打开所有电磁阀:\n" +
                                "0xBB01010000000000000000 (小火炬乙醇通断阀)\n" +
                                "0xBB02010000000000000000 (小火炬氧气通断阀)\n" +
                                "0xBB03010000000000000000 (燃烧室乙醇通断阀)\n" +
                                "0xBB04010000000000000000 (燃烧室氧气通断阀)\n" +
                                "0xBB05010000000000000000 (氮气通断阀)\n" +
                                "0xBB07010000000000000000 (灭火通断阀)")
        bulk_layout.addWidget(open_all_btn)

        close_all_btn = QPushButton("关闭所有电磁阀")
        close_all_btn.clicked.connect(self._close_all_valves)
        # 更新批量操作的ToolTip，按新协议格式
        close_all_btn.setToolTip("将依次发送6个命令关闭所有电磁阀:\n" +
                                 "0xBB01000000000000000000 (小火炬乙醇通断阀)\n" +
                                 "0xBB02000000000000000000 (小火炬氧气通断阀)\n" +
                                 "0xBB03000000000000000000 (燃烧室乙醇通断阀)\n" +
                                 "0xBB04000000000000000000 (燃烧室氧气通断阀)\n" +
                                 "0xBB05000000000000000000 (氮气通断阀)\n" +
                                 "0xBB07000000000000000000 (灭火通断阀)")
        bulk_layout.addWidget(close_all_btn)

        self.bulk_buttons = [open_all_btn, close_all_btn]

        main_layout.addWidget(bulk_control_group)
        main_layout.addStretch()

    def update_control_state(self):
        """更新界面控件状态"""
        enabled = self.serial_manager.is_connected()

        for i in self.valve_buttons:
            self.valve_buttons[i]["open"].setEnabled(enabled)
            self.valve_buttons[i]["close"].setEnabled(enabled)

        for btn in self.bulk_buttons:
            btn.setEnabled(enabled)

    def _send_valve_command(self, valve_id, valve_hw_id, status_label, is_open):
        """发送电磁阀控制命令 - 按新协议格式"""
        if not self.serial_manager.is_connected():
            self.command_sent.emit("错误: 串口未连接，无法发送命令")
            return

        # 按新协议: 0xBB + valve_id + valve_state + 保留字节(7字节)
        valve_state = 0x01 if is_open else 0x00
        command = bytes([0xBB, valve_hw_id, valve_state] + [0x00] * 7)

        if self.serial_manager.send_data(command):
            # 更新UI状态
            if is_open:
                status_label.setText("打开")
                status_label.setStyleSheet("""
                    color: white;
                    background-color: #27AE60;
                    border-radius: 3px;
                    padding: 3px;
                    min-width: 60px;
                    text-align: center;
                """)
                self.command_sent.emit("已发送: 打开电磁阀{}命令 (0x{})".format(valve_id, command.hex().upper()))
            else:
                status_label.setText("关闭")
                status_label.setStyleSheet("""
                    color: white;
                    background-color: #E74C3C;
                    border-radius: 3px;
                    padding: 3px;
                    min-width: 60px;
                    text-align: center;
                """)
                self.command_sent.emit("已发送: 关闭电磁阀{}命令 (0x{})".format(valve_id, command.hex().upper()))
        else:
            self.command_sent.emit("发送失败: 电磁阀{}控制命令".format(valve_id))

    def _open_all_valves(self):
        if not self.serial_manager.is_connected():
            self._log_task("错误: 串口未连接")
            return

        # 批量命令：0xBB + 0xFF(所有阀门) + 0x01(打开) + 保留字节
        command = bytes([0xBB, 0xFF, 0x01] + [0x00] * 7)
        
        if self.serial_manager.send_data(command):
            self._log_task("已发送: 打开所有电磁阀 (批量命令)")
            # 更新所有阀门的状态显示
            for hw_id in [0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08]:
                self._update_valve_status(hw_id, True)
        else:
            self._log_task("发送失败: 打开所有电磁阀")

    def _close_all_valves(self):
        if not self.serial_manager.is_connected():
            self._log_task("错误: 串口未连接")
            return

        # 批量命令：0xBB + 0xFF(所有阀门) + 0x00(关闭) + 保留字节
        command = bytes([0xBB, 0xFF, 0x00] + [0x00] * 7)
        
        if self.serial_manager.send_data(command):
            self._log_task("已发送: 关闭所有电磁阀 (批量命令)")
            # 更新所有阀门的状态显示
            for hw_id in [0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08]:
                self._update_valve_status(hw_id, False)
        else:
            self._log_task("发送失败: 关闭所有电磁阀")

class IgnitionControlTab(QWidget):
    """点火控制选项卡"""
    command_sent = Signal(str)  # 信号：发送了命令的消息

    def __init__(self, serial_manager, parent=None):
        super().__init__(parent)
        self.serial_manager = serial_manager
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(12, 15, 12, 15)

        # 基本点火控制
        basic_group = QGroupBox("基本点火控制")
        basic_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 14px;
                border: 2px solid #F39C12;
                border-radius: 8px;
                margin-top: 12px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
                color: #F39C12;
            }
        """)
        basic_layout = QHBoxLayout(basic_group)
        basic_layout.setSpacing(20)
        basic_layout.setContentsMargins(15, 20, 15, 15)

        # 点火按钮 - 突出显示
        self.fire_on_btn = QPushButton("🔥 开启点火")
        self.fire_on_btn.setMinimumSize(140, 70)
        self.fire_on_btn.setStyleSheet("""
            QPushButton {
                background-color: #E74C3C;
                color: white;
                font-weight: bold;
                font-size: 16px;
                border: none;
                border-radius: 8px;
            }
            QPushButton:hover {
                background-color: #C0392B;
            }
            QPushButton:pressed {
                background-color: #A93226;
            }
            QPushButton:disabled {
                background-color: #D5D8DC;
                color: #7F8C8D;
            }
        """)
        self.fire_on_btn.clicked.connect(lambda: self._send_ignition_command(0x21, "开启点火"))
        self.fire_on_btn.setToolTip("将发送命令: 0xCC210000000000000000\n标志位: 0xCC (点火控制)\n操作: 0x21 (开启点火)")
        basic_layout.addWidget(self.fire_on_btn)

        # 关闭点火按钮
        self.fire_off_btn = QPushButton("❄️ 关闭点火")
        self.fire_off_btn.setMinimumSize(140, 70)
        self.fire_off_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498DB;
                color: white;
                font-weight: bold;
                font-size: 16px;
                border: none;
                border-radius: 8px;
            }
            QPushButton:hover {
                background-color: #2980B9;
            }
            QPushButton:pressed {
                background-color: #2471A3;
            }
            QPushButton:disabled {
                background-color: #D5D8DC;
                color: #7F8C8D;
            }
        """)
        self.fire_off_btn.clicked.connect(lambda: self._send_ignition_command(0x20, "关闭点火"))
        self.fire_off_btn.setToolTip("将发送命令: 0xCC200000000000000000\n标志位: 0xCC (点火控制)\n操作: 0x20 (关闭点火)")
        basic_layout.addWidget(self.fire_off_btn)

        main_layout.addWidget(basic_group)

        # 高级点火控制
        advanced_group = QGroupBox("高级点火控制")
        advanced_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 14px;
                border: 2px solid #9B59B6;
                border-radius: 8px;
                margin-top: 12px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
                color: #9B59B6;
            }
        """)
        advanced_layout = QGridLayout(advanced_group)
        advanced_layout.setSpacing(15)
        advanced_layout.setContentsMargins(15, 20, 15, 15)

        # 高级功能按钮
        self.advanced_buttons = {}

        # 统一按钮颜色为3498DB（蓝色）- 与关闭点火按钮一致
        button_color = "#3498DB"

        ignition_data = [
            {"text": "避险程序", "code": 0x22, "icon": "🛡️", "desc": "紧急关闭氧气供应"},
            {"text": "同步点火", "code": 0x24, "icon": "🔄", "desc": "执行同步点火时序（燃烧自持工况）"},
            {"text": "分段点火", "code": 0x25, "icon": "⏱️", "desc": "执行分段点火时序（燃烧自持工况）"}
        ]

        for i, item in enumerate(ignition_data):
            btn = QPushButton(f"{item['icon']} {item['text']}")
            btn.setMinimumSize(120, 60)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {button_color};
                    color: white;
                    font-weight: bold;
                    font-size: 14px;
                    border: none;
                    border-radius: 6px;
                }}
                QPushButton:hover {{
                    background-color: #2980B9;
                }}
                QPushButton:pressed {{
                    background-color: #2471A3;
                }}
                QPushButton:disabled {{
                    background-color: #D5D8DC;
                    color: #7F8C8D;
                }}
            """)
            btn.clicked.connect(lambda _, code=item["code"], text=item["text"]:
                               self._send_ignition_command(code, text))

            # 设置工具提示，按新协议格式，并填充为10字节
            btn.setToolTip("将发送命令: 0xCC{:02X}000000000000000000\n标志位: 0xCC (点火控制)\n操作: 0x{:02X} ({})\n功能: {}".format(
                item["code"], item["code"], item["text"], item["desc"]))

            row = i // 3
            col = i % 3
            advanced_layout.addWidget(btn, row, col)
            self.advanced_buttons[item["text"]] = btn

        main_layout.addWidget(advanced_group)
        main_layout.addStretch()

    def update_control_state(self):
        """更新界面控件状态"""
        enabled = self.serial_manager.is_connected()

        self.fire_on_btn.setEnabled(enabled)
        self.fire_off_btn.setEnabled(enabled)

        for btn_name in self.advanced_buttons:
            self.advanced_buttons[btn_name].setEnabled(enabled)

    def _send_ignition_command(self, value_byte, operation_name):
        """发送点火控制命令 - 按新协议格式"""
        if not self.serial_manager.is_connected():
            self.command_sent.emit("错误: 串口未连接，无法发送命令")
            return

        # 点火命令按新协议: 0xCC + ignition_cmd + 保留字节(8字节)
        command = bytes([0xCC, value_byte] + [0x00] * 8)

        if self.serial_manager.send_data(command):
            self.command_sent.emit("已发送: 点火控制命令 \"{}\" (0x{})".format(operation_name, command.hex().upper()))
        else:
            self.command_sent.emit("发送失败: 点火控制命令 \"{}\"".format(operation_name))


class RocketControlConsole(QWidget):
    """火箭控制台 - 集成所有控制功能"""
    command_sent = Signal(str)

    # ── HMI 桥接信号 ──────────────────────────────────────────────
    sequence_valve_changed = Signal(str, bool)             # (hmi_valve_name, is_open)
    sequence_timeline_update = Signal(float, str, float)   # (elapsed_s, desc, total_duration_s)

    # HW 阀门 ID → HMI 阀门名映射
    HW_ID_TO_HMI_VALVE = {
        0x01: "XV-401",   # 小火炬丙烷通断阀
        0x02: "XV-402",   # 小火炬氧气通断阀
        0x03: "XV-104",   # 乙醇通断阀
        0x04: "XV-205",   # 液氧通断阀
        0x05: "XV-302",   # 吹扫阀
        0x06: "XV-102",   # 乙醇加压通断阀
        0x07: "XV-202",   # 液氧加压通断阀
    }

    def __init__(self, serial_manager, parent=None):
        super().__init__(parent)
        self.serial_manager = serial_manager
        self.sequence_manager = SequenceManager()
        self.sequence_running = False
        self.sequence_timer = None
        self._seq_elapsed = 0.0          # 序列执行已用时间 (秒)
        self._seq_total_duration = 0.0   # 序列总时长 (秒)
        self._seq_current_desc = ""      # 当前步骤描述
        self._seq_timer = QTimer(self)   # 50ms 时间轴平滑计时器
        self._seq_timer.timeout.connect(self._on_seq_timer_tick)
        self.init_ui()

    def init_ui(self):
        from PySide6.QtWidgets import QSizePolicy, QListWidget, QListWidgetItem
        from PySide6.QtCore import QMimeData, Qt
        from PySide6.QtGui import QDrag
 
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(15, 15, 15, 15)

        # 控制区域
        control_layout = QHBoxLayout()
        control_layout.setSpacing(15)
        
        # 颜色定义
        button_color = "#3498DB"
        hover_color = "#2980B9"
        pressed_color = "#2471A3"

        # =====电磁阀控制 =====
        valve_group = QGroupBox("电磁阀控制")
        valve_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 14px;
                border: 2px solid #E74C3C;
                border-radius: 2px;
                margin-top: 2px;
                padding-top: 2px;
                                
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
                color: #E74C3C;
            }
        """)
        valve_layout = QVBoxLayout(valve_group)
        valve_layout.setContentsMargins(15, 20, 15, 15)

        # 电磁阀控制按钮
        self.valve_buttons = {}
        valve_names = ["小火炬丙烷通断阀", "小火炬氧气通断阀", "乙醇通断阀", 
                       "液氧通断阀", "吹扫阀", "乙醇加压通断阀", "液氧加压通断阀", "火花塞"]
        valve_hw_ids = [0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08]

        valve_btn_style = f"""
            QPushButton {{
                padding: 10px 10px;
                border-radius: 10px;
                font-weight: bold;
                font-size: 11px;
                min-width: 50px;
                min-height: 20px;      # 增加最小高度
                background-color: {button_color};
                color: white;
            }}
            QPushButton:hover {{
                background-color: {hover_color};
            }}
            QPushButton:pressed {{
                background-color: {pressed_color};
            }}
        """

        valve_grid = QGridLayout()
        valve_grid.setSpacing(8)
        valve_grid.addWidget(QLabel("<b>阀门名称</b>"), 0, 0)
        valve_grid.addWidget(QLabel("<b>状态</b>"), 0, 1)
        valve_grid.addWidget(QLabel("<b>添加到序列</b>"), 0, 2, 1, 2)

        for i, (name, hw_id) in enumerate(zip(valve_names, valve_hw_ids)):
            row = i + 1
            valve_label = QLabel(name)
            valve_label.setStyleSheet("font-weight: bold; font-size: 10px;")
            valve_label.setWordWrap(True)
            valve_grid.addWidget(valve_label, row, 0)

            status_label = QLabel("关闭")
            status_label.setStyleSheet("""
                color: white;
                background-color: #E74C3C;
                border-radius: 3px;
                padding: 3px;
                min-width: 50px;
                text-align: center;
            """)
            status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            valve_grid.addWidget(status_label, row, 1)

            open_btn = QPushButton("添加-开")
            open_btn.setStyleSheet(valve_btn_style)
            open_btn.clicked.connect(lambda _, v_id=hw_id, v_name=name: 
                                     self._add_valve_sequence(v_id, v_name, True))
            open_btn.setToolTip(f"{name}打开命令:\n0xBB{hw_id:02X}010000000000000000")

            close_btn = QPushButton("添加-关")
            close_btn.setStyleSheet(valve_btn_style)
            close_btn.clicked.connect(lambda _, v_id=hw_id, v_name=name: 
                                      self._add_valve_sequence(v_id, v_name, False))
            close_btn.setToolTip(f"{name}关闭命令:\n0xBB{hw_id:02X}000000000000000000")

            valve_grid.addWidget(open_btn, row, 2)
            valve_grid.addWidget(close_btn, row, 3)

            self.valve_buttons[hw_id] = {
                "name": name,
                "status": status_label,
                "open_btn": open_btn,
                "close_btn": close_btn
            }

        valve_layout.addLayout(valve_grid)

        # 电磁阀批量控制
        valve_bulk_layout = QHBoxLayout()
        self.valve_all_open_btn = QPushButton("添加到序列 - 全部打开")
        self.valve_all_close_btn = QPushButton("添加到序列 - 全部关闭")
        self.valve_all_open_btn.setStyleSheet(valve_btn_style)
        self.valve_all_close_btn.setStyleSheet(valve_btn_style)
        self.valve_all_open_btn.clicked.connect(self._add_all_valves_open_sequence)
        self.valve_all_close_btn.clicked.connect(self._add_all_valves_close_sequence)


        valve_bulk_layout.addWidget(self.valve_all_open_btn)
        valve_bulk_layout.addWidget(self.valve_all_close_btn)
        valve_layout.addLayout(valve_bulk_layout)
        control_layout.addWidget(valve_group)

        # ===== 右列 - 点火控制 =====
        ignition_group = QGroupBox("点火控制")
        ignition_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 14px;
                border: 2px solid #F39C12;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
                color: #F39C12;
            }
        """)
        ignition_layout = QVBoxLayout(ignition_group)
        ignition_layout.setContentsMargins(15, 20, 15, 15)

        # 点火状态标签
        self.ignition_status = QLabel("未点火")
        self.ignition_status.setStyleSheet("""
            color: white;
            background-color: #E74C3C;
            border-radius: 3px;
            padding: 5px;
            font-weight: bold;
            text-align: center;
        """)
        self.ignition_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ignition_layout.addWidget(self.ignition_status)

        sequence_btn_style = f"""
            QPushButton {{
                background-color: {button_color};
                color: white;
                border: none;
                border-radius: 6px;
                font-weight: bold;
                font-size: 12px;
                padding: 8px;
                margin: 3px;
            }}
            QPushButton:hover {{
                background-color: {hover_color};
            }}
            QPushButton:disabled {{
                background-color: #BDC3C7;
                color: #7F8C8D;
            }}
        """

        self.add_ignition_on_btn = QPushButton("添加到序列 - 点火")
        self.add_ignition_on_btn.setStyleSheet(sequence_btn_style)
        self.add_ignition_on_btn.setToolTip("点火命令:\n0xCC210000000000000000")
        self.add_ignition_on_btn.clicked.connect(lambda: self._add_ignition_sequence(True))
        ignition_layout.addWidget(self.add_ignition_on_btn)

        self.add_ignition_off_btn = QPushButton("添加到序列 - 关火")
        self.add_ignition_off_btn.setStyleSheet(sequence_btn_style)
        self.add_ignition_off_btn.setToolTip("关火命令:\n0xCC200000000000000000")
        self.add_ignition_off_btn.clicked.connect(lambda: self._add_ignition_sequence(False))
        ignition_layout.addWidget(self.add_ignition_off_btn)

        # 延时控制
        ignition_layout.addWidget(QLabel("延时控制:"))
        delay_layout = QHBoxLayout()
        self.delay_spinbox = QSpinBox()
        self.delay_spinbox.setRange(100, 60000)
        self.delay_spinbox.setValue(1000)
        self.delay_spinbox.setSuffix(" ms")
        self.delay_spinbox.setStyleSheet("""
            QSpinBox {
                border: 1px solid #BDC3C7;
                border-radius: 4px;
                padding: 5px;
                background: white;
                min-width: 100px;
            }
        """)
        self.add_delay_btn = QPushButton("添加延时到序列")
        self.add_delay_btn.setStyleSheet(sequence_btn_style)
        self.add_delay_btn.clicked.connect(self._add_custom_delay_sequence)

        delay_layout.addWidget(self.delay_spinbox)
        delay_layout.addWidget(self.add_delay_btn)
        ignition_layout.addLayout(delay_layout)
        control_layout.addWidget(ignition_group)

        # 设置三列布局的比例
        control_layout.setStretch(0, 1)
        control_layout.setStretch(1, 2)
        control_layout.setStretch(2, 1)
        main_layout.addLayout(control_layout)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        valve_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        ignition_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        # ===== 序列执行区 =====
        sequence_group = QGroupBox("序列执行区")
        sequence_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sequence_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 14px;
                border: 2px solid #3498DB;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
                color: #3498DB;
            }
        """)
        sequence_layout = QVBoxLayout(sequence_group)
        sequence_layout.setContentsMargins(15, 20, 15, 15)

        # 序列列表和执行控制
        sequence_control_layout = QHBoxLayout()
        
        # 序列列表
        sequence_list_layout = QVBoxLayout()
        sequence_tip_label = QLabel(
            "操作提示：单击选中项目，↑↓键移动，Shift+↑↓快速移动，Delete键删除，右键更多操作")
        sequence_tip_label.setStyleSheet("color: #7F8C8D; font-size: 10px; font-style: italic;")
        sequence_list_layout.addWidget(sequence_tip_label)
        
        self.sequence_list = SequenceListWidget()
        self.sequence_list.setMinimumHeight(80)
        self.sequence_list.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.sequence_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.sequence_list.item_deleted.connect(self._on_sequence_item_deleted)
        self.sequence_list.item_moved.connect(self._on_sequence_item_moved)
        sequence_list_layout.addWidget(self.sequence_list)
        sequence_control_layout.addLayout(sequence_list_layout)
        
        # 序列控制按钮
        sequence_buttons_layout = QVBoxLayout()
        self.run_sequence_btn = QPushButton("执行序列")
        self.stop_sequence_btn = QPushButton("停止序列")
        self.clear_sequence_btn = QPushButton("清空序列")
        self.save_sequence_btn = QPushButton("保存序列")
        self.import_sequence_btn = QPushButton("导入序列")

        btn_style = f"""
            QPushButton {{
                background-color: {button_color};
                color: white;
                border: none;
                border-radius: 4px;
                font-weight: bold;
                padding: 8px;
                margin: 2px;
            }}
            QPushButton:hover {{
                background-color: {hover_color};
            }}
        """
        self.run_sequence_btn.setStyleSheet(btn_style)
        self.stop_sequence_btn.setStyleSheet(btn_style)
        self.clear_sequence_btn.setStyleSheet(btn_style)
        self.save_sequence_btn.setStyleSheet(btn_style)
        self.import_sequence_btn.setStyleSheet(btn_style)

        self.run_sequence_btn.clicked.connect(self._run_sequence)
        self.stop_sequence_btn.clicked.connect(self._stop_sequence)
        self.clear_sequence_btn.clicked.connect(self._clear_sequence)
        self.save_sequence_btn.clicked.connect(self._save_current_sequence)
        self.import_sequence_btn.clicked.connect(self._import_sequence)

        sequence_buttons_layout.addWidget(self.run_sequence_btn)
        sequence_buttons_layout.addWidget(self.stop_sequence_btn)
        sequence_buttons_layout.addWidget(self.clear_sequence_btn)
        sequence_buttons_layout.addWidget(self.save_sequence_btn)
        sequence_buttons_layout.addWidget(self.import_sequence_btn)
        sequence_control_layout.addLayout(sequence_buttons_layout)

        sequence_layout.addLayout(sequence_control_layout)
        main_layout.addWidget(sequence_group, 1)

        # ===== 任务窗口 =====
        task_group = QGroupBox("任务窗口")
        task_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 14px;
                border: 2px solid #3498DB;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
                color: #3498DB;
            }
        """)
        task_layout = QVBoxLayout(task_group)

        self.task_list = QTextEdit()
        self.task_list.setReadOnly(True)
        self.task_list.setMaximumHeight(150)
        self.task_list.setStyleSheet("""
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
        task_layout.addWidget(self.task_list)

        task_buttons_layout = QHBoxLayout()
        self.clear_task_btn = QPushButton("清空任务")
        self.clear_task_btn.clicked.connect(self._clear_task_window)


        self.clear_task_btn.setStyleSheet(btn_style)


        task_buttons_layout.addWidget(self.clear_task_btn)
        task_buttons_layout.addStretch()
        task_layout.addLayout(task_buttons_layout)

        main_layout.addWidget(task_group)

        # 初始化任务窗口
        self._log_task("点火控制台已启动")
        self._log_task("等待指令...")

    def _add_valve_sequence(self, valve_id, valve_name, is_open):
        """添加电磁阀操作到序列"""
        action = "开启" if is_open else "关闭"
        action_type = "valve_open" if is_open else "valve_close"
        
        item = SequenceItem(valve_name, action_type)
        item_data = item.data(Qt.ItemDataRole.UserRole)
        item_data["valve_id"] = valve_id
        item_data["valve_name"] = valve_name
        item_data["is_open"] = is_open
        item.setData(Qt.ItemDataRole.UserRole, item_data)
        
        self.sequence_list.addItem(item)
        self._log_task(f"已添加到序列: {action} - {valve_name}")
        self.sequence_list.scrollToItem(item)
    
    def _add_all_valves_open_sequence(self):
        """添加全部打开电磁阀到序列"""
        item = SequenceItem("打开所有电磁阀", "all_valves_open")
        item_data = item.data(Qt.ItemDataRole.UserRole)
        item_data["action"] = "all_valves_open"
        item_data["is_open"] = True
        item.setData(Qt.ItemDataRole.UserRole, item_data)
        
        self.sequence_list.addItem(item)
        self._log_task("已添加到序列: 打开所有电磁阀")
        self.sequence_list.scrollToItem(item)
    
    def _add_all_valves_close_sequence(self):
        """添加全部关闭电磁阀到序列"""
        item = SequenceItem("关闭所有电磁阀", "all_valves_close")
        item_data = item.data(Qt.ItemDataRole.UserRole)
        item_data["action"] = "all_valves_close"
        item_data["is_open"] = False
        item.setData(Qt.ItemDataRole.UserRole, item_data)
        
        self.sequence_list.addItem(item)
        self._log_task("已添加到序列: 关闭所有电磁阀")
        self.sequence_list.scrollToItem(item)
    
    def _add_ignition_sequence(self, is_on):
        """添加点火操作到序列"""
        action = "点火" if is_on else "熄火"
        action_type = "ignition_on" if is_on else "ignition_off"
        
        item = SequenceItem(action, action_type)
        item_data = item.data(Qt.ItemDataRole.UserRole)
        item_data["is_on"] = is_on
        item.setData(Qt.ItemDataRole.UserRole, item_data)
        
        self.sequence_list.addItem(item)
        self._log_task(f"已添加到序列: {action}")
        self.sequence_list.scrollToItem(item)
    
    def _add_delay_sequence(self, delay_ms=1000):
        """添加延时操作到序列"""
        item = SequenceItem("延时", "delay", delay_ms)
        self.sequence_list.addItem(item)
        
        if delay_ms >= 1000:
            delay_text = f"{delay_ms/1000:.1f} 秒"
        else:
            delay_text = f"{delay_ms} 毫秒"
        self._log_task(f"已添加到序列: 延时 ({delay_text})")
        self.sequence_list.scrollToItem(item)
    
    def _update_delay_tooltip(self):
        """更新延时按钮的提示信息"""
        delay_ms = self.delay_spinbox.value()
        self.add_delay_btn.setToolTip(f"延时功能:\n上位机等待指定的毫秒数再继续执行下一条命令\n当前延时: {delay_ms}毫秒")
        
    def _add_custom_delay_sequence(self):
        """添加用户自定义延时到序列"""
        delay_ms = self.delay_spinbox.value()
        self._add_delay_sequence(delay_ms)

    def _save_current_sequence(self):
        """保存当前序列"""
        if self.sequence_list.count() == 0:
            QMessageBox.warning(self, "提示", "当前序列为空，无法保存")
            return

        name, ok = QInputDialog.getText(
            self,
            "保存序列",
            "请输入实验序列名称（可选，留空将自动生成）:",
            QLineEdit.EchoMode.Normal,
            ""
        )

        if not ok:
            return

        success, result = self.sequence_manager.save_sequence(self.sequence_list, name if name else None)

        if success:
            self._log_task(f"✅ 序列已保存: {os.path.basename(result)}")
            QMessageBox.information(
                self,
                "保存成功",
                f"序列已保存到:\n{result}\n\n包含 {self.sequence_list.count()} 个命令"
            )
        else:
            self._log_task(f"❌ 保存失败: {result}")
            QMessageBox.warning(self, "保存失败", f"错误: {result}")

    def _import_sequence(self):
        """导入序列"""
        dialog = SequenceSelectorDialog(self.sequence_manager, self)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            filepath, name = dialog.get_selection()
            if not filepath:
                return

            success, items_data, seq_name = self.sequence_manager.load_sequence(filepath)

            if not success:
                QMessageBox.warning(self, "导入失败", f"无法加载序列: {items_data}")
                return

            if self.sequence_list.count() > 0:
                reply = QMessageBox.question(
                    self,
                    "确认导入",
                    f"当前序列有 {self.sequence_list.count()} 项。\n导入 \"{seq_name}\" 会清空当前序列吗？",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Yes
                )

                if reply == QMessageBox.StandardButton.Cancel:
                    return
                elif reply == QMessageBox.StandardButton.Yes:
                    self.sequence_list.clear()

            imported_count = 0
            for item_info in items_data:
                text = item_info['text']
                data = item_info['data']

                action_type = data.get('action_type', 'unknown')
                delay_ms = data.get('delay_ms', 0)

                item = SequenceItem(text, action_type, delay_ms)
                item.setData(Qt.ItemDataRole.UserRole, data)
                self._restore_item_color(item, action_type)

                self.sequence_list.addItem(item)
                imported_count += 1

            self._log_task(f"📂 已导入序列 \"{seq_name}\" ({imported_count}项)")
            QMessageBox.information(
                self,
                "导入成功",
                f"成功导入序列 \"{seq_name}\"\n共 {imported_count} 个命令"
            )

    def _restore_item_color(self, item, action_type):
        """根据action_type恢复项目颜色"""
        colors = {
            "motor": "#95C7F0",
            "motor_v2": "#95C7F0",
            "valve_open": "#F2A7A7",
            "valve_close": "#F2A7A7",
            "ignition_on": "#FFD699",
            "ignition_off": "#FFD699",
            "delay": "#99D8CA",
            "all_valves_open": "#F2A7A7",
            "all_valves_close": "#F2A7A7"
        }

        if action_type in colors:
            color = QColor(colors[action_type])
            color.setAlpha(180)
            brush = QBrush(color)
            brush.setStyle(Qt.BrushStyle.SolidPattern)
            item.setBackground(brush)
            
            dark_text_brush = QBrush(QColor("#000000"))
            item.setForeground(dark_text_brush)
            
            font = QFont()
            font.setBold(True)
            item.setFont(font)

    def _run_sequence(self):
        """执行序列"""
        if self.sequence_running:
            self._log_task("序列已在执行中")
            return

        if not self.serial_manager.is_connected():
            self._log_task("错误: 串口未连接")
            return

        if self.sequence_list.count() == 0:
            self._log_task("序列为空，请先添加操作")
            return

        self.sequence_running = True
        self.run_sequence_btn.setEnabled(False)
        self.stop_sequence_btn.setEnabled(True)

        # 计算序列总时长 (累加所有 delay 项)
        total_ms = 0.0
        for i in range(self.sequence_list.count()):
            item = self.sequence_list.item(i)
            data = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(data, dict) and data.get("action_type") == "delay":
                total_ms += data.get("delay_ms", 0)
        self._seq_total_duration = max(total_ms / 1000.0, 0.5)
        self._seq_elapsed = 0.0
        self._seq_current_desc = "开始执行..."
        self._seq_timer.start(50)  # 50ms 平滑计时器

        self._log_task(f"开始执行序列... (总时长 {self._seq_total_duration:.1f}s)")
        self._execute_sequence_item(0)

    def _execute_sequence_item(self, index):
        """执行序列中的指定项目"""
        if not self.sequence_running or index >= self.sequence_list.count():
            self._stop_sequence()
            return

        item = self.sequence_list.item(index)
        if not item:
            self._execute_sequence_item(index + 1)
            return

        action_data = item.data(Qt.ItemDataRole.UserRole)
        action_type = action_data.get("action_type")

        self._log_task(f"执行: {item.text()}")
        self._seq_current_desc = item.text()
     
        # 电磁阀操作
        if action_type == "valve_open" or action_type == "valve_close":
            if isinstance(action_data, dict) and "valve_id" in action_data:
                valve_id = action_data["valve_id"]
                is_open = action_data.get("is_open", action_type == "valve_open")
                valve_name = action_data.get("valve_name", f"电磁阀{valve_id:02X}")

                valve_state = 0x01 if is_open else 0x00
                command = bytes([0xBB, valve_id, valve_state] + [0x00] * 7)
                success = self.serial_manager.send_data(command)

                if success:
                    action_text = "打开" if is_open else "关闭"
                    self._log_task(f"{action_text} {valve_name} 命令已发送")

                    # 通知 HMI 面板更新阀门颜色
                    hmi_valve = self.HW_ID_TO_HMI_VALVE.get(valve_id)
                    if hmi_valve:
                        self.sequence_valve_changed.emit(hmi_valve, is_open)
                    
                    if valve_id in self.valve_buttons:
                        status = self.valve_buttons[valve_id]["status"]
                        if is_open:
                            status.setText("打开")
                            status.setStyleSheet("""
                                color: white;
                                background-color: #27AE60;
                                border-radius: 2px;
                                padding: 2px;
                                min-width: 50px;
                                text-align: center;
                            """)
                        else:
                            status.setText("关闭")
                            status.setStyleSheet("""
                                color: white;
                                background-color: #E74C3C;
                                border-radius: 2px;
                                padding: 2px;
                                min-width: 50px;
                                text-align: center;
                            """)
                else:
                    self._log_task(f"电磁阀控制命令发送失败")
            else:
                self._log_task("警告：执行的电磁阀命令格式不正确")

        # 批量电磁阀操作
        elif action_type == "all_valves_open":
            command = bytes([0xBB, 0xFF, 0x01] + [0x00] * 7)
            if self.serial_manager.send_data(command):
                self._log_task("已发送: 打开所有电磁阀 (批量命令)")
                # 通知 HMI 面板
                for hw_id, hmi_valve in self.HW_ID_TO_HMI_VALVE.items():
                    self.sequence_valve_changed.emit(hmi_valve, True)
                for hw_id in [0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08]:
                    if hw_id in self.valve_buttons:
                        status = self.valve_buttons[hw_id]["status"]
                        status.setText("打开")
                        status.setStyleSheet("""
                            color: white;
                            background-color: #27AE60;
                            border-radius: 2px;
                            padding: 2px;
                            min-width: 50px;
                            text-align: center;
                        """)
            else:
                self._log_task("发送失败: 打开所有电磁阀")

        elif action_type == "all_valves_close":
            command = bytes([0xBB, 0xFF, 0x00] + [0x00] * 7)
            if self.serial_manager.send_data(command):
                self._log_task("已发送: 关闭所有电磁阀 (批量命令)")
                # 通知 HMI 面板
                for hw_id, hmi_valve in self.HW_ID_TO_HMI_VALVE.items():
                    self.sequence_valve_changed.emit(hmi_valve, False)
                for hw_id in [0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08]:
                    if hw_id in self.valve_buttons:
                        status = self.valve_buttons[hw_id]["status"]
                        status.setText("关闭")
                        status.setStyleSheet("""
                            color: white;
                            background-color: #E74C3C;
                            border-radius: 2px;
                            padding: 2px;
                            min-width: 50px;
                            text-align: center;
                        """)
            else:
                self._log_task("发送失败: 关闭所有电磁阀")

        # 点火操作
        elif action_type == "ignition_on":
            command = bytes([0xCC, 0x21] + [0x00] * 8)
            if self.serial_manager.send_data(command):
                self._log_task("点火命令已发送: 0xCC210000000000000000")
                self.ignition_status.setText("已点火")
                self.ignition_status.setStyleSheet("""
                    color: white;
                    background-color: #27AE60;
                    border-radius: 2px;
                    padding: 2px;
                    font-weight: bold;
                    text-align: center;
                """)
            else:
                self._log_task("点火命令发送失败")

        elif action_type == "ignition_off":
            command = bytes([0xCC, 0x20] + [0x00] * 8)
            if self.serial_manager.send_data(command):
                self._log_task("熄火命令已发送: 0xCC200000000000000000")
                self.ignition_status.setText("未点火")
                self.ignition_status.setStyleSheet("""
                    color: white;
                    background-color: #E74C3C;
                    border-radius: 2px;
                    padding: 2px;
                    font-weight: bold;
                    text-align: center;
                """)
            else:
                self._log_task("熄火命令发送失败")

        # 延时操作
        elif action_type == "delay":
            delay_ms = action_data.get("delay_ms", 1000)
            self._log_task(f"执行延时: {delay_ms}ms")
            QTimer.singleShot(delay_ms, lambda: self._execute_sequence_item(index + 1))
            return

        # 默认延时
        QTimer.singleShot(100, lambda: self._execute_sequence_item(index + 1))

    def _stop_sequence(self):
        """停止序列执行"""
        self.sequence_running = False
        self._seq_timer.stop()
        # 通知 HMI 时间轴走到底
        self.sequence_timeline_update.emit(
            self._seq_total_duration, "序列执行完成", self._seq_total_duration)
        self.run_sequence_btn.setEnabled(True)
        self.stop_sequence_btn.setEnabled(False)
        self._log_task("序列执行已停止")

    def _on_seq_timer_tick(self):
        """50ms 时序平滑计时器回调 —— 连续 emit 时间轴更新给 HMI"""
        if not self.sequence_running:
            return
        self._seq_elapsed += 0.05
        if self._seq_elapsed > self._seq_total_duration:
            self._seq_elapsed = self._seq_total_duration
        self.sequence_timeline_update.emit(
            self._seq_elapsed, self._seq_current_desc, self._seq_total_duration)

    def _clear_sequence(self):
        """清空序列"""
        self.sequence_list.clear()
        self._log_task("序列已清空")

    def _on_sequence_item_moved(self, from_row, to_row):
        self._log_task(f"序列项目从位置 {from_row + 1} 移动到 {to_row + 1}")

    def _on_sequence_item_deleted(self, index):
        if index == -1:
            self._log_task("序列项目顺序已调整")
        else:
            self._log_task(f"已从序列中删除项目 #{index+1}")

    def _clear_task_window(self):
        self.task_list.clear()
        self._log_task("任务窗口已清空")

    def set_replay_mode(self, enabled):
        """回放模式下禁用所有串口指令按钮 (物理安全锁)"""
        disabled = enabled
        if hasattr(self, 'run_sequence_btn'):
            self.run_sequence_btn.setEnabled(not disabled)
        if hasattr(self, 'stop_sequence_btn'):
            self.stop_sequence_btn.setEnabled(not disabled)
        if hasattr(self, 'valve_buttons'):
            for items in self.valve_buttons.values():
                if 'open_btn' in items:
                    items['open_btn'].setEnabled(not disabled)
                if 'close_btn' in items:
                    items['close_btn'].setEnabled(not disabled)
        if hasattr(self, 'valve_all_open_btn'):
            self.valve_all_open_btn.setEnabled(not disabled)
            self.valve_all_close_btn.setEnabled(not disabled)
        if hasattr(self, 'add_ignition_on_btn'):
            self.add_ignition_on_btn.setEnabled(not disabled)
            self.add_ignition_off_btn.setEnabled(not disabled)
        if hasattr(self, 'add_delay_btn'):
            self.add_delay_btn.setEnabled(not disabled)
            self.delay_spinbox.setEnabled(not disabled)

    def _log_task(self, message):
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.task_list.append(f"[{timestamp}] {message}")

    def _send_emergency_stop(self):
        if not self.serial_manager.is_connected():
            self._log_task("错误: 串口未连接")
            return

        command = bytes([0xEE] + [0x00] * 9)
        if self.serial_manager.send_data(command):
            self._log_task("强制停止命令(灭火序列)已发送！")
            self.command_sent.emit("强制停止命令已发送")
        else:
            self._log_task("强制停止命令发送失败")

    def update_control_state(self):
        """更新控件状态"""
        enabled = self.serial_manager.is_connected()

        # 电机控制
        if hasattr(self, 'motor_panel'):
            self.motor_panel.set_enabled(enabled and not self.sequence_running)
     #   if hasattr(self, 'motor_stop_btn'):
      #      self.motor_stop_btn.setEnabled(enabled)

        # 电磁阀控制
        controls_enabled = enabled and not self.sequence_running
        if hasattr(self, 'valve_buttons'):
            for _, items in self.valve_buttons.items():
                items["open_btn"].setEnabled(controls_enabled)
                items["close_btn"].setEnabled(controls_enabled)
        if hasattr(self, 'valve_all_open_btn'):
            self.valve_all_open_btn.setEnabled(controls_enabled)
            self.valve_all_close_btn.setEnabled(controls_enabled)

        # 点火控制
        if hasattr(self, 'add_ignition_on_btn'):
            self.add_ignition_on_btn.setEnabled(controls_enabled)
            self.add_ignition_off_btn.setEnabled(controls_enabled)
        if hasattr(self, 'add_delay_btn'):
            self.add_delay_btn.setEnabled(controls_enabled)
            self.delay_spinbox.setEnabled(controls_enabled)

        # 序列控制
        if hasattr(self, 'run_sequence_btn'):
            self.run_sequence_btn.setEnabled(enabled and not self.sequence_running)
            self.stop_sequence_btn.setEnabled(enabled and self.sequence_running)
            self.clear_sequence_btn.setEnabled(enabled)
            self.save_sequence_btn.setEnabled(enabled)
            self.import_sequence_btn.setEnabled(enabled)

        # 任务控制
        if hasattr(self, 'clear_task_btn'):
            self.clear_task_btn.setEnabled(enabled)