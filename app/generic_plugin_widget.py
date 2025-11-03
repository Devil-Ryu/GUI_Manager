from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, 
    QPushButton, QGroupBox, QFormLayout, QLineEdit, QComboBox,
    QSpinBox, QDoubleSpinBox, QCheckBox, QDateTimeEdit, QListWidget,
    QListWidgetItem, QMessageBox, QFileDialog, QScrollArea, QFrame, QGridLayout, QDialog
)
from PySide6.QtCore import Qt, Signal, QDateTime, QUrl
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import QSizePolicy
import json
import os
from datetime import datetime
import logging
import re
import html
from app.plugin_import_dialog import ParameterConfigWidget

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def ansi_to_html(text: str) -> str:
    """将 ANSI 转义序列转换为 HTML 格式，支持 rich 库的彩色输出"""
    if not isinstance(text, str):
        text = str(text)
    
    # 先处理 OSC 8 超链接与其他 OSC 序列，防止出现 "]8;..." 残留
    # 格式： ESC ] 8 ; params ; URI ST text ESC ] 8 ; ; ST
    # ST 可以是 BEL(\x07) 或 ESC \
    def _osc_st_pattern():
        return r"(?:\x07|\x1b\\)"  # BEL 或 ESC \

    # 将 OSC 8 超链接转换为 HTML 超链接，占位保护后再统一转义
    try:
        osc8_link_pattern = rf"\x1b\]8;[^\x1b\x07]*;([^\x1b\x07]+){_osc_st_pattern()}(.*? )?\x1b\]8;;{_osc_st_pattern()}"
    except Exception:
        osc8_link_pattern = r"\x1b\]8;[^]*;([^]+)(?:|\")(.*? )?\x1b\]8;;(?:|\")"

    # 收集生成的占位符
    link_placeholders = {}
    link_counter = 0

    def _replace_osc8(m):
        nonlocal link_counter
        url = m.group(1) or ""
        text_part = (m.group(2) or "").rstrip(" ")
        ph = f"__A_PLACEHOLDER_{link_counter}__"
        # 直接生成 a 标签，稍后与 span 一起做保护
        link_placeholders[ph] = f"<a href=\"{url}\" target=\"_blank\">{text_part}</a>"
        link_counter += 1
        return ph

    try:
        # 先替换所有 OSC8 超链接
        import re as _re_oscl
        text = _re_oscl.sub(osc8_link_pattern, _replace_osc8, text, flags=_re_oscl.DOTALL)
        # 其余 OSC 序列（如设置标题等）直接去掉
        text = _re_oscl.sub(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)", "", text)
    except Exception:
        pass

    # ANSI 颜色码映射（基础 16 色）
    # 基本颜色
    color_map = {
        30: '#000000',  # 黑色
        31: '#CD3131',  # 红色
        32: '#0DBC79',  # 绿色
        33: '#E5E510',  # 黄色
        34: '#2472C8',  # 蓝色
        35: '#BC3FBC',  #  magenta
        36: '#11A8CD',  # 青色
        37: '#E5E5E5',  # 白色
        90: '#666666',  # 亮黑/灰色
        91: '#F14C4C',  # 亮红
        92: '#23D18B',  # 亮绿
        93: '#F5F543',  # 亮黄
        94: '#3B8EEA',  # 亮蓝
        95: '#D670D6',  # 亮紫
        96: '#29B8DB',  # 亮青
        97: '#E5E5E5',  # 亮白
    }
    
    # 背景颜色码映射（基础 16 色）
    bg_color_map = {
        40: '#000000',  # 黑色背景
        41: '#CD3131',  # 红色背景
        42: '#0DBC79',  # 绿色背景
        43: '#E5E510',  # 黄色背景
        44: '#2472C8',  # 蓝色背景
        45: '#BC3FBC',  # 紫色背景
        46: '#11A8CD',  # 青色背景
        47: '#E5E5E5',  # 白色背景
    }
    
    # 重置所有样式
    text = text.replace('\x1B[0m', '</span>')
    text = text.replace('\033[0m', '</span>')
    text = text.replace('\u001b[0m', '</span>')
    
    # 处理 ANSI 转义序列
    # 匹配格式: \x1B[或\033[或\u001b[ 后跟数字和分号，最后是 m
    ansi_pattern = r'(?:\x1B\[|\033\[|\u001b\[)([0-9;]*)m'
    
    def _color256_to_hex(n: int) -> str | None:
        """将 0-255 的 ANSI 256 色转换为十六进制颜色。"""
        try:
            n = int(n)
        except Exception:
            return None
        if n < 0 or n > 255:
            return None
        # 0-15: 标准与亮色（近似映射到基础色）
        basic_map = {
            0:  "#000000", 1:  "#CD3131", 2:  "#0DBC79", 3:  "#E5E510",
            4:  "#2472C8", 5:  "#BC3FBC", 6:  "#11A8CD", 7:  "#E5E5E5",
            8:  "#666666", 9:  "#F14C4C", 10: "#23D18B", 11: "#F5F543",
            12: "#3B8EEA", 13: "#D670D6", 14: "#29B8DB", 15: "#E5E5E5",
        }
        if n <= 15:
            return basic_map.get(n)
        # 16-231: 6x6x6 色立方
        if 16 <= n <= 231:
            n -= 16
            r = (n // 36) % 6
            g = (n // 6) % 6
            b = n % 6
            def level(x):
                return 0 if x == 0 else 55 + 40 * x
            return f"#{level(r):02x}{level(g):02x}{level(b):02x}"
        # 232-255: 灰度 (8..238 step 10)
        if 232 <= n <= 255:
            v = 8 + (n - 232) * 10
            return f"#{v:02x}{v:02x}{v:02x}"
        return None

    open_spans = 0

    def replace_ansi(match):
        nonlocal open_spans
        codes = match.group(1).split(';')
        if not codes or codes == ['']:
            return '</span>' if open_spans > 0 else ''
        
        styles = []
        fg_color = None
        bg_color = None
        bold = False
        dim = False
        italic = False
        underline = False
        
        i = 0
        while i < len(codes):
            code_str = codes[i]
            if not code_str:
                i += 1
                continue
            try:
                code = int(code_str)
            except ValueError:
                i += 1
                continue

            if code == 0:
                # 重置：仅在存在已开启样式时输出闭合
                if open_spans > 0:
                    open_spans -= 1
                    return '</span>'
                else:
                    return ''
            elif code == 1:
                bold = True
            elif code == 2:
                dim = True
            elif code == 3:
                italic = True
            elif code == 4:
                underline = True
            elif 30 <= code <= 37:
                fg_color = color_map.get(code)
            elif 40 <= code <= 47:
                bg_color = bg_color_map.get(code)
            elif 90 <= code <= 97:
                fg_color = color_map.get(code)
            elif 100 <= code <= 107:
                bg_color = bg_color_map.get(code - 60)
            elif code == 38:
                # 扩展前景色：38;5;n 或 38;2;r;g;b
                if i + 1 < len(codes):
                    try:
                        mode = int(codes[i + 1])
                    except Exception:
                        mode = None
                    if mode == 5 and i + 2 < len(codes):
                        fg_color = _color256_to_hex(codes[i + 2])
                        i += 2
                    elif mode == 2 and i + 4 < len(codes):
                        try:
                            r = max(0, min(255, int(codes[i + 2])))
                            g = max(0, min(255, int(codes[i + 3])))
                            b = max(0, min(255, int(codes[i + 4])))
                            fg_color = f"#{r:02x}{g:02x}{b:02x}"
                            i += 4
                        except Exception:
                            pass
            elif code == 48:
                # 扩展背景色：48;5;n 或 48;2;r;g;b
                if i + 1 < len(codes):
                    try:
                        mode = int(codes[i + 1])
                    except Exception:
                        mode = None
                    if mode == 5 and i + 2 < len(codes):
                        bg_color = _color256_to_hex(codes[i + 2])
                        i += 2
                    elif mode == 2 and i + 4 < len(codes):
                        try:
                            r = max(0, min(255, int(codes[i + 2])))
                            g = max(0, min(255, int(codes[i + 3])))
                            b = max(0, min(255, int(codes[i + 4])))
                            bg_color = f"#{r:02x}{g:02x}{b:02x}"
                            i += 4
                        except Exception:
                            pass
            i += 1
        
        # 构建样式字符串
        style_parts = []
        if fg_color:
            style_parts.append(f'color: {fg_color}')
        if bg_color:
            style_parts.append(f'background-color: {bg_color}')
        if bold:
            style_parts.append('font-weight: bold')
        if dim:
            style_parts.append('opacity: 0.6')
        if italic:
            style_parts.append('font-style: italic')
        if underline:
            style_parts.append('text-decoration: underline')
        
        if style_parts:
            open_spans += 1
            return f'<span style="{"; ".join(style_parts)}">'
        return ''
    
    # 替换所有 ANSI 序列为 HTML 标签（此时标签还是占位符，不会被转义）
    text = re.sub(ansi_pattern, replace_ansi, text)
    
    # 转义 HTML 特殊字符（转义文本内容，但不影响我们已经添加的 HTML 标签）
    # 使用占位符保护我们添加的 HTML 标签
    span_placeholders = {}
    placeholder_counter = 0
    
    def protect_span(match):
        nonlocal placeholder_counter
        placeholder = f"__SPAN_PLACEHOLDER_{placeholder_counter}__"
        span_placeholders[placeholder] = match.group(0)
        placeholder_counter += 1
        return placeholder
    
    # 保护已添加的 span/a 标签
    text = re.sub(r'<span[^>]*>|</span>|<a[^>]*>|</a>', protect_span, text)
    
    # 转义 HTML 特殊字符
    text = html.escape(text)
    
    # 恢复 span/a 标签与超链接占位
    for placeholder, original in span_placeholders.items():
        text = text.replace(placeholder, original)
    for placeholder, original in link_placeholders.items():
        text = text.replace(placeholder, original)
    
    # 不在此处处理换行符；上层逐行插入并追加 <br/>
    
    # 计算打开的 span 标签数量，确保在文本末尾关闭所有标签
    open_span_count = text.count('<span') - text.count('</span>')
    if open_span_count > 0:
        text += '</span>' * open_span_count

    # 若无任何 span 标签（即该行没有 ANSI），仍包一层 span，强制以富文本模式渲染，从而解析 HTML 实体
    if '<span' not in text:
        text = f"<span>{text}</span>"
    
    return text


class ParameterEditor(QWidget):
    """参数编辑器组件"""
    
    parameters_changed = Signal(dict)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parameters = {}
        self.param_widgets = {}
        self.init_ui()
    
    def init_ui(self):
        """初始化界面（每行显示3个参数：标签+控件 成对布局）"""
        from PySide6.QtWidgets import QGridLayout
        self.layout = QGridLayout(self)
        try:
            # 为控件列提供伸展：1、3、5列为输入控件
            self.layout.setColumnStretch(1, 1)
            self.layout.setColumnStretch(3, 1)
            self.layout.setColumnStretch(5, 1)
        except Exception:
            pass
    
    def set_parameters(self, parameters):
        """设置参数"""
        self.parameters = parameters
        self.refresh_ui()

    def add_parameter(self, name: str, param_info: dict):
        """新增一个参数定义并刷新UI"""
        if not isinstance(name, str) or not name:
            return
        if not isinstance(param_info, dict):
            return
        self.parameters[name] = dict(param_info)
        self.refresh_ui()
        self.parameters_changed.emit(self.get_parameters())

    def remove_parameter(self, name: str):
        """删除一个参数定义并刷新UI"""
        try:
            if name in self.parameters:
                del self.parameters[name]
                self.refresh_ui()
                self.parameters_changed.emit(self.get_parameters())
        except Exception:
            pass
    
    def refresh_ui(self):
        """刷新UI"""
        # 清除现有控件
        while self.layout.count() > 0:
            item = self.layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        
        self.param_widgets.clear()
        
        # 添加参数控件（每行3组：label+widget）
        index = 0
        for name, param_info in self.parameters.items():
            widget = self._create_param_widget(param_info)
            if not widget:
                continue
            label = QLabel(f"{param_info.get('label', name)}:")
            label.setToolTip(param_info.get('description', ''))
            try:
                label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            except Exception:
                pass
            row = index // 3
            group = index % 3
            col_label = group * 2
            col_widget = col_label + 1
            self.layout.addWidget(label, row, col_label, Qt.AlignLeft | Qt.AlignVCenter)
            self.layout.addWidget(widget, row, col_widget)
            self.param_widgets[name] = widget
            index += 1
    
    def _create_param_widget(self, param_info):
        """根据参数类型创建对应的控件"""
        param_type = param_info.get('type', 'string')
        value = param_info.get('value', None)
        
        if param_type == 'string':
            widget = QLineEdit()
            if value is not None:
                widget.setText(str(value))
            widget.textChanged.connect(self.on_parameter_changed)
            return widget
        
        elif param_type == 'integer':
            widget = QSpinBox()
            widget.setRange(param_info.get('min', -999999), param_info.get('max', 999999))
            if value is not None:
                try:
                    # 确保值是整数类型
                    int_value = int(value) if not isinstance(value, int) else value
                    widget.setValue(int_value)
                except (ValueError, TypeError):
                    # 如果转换失败，使用默认值0
                    widget.setValue(0)
            widget.valueChanged.connect(self.on_parameter_changed)
            return widget
        
        elif param_type == 'float':
            widget = QDoubleSpinBox()
            widget.setRange(param_info.get('min', -999999.99), param_info.get('max', 999999.99))
            widget.setDecimals(param_info.get('decimals', 2))
            if value is not None:
                try:
                    # 确保值是浮点数类型
                    float_value = float(value) if not isinstance(value, (int, float)) else value
                    widget.setValue(float_value)
                except (ValueError, TypeError):
                    # 如果转换失败，使用默认值0.0
                    widget.setValue(0.0)
            widget.valueChanged.connect(self.on_parameter_changed)
            return widget
        
        elif param_type == 'boolean':
            widget = QCheckBox()
            if value is not None:
                widget.setChecked(value)
            widget.stateChanged.connect(self.on_parameter_changed)
            return widget
        
        elif param_type == 'select':
            widget = QComboBox()
            options = param_info.get('options', [])
            for option in options:
                # 兼容 (value, label) / [value, label] / 纯字符串 三种形式
                if isinstance(option, tuple) and len(option) == 2:
                    value, label = option[0], option[1]
                elif isinstance(option, list) and len(option) == 2:
                    value, label = option[0], option[1]
                else:
                    value, label = option, str(option)
                widget.addItem(str(label), value)
            if value is not None:
                index = widget.findData(value)
                if index >= 0:
                    widget.setCurrentIndex(index)
                else:
                    # 尝试将值转换为字符串并查找索引
                    value_str = str(value)
                    index = widget.findText(value_str)
                    if index >= 0:
                        widget.setCurrentIndex(index)
            widget.currentIndexChanged.connect(self.on_parameter_changed)
            return widget
        
        elif param_type == 'datetime':
            widget = QDateTimeEdit()
            widget.setCalendarPopup(True)
            if value is not None:
                if isinstance(value, str):
                    # 尝试解析字符串
                    datetime = QDateTime.fromString(value, Qt.ISODate)
                    if datetime.isValid():
                        widget.setDateTime(datetime)
                else:
                    widget.setDateTime(value)
            else:
                widget.setDateTime(QDateTime.currentDateTime())
            widget.dateTimeChanged.connect(self.on_parameter_changed)
            return widget
        
        elif param_type == 'file':
            widget = QPushButton("选择文件...")
            if value is not None:
                widget.setText(value)
            widget.clicked.connect(lambda checked, w=widget, p=param_info: self.on_select_file(w, p))
            return widget
        
        return None
    
    def on_select_file(self, widget, param_info):
        """选择文件"""
        options = QFileDialog.Options()
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择文件", "", 
            param_info.get('filter', 'All Files (*)'), 
            options=options
        )
        if file_path:
            widget.setText(file_path)
            self.on_parameter_changed()
    
    def on_parameter_changed(self):
        """参数改变时触发"""
        self.parameters_changed.emit(self.get_parameters())
    
    def get_parameters(self):
        """获取参数值"""
        result = {}
        
        for name, param_info in self.parameters.items():
            if name in self.param_widgets:
                widget = self.param_widgets[name]
                param_type = param_info.get('type', 'string')
                
                if param_type == 'string':
                    result[name] = widget.text()
                elif param_type == 'integer':
                    result[name] = widget.value()
                elif param_type == 'float':
                    result[name] = widget.value()
                elif param_type == 'boolean':
                    result[name] = widget.isChecked()
                elif param_type == 'select':
                    result[name] = widget.currentData()
                elif param_type == 'datetime':
                    result[name] = widget.dateTime().toString(Qt.ISODate)
                elif param_type == 'file':
                    result[name] = widget.text()
        
        return result


class GenericPluginWidget(QWidget):
    """通用插件界面组件，为没有UI的插件提供默认界面"""
    
    start_plugin = Signal()
    stop_plugin = Signal()
    parameters_changed = Signal(dict)
    definitions_changed = Signal(dict)
    
    def __init__(self, plugin_name, plugin_id, parent=None, entry_module_path: str | None = None, entry_function_name: str | None = None):
        super().__init__(parent)
        self.plugin_name = plugin_name
        self.plugin_id = plugin_id
        self.entry_module_path = entry_module_path
        self.entry_function_name = entry_function_name
        self.is_running = False
        self.param_editor = None
        self.log_output = None
        self.status_indicator = None
        self.init_ui()
    
    def update_button_state(self):
        """更新按钮状态"""
        self.start_button.setEnabled(not self.is_running)
        self.stop_button.setEnabled(self.is_running)
    
    def init_ui(self):
        """初始化界面"""
        layout = QVBoxLayout(self)
        
        # 插件信息
        info_group = QGroupBox("插件信息")
        info_layout = QGridLayout()
        info_layout.setHorizontalSpacing(8)
        info_layout.setVerticalSpacing(6)

        def make_value_label(text: str, max_len: int = 80, elide_middle: bool = False) -> QLabel:
            full = text if isinstance(text, str) else "-"
            shown = full
            if isinstance(full, str) and len(full) > max_len:
                if elide_middle and max_len > 10:
                    head = full[: max_len // 2 - 2]
                    tail = full[-(max_len // 2 - 3) :]
                    shown = f"{head}…{tail}"
                else:
                    shown = full[: max_len - 1] + "…"
            label = QLabel(shown)
            label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            label.setToolTip(full)
            label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            return label

        # 名称 / ID
        info_layout.addWidget(QLabel("名称:"), 0, 0, Qt.AlignLeft)
        info_layout.addWidget(make_value_label(self.plugin_name, 60), 0, 1)
        info_layout.addWidget(QLabel("ID:"), 0, 2, Qt.AlignLeft)
        info_layout.addWidget(make_value_label(self.plugin_id, 60), 0, 3)

        # 函数入口
        entry_func = self.entry_function_name if isinstance(self.entry_function_name, str) else "-"
        info_layout.addWidget(QLabel("函数入口:"), 1, 0, Qt.AlignLeft)
        info_layout.addWidget(make_value_label(entry_func, 80), 1, 1)

        # 更新日期
        updated_at = "-"
        try:
            entry_file_for_date = self.entry_module_path
            if entry_file_for_date and entry_file_for_date != "-" and os.path.exists(entry_file_for_date):
                ts = os.path.getmtime(entry_file_for_date)
                updated_at = datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            pass
        info_layout.addWidget(QLabel("插件更新日期:"), 1, 2, Qt.AlignLeft)
        info_layout.addWidget(make_value_label(updated_at, 80), 1, 3)

        # 主程序文件行：路径跨两列，按钮放第4列并左对齐（与上方文字对齐）
        entry_file = self.entry_module_path if self.entry_module_path else "-"
        info_layout.addWidget(QLabel("主程序文件:"), 2, 0, Qt.AlignLeft)
        self.entry_file_label = make_value_label(entry_file, 100, elide_middle=True)
        info_layout.addWidget(self.entry_file_label, 2, 1, 1, 2)  # 跨两列以留出第4列
        self.open_dir_btn = QPushButton("打开插件目录")
        try:
            self.open_dir_btn.setMinimumHeight(24)
        except Exception:
            pass
        self.open_dir_btn.clicked.connect(self.on_open_plugin_dir_clicked)
        info_layout.addWidget(self.open_dir_btn, 2, 3, Qt.AlignLeft)

        info_group.setLayout(info_layout)
        
        # 参数配置
        self.param_group = QGroupBox("参数配置")
        self.param_layout = QVBoxLayout()
        
        self.param_editor = ParameterEditor()
        self.param_editor.parameters_changed.connect(self.on_parameters_changed)

        # 参数操作：编辑参数（复用导入插件时的参数配置界面）
        self.edit_params_btn = QPushButton("编辑参数")
        # 让按钮横向拉伸填满整行
        self.edit_params_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        try:
            self.edit_params_btn.setMinimumHeight(28)
        except Exception:
            pass
        self.edit_params_btn.clicked.connect(self.on_edit_params_clicked)
        
        # 默认参数示例
        default_params = {
            "param1": {
                "type": "string",
                "label": "参数1",
                "description": "这是一个字符串参数示例",
                "value": "默认值"
            },
            "param2": {
                "type": "integer",
                "label": "参数2",
                "description": "这是一个整数参数示例",
                "value": 100,
                "min": 0,
                "max": 1000
            },
            "param3": {
                "type": "boolean",
                "label": "参数3",
                "description": "这是一个布尔参数示例",
                "value": True
            }
        }
        
        self.param_editor.set_parameters(default_params)
        
        # 直接将按钮加入垂直布局以占满整行
        self.param_layout.addWidget(self.edit_params_btn)
        self.param_layout.addWidget(self.param_editor)
        self.param_group.setLayout(self.param_layout)
        
        # 输出日志 + 手动输入
        log_group = QGroupBox("输出日志")
        log_layout = QVBoxLayout()
        # 输入行
        input_row = QHBoxLayout()
        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText("在此输入并提交给脚本…")
        self.input_edit.returnPressed.connect(self.on_send_input_clicked)  # 按回车提交输入
        self.input_send_btn = QPushButton("提交输入")
        self.input_send_btn.clicked.connect(self.on_send_input_clicked)
        input_row.addWidget(self.input_edit)
        input_row.addWidget(self.input_send_btn)
        log_layout.addLayout(input_row)
        # 日志窗口（使用富文本以渲染 ANSI→HTML）
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setLineWrapMode(QTextEdit.NoWrap)
        try:
            self.log_text.setAcceptRichText(True)
        except Exception:
            pass
        
        log_layout.addWidget(self.log_text)
        log_group.setLayout(log_layout)
        
        # 控制按钮
        button_layout = QHBoxLayout()
        
        self.start_button = QPushButton("启动插件")
        self.stop_button = QPushButton("停止插件")
        self.save_params_button = QPushButton("保存参数")
        
        self.start_button.clicked.connect(self.on_start_clicked)
        self.stop_button.clicked.connect(self.on_stop_clicked)
        self.save_params_button.clicked.connect(self.on_save_params_clicked)
        
        button_layout.addWidget(self.start_button)
        button_layout.addWidget(self.stop_button)
        button_layout.addWidget(self.save_params_button)
        button_layout.addStretch()
        
        # 添加到主布局
        layout.addWidget(info_group)
        layout.addWidget(self.param_group)
        layout.addWidget(log_group, 1)
        layout.addLayout(button_layout)
        
        # 添加状态指示器
        self.status_indicator = PluginStatusIndicator()
        layout.addWidget(self.status_indicator)
        
        # 保存对关键控件的引用
        self.log_output = self.log_text
        self.param_editor = self.param_editor
        
        # 更新按钮状态
        self.update_button_state()

    def _open_param_editor_dialog(self):
        dlg = ParameterEditDialog(self)
        # 将当前参数字典转换为导入对话框所需的列表结构
        curr_params = []
        try:
            for name, info in (self.param_editor.parameters or {}).items():
                item = {
                    "name": name,
                    "type": info.get("type", "string"),
                    "label": info.get("label", name),
                    "description": info.get("description", ""),
                    "value": info.get("value", ""),
                    "min": info.get("min"),
                    "max": info.get("max"),
                    "options": info.get("options", []),
                }
                curr_params.append(item)
        except Exception:
            curr_params = []
        dlg.set_parameters(curr_params)
        if dlg.exec():
            params_list = dlg.get_parameters()
            # 允许用户清空全部参数：当列表为空时，清空并持久化
            if not params_list:
                self.param_editor.set_parameters({})
                self.parameters_changed.emit({})
                try:
                    self.definitions_changed.emit({})
                except Exception:
                    pass
            else:
                # 1) 读取旧参数快照
                try:
                    old_params = dict(self.param_editor.parameters or {})
                except Exception:
                    old_params = {}
                # 2) 将对话框列表转换为新参数映射（仅有效项）
                new_params_map = {}
                for item in params_list:
                    name = item.get("name")
                    if not name:
                        continue
                    info = dict(item)
                    info.pop("name", None)
                    new_params_map[name] = info
                if not new_params_map:
                    # 没有有效项，相当于清空
                    self.param_editor.set_parameters({})
                    self.parameters_changed.emit({})
                    try:
                        self.definitions_changed.emit({})
                    except Exception:
                        pass
                    return
                # 3) 基于旧参数进行合并：
                #    - 删除：旧里有但新里没有的键
                #    - 修改：旧里有且新里有 → 字段级更新（新覆盖旧）
                #    - 新增：仅在新里存在的键
                merged = {}
                # 修改/新增
                for name, info in new_params_map.items():
                    base = dict(old_params.get(name, {}))
                    base.update(info or {})
                    merged[name] = base
                # 删除已在对话框中移除的项：跳过未出现在 new_params_map 的旧键
                # 4) 应用到编辑器并触发保存
                self.param_editor.set_parameters(merged)
                self.parameters_changed.emit(self.param_editor.get_parameters())
                # 同步发出定义变更信号，用于持久化定义覆盖
                try:
                    self.definitions_changed.emit(merged)
                except Exception:
                    pass

    def _get_main_window(self):
        p = self.parent()
        while p is not None and not hasattr(p, 'submit_manual_input'):
            p = p.parent() if hasattr(p, 'parent') else None
        return p

    def prepare_for_input(self, prompt: str, default_text: str = "", password: bool = False):
        """在输入行展示提示并聚焦。"""
        try:
            if hasattr(self, 'input_edit') and self.input_edit:
                # 密码场景不在此隐藏，仅提示
                self.input_edit.setPlaceholderText(prompt or "在此输入并提交给脚本…")
                if default_text:
                    self.input_edit.setText(default_text)
                self.input_edit.setFocus()
        except Exception:
            pass
    
    def set_parameters(self, parameters):
        """设置参数"""
        self.param_editor.set_parameters(parameters)
        # 连接参数变化信号
        self.param_editor.parameters_changed.connect(self.on_parameters_changed)
    
    def get_parameters(self):
        """获取参数"""
        return self.param_editor.get_parameters()
    
    def set_running(self, is_running):
        """设置运行状态"""
        self.is_running = is_running
        self.update_button_state()
        # 更新状态指示器
        if self.status_indicator:
            self.status_indicator.set_status(is_running)
    
    def update_button_state(self):
        """更新按钮状态"""
        self.start_button.setEnabled(not self.is_running)
        self.stop_button.setEnabled(self.is_running)
    
    def append_log(self, message):
        """添加日志信息，支持 ANSI 彩色文本，使用 insertHtml 降低多余空行"""
        try:
            if message is None:
                return
            html_text = ansi_to_html(str(message))
            if html_text:
                self.log_text.insertHtml(html_text + "<br/>")
        except Exception:
            try:
                plain_text = str(message).replace("\n", "<br>").replace("\r", "")
                if plain_text:
                    self.log_text.insertHtml(plain_text + "<br/>")
            except Exception:
                pass
        # 滚动到底部
        try:
            if self.log_output:
                self.log_output.verticalScrollBar().setValue(
                    self.log_output.verticalScrollBar().maximum())
        except Exception:
            pass

    def clear_log(self):
        """清空日志窗口"""
        try:
            self.log_text.clear()
        except Exception:
            pass

    def on_open_plugin_dir_clicked(self):
        """打开插件所在目录"""
        try:
            # 1) 优先使用主程序文件路径推导目录
            path = self.entry_module_path
            directory = None
            if isinstance(path, str) and path not in ("", "-"):
                try:
                    abs_path = path if os.path.isabs(path) else os.path.abspath(path)
                    directory = os.path.dirname(abs_path)
                except Exception:
                    directory = None

            # 2) 回退：根据插件ID在项目的 plugins 目录下查找
            if not directory or not os.path.isdir(directory):
                try:
                    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
                    plugins_root = os.path.join(project_root, "plugins")
                    candidate = os.path.join(plugins_root, str(self.plugin_id))
                    if os.path.isdir(candidate):
                        directory = candidate
                except Exception:
                    pass

            if directory and os.path.isdir(directory):
                QDesktopServices.openUrl(QUrl.fromLocalFile(directory))
            else:
                # 显示提示，便于定位问题
                QMessageBox.warning(self, "无法打开", "未能定位到插件目录或主程序文件路径无效。")
        except Exception as e:
            try:
                QMessageBox.warning(self, "无法打开", f"发生异常: {e}")
            except Exception:
                pass

    def on_send_input_clicked(self):
        """将手动输入提交给等待中的脚本。"""
        try:
            text = self.input_edit.text() if hasattr(self, 'input_edit') else ""
            mw = self._get_main_window()
            if mw and hasattr(mw, 'submit_manual_input'):
                mw.submit_manual_input(self.plugin_id, text)
            self.input_edit.clear()
        except Exception:
            pass
    
    def on_start_clicked(self):
        """启动按钮点击"""
        # 在启动前确保参数已保存
        if self.param_editor:
            current_params = self.param_editor.get_parameters()
            self.parameters_changed.emit(current_params)
        # 启动前清空界面日志
        try:
            self.clear_log()
        except Exception:
            pass
        self.start_plugin.emit()
        self.set_running(True)
    
    def on_stop_clicked(self):
        """停止按钮点击"""
        self.stop_plugin.emit()
        self.set_running(False)
    
    def on_save_params_clicked(self):
        """保存参数按钮点击"""
        params = self.get_parameters()
        self.parameters_changed.emit(params)
        QMessageBox.information(self, "参数保存", "参数已保存")
    
    def on_parameters_changed(self, params):
        """参数改变回调"""
        self.parameters_changed.emit(params)
        self.append_log(f"参数已更新: {json.dumps(params, ensure_ascii=False)}")
        
    def on_edit_params_clicked(self):
        """编辑参数：弹出导入风格的参数配置框"""
        self._open_param_editor_dialog()
    
    def show_error(self, message):
        """显示错误信息"""
        self.append_log(f"错误: {message}")
        QMessageBox.warning(self, "错误", message)
    
    def show_info(self, message):
        """显示信息"""
        self.append_log(message)


class PluginStatusIndicator(QWidget):
    """插件状态指示器"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
    
    def init_ui(self):
        """初始化界面"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.status_label = QLabel("已停止")
        self.status_indicator = QLabel()
        self.status_indicator.setFixedSize(12, 12)
        self.status_indicator.setStyleSheet("background-color: red; border-radius: 6px;")
        
        layout.addWidget(self.status_indicator)
        layout.addWidget(self.status_label)
        layout.addStretch()
    
    def set_status(self, is_running):
        """设置状态"""
        if is_running:
            self.status_label.setText("运行中")
            self.status_indicator.setStyleSheet("background-color: green; border-radius: 6px;")
        else:
            self.status_label.setText("已停止")
            self.status_indicator.setStyleSheet("background-color: red; border-radius: 6px;")


class _AddParameterDialog(QDialog):
    """添加/编辑参数对话框（简化版）"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("添加参数")
        from PySide6.QtWidgets import QFormLayout, QDialogButtonBox
        layout = QFormLayout(self)
        self.name_edit = QLineEdit()
        self.label_edit = QLineEdit()
        self.type_combo = QComboBox()
        self.type_combo.addItems(["string", "integer", "float", "boolean", "select", "datetime", "file"])
        self.value_edit = QLineEdit()
        self.options_edit = QLineEdit()
        self.options_edit.setPlaceholderText("select 类型用逗号分隔选项")
        layout.addRow("名称", self.name_edit)
        layout.addRow("显示名", self.label_edit)
        layout.addRow("类型", self.type_combo)
        layout.addRow("默认值", self.value_edit)
        layout.addRow("选项", self.options_edit)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        layout.addRow(btns)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)

    def get_param(self):
        name = self.name_edit.text().strip()
        ptype = self.type_combo.currentText()
        label = self.label_edit.text().strip() or name
        raw_value = self.value_edit.text().strip()
        info = {"type": ptype, "label": label, "description": "",
                "value": self._parse_value(ptype, raw_value)}
        if ptype == "select":
            opts = [x.strip() for x in self.options_edit.text().split(',') if x.strip()]
            info["options"] = opts
        return name, info

    @staticmethod
    def _parse_value(ptype: str, text: str):
        try:
            if ptype == "integer":
                return int(text) if text != "" else 0
            if ptype == "float":
                return float(text) if text != "" else 0.0
            if ptype == "boolean":
                return text.lower() in ("1", "true", "yes", "on")
            return text
        except Exception:
            return text


class ParameterEditDialog(QDialog):
    """参数编辑对话框：复用导入插件时的参数配置组件"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("编辑参数")
        self.setMinimumWidth(560)
        from PySide6.QtWidgets import QVBoxLayout, QHBoxLayout, QScrollArea, QWidget, QDialogButtonBox
        main_layout = QVBoxLayout(self)
        self.scroll = QScrollArea()
        self.scroll_widget = QWidget()
        self.list_layout = QVBoxLayout(self.scroll_widget)
        # 让参数区靠上对齐
        try:
            self.list_layout.setAlignment(Qt.AlignTop)
            self.scroll.setAlignment(Qt.AlignTop)
            main_layout.setAlignment(self.scroll, Qt.AlignTop)
        except Exception:
            pass
        self.scroll.setWidget(self.scroll_widget)
        self.scroll.setWidgetResizable(True)
        main_layout.addWidget(self.scroll)

        ops = QHBoxLayout()
        self.add_btn = QPushButton("添加参数")
        self.add_btn.clicked.connect(self._add_item)
        ops.addWidget(self.add_btn)
        # 保持整体靠上，不再强制居中
        main_layout.addLayout(ops)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        main_layout.addWidget(btns)

    def set_parameters(self, params_list):
        # 清空
        from PySide6.QtWidgets import QWidget
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        # 填充
        for idx, p in enumerate(params_list or []):
            section, w = self._create_section(idx)
            self._fill_widget_from_param(w, p)
            w.param_removed.connect(self._on_removed)
            # 名称变化时更新折叠标题
            try:
                w.name_edit.textChanged.connect(lambda _=None, s=section, wi=w: self._update_section_title(s, wi))
            except Exception:
                pass
            self.list_layout.addWidget(section)

    def get_parameters(self):
        # 读取所有 ParameterConfigWidget
        params = []
        for i in range(self.list_layout.count()):
            item = self.list_layout.itemAt(i)
            container = item.widget()
            if not container:
                continue
            # 在折叠容器中查找真正的 ParameterConfigWidget
            cfg = container.findChild(ParameterConfigWidget)
            if cfg:
                params.append(cfg.get_parameter_config())
        return params

    def _add_item(self):
        idx = self._count_sections()
        section, w = self._create_section(idx)
        w.param_removed.connect(self._on_removed)
        try:
            w.name_edit.textChanged.connect(lambda _=None, s=section, wi=w: self._update_section_title(s, wi))
        except Exception:
            pass
        self.list_layout.addWidget(section)

    def _on_removed(self, _index):
        # 找到触发者所在的折叠区并移除
        import inspect
        sender = self.sender()
        # sender 为 ParameterConfigWidget
        section = sender.parent() if sender else None
        try:
            if section:
                section.setParent(None)
                section.deleteLater()
        except Exception:
            pass
        # 重新编号
        for i in range(self.list_layout.count()):
            item = self.list_layout.itemAt(i)
            sec = item.widget()
            if sec:
                w = sec.findChild(ParameterConfigWidget)
                if w:
                    w.update_index(i)
                    self._update_section_title(sec, w)

    @staticmethod
    def _fill_widget_from_param(w: ParameterConfigWidget, p: dict):
        try:
            w.name_edit.setText(str(p.get("name", "")))
            w.type_combo.setCurrentText(str(p.get("type", "string")))
            w.label_edit.setText(str(p.get("label", p.get("name", ""))))
            w.description_edit.setText(str(p.get("description", "")))
            val = p.get("value", "")
            w.value_edit.setText(str(val))
            # min/max
            if p.get("type") in ("integer", "float"):
                if p.get("min") is not None:
                    w.min_edit.setText(str(p.get("min")))
                if p.get("max") is not None:
                    w.max_edit.setText(str(p.get("max")))
            # options
            if p.get("type") == "select":
                lines = []
                for opt in p.get("options", []):
                    # 兼容 (value,label) / [value,label] / 纯字符串
                    if isinstance(opt, tuple) and len(opt) == 2:
                        v, lbl = opt[0], opt[1]
                        lines.append(f"{v},{lbl}")
                    elif isinstance(opt, list) and len(opt) == 2:
                        v, lbl = opt[0], opt[1]
                        lines.append(f"{v},{lbl}")
                    else:
                        lines.append(str(opt))
                w.options_edit.setText("\n".join(lines))
        except Exception:
            pass

    # ---- 折叠区实现 ----
    def _create_section(self, idx: int):
        from PySide6.QtWidgets import QWidget, QVBoxLayout, QToolButton, QSizePolicy, QFrame, QHBoxLayout
        container = QWidget(self)
        v = QVBoxLayout(container)
        v.setContentsMargins(0, 0, 0, 0)
        header = QToolButton()
        header.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        header.setArrowType(Qt.DownArrow)
        header.setText(f"参数 {idx + 1}")
        header.setCheckable(True)
        header.setChecked(True)
        header.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        v.addWidget(header)

        content = QFrame()
        content.setFrameShape(QFrame.NoFrame)
        vl = QVBoxLayout(content)
        vl.setContentsMargins(8, 4, 8, 8)
        w = ParameterConfigWidget(idx, content)
        vl.addWidget(w)
        v.addWidget(content)

        def toggle(expanded: bool):
            content.setVisible(expanded)
            header.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)
        header.toggled.connect(toggle)
        toggle(True)
        return container, w

    def _update_section_title(self, section_widget, cfg_widget: ParameterConfigWidget):
        try:
            header = section_widget.findChild(type(section_widget).findChild.__class__, "")
        except Exception:
            header = None
        # 更可靠：直接遍历第一个子控件就是 QToolButton
        try:
            if hasattr(section_widget, 'layout'):
                pass
        except Exception:
            pass
        try:
            btn = section_widget.findChildren(type(QPushButton()))[0]  # may fail
        except Exception:
            btn = None
        # 保险：直接在布局第一个小部件取 QToolButton
        try:
            lay = section_widget.layout()
            if lay and lay.count() > 0:
                maybe_btn = lay.itemAt(0).widget()
                if hasattr(maybe_btn, 'setText'):
                    name_text = cfg_widget.name_edit.text() or f"参数 {cfg_widget.index + 1}"
                    maybe_btn.setText(f"参数 {cfg_widget.index + 1}: {name_text}")
        except Exception:
            pass

    def _count_sections(self) -> int:
        return self.list_layout.count()