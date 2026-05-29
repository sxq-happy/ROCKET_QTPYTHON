# hmi_components.py - 实时监控看板 (HMI Panel)
"""
2KN 推力供给系统实时监控看板
基于 HMI.svg，通过直接修改 SVG DOM 来更新动态数值，
不使用任何叠加层组件。
"""

import xml.etree.ElementTree as ET
import copy
import math
import os
import time

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGraphicsView, QGraphicsScene,
    QLabel, QFrame, QSizePolicy, QGraphicsPixmapItem
)
from PySide6.QtCore import Qt, QRectF, QTimer, QByteArray, QSize
from PySide6.QtGui import QPainter, QFont, QColor, QImage, QPixmap

from PySide6.QtSvg import QSvgRenderer

# ── SVG 命名空间 ------------------------------------------------------------
SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)
ET.register_namespace("inkscape", "http://www.inkscape.org/namespaces/inkscape")
ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")
ET.register_namespace("sodipodi", "http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd")
# NOTE: Do NOT register "svg" prefix — it conflicts with the default namespace
# and causes ElementTree to emit <svg:svg> which QSvgRenderer cannot parse.


def _svg_find(root, element_id):
    """在 SVG ElementTree 中按 id 或 inkscape:label 查找元素"""
    for el in root.iter():
        if el.get("id") == element_id or el.get("{http://www.inkscape.org/namespaces/inkscape}label") == element_id:
            return el
    return None


def _svg_set_text(root, element_id, new_text):
    """替换 SVG 中指定 id 的 <text> 元素的文本内容"""
    el = _svg_find(root, element_id)
    if el is None:
        return False
    el.text = new_text
    # 同时处理 <tspan> 子元素（如果有）
    for tspan in el.findall(f"{{{SVG_NS}}}tspan"):
        tspan.text = new_text
    return True


def _svg_set_fill(root, element_id, color_hex):
    """设置 SVG 元素的 fill 颜色"""
    el = _svg_find(root, element_id)
    if el is None:
        return False
    el.set("fill", color_hex)
    return True


def _parse_svg_number(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_transform(transform):
    """
    Parse a small subset of SVG transform syntax.
    Returns an affine matrix [a, b, c, d, e, f].
    """
    if not transform:
        return (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)

    a, b, c, d, e, f = 1.0, 0.0, 0.0, 1.0, 0.0, 0.0

    def multiply(m2):
        nonlocal a, b, c, d, e, f
        a1, b1, c1, d1, e1, f1 = a, b, c, d, e, f
        a2, b2, c2, d2, e2, f2 = m2
        a = a1 * a2 + c1 * b2
        b = b1 * a2 + d1 * b2
        c = a1 * c2 + c1 * d2
        d = b1 * c2 + d1 * d2
        e = a1 * e2 + c1 * f2 + e1
        f = b1 * e2 + d1 * f2 + f1

    import re

    for name, args_text in re.findall(r"([a-zA-Z]+)\(([^)]*)\)", transform):
        args = [
            _parse_svg_number(v)
            for v in re.split(r"[,\s]+", args_text.strip())
            if v
        ]
        name = name.lower()
        if name == "matrix" and len(args) >= 6:
            multiply(tuple(args[:6]))
        elif name == "translate":
            tx = args[0] if len(args) >= 1 else 0.0
            ty = args[1] if len(args) >= 2 else 0.0
            multiply((1.0, 0.0, 0.0, 1.0, tx, ty))
        elif name == "scale":
            sx = args[0] if len(args) >= 1 else 1.0
            sy = args[1] if len(args) >= 2 else sx
            multiply((sx, 0.0, 0.0, sy, 0.0, 0.0))
        elif name == "rotate" and len(args) >= 1:
            angle = math.radians(args[0])
            cos_a = math.cos(angle)
            sin_a = math.sin(angle)
            if len(args) >= 3:
                cx, cy = args[1], args[2]
                multiply((1.0, 0.0, 0.0, 1.0, cx, cy))
                multiply((cos_a, sin_a, -sin_a, cos_a, 0.0, 0.0))
                multiply((1.0, 0.0, 0.0, 1.0, -cx, -cy))
            else:
                multiply((cos_a, sin_a, -sin_a, cos_a, 0.0, 0.0))

    return (a, b, c, d, e, f)


def _apply_matrix_to_point(matrix, x, y):
    a, b, c, d, e, f = matrix
    return (a * x + c * y + e, b * x + d * y + f)


def _svg_tag_name(el):
    return el.tag.rsplit("}", 1)[-1] if isinstance(el.tag, str) else ""


def _svg_href(el):
    return (
        el.get("href")
        or el.get("{http://www.w3.org/1999/xlink}href")
        or ""
    )


def _find_nearest_valve_name(cx, cy):
    best_name = None
    best_dist = None
    for name, (vx, vy) in VALVE_INDICATORS.items():
        dist = (cx - vx) ** 2 + (cy - vy) ** 2
        if best_dist is None or dist < best_dist:
            best_dist = dist
            best_name = name
    return best_name


# ── SVG 绑定表 -------------------------------------------------------------
# 每个逻辑字段对应 SVG 中的目标元素名（id 或 inkscape:label）
VALUE_BINDINGS = {
    # 乙醇箱
    "value_TI_ethanol_tank": {
        "targets": ["value_TI_ethanol_tank"],
        "format": "{:.1f} °C",
        "desc": "乙醇箱温度",
    },
    "value_PT_ethanol_tank": {
        "targets": ["value_PT_ethanol_tank", "text4"],
        "format": "{:.2f} MPa",
        "desc": "乙醇箱压力 PT",
    },
    # 液氧箱
    "value_PT_LOX_tank": {
        "targets": ["value_PT_LOX_tank", "text7-4"],
        "format": "{:.2f} MPa",
        "desc": "液氧箱压力 PT",
    },
    # 推力室入口
    "value_PT_301": {
        "targets": ["value_PT_301", "text17"],
        "format": "{:.2f} MPa",
        "desc": "PT-301 乙醇入口压力",
    },
    "value_TT_301": {
        "targets": ["value_TT_301", "text19"],
        "format": "{:.1f} °C",
        "desc": "TT-301 乙醇入口温度",
    },
    "value_PT_302": {
        "targets": ["value_PT_302", "text13"],
        "format": "{:.2f} MPa",
        "desc": "PT-302 液氧入口压力",
    },
    "value_TT_302": {
        "targets": ["value_TT_302", "text11"],
        "format": "{:.1f} °C",
        "desc": "TT-302 液氧入口温度",
    },
    # 燃烧室
    "value_TT_303": {
        "targets": ["value_TT_303", "text10"],
        "format": "{:.1f} °C",
        "desc": "TT-303 燃烧室温度",
    },
    "value_PT_303": {
        "targets": ["value_PT_303", "text7"],
        "format": "{:.2f} MPa",
        "desc": "PT-303 燃烧室压力",
    },
    # 推力
    "value_ZT_301": {
        "targets": ["value_ZT_301", "text5"],
        "format": "{:.1f} N",
        "desc": "ZT-301 主推力",
    },
}

# PLC 状态文本
PLC_TEXT_ID = "text_PLC_comm_status"

# 阀门绑定：逻辑阀门名 -> SVG 中的目标元素名（id 或 inkscape:label）
VALVE_BINDINGS = {
    "XV-102": ["valve_XV_102"],
    "XV-103": ["valve_XV_103"],
    "XV-104": ["valve_XV_104"],
    "XV-202": ["valve_XV_202"],
    "XV-203": ["valve_XV_203"],
    "XV-205": ["valve_XV_205"],
    "XV-206": ["valve_XV_206"],
    "XV-302": ["valve_XV_302"],
    "XV-401": ["valve_XV_401"],
    "XV-402": ["valve_XV_402"],
}

# 仅用于未命名/未绑定阀门的兜底定位，不要依赖它作为主映射。
VALVE_INDICATORS = {
    # 乙醇系统
    "XV-102": (220, 155),
    "XV-103": (430, 355),
    "XV-104": (230, 835),
    # 液氧系统
    "XV-202": (1740, 155),
    "XV-203": (1740, 355),
    "XV-205": (1580, 835),
    "XV-206": (1420, 895),
    # 点火/吹扫
    "XV-302": (890, 140),
    "XV-401": (870, 270),
    "XV-402": (870, 340),
}

# 默认不显示调试/状态圆点，避免遮挡原始 SVG 版面
SHOW_VALVE_INDICATORS = False

# ── 主 HMI 面板 -------------------------------------------------------------
class HMIPanel(QWidget):
    """实时监控看板 - 直接修改 SVG DOM 来更新显示"""

    def __init__(self, serial_manager, parent=None):
        super().__init__(parent)
        self.serial_manager = serial_manager

        # 加载 SVG 模板
        svg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "HMI.svg")
        with open(svg_path, "r", encoding="utf-8") as f:
            # 保持 SVG 原样读取，避免把普通 `href` 改写成未声明的命名空间前缀。
            self._svg_template = f.read()

        # 解析模板获取 viewBox 尺寸
        template_tree = ET.fromstring(self._svg_template)
        vb = template_tree.get("viewBox", "0 0 1920 1080")
        parts = vb.split()
        self.svg_width = float(parts[2]) if len(parts) >= 4 else 1920.0
        self.svg_height = float(parts[3]) if len(parts) >= 4 else 1080.0

        # 传感器数据缓存
        self.sensor_values = {k: 0.0 for k in VALUE_BINDINGS}
        self.valve_states = {k: False for k in VALVE_INDICATORS}
        self._valve_state_set = set()  # 记录哪些阀门被外部主动设置过状态
        self._timeline_t = -5.0       # 时序进度条时间
        self._timeline_desc = "等待试车..."
        self._elapsed_time = 0.0      # 人类直觉读秒 (从0开始的绝对时间)
        self.timeline_range = (-5.0, 5.0)  # (t_min, t_max)，序列执行时会动态更新
        self.plc_connected = False
        self._dirty = True

        # 数据采集
        self.is_collecting = False
        self.last_pressure = 0.0
        self.last_temp1 = 0.0
        self.last_temp2 = 0.0
        self.last_thrust = 0.0
        self._last_data_time = time.time()

        self._init_ui()
        self._connect_signals()

        # 建好 scene 后插入阀门指示圆（在 SVG item 上方的 z 层）
        self._inject_valve_indicators()

        self._render()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # QGraphicsView / Scene
        self.scene = QGraphicsScene(self)
        self.view = QGraphicsView(self.scene)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.view.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setFrameShape(QFrame.Shape.NoFrame)
        self.view.setStyleSheet("background-color: #121212; border: none;")
        self.view.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.scene.setSceneRect(QRectF(0, 0, self.svg_width, self.svg_height))

        # 先用 QSvgRenderer 解析，再把结果转成位图放进 scene
        self.renderer = QSvgRenderer()
        self.svg_item = QGraphicsPixmapItem()
        self.svg_item.setZValue(0)
        self.scene.addItem(self.svg_item)

        main_layout.addWidget(self.view)

        # 底部状态栏
        self._create_status_bar(main_layout)

    def _create_status_bar(self, layout):
        bar = QFrame()
        bar.setStyleSheet("QFrame { background-color: #1a1a1a; border-top: 1px solid #333; max-height: 42px; }")
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(12, 4, 12, 4)

        self.status_label = QLabel("数据采集: 就绪")
        self.status_label.setFont(QFont("Arial", 10))
        self.status_label.setStyleSheet("color: #888; background: transparent;")
        bar_layout.addWidget(self.status_label)
        bar_layout.addStretch()

        self.data_age_label = QLabel("")
        self.data_age_label.setFont(QFont("Arial", 9))
        self.data_age_label.setStyleSheet("color: #666; background: transparent;")
        bar_layout.addWidget(self.data_age_label)
        layout.addWidget(bar)

    # ── 阀门指示圆注入到 SVG item 上方 ----------------------------------------
    def _inject_valve_indicators(self):
        """在 scene 中添加阀门状态小圆点（在 SVG item 上层）"""
        if not SHOW_VALVE_INDICATORS:
            self._valve_circles = {}
            return

        from PySide6.QtGui import QPen, QBrush
        from PySide6.QtWidgets import QGraphicsEllipseItem

        self._valve_circles = {}
        for name, (cx, cy) in VALVE_INDICATORS.items():
            r = 7
            dot = QGraphicsEllipseItem(cx - r, cy - r, r * 2, r * 2)
            dot.setPen(QPen(QColor("#888888"), 1.5))
            dot.setBrush(QBrush(QColor("#555555")))
            dot.setZValue(5)
            self.scene.addItem(dot)
            self._valve_circles[name] = dot

    # ── SVG 构建与渲染 --------------------------------------------------------
    def _build_svg_bytes(self):
        """根据当前传感器数据重建整个 SVG XML 并返回 bytes"""
        tree = ET.fromstring(self._svg_template)

        # 更新传感器数值文本
        for value_name, spec in VALUE_BINDINGS.items():
            val = self.sensor_values.get(value_name, 0.0)
            text = spec["format"].format(val)
            for target in spec["targets"]:
                if _svg_set_text(tree, target, text):
                    break

        # 更新 PLC 状态文本
        plc_text = "PLC 通讯状态: 正常" if self.plc_connected else "PLC 通讯状态: 未连接"
        _svg_set_text(tree, PLC_TEXT_ID, plc_text)

        # 更新 PLC 状态框颜色
        plc_box = _svg_find(tree, "box_PLC_comm_status")
        if plc_box is not None:
            plc_box.set("stroke", "#00ff00" if self.plc_connected else "#ff3333")

        plc_text_el = _svg_find(tree, PLC_TEXT_ID)
        if plc_text_el is not None:
            plc_text_el.set("fill", "#00ff00" if self.plc_connected else "#ff3333")

        # 更新阀门状态
        self._apply_valve_colors(tree)

        # 更新时序进度条
        self._render_timeline(tree)

        # 更新人类直觉读秒计时器
        self._render_elapsed_time(tree)

        svg_str = ET.tostring(tree, encoding="unicode")
        return svg_str.encode("utf-8")

    def _render_timeline(self, tree):
        """在 SVG 中更新试车时序进度条元素。"""
        t = getattr(self, "_timeline_t", -5.0)
        desc = getattr(self, "_timeline_desc", "等待试车...")

        # 动态时间范围 → 0~1000 px
        t_min, t_max = self.timeline_range
        span = t_max - t_min if t_max != t_min else 10.0
        pixel = (t - t_min) / span * 1000.0
        pixel = max(0.0, min(1000.0, pixel))

        # 进度条填充宽度
        fill_el = _svg_find(tree, "timeline_fill")
        if fill_el is not None:
            fill_el.set("width", f"{pixel:.1f}")

        # 游标位置
        cursor_el = _svg_find(tree, "timeline_cursor")
        if cursor_el is not None:
            cursor_el.set("transform", f"translate({pixel:.1f}, 0)")

        # 时间文本
        if t < 0:
            time_text = f"T-{abs(t):.2f}s"
        elif t == 0:
            time_text = "T+0.00s"
        else:
            time_text = f"T+{t:.2f}s"
        _svg_set_text(tree, "text_current_time", time_text)

        # 状态描述
        _svg_set_text(tree, "text_current_state", desc)

    def _render_elapsed_time(self, tree):
        """更新人类直觉读秒计时器 text_elapsed_time，格式 MM:SS.ms"""
        t = getattr(self, "_elapsed_time", 0.0)
        minutes = int(t // 60)
        seconds = int(t % 60)
        centiseconds = round((t - int(t)) * 100)
        elapsed_text = f"{minutes:02d}:{seconds:02d}.{centiseconds:02d}"
        _svg_set_text(tree, "text_elapsed_time", elapsed_text)

    def _apply_valve_colors(self, tree):
        """把绑定阀门的 <use> 替换为内联带色几何，绕过 CSS 优先级。
        不动 def、不动 CSS、不动未绑定的阀门。"""
        for valve_name, targets in VALVE_BINDINGS.items():
            if valve_name not in self._valve_state_set:
                continue
            is_open = self.valve_states.get(valve_name, False)
            color = "#00ff00" if is_open else "#ff3333"
            stroke_c = "#00cc00" if is_open else "#cc0000"
            for target in targets:
                use_el = _svg_find(tree, target)
                if use_el is None:
                    continue
                href = _svg_href(use_el)
                g = self._expand_valve_use(tree, use_el, href, color, stroke_c)
                if g is not None:
                    # 把 <use> 替换为内联 <g>
                    parent = self._find_parent(tree, use_el)
                    if parent is not None:
                        idx = list(parent).index(use_el)
                        parent.remove(use_el)
                        parent.insert(idx, g)
                break  # 只处理第一个匹配的 target

    def _find_parent(self, tree, child):
        """在 ElementTree 中查找 child 的父元素。"""
        for parent in tree.iter():
            for c in parent:
                if c is child:
                    return parent
        return None

    def _expand_valve_use(self, tree, use_el, href, fill_color, stroke_color):
        """根据 href 类型展开 <use> 为带色的内联 <g>。"""
        SVG = SVG_NS
        x = _parse_svg_number(use_el.get("x"))
        y = _parse_svg_number(use_el.get("y"))
        transform = use_el.get("transform", "")

        g = ET.Element(f"{{{SVG}}}g")
        # 保留原始 id / label
        for aname in ("id",):
            if aname in use_el.attrib:
                g.set(aname, use_el.get(aname))
        label = use_el.get("{http://www.inkscape.org/namespaces/inkscape}label")
        if label:
            g.set("{http://www.inkscape.org/namespaces/inkscape}label", label)

        inner = ET.SubElement(g, f"{{{SVG}}}g")
        if x != 0 or y != 0:
            inner.set("transform", f"translate({x},{y})")

        if href in ("#valve", "#elec-valve"):
            # 蝴蝶翅膀
            path = ET.SubElement(inner, f"{{{SVG}}}path")
            path.set("d", "M -15 -10 L 15 10 L 15 -10 L -15 10 Z")
            path.set("fill", fill_color)
            path.set("stroke", stroke_color)
            path.set("stroke-width", "1.5")
            # 中心销
            circle = ET.SubElement(inner, f"{{{SVG}}}circle")
            circle.set("cx", "0"); circle.set("cy", "0"); circle.set("r", "3")
            circle.set("fill", stroke_color)
            # T 型执行器（仅 elec-valve）
            if href == "#elec-valve":
                act = ET.SubElement(inner, f"{{{SVG}}}path")
                act.set("d", "M 0 -2 L 0 -12 M -8 -12 L 8 -12")
                act.set("stroke", "#888888")
                act.set("stroke-width", "1.5")
                act.set("fill", "none")
        elif href == "#check-valve":
            circle = ET.SubElement(inner, f"{{{SVG}}}circle")
            circle.set("cx", "0"); circle.set("cy", "0"); circle.set("r", "12")
            circle.set("fill", fill_color)
            circle.set("stroke", stroke_color)
            circle.set("stroke-width", "1.5")
            arrow = ET.SubElement(inner, f"{{{SVG}}}path")
            arrow.set("d", "M -8 0 L 6 0 M 6 -5 L 6 5 M 0 -4 L 5 0 L 0 4")
            arrow.set("stroke", stroke_color)
            arrow.set("stroke-width", "1.5")
            arrow.set("fill", "none")

        if transform:
            g.set("transform", transform)
        return g

    def _render(self):
        """重建 SVG 并交给 renderer 渲染"""
        try:
            svg_bytes = self._build_svg_bytes()
            if not self.renderer.load(QByteArray(svg_bytes)):
                print("[HMI] SVG render error: renderer.load() returned False")
                return

            render_size = self.renderer.defaultSize()
            if render_size.isEmpty():
                render_size = QSize(int(self.svg_width), int(self.svg_height))

            image = QImage(render_size, QImage.Format.Format_ARGB32_Premultiplied)
            image.fill(Qt.GlobalColor.transparent)

            painter = QPainter(image)
            try:
                self.renderer.render(painter, QRectF(0, 0, render_size.width(), render_size.height()))
            finally:
                painter.end()

            self.svg_item.setPixmap(QPixmap.fromImage(image))
            self._dirty = False
        except Exception as e:
            print(f"[HMI] SVG render error: {e}")

    def _mark_dirty(self):
        self._dirty = True

    # ── 信号连接 --------------------------------------------------------------
    def _connect_signals(self):
        if hasattr(self.serial_manager, 'port2_data_received'):
            self.serial_manager.port2_data_received.connect(self._on_sensor_data)
        if hasattr(self.serial_manager, 'data_received'):
            self.serial_manager.data_received.connect(self._on_sensor_data)

        if hasattr(self.serial_manager, 'port2_connected'):
            self.serial_manager.port2_connected.connect(self._on_plc_connected)
        if hasattr(self.serial_manager, 'port2_disconnected'):
            self.serial_manager.port2_disconnected.connect(self._on_plc_disconnected)
        if hasattr(self.serial_manager, 'port1_connected'):
            self.serial_manager.port1_connected.connect(self._on_plc_connected)
        if hasattr(self.serial_manager, 'port1_disconnected'):
            self.serial_manager.port1_disconnected.connect(self._on_plc_disconnected)

        # 渲染节拍定时器：100ms 检查一次是否需要重绘
        self._render_timer = QTimer(self)
        self._render_timer.timeout.connect(self._render_tick)
        self._render_timer.start(100)

        # 传感器轮询定时器
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll_sensors)
        self._poll_timer.start(250)

        # 数据时效检查
        self._stale_timer = QTimer(self)
        self._stale_timer.timeout.connect(self._check_data_freshness)
        self._stale_timer.start(2000)

    def _render_tick(self):
        if self._dirty:
            self._render()

    # ── 9 通道 Modbus 04 命令采集 (中盛科技模块) -------------------------------
    # CH0~CH4: 推力 + 4 压力 (4-20mA), CH5~CH8: 4 温度 (K 型热电偶)
    # 每通道 2 字节有符号整数 x 0.1, 0xFFFF = 断线
    CHANNEL_MAP = [
        ("value_ZT_301",          1.0),     # CH0: 推力 ZT-301
        ("value_PT_301",          1.0),     # CH1: 乙醇入口压力 PT-301
        ("value_PT_302",          1.0),     # CH2: 液氧入口压力 PT-302
        ("value_PT_303",          1.0),     # CH3: 燃烧室压力 PT-303
        ("value_PT_ethanol_tank", 1.0),     # CH4: 乙醇箱压力
        ("value_TT_301",          1.0),     # CH5: 乙醇入口温度 TT-301 (热电偶)
        ("value_TT_302",          1.0),     # CH6: 液氧入口温度 TT-302 (热电偶)
        ("value_TT_303",          1.0),     # CH7: 燃烧室温度 TT-303 (热电偶)
        ("value_PT_LOX_tank",     1.0),     # CH8: 液氧箱压力
    ]

    # 读 9 寄存器, 起始地址 0x0000, CRC16=0C30
    POLL_CMD = 0x010400000009300C

    def _on_sensor_data(self, data: bytes):
        """解析 04 功能码响应: 地址01 + 04 + 字节数(18) + 18字节数据 + CRC"""
        if len(data) < 23 or data[0] != 0x01 or data[1] != 0x04:
            return

        byte_count = data[2]
        if byte_count < 18:
            return

        self._last_data_time = time.time()
        self.is_collecting = True
        self.status_label.setText("数据采集: 运行中")
        self.status_label.setStyleSheet("color: #00ff00; background: transparent; font-weight: bold;")

        try:
            for ch, (key, scale) in enumerate(self.CHANNEL_MAP):
                offset = 3 + ch * 2
                raw = int.from_bytes(data[offset:offset + 2], 'big', signed=False)
                if raw == 0xFFFF:
                    continue
                val = int.from_bytes(data[offset:offset + 2], 'big', signed=True) * 0.1 * scale
                self.sensor_values[key] = val

            # 衍生值: 乙醇箱温度取 TT-301
            tt301 = self.sensor_values.get("value_TT_301", 0.0)
            self.sensor_values["value_TI_ethanol_tank"] = tt301

            self.last_thrust = self.sensor_values.get("value_ZT_301", 0.0)
            self.last_temp1 = self.sensor_values.get("value_TT_301", 0.0)
            self.last_temp2 = self.sensor_values.get("value_TT_302", 0.0)
            self.last_pressure = self.sensor_values.get("value_PT_301", 0.0)

            self._mark_dirty()
        except Exception as e:
            print(f"[HMI] 传感器数据解析错误: {e}")

    def _poll_sensors(self):
        """发送 04 功能码读取 9 路通道"""
        if not self.serial_manager.is_port2_connected():
            return
        try:
            self.serial_manager.send_to_port2(self.POLL_CMD.to_bytes(8, 'big'))
        except Exception:
            pass

    def _check_data_freshness(self):
        age = time.time() - self._last_data_time
        if age > 5:
            self.data_age_label.setText(f"数据延迟: {age:.0f}s")
            self.data_age_label.setStyleSheet("color: #ff5555; background: transparent;")
        elif age > 2:
            self.data_age_label.setText(f"数据更新: {age:.0f}s 前")
            self.data_age_label.setStyleSheet("color: #ffaa00; background: transparent;")
        else:
            self.data_age_label.setText("数据: 实时")
            self.data_age_label.setStyleSheet("color: #00ff00; background: transparent;")

        if not self.serial_manager.is_port2_connected() and not self.serial_manager.is_port1_connected():
            self.status_label.setText("数据采集: 串口未连接")
            self.status_label.setStyleSheet("color: #ff5555; background: transparent;")
            self.is_collecting = False

    # ── PLC 状态 --------------------------------------------------------------
    def _on_plc_connected(self, *args):
        self.plc_connected = True
        self._mark_dirty()

    def _on_plc_disconnected(self):
        self.plc_connected = False
        self._mark_dirty()

    # ── 阀门状态（外部调用）---------------------------------------------------
    def set_valve_state(self, valve_name, is_open):
        """更新阀门状态并在 scene 中的指示圆上反映"""
        if valve_name in self.valve_states:
            self.valve_states[valve_name] = is_open
            self._valve_state_set.add(valve_name)
        if valve_name in self._valve_circles:
            dot = self._valve_circles[valve_name]
            if is_open:
                dot.setBrush(QColor("#00ff00"))
                dot.setPen(QColor("#00cc00"))
                dot.setVisible(True)
            else:
                dot.setVisible(False)
        self._mark_dirty()

    # ── 时序进度条 ------------------------------------------------------------
    def update_timeline(self, t_seconds, state_desc, total_duration=0.0):
        """更新试车时序进度条状态（轻量，仅记录值，渲染时生效）。

        t_seconds: 当前时间 (mock: -5.0~5.0, 真实序列: 0~total_duration)
        state_desc: 状态提示文本
        total_duration: 真实序列的总时长(秒)。>0 时覆盖 timeline_range 为 (0, total_duration)
        """
        self._timeline_t = t_seconds
        self._timeline_desc = state_desc
        if total_duration > 0:
            self.timeline_range = (0.0, total_duration)
            self._elapsed_time = max(0.0, t_seconds)  # 真实序列: t 从 0 开始
        else:
            self.timeline_range = (-5.0, 5.0)  # mock 模式默认
            self._elapsed_time = t_seconds + 5.0  # mock: t=-5 → elapsed=0
        self._mark_dirty()

    # ── 缩放 -----------------------------------------------------------------
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'view'):
            self.view.fitInView(
                QRectF(0, 0, self.svg_width, self.svg_height),
                Qt.AspectRatioMode.KeepAspectRatio
            )

    # ── 清理 -----------------------------------------------------------------
    def cleanup(self):
        self.is_collecting = False
        for t in ['_render_timer', '_poll_timer', '_stale_timer']:
            timer = getattr(self, t, None)
            if timer:
                timer.stop()
