import sys
import os
import logging
import inspect
import re
import html
from datetime import datetime
from PySide6.QtWidgets import (
    QMainWindow, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout, 
    QListWidget, QListWidgetItem, QPushButton, QLabel, QCheckBox,
    QSpinBox, QGroupBox, QTextEdit, QMessageBox, QSplitter, QFrame,
    QApplication, QInputDialog, QLineEdit, QComboBox
)
from app.generic_plugin_widget import GenericPluginWidget, ansi_to_html
from app.plugin_import_dialog import PluginImportDialog
from app.plugin_importer import PluginImporter
from PySide6.QtCore import Qt, Signal, QTimer, QSize, Slot
from PySide6.QtGui import QIcon, QColor, QPalette, QPainter, QPen, QPixmap, QPolygonF, QPainterPath
from PySide6.QtCore import QPointF

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 通用：创建左对齐、超出省略并带完整tooltip的标签
def _make_value_label(text: str, max_len: int = 80, elide_middle: bool = False) -> QLabel:
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

# 设计简洁可读的“可编辑”图标（自适应亮/暗主题）
def _make_edit_hint_icon(palette: QPalette, size: int = 16) -> QIcon:
    try:
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        painter = QPainter(pm)
        painter.setRenderHint(QPainter.Antialiasing, True)
        # 使用文本颜色，确保在亮/暗主题都有对比度
        color = palette.color(QPalette.ColorRole.Text)
        pen = QPen(color)
        pen.setWidthF(max(1.2, size * 0.08))
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)

        # 绘制斜向铅笔主体（45°），简洁线条
        path = QPainterPath()
        path.moveTo(size * 0.25, size * 0.72)
        path.lineTo(size * 0.68, size * 0.29)
        painter.drawPath(path)

        # 绘制铅笔尖（小三角）
        tri = QPolygonF()
        tri.append(QPointF(size * 0.68, size * 0.29))
        tri.append(QPointF(size * 0.85, size * 0.12))
        tri.append(QPointF(size * 0.80, size * 0.34))
        painter.setBrush(color)
        painter.drawPolygon(tri)

        # 底部短基线，暗示“编辑文本”含义
        pen2 = QPen(color)
        pen2.setWidthF(max(1.0, size * 0.07))
        painter.setPen(pen2)
        painter.drawLine(size * 0.20, size * 0.85, size * 0.55, size * 0.85)

        painter.end()
        return QIcon(pm)
    except Exception:
        # 兜底：返回一个空图标，外层可回退到字符
        return QIcon()


class PluginListItem(QListWidgetItem):
    """插件列表项"""
    
    def __init__(self, plugin, parent=None):
        super().__init__(parent)
        self.plugin = plugin
        # 使用自定义行部件展示文本，避免与item文字重叠
        self.setText("")
        self.setToolTip(plugin.description)
        self.setSizeHint(QSize(0, 36))  # 设置最小高度，改善显示效果
        self.update_status()
    
    def update_status(self, main_window=None):
        """更新插件状态显示"""
        # 检查是否有Tab显示（启用状态）
        is_tab_enabled = False
        if main_window and hasattr(main_window, 'plugin_ui_tabs'):
            is_tab_enabled = self.plugin.plugin_id in main_window.plugin_ui_tabs
        # 计算状态与颜色
        if self.plugin.is_running:
            status_suffix = " [运行中]"
            color = "#21cc44"
        elif is_tab_enabled:
            status_suffix = " [已启用]"
            color = "#21cc44"
        else:
            status_suffix = " [已停止]"
            color = "#ffffff" if getattr(main_window, 'is_dark_theme', False) else "#333333"

        # 应用到自定义行部件的名称标签
        try:
            list_widget = self.listWidget()
            if list_widget:
                row_widget = list_widget.itemWidget(self)
                if row_widget and hasattr(row_widget, '_name_label'):
                    row_widget._name_label.setText(f"{self.plugin.name}{status_suffix}")
                    # 仅改变文字颜色，避免影响布局/尺寸
                    row_widget._name_label.setStyleSheet(f"color: {color};")
        except Exception:
            pass
        # 保持item为可选、可用
        self.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)


class PluginControlPanel(QWidget):
    """插件控制面板"""
    
    def __init__(self, plugin, config_manager, main_window=None, parent=None):
        super().__init__(parent)
        self.plugin = plugin
        self.config_manager = config_manager
        self.main_window = main_window  # 保存主窗口引用
        self.init_ui()
    
    def init_ui(self):
        """初始化界面"""
        layout = QVBoxLayout(self)
        
        # 插件信息
        info_group = QGroupBox("插件信息")
        from PySide6.QtWidgets import QGridLayout
        info_layout = QGridLayout()
        info_layout.setHorizontalSpacing(8)
        info_layout.setVerticalSpacing(6)

        # 计算主程序文件、入口函数、更新日期
        entry_file_path = getattr(self.plugin, '_entry_module_path', None)
        entry_function = getattr(self.plugin, '_entry_function_name', None)
        if not entry_file_path:
            # 回退到类定义文件
            try:
                entry_file_path = inspect.getfile(self.plugin.__class__)
            except Exception:
                entry_file_path = "-"
        display_entry_file = entry_file_path if isinstance(entry_file_path, str) else "-"
        display_entry_func = entry_function if isinstance(entry_function, str) else "-"
        # 更新时间取主程序文件，否则取类定义文件
        try:
            ts = os.path.getmtime(display_entry_file) if display_entry_file and display_entry_file != "-" else None
        except Exception:
            ts = None
        if ts is None:
            try:
                ts = os.path.getmtime(inspect.getfile(self.plugin.__class__))
            except Exception:
                ts = None
        display_updated_at = datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S') if ts else "-"

        # 工具方法：左对齐且超出省略，悬停显示完整内容
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

        # 工具方法：创建左对齐、超出省略并带完整tooltip的标签（用于插件UI信息区）
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

        # 工具方法：创建左对齐、超出省略并带完整tooltip的标签（用于插件GUI信息区）
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

        # 工具方法：创建左对齐、超出省略并带完整tooltip的标签
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

        # 行1：名称
        info_layout.addWidget(QLabel("名称:"), 0, 0, Qt.AlignLeft)
        info_layout.addWidget(_make_value_label(self.plugin.name, 60), 0, 1)
        # 行2：描述（可编辑，使用配置覆盖显示）
        info_layout.addWidget(QLabel("描述:"), 1, 0, Qt.AlignLeft)
        try:
            curr_desc = self.config_manager.get_plugin_setting(self.plugin.plugin_id, 'description', self.plugin.description)
        except Exception:
            curr_desc = self.plugin.description
        self.desc_value_label = _make_value_label(curr_desc, 100)
        info_layout.addWidget(self.desc_value_label, 1, 1, 1, 2)
        # 使用自绘简洁图标作为编辑入口（适配明亮/暗黑）
        from PySide6.QtWidgets import QToolButton
        edit_btn = QToolButton()
        try:
            icon = _make_edit_hint_icon(self.palette())
            if not icon.isNull():
                edit_btn.setIcon(icon)
                edit_btn.setIconSize(QSize(16, 16))
            else:
                edit_btn.setText("✎")
        except Exception:
            edit_btn.setText("✎")
        edit_btn.setToolTip("编辑描述")
        # 去除可见边框/背景，仅显示图标
        try:
            edit_btn.setAutoRaise(True)
            edit_btn.setStyleSheet("QToolButton{border:none;background:transparent;padding:0;} QToolButton:hover{background:transparent;}")
            edit_btn.setFocusPolicy(Qt.NoFocus)
        except Exception:
            pass
        try:
            edit_btn.setFixedSize(24, 24)
        except Exception:
            pass
        edit_btn.clicked.connect(self.on_edit_description_clicked)
        info_layout.addWidget(edit_btn, 1, 3, Qt.AlignLeft)
        self.edit_desc_btn = edit_btn
        # 行3：界面/状态
        info_layout.addWidget(QLabel("界面:"), 2, 0, Qt.AlignLeft)
        info_layout.addWidget(QLabel('有' if self.plugin.has_ui else '无'), 2, 1)
        info_layout.addWidget(QLabel("状态:"), 3, 0, Qt.AlignLeft)
        info_layout.addWidget(QLabel('运行中' if self.plugin.is_running else '已停止'), 3, 1)
        # 行4：函数入口
        info_layout.addWidget(QLabel("函数入口:"), 4, 0, Qt.AlignLeft)
        info_layout.addWidget(_make_value_label(display_entry_func, 80), 4, 1)
        # 行5：插件更新日期
        info_layout.addWidget(QLabel("插件更新日期:"), 5, 0, Qt.AlignLeft)
        info_layout.addWidget(_make_value_label(display_updated_at, 80), 5, 1)
        # 行6：主程序文件（置底部）
        info_layout.addWidget(QLabel("主程序文件:"), 6, 0, Qt.AlignLeft)
        info_layout.addWidget(_make_value_label(display_entry_file, 100, elide_middle=True), 6, 1, 1, 3)

        info_group.setLayout(info_layout)
        
        # 启动控制
        control_group = QGroupBox("启动控制")
        control_layout = QVBoxLayout()
        
        # 自动启动选项布局
        self.auto_start_checkbox = QCheckBox("随主程序自动启动界面")
        self.auto_start_checkbox.setChecked(self.config_manager.is_plugin_auto_start(self.plugin.plugin_id))
        self.auto_start_checkbox.stateChanged.connect(self.on_auto_start_changed)
        
        self.auto_run_checkbox = QCheckBox("启动后自动运行")
        self.auto_run_checkbox.setChecked(self.config_manager.get_plugin_setting(self.plugin.plugin_id, 'auto_run', False))
        self.auto_run_checkbox.stateChanged.connect(self.on_auto_run_changed)
        
        # 设置依赖关系：只有勾选了自动启动界面才能勾选自动运行
        self.auto_run_checkbox.setEnabled(self.auto_start_checkbox.isChecked())
        
        control_layout.addWidget(self.auto_start_checkbox)
        control_layout.addWidget(self.auto_run_checkbox)
        
        order_layout = QHBoxLayout()
        order_layout.addWidget(QLabel("启动顺序:"))
        self.order_spinbox = QSpinBox()
        self.order_spinbox.setRange(0, 999)
        self.order_spinbox.setValue(self.config_manager.get_plugin_start_order(self.plugin.plugin_id))
        self.order_spinbox.valueChanged.connect(self.on_order_changed)
        order_layout.addWidget(self.order_spinbox)
        order_layout.addStretch()
        
        # Python解释器选择
        python_env_layout = QHBoxLayout()
        python_env_layout.addWidget(QLabel("Python解释器:"))
        self.python_env_combo = QComboBox()
        self.python_env_combo.addItem("使用默认解释器", None)
        self._refresh_python_env_combo()
        self.python_env_combo.currentIndexChanged.connect(self.on_python_env_changed)
        python_env_layout.addWidget(self.python_env_combo)
        python_env_layout.addStretch()
        
        button_layout = QHBoxLayout()
        self.start_button = QPushButton("启用")
        self.stop_button = QPushButton("停用")
        self.uninstall_button = QPushButton("卸载插件")
        self.update_button = QPushButton("更新插件")
        self.start_button.clicked.connect(self.on_start_clicked)
        self.stop_button.clicked.connect(self.on_stop_clicked)
        self.uninstall_button.clicked.connect(self.on_uninstall_clicked)
        self.update_button.clicked.connect(self.on_update_clicked)
        self.update_button_state()
        
        button_layout.addWidget(self.start_button)
        button_layout.addWidget(self.stop_button)
        button_layout.addWidget(self.uninstall_button)
        button_layout.addWidget(self.update_button)
        button_layout.addStretch()
        
        control_layout.addLayout(order_layout)
        control_layout.addLayout(python_env_layout)
        control_layout.addLayout(button_layout)
        control_group.setLayout(control_layout)
        
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
        
        layout.addWidget(info_group)
        layout.addWidget(control_group)
        layout.addWidget(log_group, 1)
        
        # 连接插件信号
        self.plugin.signals.status_changed.connect(self.on_status_changed)
        # 日志输出通过主窗口统一转发至当前控制面板与通用Tab，避免重复追加
        self.plugin.signals.error_occurred.connect(self.on_error_occurred)
        
        # 加载历史日志（去除ANSI，输出纯文本）
        if hasattr(self.plugin, 'log_history'):
            for log_message in self.plugin.log_history:
                try:
                    self._append_log_with_color(log_message)
                except Exception:
                    try:
                        plain_text = str(log_message).replace("\n", " ").replace("\r", " ")
                        self.log_text.append(plain_text)
                    except Exception:
                        pass

    def prepare_for_input(self, prompt: str, default_text: str = "", password: bool = False):
        """在输入行展示提示并聚焦。"""
        try:
            if hasattr(self, 'input_edit') and self.input_edit:
                self.input_edit.setPlaceholderText(prompt or "在此输入并提交给脚本…")
                if default_text:
                    self.input_edit.setText(default_text)
                self.input_edit.setFocus()
        except Exception:
            pass

    def on_send_input_clicked(self):
        """将手动输入提交给等待中的脚本。"""
        try:
            text = self.input_edit.text() if hasattr(self, 'input_edit') else ""
            if hasattr(self, 'main_window') and self.main_window and hasattr(self.main_window, 'submit_manual_input'):
                self.main_window.submit_manual_input(self.plugin.plugin_id, text)
            self.input_edit.clear()
        except Exception:
            pass
    
    def update_button_state(self):
        """更新按钮状态"""
        # 启用状态：只要该插件已有Tab被展示，即视为“已启用”
        is_ui_enabled = False
        if hasattr(self, 'main_window') and self.main_window and hasattr(self.main_window, 'plugin_ui_tabs'):
            is_ui_enabled = self.plugin.plugin_id in self.main_window.plugin_ui_tabs
        # “启用”仅在未展示时可用；“停用”在已展示或正在运行时可用
        self.start_button.setEnabled(not is_ui_enabled)
        self.stop_button.setEnabled(is_ui_enabled or self.plugin.is_running)
    
    def on_auto_start_changed(self, state):
        """自动启动设置改变"""
        auto_start = state == 2
        self.config_manager.set_plugin_auto_start(self.plugin.plugin_id, auto_start)
        
        # 如果取消自动启动界面，则自动取消自动运行
        if not auto_start:
            self.auto_run_checkbox.setChecked(False)
            self.config_manager.set_plugin_setting(self.plugin.plugin_id, 'auto_run', False)
        
        # 更新自动运行勾选框的可用状态
        self.auto_run_checkbox.setEnabled(auto_start)
    
    def on_auto_run_changed(self, state):
        """自动运行设置改变"""
        auto_run = state == 2
        self.config_manager.set_plugin_setting(self.plugin.plugin_id, 'auto_run', auto_run)
    
    def on_order_changed(self, order):
        """启动顺序改变"""
        self.config_manager.set_plugin_start_order(self.plugin.plugin_id, order)
    
    def on_start_clicked(self):
        """启用按钮点击：仅启动界面；若勾选“启动后自动运行”则再运行"""
        # 先显示插件界面
        if hasattr(self, 'main_window') and self.main_window:
            self.main_window._show_plugin_tab(self.plugin)
        else:
            try:
                # 兜底：尝试父级链查找
                p = self.parent()
                while p is not None and not hasattr(p, '_show_plugin_tab'):
                    p = p.parent()
                if p is not None:
                    p._show_plugin_tab(self.plugin)
            except Exception:
                pass

        # 清空右侧控制面板日志（若存在）
        try:
            if hasattr(self, 'log_text') and self.log_text:
                self.log_text.clear()
        except Exception:
            pass

        # 仅当勾选“启动后自动运行”时才启动任务
        try:
            should_auto_run = getattr(self, 'auto_run_checkbox', None) is not None and self.auto_run_checkbox.isChecked()
        except Exception:
            should_auto_run = False

        if should_auto_run:
            if not self.plugin.has_ui and getattr(self.plugin, 'parameters', {}) is not None and hasattr(self, 'main_window') and self.main_window and hasattr(self.main_window, '_start_plugin_with_params'):
                self.main_window._start_plugin_with_params(self.plugin)
            else:
                # 启动前清空插件内部日志
                try:
                    if hasattr(self.plugin, 'log_history'):
                        self.plugin.log_history = []
                except Exception:
                    pass
                # 清空通用界面日志
                try:
                    if hasattr(self.plugin, '_generic_widget') and self.plugin._generic_widget and hasattr(self.plugin._generic_widget, 'clear_log'):
                        self.plugin._generic_widget.clear_log()
                except Exception:
                    pass
                self.plugin.start()
        
        # 刷新按钮可用状态
        self.update_button_state()
        # 更新插件列表状态显示
        if hasattr(self, 'main_window') and self.main_window:
            self.main_window._update_plugin_list_status(self.plugin.plugin_id)
    
    def on_uninstall_clicked(self):
        """卸载按钮点击：确认并执行卸载"""
        reply = QMessageBox.question(
            self,
            "确认卸载",
            f"确定要卸载插件 '{self.plugin.name}' 吗？这将删除其文件和配置。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            try:
                if hasattr(self, 'main_window') and self.main_window:
                    self.main_window._uninstall_plugin(self.plugin)
            except Exception as e:
                QMessageBox.critical(self, "卸载失败", f"卸载插件时出错：{str(e)}")

    def on_update_clicked(self):
        """更新按钮点击：弹出导入框，预填当前插件信息和参数配置，加速替换导入。"""
        try:
            plugin = self.plugin
            # 构造导入对话框
            dlg = PluginImportDialog(self)
            # 预填：名称/ID（更新场景锁定不被后续覆盖）
            try:
                if hasattr(dlg, 'set_update_identity'):
                    dlg.set_update_identity(plugin.name, plugin.plugin_id)
                else:
                    dlg.plugin_name_edit.setText(plugin.name)
                    setattr(dlg, '_plugin_id_user_edited', True)
                    dlg.plugin_id_edit.setText(plugin.plugin_id)
                    try:
                        dlg.plugin_id_edit.setReadOnly(True)
                    except Exception:
                        pass
            except Exception:
                pass
            # 预填：插件类型（决定是否显示参数区域）
            try:
                dlg.plugin_type_combo.setCurrentIndex(1 if plugin.has_ui else 0)
            except Exception:
                pass
            # 预填：首选入口文件与函数（用户选择文件夹后会自动选中）
            try:
                entry_path = getattr(plugin, '_entry_module_path', None)
                preferred_entry = None
                if isinstance(entry_path, str) and entry_path:
                    preferred_entry = os.path.basename(entry_path)
                preferred_func = getattr(plugin, '_entry_function_name', None)
                if hasattr(dlg, 'set_preferred_entry_and_function'):
                    dlg.set_preferred_entry_and_function(preferred_entry, preferred_func if isinstance(preferred_func, str) else None)
            except Exception:
                pass

            # 预填：原插件目录，并立即解析入口文件/函数（无需手动浏览）
            try:
                plugin_dir = None
                if isinstance(entry_path, str) and entry_path:
                    plugin_dir = os.path.dirname(entry_path)
                if not plugin_dir:
                    import inspect as _inspect
                    try:
                        cls_file = _inspect.getfile(plugin.__class__)
                        plugin_dir = os.path.dirname(cls_file)
                    except Exception:
                        plugin_dir = None
                if plugin_dir and os.path.isdir(plugin_dir):
                    dlg.folder_path_edit.setText(plugin_dir)
                    # 触发文件发现并根据首选项自动选择入口文件/函数
                    dlg.discover_python_files(plugin_dir)
            except Exception:
                pass
            # 预填：参数定义与已保存值（仅无界面插件显示参数）
            try:
                if not plugin.has_ui:
                    # 清空默认的测试参数小部件
                    try:
                        layout = dlg.params_list_layout
                        while layout.count():
                            item = layout.takeAt(0)
                            w = item.widget()
                            if w:
                                w.setParent(None)
                        # 同步重置参数列表，避免首个索引从2开始
                        if hasattr(dlg, 'plugin_info') and isinstance(dlg.plugin_info, dict):
                            dlg.plugin_info['parameters'] = []
                    except Exception:
                        pass
                    # 读取配置：定义覆盖与已保存值
                    full_cfg = self.config_manager.load_plugin_config(plugin.plugin_id, {}) or {}
                    override_defs = full_cfg.get('__definitions__', {}) if isinstance(full_cfg, dict) else {}
                    saved_values = {}
                    if '__definitions__' in full_cfg:
                        saved_values = full_cfg.get('__values__', {}) or {}
                    else:
                        # 旧格式：cfg 即为 values
                        if isinstance(full_cfg, dict):
                            saved_values = dict(full_cfg)
                    base_defs = getattr(plugin, 'parameters', {}) or {}
                    param_defs = override_defs if override_defs else base_defs
                    # 构建参数小部件
                    for name, info in (param_defs or {}).items():
                        w = dlg.add_parameter()
                        if not w:
                            continue
                        try:
                            w.name_edit.setText(str(name))
                            w.type_combo.setCurrentText(str(info.get('type', 'string')))
                            w.label_edit.setText(str(info.get('label', name)))
                            w.description_edit.setText(str(info.get('description', '')))
                            # 合并值
                            value = saved_values.get(name, info.get('value', ''))
                            w.value_edit.setText(str(value))
                            # min/max
                            if info.get('type') in ('integer', 'float'):
                                if info.get('min') is not None:
                                    w.min_edit.setText(str(info.get('min')))
                                if info.get('max') is not None:
                                    w.max_edit.setText(str(info.get('max')))
                            # options
                            if info.get('type') == 'select':
                                lines = []
                                for opt in info.get('options', []) or []:
                                    if isinstance(opt, (list, tuple)) and len(opt) == 2:
                                        v, lbl = opt[0], opt[1]
                                        lines.append(f"{v},{lbl}")
                                    else:
                                        lines.append(str(opt))
                                dlg.params_list_layout.itemAt(dlg.params_list_layout.count()-1).widget().options_edit.setText("\n".join(lines))
                        except Exception:
                            pass
            except Exception:
                pass

            # 弹出对话框
            if dlg.exec():
                info = dlg.get_plugin_info()
                # 执行导入（复制并覆盖同名插件目录，保持参数配置）
                importer = PluginImporter(self.main_window.plugin_manager.plugins_dir if hasattr(self, 'main_window') and self.main_window else self.config_manager.plugins_dir if hasattr(self.config_manager, 'plugins_dir') else os.path.join(os.getcwd(), 'plugins'))
                ok, err = importer.import_plugin(info)
                if ok:
                    # 文件已覆盖，执行非中断式更新（不影响其他插件）
                    try:
                        if hasattr(self, 'main_window') and self.main_window:
                            self.main_window._update_plugin(self.plugin)
                    except Exception:
                        pass
                    QMessageBox.information(self, "更新成功", f"插件 '{plugin.name}' 已替换导入")
                else:
                    QMessageBox.critical(self, "更新失败", f"导入时出错：{err}")
        except Exception as e:
            QMessageBox.critical(self, "更新失败", f"更新插件时出错：{str(e)}")

    def on_stop_clicked(self):
        """停用按钮点击：强制终止插件并移除Tab"""
        if hasattr(self.plugin, 'kill'):
            self.plugin.kill()
        else:
            self.plugin.stop(wait=False)
        if hasattr(self, 'main_window') and self.main_window:
            self.main_window._remove_plugin_tab(self.plugin)
        # 刷新按钮可用状态
        self.update_button_state()
        # 更新插件列表状态显示
        if hasattr(self, 'main_window') and self.main_window:
            self.main_window._update_plugin_list_status(self.plugin.plugin_id)
    
    def on_status_changed(self, plugin_id, status):
        """状态改变回调"""
        if plugin_id == self.plugin.plugin_id:
            self.update_button_state()
            for child in self.findChildren(QLabel):
                if child.text().startswith("状态:"):
                    child.setText(f"状态: {status}")
    
    def _append_log_with_color(self, message: str):
        """添加日志信息，支持 ANSI 彩色文本"""
        try:
            if message is None:
                return
            # 将 ANSI 转义序列转换为 HTML 格式
            html_text = ansi_to_html(str(message))
            if html_text:
                # 使用 span + white-space:pre 保留连续空格/制表符/换行
                self.log_text.append(f'<span style="white-space:pre;">{html_text}</span>')
        except Exception:
            # 降级处理：如果转换失败，尝试直接添加文本
            try:
                plain_text = str(message).replace("\n", "<br>").replace("\r", "")
                if plain_text:
                    self.log_text.append(plain_text)
            except Exception:
                pass
    def on_output_generated(self, plugin_id, output):
        """输出产生回调"""
        if plugin_id == self.plugin.plugin_id:
            self._append_log_with_color(output)
    
    def on_error_occurred(self, plugin_id, error_message):
        """错误发生回调"""
        if plugin_id == self.plugin.plugin_id:
            self.log_text.append(f"错误: {error_message}")
            QMessageBox.warning(self, "插件错误", f"插件 {self.plugin.name} 发生错误:\n{error_message}")

    def on_edit_description_clicked(self):
        """编辑插件描述并保存到配置"""
        try:
            from PySide6.QtWidgets import QInputDialog
            curr = self.config_manager.get_plugin_setting(self.plugin.plugin_id, 'description', self.plugin.description)
            text, ok = QInputDialog.getMultiLineText(self, "编辑插件描述", "插件描述：", curr or "")
            if ok:
                self.config_manager.set_plugin_setting(self.plugin.plugin_id, 'description', text or "")
                # 更新本面板显示
                try:
                    if hasattr(self, 'desc_value_label') and self.desc_value_label:
                        self.desc_value_label.setText(text or "")
                        self.desc_value_label.setToolTip(text or "")
                except Exception:
                    pass
                # 更新左侧列表项 tooltip
                try:
                    list_widget = self.main_window.plugin_list if hasattr(self, 'main_window') and self.main_window else None
                    if list_widget:
                        for i in range(list_widget.count()):
                            item = list_widget.item(i)
                            if hasattr(item, 'plugin') and item.plugin.plugin_id == self.plugin.plugin_id:
                                item.setToolTip(text or "")
                                break
                except Exception:
                    pass
        except Exception:
            pass
    
    def _refresh_python_env_combo(self):
        """刷新Python解释器选择下拉框"""
        if not hasattr(self, 'python_env_combo'):
            return
        
        # 保存当前选择
        current_env_id = None
        current_index = self.python_env_combo.currentIndex()
        if current_index >= 0:
            current_env_id = self.python_env_combo.currentData()
        
        # 清空并重新填充
        self.python_env_combo.clear()
        self.python_env_combo.addItem("使用默认解释器", None)
        
        # 从环境管理器获取所有环境
        if hasattr(self, 'main_window') and self.main_window:
            env_manager = self.main_window.python_env_widget.get_environment_manager()
            environments = env_manager.get_all_environments()
            for env_id, env_data in environments.items():
                display_name = f"{env_data.get('name', '')} ({env_data.get('version', '')})"
                self.python_env_combo.addItem(display_name, env_id)
        
        # 恢复选择
        if current_env_id is not None:
            for i in range(self.python_env_combo.count()):
                if self.python_env_combo.itemData(i) == current_env_id:
                    self.python_env_combo.setCurrentIndex(i)
                    break
        else:
            # 加载保存的配置
            saved_env_id = self.config_manager.get_plugin_python_env(self.plugin.plugin_id)
            if saved_env_id:
                for i in range(self.python_env_combo.count()):
                    if self.python_env_combo.itemData(i) == saved_env_id:
                        self.python_env_combo.setCurrentIndex(i)
                        break
    
    def on_python_env_changed(self):
        """Python解释器选择改变"""
        if not hasattr(self, 'python_env_combo'):
            return
        env_id = self.python_env_combo.currentData()
        self.config_manager.set_plugin_python_env(self.plugin.plugin_id, env_id)


class PluginUIWidget(QWidget):
    """插件UI容器"""
    
    def __init__(self, plugin, parent=None):
        super().__init__(parent)
        self.plugin = plugin
        self.plugin_widget = None
        self.init_ui()
    
    def init_ui(self):
        """初始化界面"""
        layout = QVBoxLayout(self)
        
        # 顶部插件信息（与通用面板一致的字段）
        from PySide6.QtWidgets import QGroupBox, QGridLayout
        info_group = QGroupBox("插件信息")
        info_layout = QGridLayout()
        info_layout.setHorizontalSpacing(8)
        info_layout.setVerticalSpacing(6)

        # 计算主程序文件、入口函数、更新日期
        entry_file_path = getattr(self.plugin, '_entry_module_path', None)
        entry_function = getattr(self.plugin, '_entry_function_name', None)
        if not entry_file_path:
            try:
                entry_file_path = inspect.getfile(self.plugin.__class__)
            except Exception:
                entry_file_path = "-"
        display_entry_file = entry_file_path if isinstance(entry_file_path, str) else "-"
        display_entry_func = entry_function if isinstance(entry_function, str) else "-"
        try:
            ts = os.path.getmtime(display_entry_file) if display_entry_file and display_entry_file != "-" else None
        except Exception:
            ts = None
        if ts is None:
            try:
                ts = os.path.getmtime(inspect.getfile(self.plugin.__class__))
            except Exception:
                ts = None
        display_updated_at = datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S') if ts else "-"

        # 行：名称 / ID
        info_layout.addWidget(QLabel("名称:"), 0, 0, Qt.AlignLeft)
        info_layout.addWidget(_make_value_label(self.plugin.name, 60), 0, 1)
        info_layout.addWidget(QLabel("ID:"), 0, 2, Qt.AlignLeft)
        info_layout.addWidget(_make_value_label(self.plugin.plugin_id, 60), 0, 3)
        # 行：函数入口 / 更新日期
        info_layout.addWidget(QLabel("函数入口:"), 1, 0, Qt.AlignLeft)
        info_layout.addWidget(_make_value_label(display_entry_func, 80), 1, 1)
        info_layout.addWidget(QLabel("插件更新日期:"), 1, 2, Qt.AlignLeft)
        info_layout.addWidget(_make_value_label(display_updated_at, 80), 1, 3)
        # 行：主程序文件（置底部）
        info_layout.addWidget(QLabel("主程序文件:"), 2, 0, Qt.AlignLeft)
        info_layout.addWidget(_make_value_label(display_entry_file, 100, elide_middle=True), 2, 1, 1, 3)
        info_group.setLayout(info_layout)
        # 固定“插件信息”区域高度，防止随内容伸缩
        try:
            info_group.setFixedHeight(150)
        except Exception:
            pass
        layout.addWidget(info_group)

        if self.plugin.has_ui:
            try:
                self.plugin_widget = self.plugin.create_ui(self)
                if self.plugin_widget:
                    layout.addWidget(self.plugin_widget)
                else:
                    layout.addWidget(QLabel("插件UI创建失败"))
            except Exception as e:
                logger.error(f"创建插件 {self.plugin.name} UI失败: {str(e)}")
                layout.addWidget(QLabel(f"创建UI失败: {str(e)}"))
        else:
            layout.addWidget(QLabel("此插件没有界面"))
            layout.addStretch()


from app.status_monitor import StatusMonitorWidget
from app.python_env_widget import PythonEnvironmentWidget


class MainWindow(QMainWindow):
    """主窗口"""
    
    def __init__(self, plugin_manager, config_manager, parent=None):
        super().__init__(parent)
        self.plugin_manager = plugin_manager
        self.config_manager = config_manager
        # 检测系统主题
        self.is_dark_theme = self._detect_system_theme()
        self.setWindowTitle("Python脚本管理工具")
        
        # 初始化状态监控组件
        self.status_monitor = StatusMonitorWidget(self.plugin_manager)
        
        # 设置环境管理器引用到BasePlugin，以便插件可以访问
        from app.plugin_manager import BasePlugin
        BasePlugin._env_manager_ref = lambda: self.python_env_widget.get_environment_manager() if hasattr(self, 'python_env_widget') else None
        
        self.setup_ui()
        
        # 重新设置环境管理器引用（setup_ui后python_env_widget才创建）
        BasePlugin._env_manager_ref = lambda: self.python_env_widget.get_environment_manager()
        # 应用主题（根据配置）
        self._apply_theme(self.config_manager.get_theme())
        # 应用保存的字体大小
        self.apply_font_size(self.config_manager.get_font_size())
        
        # 连接信号
        self.plugin_manager.signals.status_changed.connect(self.on_plugin_status_changed)
        self.plugin_manager.signals.error_occurred.connect(self.on_plugin_error)
        self.plugin_manager.signals.output_generated.connect(self.on_plugin_output)
        
        # 连接状态监控信号
        self.status_monitor.plugin_selected.connect(self.on_plugin_selected_in_monitor)
        
        # 将所有插件添加到状态监控
        for plugin in self._get_plugins_in_display_order():
            self.status_monitor.add_plugin(plugin.plugin_id, plugin.name)
            self.status_monitor.update_plugin_status(plugin.plugin_id, "运行中" if plugin.is_running else "已停止")
            # 连接输入请求信号（全局处理，确保即使未打开控制面板也能弹窗）
            try:
                plugin.signals.input_requested.connect(self.on_plugin_input_requested)
            except Exception:
                pass
        
        # 自动启动设置为自动启动的插件
        self._auto_start_plugins()
        
        # 加载窗口配置
        self.load_window_config()
    
    def _auto_start_plugins(self):
        """自动启动设置为自动启动的插件"""
        plugins = self.config_manager.get_plugins_in_start_order(self.plugin_manager.get_all_plugins())
        for plugin in plugins:
            if self.config_manager.is_plugin_auto_start(plugin.plugin_id):
                # 先显示Tab界面
                self._show_plugin_tab(plugin)
                
                # 检查是否需要自动运行插件
                auto_run = self.config_manager.get_plugin_setting(plugin.plugin_id, 'auto_run', False)
                if auto_run:
                    # 自动运行插件
                    if not plugin.has_ui and getattr(plugin, 'parameters', {}) is not None:
                        self._start_plugin_with_params(plugin)
                    else:
                        plugin.start()
                    logger.info(f"自动启动插件: {plugin.name} (自动运行)")
                else:
                    logger.info(f"自动启动插件: {plugin.name} (仅启动界面)")
    
    def _setup_menu(self):
        """（已弃用）原视图菜单，保留空实现以避免调用错误"""
        pass
    
    def on_font_size_changed(self, font_size):
        """处理字体大小变化"""
        # 改为点击“应用”后才生效，此处不做实时应用
        pass
    
    def apply_font_size(self, font_size):
        """应用字体大小到所有控件"""
        app = QApplication.instance()
        if app:
            # 首先设置应用程序全局字体
            font = app.font()
            font.setPointSize(font_size)
            app.setFont(font)
            
            # 使用更有效的方式更新所有控件
            self._update_widget_font_recursive(self, font_size)
            # 避免强制 processEvents 引发卡顿，由事件循环自然刷新
    
    def _update_widget_font_recursive(self, parent_widget, font_size):
        """递归更新所有子控件的字体大小"""
        # 更新当前控件的字体
        if parent_widget != self or isinstance(parent_widget, (QLabel, QPushButton, QTextEdit, QListWidget, QTabWidget)):
            widget_font = parent_widget.font()
            widget_font.setPointSize(font_size)
            parent_widget.setFont(widget_font)
        
        # 递归更新所有子控件
        for child in parent_widget.findChildren(QWidget):
            # 避免循环引用和不必要的处理
            if child != self and not isinstance(child, (QMainWindow, QApplication)):
                self._update_widget_font_recursive(child, font_size)
                # 对特殊控件类型进行额外处理
                if isinstance(child, QTabWidget):
                    # 确保标签页内容也更新
                    for i in range(child.count()):
                        tab_widget = child.widget(i)
                        if tab_widget:
                            self._update_widget_font_recursive(tab_widget, font_size)
                # 避免逐控件 repaint/updateGeometry 引发卡顿，交由Qt自动刷新
    
    def _detect_system_theme(self):
        """检测系统主题是否为暗黑模式"""
        # 获取应用程序样式
        app = QApplication.instance()
        if app:
            # 简单检测：检查默认背景色是否为深色
            palette = app.palette()
            background_color = palette.color(QPalette.ColorRole.Window)
            # 计算亮度，低于128认为是深色主题
            brightness = (background_color.red() * 299 + 
                         background_color.green() * 587 + 
                         background_color.blue() * 114) / 1000
            return brightness < 128
        return False
    
    def _apply_theme(self, theme: str | None = None):
        """应用主题: 'light' | 'dark' | 'default'"""
        app = QApplication.instance()
        if not app:
            return
        # 解析主题
        effective = theme or 'default'
        if effective not in ('light', 'dark', 'default'):
            effective = 'default'
        if effective == 'default':
            use_dark = bool(self.is_dark_theme)
        else:
            use_dark = (effective == 'dark')
        self.is_dark_theme = use_dark

        pal = app.palette()
        if use_dark:
            pal = QPalette()
            pal.setColor(QPalette.Window, QColor(53, 53, 53))
            pal.setColor(QPalette.WindowText, QColor(220, 220, 220))
            pal.setColor(QPalette.Base, QColor(42, 42, 42))
            pal.setColor(QPalette.AlternateBase, QColor(66, 66, 66))
            pal.setColor(QPalette.ToolTipBase, QColor(53, 53, 53))
            pal.setColor(QPalette.ToolTipText, QColor(220, 220, 220))
            pal.setColor(QPalette.Text, QColor(220, 220, 220))
            # 占位符文本颜色（修复 Win10 暗黑模式下输入框文字/占位符过暗的问题）
            try:
                pal.setColor(QPalette.PlaceholderText, QColor(160, 160, 160))
            except Exception:
                pass
            pal.setColor(QPalette.Button, QColor(53, 53, 53))
            pal.setColor(QPalette.ButtonText, QColor(220, 220, 220))
            pal.setColor(QPalette.BrightText, QColor(255, 0, 0))
            pal.setColor(QPalette.Highlight, QColor(42, 130, 218))
            pal.setColor(QPalette.HighlightedText, QColor(0, 0, 0))
        else:
            pal = QPalette()  # 使用系统默认亮色
        app.setPalette(pal)

        # 异步刷新依赖主题的控件样式（避免阻塞）
        QTimer.singleShot(0, self._refresh_row_styles)

    def _refresh_row_styles(self):
        """刷新可用插件行部件的箭头颜色与名称颜色"""
        normal_color = "#ffffff" if getattr(self, 'is_dark_theme', False) else "#333333"
        disabled_color = "#666666" if getattr(self, 'is_dark_theme', False) else "#aaaaaa"
        arrow_style = (
            f"QToolButton{{color:{normal_color}; font-size:16px; font-weight:600; padding:0;}} "
            f"QToolButton:disabled{{color:{disabled_color};}}"
        )
        try:
            for i in range(self.plugin_list.count()):
                item = self.plugin_list.item(i)
                widget = self.plugin_list.itemWidget(item)
                if not widget:
                    continue
                if hasattr(widget, '_up_btn'):
                    widget._up_btn.setStyleSheet(arrow_style)
                if hasattr(widget, '_down_btn'):
                    widget._down_btn.setStyleSheet(arrow_style)
                # 同步名称颜色与状态
                if hasattr(item, 'update_status'):
                    item.update_status(self)
        except Exception:
            pass

    def on_theme_toggled(self, state):
        """界面设置：切换明亮/暗黑主题"""
        use_dark = state == 2
        self.config_manager.set_theme('dark' if use_dark else 'light')
        self._apply_theme('dark' if use_dark else 'light')

    def on_light_mode_selected(self, state):
        """选择明亮主题（与暗黑互斥）"""
        if state == 2:
            try:
                if hasattr(self, 'dark_checkbox'):
                    self.dark_checkbox.blockSignals(True)
                    self.dark_checkbox.setChecked(False)
                    self.dark_checkbox.blockSignals(False)
            except Exception:
                pass
            self.config_manager.set_theme('light')
            self._apply_theme('light')
        elif state == 0:
            # 防止两者都未选：若两者均未选，恢复当前有效主题
            if hasattr(self, 'dark_checkbox') and not self.dark_checkbox.isChecked():
                self.light_checkbox.blockSignals(True)
                self.light_checkbox.setChecked(True if not getattr(self, 'is_dark_theme', False) else False)
                self.light_checkbox.blockSignals(False)

    def on_dark_mode_selected(self, state):
        """选择暗黑主题（与明亮互斥）"""
        if state == 2:
            try:
                if hasattr(self, 'light_checkbox'):
                    self.light_checkbox.blockSignals(True)
                    self.light_checkbox.setChecked(False)
                    self.light_checkbox.blockSignals(False)
            except Exception:
                pass
            self.config_manager.set_theme('dark')
            self._apply_theme('dark')
        elif state == 0:
            if hasattr(self, 'light_checkbox') and not self.light_checkbox.isChecked():
                self.dark_checkbox.blockSignals(True)
                self.dark_checkbox.setChecked(True if getattr(self, 'is_dark_theme', False) else False)
                self.dark_checkbox.blockSignals(False)
    
    def setup_ui(self):
        """设置UI界面"""
        # 创建中心部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 主布局
        main_layout = QVBoxLayout(central_widget)
        
        
        # 创建选项卡
        self.tab_widget = QTabWidget()
        
        # 插件管理选项卡
        self.plugin_tab = QWidget()
        self.setup_plugin_tab()
        self.tab_widget.addTab(self.plugin_tab, "插件管理")
        
        # Python环境管理选项卡
        self.python_env_widget = PythonEnvironmentWidget(self.config_manager, self)
        self.python_env_widget.environment_changed.connect(self.on_python_env_changed)
        self.tab_widget.addTab(self.python_env_widget, "Python环境管理")
        
        # 状态监控选项卡
        self.tab_widget.addTab(self.status_monitor, "状态监控")
        
        # 插件UI选项卡字典
        self.plugin_ui_tabs = {}
        
        # 添加到主布局
        main_layout.addWidget(self.tab_widget)
    
    def setup_plugin_tab(self):
        """设置插件管理选项卡"""
        # 创建分割器
        splitter = QSplitter(Qt.Horizontal)
        
        # 左侧插件列表
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        
        self.plugin_list = QListWidget()
        self.plugin_list.setAlternatingRowColors(True)
        self.plugin_list.setSelectionMode(QListWidget.SingleSelection)  # 确保单选
        self.plugin_list.setFocusPolicy(Qt.StrongFocus)  # 确保焦点正常
        # 取消拖动排序，改为按钮控制
        self.plugin_list.setDragEnabled(False)
        self.plugin_list.setAcceptDrops(False)
        self.plugin_list.setDropIndicatorShown(False)
        self.plugin_list.setDragDropMode(QListWidget.NoDragDrop)
        self.plugin_list.currentItemChanged.connect(self.on_plugin_selected)
        # 双击启用/停用插件
        try:
            self.plugin_list.itemDoubleClicked.connect(self.on_plugin_item_double_clicked)
        except Exception:
            pass
        
        # 按记忆顺序加载插件
        all_plugins = {p.plugin_id: p for p in self.plugin_manager.get_all_plugins()}
        ordered_ids = self.config_manager.get_plugin_list_order()
        for pid in ordered_ids:
            if pid in all_plugins:
                self._add_plugin_list_row(all_plugins[pid])
                del all_plugins[pid]
        for p in all_plugins.values():
            self._add_plugin_list_row(p)
        
        # 操作按钮
        button_layout = QHBoxLayout()
        self.start_all_button = QPushButton("全部启动")
        self.stop_all_button = QPushButton("全部停止")
        self.refresh_button = QPushButton("刷新列表")
        self.import_button = QPushButton("导入插件")
        
        self.start_all_button.clicked.connect(self.on_start_all_clicked)
        self.stop_all_button.clicked.connect(self.on_stop_all_clicked)
        self.refresh_button.clicked.connect(self.on_refresh_clicked)
        self.import_button.clicked.connect(self.on_import_clicked)
        
        button_layout.addWidget(self.start_all_button)
        button_layout.addWidget(self.stop_all_button)
        button_layout.addWidget(self.refresh_button)
        button_layout.addWidget(self.import_button)
        
        left_layout.addWidget(QLabel("可用插件:"))
        left_layout.addWidget(self.plugin_list, 1)
        left_layout.addLayout(button_layout)
        
        # 界面设置区：放在“可用插件”列表下方
        appearance_group = QGroupBox("界面设置")
        appearance_layout = QVBoxLayout()
        appearance_layout.setContentsMargins(8, 6, 8, 6)
        # 上行：主题单选（两个checkbox互斥）
        theme_row = QHBoxLayout()
        theme_row.setContentsMargins(0, 0, 0, 0)
        theme_row.addWidget(QLabel("主题："))
        self.light_checkbox = QCheckBox("明亮")
        self.dark_checkbox = QCheckBox("暗黑")
        initial_theme = self.config_manager.get_theme()
        if initial_theme == 'default':
            if bool(self.is_dark_theme):
                self.dark_checkbox.setChecked(True)
            else:
                self.light_checkbox.setChecked(True)
        else:
            if initial_theme == 'dark':
                self.dark_checkbox.setChecked(True)
            else:
                self.light_checkbox.setChecked(True)
        self.light_checkbox.stateChanged.connect(self.on_light_mode_selected)
        self.dark_checkbox.stateChanged.connect(self.on_dark_mode_selected)
        theme_row.addWidget(self.light_checkbox)
        theme_row.addWidget(self.dark_checkbox)
        theme_row.addStretch()
        appearance_layout.addLayout(theme_row)
        # 下行：字体大小与应用
        font_row = QHBoxLayout()
        font_row.setContentsMargins(0, 0, 0, 0)
        font_label2 = QLabel("字体大小：")
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(8, 32)
        self.font_size_spin.setSingleStep(1)
        self.font_size_spin.setValue(self.config_manager.get_font_size())
        # 不在 valueChanged 时应用，仅在点击“应用”时应用
        self.font_apply_btn = QPushButton("应用")
        self.font_apply_btn.clicked.connect(self.on_apply_font_size_clicked)
        font_row.addWidget(font_label2)
        font_row.addWidget(self.font_size_spin)
        font_row.addStretch()
        font_row.addWidget(self.font_apply_btn)
        appearance_layout.addLayout(font_row)
        appearance_group.setLayout(appearance_layout)
        left_layout.addWidget(appearance_group)
        
        # 右侧插件控制
        self.right_widget = QWidget()
        self.right_layout = QVBoxLayout(self.right_widget)
        self.right_layout.addWidget(QLabel("请选择一个插件查看详情"))
        
        # 添加到分割器
        splitter.addWidget(left_widget)
        splitter.addWidget(self.right_widget)
        splitter.setSizes([200, 600])  # 设置初始大小比例
        
        # 添加到选项卡布局
        tab_layout = QVBoxLayout(self.plugin_tab)
        tab_layout.addWidget(splitter)
    
    def on_python_env_changed(self):
        """Python环境列表变化时的回调"""
        # 刷新所有插件控制面板的Python解释器选择框
        if hasattr(self, 'right_layout') and self.right_layout.count() > 0:
            panel = self.right_layout.itemAt(0).widget()
            if panel and hasattr(panel, '_refresh_python_env_combo'):
                panel._refresh_python_env_combo()

    def on_apply_font_size_clicked(self):
        """点击“应用”后再设置字体大小，使用异步调用避免卡顿"""
        font_size = self.font_size_spin.value() if hasattr(self, 'font_size_spin') else self.config_manager.get_font_size()
        # 先保存配置
        self.config_manager.set_font_size(font_size)
        # UI反馈：禁用按钮并显示忙光标
        try:
            self.font_apply_btn.setEnabled(False)
        except Exception:
            pass
        app = QApplication.instance()
        if app:
            app.setOverrideCursor(Qt.WaitCursor)
            app.processEvents()
        # 异步应用，避免阻塞主线程事件循环
        def _do_apply():
            try:
                self.apply_font_size(font_size)
            finally:
                if app:
                    app.restoreOverrideCursor()
                try:
                    self.font_apply_btn.setEnabled(True)
                except Exception:
                    pass
        QTimer.singleShot(0, _do_apply)
    
    def on_plugin_selected(self, current, previous):
        """插件选择改变"""
        if not current:
            return
        
        # 清除右侧布局
        for i in reversed(range(self.right_layout.count())):
            widget = self.right_layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)
        
        # 添加插件控制面板
        plugin = current.plugin
        control_panel = PluginControlPanel(plugin, self.config_manager, self, self.right_widget)
        self.right_layout.addWidget(control_panel)
        
        # 不再在选择时自动创建插件UI/参数选项卡，改为在启用后由状态变化创建
    
    def on_plugin_item_double_clicked(self, item):
        """双击列表项：启用/停用插件
        - 若无Tab：仅显示Tab（不自动运行）
        - 若已有Tab：停用并移除Tab；如在运行则强制终止
        """
        try:
            plugin = getattr(item, 'plugin', None)
            if not plugin:
                return
            plugin_id = plugin.plugin_id
            # 已启用则停用
            if hasattr(self, 'plugin_ui_tabs') and plugin_id in self.plugin_ui_tabs:
                # 停止运行（强制）并移除Tab
                try:
                    if hasattr(plugin, 'kill'):
                        plugin.kill()
                    else:
                        plugin.stop(wait=False)
                except Exception:
                    pass
                self._remove_plugin_tab(plugin)
            else:
                # 未启用则显示Tab（不启动任务）
                self._show_plugin_tab(plugin)
                # 刚启用界面时清空通用界面日志
                try:
                    if hasattr(plugin, '_generic_widget') and plugin._generic_widget and hasattr(plugin._generic_widget, 'clear_log'):
                        plugin._generic_widget.clear_log()
                except Exception:
                    pass
            # 刷新行与状态监控
            self._update_plugin_list_status(plugin_id)
            if hasattr(self, 'status_monitor'):
                gui_status = "已启用" if plugin_id in self.plugin_ui_tabs else "未启用"
                self.status_monitor.update_plugin_gui_status(plugin_id, gui_status)
            # 同步右侧面板按钮
            self._refresh_right_panel_buttons(plugin_id)
        except Exception:
            pass

    def _refresh_all_plugin_list_status(self):
        """刷新左侧所有插件行的启用/停用状态展示"""
        try:
            for i in range(self.plugin_list.count()):
                item = self.plugin_list.item(i)
                if hasattr(item, 'update_status'):
                    item.update_status(self)
        except Exception:
            pass

    def _refresh_right_panel_buttons(self, plugin_id: str | None = None):
        """根据当前Tab启用状态刷新右侧控制面板按钮可用性"""
        try:
            if self.right_layout.count() == 0:
                return
            panel = self.right_layout.itemAt(0).widget()
            if not panel or not hasattr(panel, 'plugin'):
                return
            pid = getattr(panel.plugin, 'plugin_id', None)
            if plugin_id is None or plugin_id == pid:
                if hasattr(panel, 'update_button_state'):
                    panel.update_button_state()
        except Exception:
            pass

    def on_start_all_clicked(self):
        """全部启用按钮点击：仅显示所有插件的Tab，不启动插件"""
        plugins = self.config_manager.get_plugins_in_start_order(self.plugin_manager.get_all_plugins())
        for plugin in plugins:
            # 仅显示Tab，不启动插件
            self._show_plugin_tab(plugin)
            # 同步清空通用界面的日志显示（仅创建时清空）
            try:
                if hasattr(plugin, '_generic_widget') and plugin._generic_widget and hasattr(plugin._generic_widget, 'clear_log'):
                    plugin._generic_widget.clear_log()
            except Exception:
                pass
        # 同步刷新列表状态与右侧面板
        self._refresh_all_plugin_list_status()
        self._refresh_right_panel_buttons()
    
    def on_stop_all_clicked(self):
        """全部停用按钮点击：停止所有插件并移除所有Tab"""
        # 为避免阻塞UI线程，后台线程执行停止逻辑
        if not hasattr(self, "_stopping_all"):
            self._stopping_all = False
        if self._stopping_all:
            return
        self._stopping_all = True

        import threading
        def _do_stop_all():
            try:
                # 拿快照，避免遍历时被修改
                try:
                    plugins_snapshot = list(self.plugin_manager.get_all_plugins())
                except Exception:
                    plugins_snapshot = []
                # 优先强杀，避免等待
                for p in plugins_snapshot:
                    try:
                        if hasattr(p, 'kill'):
                            p.kill()
                        else:
                            p.stop(wait=False)
                    except Exception:
                        pass
                # 停止后在主线程刷新UI（移除Tabs + 刷新状态）
                try:
                    from PySide6.QtCore import QMetaObject, Qt
                    QMetaObject.invokeMethod(self, "_refresh_ui_after_stop_all", Qt.QueuedConnection)
                except Exception:
                    pass
            finally:
                # 标志复位需在主线程执行
                try:
                    from PySide6.QtCore import QMetaObject, Qt
                    QMetaObject.invokeMethod(self, "_reset_stopping_all_flag", Qt.QueuedConnection)
                except Exception:
                    self._stopping_all = False

        threading.Thread(target=_do_stop_all, daemon=True).start()
        # 取消使用 QTimer 于非Qt线程，守护性复位放到主线程方法中由计时器触发

    
    def on_refresh_clicked(self):
        """刷新列表按钮点击"""
        # 停止所有插件
        self.plugin_manager.stop_all_plugins()
        
        # 保存当前选中的标签页索引
        current_tab_index = self.tab_widget.currentIndex()
        
        # 清空插件UI选项卡
        # 先获取非内置标签页的数量（插件管理、Python环境管理、状态监控）
        builtin_tabs_count = 3  # 插件管理、Python环境管理、状态监控
        
        # 保存插件UI选项卡的引用，以便在刷新后恢复
        saved_plugin_tabs = {}
        for plugin_id, (widget, tab_index) in list(self.plugin_ui_tabs.items()):
            # 保存插件ID和对应的widget引用
            plugin = self.plugin_manager.get_plugin(plugin_id)
            if plugin:
                saved_plugin_tabs[plugin_id] = {
                    'plugin': plugin,
                    'widget': widget,
                    'had_tab': True
                }
        
        # 从后往前移除插件UI标签页，避免索引变化问题
        # 先找到所有插件tab的索引
        plugin_tab_indices = []
        for i in range(self.tab_widget.count()):
            widget = self.tab_widget.widget(i)
            for plugin_id, (saved_widget, _) in list(self.plugin_ui_tabs.items()):
                if widget is saved_widget:
                    plugin_tab_indices.append(i)
                    break
        
        # 从大到小排序，从后往前删除
        plugin_tab_indices.sort(reverse=True)
        for idx in plugin_tab_indices:
            self.tab_widget.removeTab(idx)
        
        # 清空插件UI选项卡字典
        self.plugin_ui_tabs.clear()
        
        # 清空状态监控 - 使用现有的remove_plugin方法移除所有插件
        # 先保存所有插件ID到临时列表
        plugin_ids_to_remove = list(self.status_monitor.plugin_status_map.keys())
        # 逐个移除所有插件
        for plugin_id in plugin_ids_to_remove:
            self.status_monitor.remove_plugin(plugin_id)
        
        # 重新加载插件
        self.plugin_manager.load_plugins()
        
        # 更新插件列表和状态监控
        self.plugin_list.clear()
        all_plugins_map = {p.plugin_id: p for p in self.plugin_manager.get_all_plugins()}
        ordered_ids = self.config_manager.get_plugin_list_order()
        for pid in ordered_ids:
            if pid in all_plugins_map:
                self._add_plugin_list_row(all_plugins_map[pid])
                del all_plugins_map[pid]
        for p in all_plugins_map.values():
            self._add_plugin_list_row(p)
        # 按与可用插件列表一致的顺序添加到状态监控
        for plugin in self._get_plugins_in_display_order():
            self.status_monitor.add_plugin(plugin.plugin_id, plugin.name)
            self.status_monitor.update_plugin_status(plugin.plugin_id, "已停止" if not plugin.is_running else "运行中")
        
        # 恢复之前有Tab的插件UI（如果插件仍然存在）
        for plugin_id, saved_info in saved_plugin_tabs.items():
            plugin = self.plugin_manager.get_plugin(plugin_id)
            if plugin and saved_info.get('had_tab', False):
                # 检查是否应该自动启动
                if self.config_manager.is_plugin_auto_start(plugin_id):
                    self._show_plugin_tab(plugin)
        
        # 清空右侧布局
        for i in reversed(range(self.right_layout.count())):
            widget = self.right_layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)
        
        self.right_layout.addWidget(QLabel("请选择一个插件查看详情"))
        
        # 恢复到插件管理标签页
        self.tab_widget.setCurrentIndex(0)

    # --- 主线程辅助：供后台线程队列调用 ---
    @Slot()
    def _reset_stopping_all_flag(self):
        try:
            self._stopping_all = False
        except Exception:
            pass

    @Slot()
    def _refresh_ui_after_stop_all(self):
        # 强制同步所有插件状态为 stopped，避免信号丢失导致列表未更新
        try:
            for p in self.plugin_manager.get_all_plugins():
                try:
                    if getattr(p, 'is_running', False):
                        p.is_running = False
                    if hasattr(p, 'signals') and hasattr(p.signals, 'status_changed'):
                        p.signals.status_changed.emit(p.plugin_id, "stopped")
                except Exception:
                    pass
        except Exception:
            pass
        # 移除所有插件Tab（存在即移除）
        try:
            for plugin_id in list(self.plugin_ui_tabs.keys()):
                plugin = self.plugin_manager.get_plugin(plugin_id)
                if plugin:
                    self._remove_plugin_tab(plugin)
        except Exception:
            pass
        # 刷新列表与按钮
        try:
            self._refresh_all_plugin_list_status()
            self._refresh_right_panel_buttons()
        except Exception:
            pass

    def _save_plugin_list_order(self):
        """保存当前可用插件列表顺序到配置"""
        order_ids = []
        for i in range(self.plugin_list.count()):
            item = self.plugin_list.item(i)
            if hasattr(item, 'plugin') and hasattr(item.plugin, 'plugin_id'):
                order_ids.append(item.plugin.plugin_id)
        self.config_manager.set_plugin_list_order(order_ids)
        # 同步状态监控表格的顺序
        try:
            if hasattr(self, 'status_monitor') and self.status_monitor:
                self.status_monitor.set_order(order_ids)
        except Exception:
            pass

    def _get_plugins_in_display_order(self):
        """获取按左侧列表相同顺序排列的插件列表。

        规则：优先使用配置中记录的顺序；其余未记录的插件按读取顺序追加。
        """
        try:
            all_plugins_map = {p.plugin_id: p for p in self.plugin_manager.get_all_plugins()}
        except Exception:
            all_plugins_map = {}
        ordered_ids = self.config_manager.get_plugin_list_order()
        ordered_list = []
        for pid in ordered_ids:
            if pid in all_plugins_map:
                ordered_list.append(all_plugins_map.pop(pid))
        # 追加剩余未在顺序表中的插件（保持稳定）
        ordered_list.extend(all_plugins_map.values())
        return ordered_list

    def _add_plugin_list_row(self, plugin):
        """向列表添加一行，包含名称与上移/下移箭头（纯色单箭头样式）"""
        from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QToolButton
        row_item = PluginListItem(plugin, self.plugin_list)
        # 使用自定义部件后，避免与item文字叠加产生“重影”
        row_item.setText("")
        self.plugin_list.addItem(row_item)
        # 自定义行部件
        row_widget = QWidget()
        hl = QHBoxLayout(row_widget)
        hl.setContentsMargins(6, 2, 6, 2)
        name_label = QLabel(plugin.name)
        up_btn = QToolButton()
        down_btn = QToolButton()
        up_btn.setAutoRaise(True)
        down_btn.setAutoRaise(True)
        # 使用纯色单箭头字符
        up_btn.setText("▲")
        down_btn.setText("▼")
        # 提高可见性：加大尺寸
        up_btn.setFixedSize(28, 28)
        down_btn.setFixedSize(28, 28)
        # 动态样式：暗色主题使用更高对比度的白色
        normal_color = "#ffffff" if getattr(self, 'is_dark_theme', False) else "#333333"
        disabled_color = "#666666" if getattr(self, 'is_dark_theme', False) else "#aaaaaa"
        arrow_style = (
            f"QToolButton{{color:{normal_color}; font-size:16px; font-weight:600; padding:0;}} "
            f"QToolButton:disabled{{color:{disabled_color};}}"
        )
        up_btn.setStyleSheet(arrow_style)
        down_btn.setStyleSheet(arrow_style)
        hl.addWidget(name_label)
        hl.addStretch()
        hl.addWidget(up_btn)
        hl.addWidget(down_btn)
        self.plugin_list.setItemWidget(row_item, row_widget)

        # 绑定移动事件
        up_btn.clicked.connect(lambda: self._move_plugin_row(plugin.plugin_id, direction=-1))
        down_btn.clicked.connect(lambda: self._move_plugin_row(plugin.plugin_id, direction=1))
        # 保存引用以便刷新可用状态
        row_widget._up_btn = up_btn
        row_widget._down_btn = down_btn
        row_widget._name_label = name_label
        # 初始化行状态显示
        try:
            row_item.update_status(self)
        except Exception:
            pass
        self._refresh_move_buttons()

    def _move_plugin_row(self, plugin_id, direction):
        """根据插件ID将列表项上移或下移一行（通过重建列表，避免自定义部件移动的不确定性）"""
        # 收集当前顺序
        items = []  # [(plugin, item)]
        index = -1
        for i in range(self.plugin_list.count()):
            item = self.plugin_list.item(i)
            plugin = getattr(item, 'plugin', None)
            if plugin is None:
                continue
            items.append(plugin)
            if plugin.plugin_id == plugin_id:
                index = len(items) - 1
        if index < 0:
            return
        new_index = index + direction
        if new_index < 0 or new_index >= len(items):
            return
        # 计算新顺序（交换 index 与 new_index）
        items[index], items[new_index] = items[new_index], items[index]
        # 清空列表并按新顺序重建
        self.plugin_list.clear()
        for p in items:
            self._add_plugin_list_row(p)
        # 保存顺序并刷新按钮
        self._save_plugin_list_order()
        self._refresh_move_buttons()
        # 重建后刷新每一行的状态文案与颜色
        try:
            for i in range(self.plugin_list.count()):
                it = self.plugin_list.item(i)
                if hasattr(it, 'plugin'):
                    it.update_status(self)
        except Exception:
            pass

    def _refresh_move_buttons(self):
        """根据行位置，刷新每行上/下按钮的可用状态，避免移动后按钮消失或不可用"""
        count = self.plugin_list.count()
        for i in range(count):
            item = self.plugin_list.item(i)
            widget = self.plugin_list.itemWidget(item)
            if not widget:
                continue
            # 顶部行不能上移，底部行不能下移
            if hasattr(widget, '_up_btn'):
                widget._up_btn.setEnabled(i > 0)
            if hasattr(widget, '_down_btn'):
                widget._down_btn.setEnabled(i < count - 1)
        
    def on_import_clicked(self):
        """处理导入插件按钮点击事件"""
        # 打开插件导入对话框
        dialog = PluginImportDialog(self)
        if dialog.exec():
            # 获取用户输入的插件信息
            plugin_info = dialog.get_plugin_info()
            
            # 创建插件导入器
            importer = PluginImporter(self.plugin_manager.plugins_dir)
            
            # 执行导入
            success, error_message = importer.import_plugin(plugin_info)
            
            if success:
                QMessageBox.information(self, "导入成功", f"插件 '{plugin_info['plugin_name']}' 已成功导入")
                # 轻量刷新：仅加载新导入的插件，避免停止正在运行的其他插件
                try:
                    plugin_id = plugin_info.get('plugin_id')
                    plugin_dir = os.path.join(self.plugin_manager.plugins_dir, plugin_id)
                    # 若已存在同名插件，先跳过（由“更新插件”流程处理）
                    if plugin_id not in self.plugin_manager.plugins:
                        new_plugin = self.plugin_manager._load_plugin(plugin_id, plugin_dir)
                        if new_plugin:
                            # 注册并连接信号
                            self.plugin_manager.plugins[new_plugin.plugin_id] = new_plugin
                            try:
                                new_plugin.signals.status_changed.connect(self.on_plugin_status_changed)
                                new_plugin.signals.error_occurred.connect(lambda pid, msg, _=None: self.on_plugin_error(pid, msg))
                                new_plugin.signals.output_generated.connect(lambda pid, out, _=None: self.on_plugin_output(pid, out))
                            except Exception:
                                pass
                            # 添加到左侧列表
                            self._add_plugin_list_row(new_plugin)
                            # 添加到状态监控
                            try:
                                self.status_monitor.add_plugin(new_plugin.plugin_id, new_plugin.name)
                                self.status_monitor.update_plugin_status(new_plugin.plugin_id, "已停止")
                            except Exception:
                                pass
                            # 选中新插件并显示右侧面板
                            try:
                                # 找到刚添加的行
                                for i in range(self.plugin_list.count()):
                                    item = self.plugin_list.item(i)
                                    if hasattr(item, 'plugin') and item.plugin.plugin_id == new_plugin.plugin_id:
                                        self.plugin_list.setCurrentItem(item)
                                        self.on_plugin_selected(item, None)
                                        break
                            except Exception:
                                pass
                except Exception:
                    pass
            else:
                QMessageBox.critical(self, "导入失败", f"导入插件时出错: {error_message}")
    
    def on_plugin_status_changed(self, plugin_id, status):
        """插件状态改变回调"""
        # 转换英文状态为中文
        status_mapping = {
            "running": "运行中",
            "stopped": "已停止",
            "paused": "已暂停",
            "error": "错误"
        }
        # 使用映射转换状态
        if status.lower() in status_mapping:
            status = status_mapping[status.lower()]
        
        # 更新插件列表项状态
        for i in range(self.plugin_list.count()):
            item = self.plugin_list.item(i)
            if item.plugin.plugin_id == plugin_id:
                item.update_status(self)  # 传入主窗口引用
                # 更新通用插件界面的状态
                if hasattr(item.plugin, '_generic_widget'):
                    item.plugin._generic_widget.set_running(status == "运行中")
                    # 若切换到“运行中”，在通用界面日志先清空（保持用户要求：启用/启动时清空）
                    if status == "运行中" and hasattr(item.plugin._generic_widget, 'clear_log'):
                        try:
                            item.plugin._generic_widget.clear_log()
                        except Exception:
                            pass
                break
        
        # 不再因状态变化自动创建或移除Tab；Tab完全由“启用/停用”控制

        # 更新状态监控
        self.status_monitor.update_plugin_status(plugin_id, status)

    def _show_plugin_tab(self, plugin):
        """根据插件类型创建并展示Tab（不切换、不启动）"""
        plugin_id = plugin.plugin_id
        if plugin_id in self.plugin_ui_tabs:
            return
        if plugin.has_ui:
            ui_widget = PluginUIWidget(plugin)
            tab_index = self.tab_widget.addTab(ui_widget, plugin.name)
            self.plugin_ui_tabs[plugin_id] = (ui_widget, tab_index)
        else:
            saved_params = self.config_manager.load_plugin_config(plugin.plugin_id, {})
            entry_path = getattr(plugin, '_entry_module_path', None)
            if not entry_path:
                try:
                    entry_path = inspect.getfile(plugin.__class__)
                except Exception:
                    entry_path = None
            entry_func_name = getattr(plugin, '_entry_function_name', None)
            generic_widget = GenericPluginWidget(
                plugin.name,
                plugin.plugin_id,
                self,
                entry_module_path=entry_path,
                entry_function_name=entry_func_name,
            )
            # 允许从配置中覆盖参数定义
            full_cfg = self.config_manager.load_plugin_config(plugin.plugin_id, {})
            override_defs = {}
            try:
                if isinstance(full_cfg, dict) and '__definitions__' in full_cfg:
                    override_defs = full_cfg.get('__definitions__', {}) or {}
            except Exception:
                override_defs = {}
            base_defs = getattr(plugin, 'parameters', {}) or {}
            param_definitions = override_defs if override_defs else base_defs
            # 如果存在旧格式保存的 values（非 __values__），做兼容性提取
            saved_values = {}
            try:
                if isinstance(full_cfg, dict):
                    if '__definitions__' in full_cfg:
                        saved_values = full_cfg.get('__values__', {}) or {}
                    else:
                        saved_values = dict(full_cfg)
            except Exception:
                saved_values = {}

            for param_name, param_info in param_definitions.items():
                try:
                    if param_name in saved_values:
                        param_info['value'] = saved_values[param_name]
                except Exception:
                    pass
            generic_widget.set_parameters(param_definitions)
            # 通用界面内部仅启动/停止插件，不移除Tab
            generic_widget.start_plugin.connect(lambda p=plugin: self._start_plugin_with_params(p))
            generic_widget.stop_plugin.connect(lambda p=plugin: (p.kill() if hasattr(p, 'kill') else p.stop(wait=False)))
            generic_widget.parameters_changed.connect(lambda params, pid=plugin.plugin_id: self._save_plugin_parameters(pid, params))
            # 监听定义变更，并持久化覆盖
            try:
                generic_widget.definitions_changed.connect(lambda defs, pid=plugin.plugin_id: self._save_plugin_param_definitions(pid, defs))
            except Exception:
                pass
            tab_index = self.tab_widget.addTab(generic_widget, plugin.name)
            self.plugin_ui_tabs[plugin_id] = (generic_widget, tab_index)
            setattr(plugin, '_generic_widget', generic_widget)
            
            # 加载历史日志（如果存在）
            if hasattr(plugin, 'log_history') and plugin.log_history:
                for log_message in plugin.log_history:
                    try:
                        generic_widget.append_log(log_message)
                    except Exception:
                        pass
        
        # 更新插件列表状态显示
        self._update_plugin_list_status(plugin_id)
        
        # 更新状态监控的GUI状态
        if hasattr(self, 'status_monitor'):
            gui_status = "已启用" if plugin_id in self.plugin_ui_tabs else "未启用"
            self.status_monitor.update_plugin_gui_status(plugin_id, gui_status)

    def _remove_plugin_tab(self, plugin):
        """移除插件对应的Tab（由停用触发）"""
        plugin_id = plugin.plugin_id
        if plugin_id in self.plugin_ui_tabs:
            widget, tab_index = self.plugin_ui_tabs.pop(plugin_id)
            for i in range(self.tab_widget.count()):
                if self.tab_widget.widget(i) is widget:
                    self.tab_widget.removeTab(i)
                    break
            if hasattr(plugin, '_generic_widget'):
                try:
                    delattr(plugin, '_generic_widget')
                except Exception:
                    pass
        
        # 更新插件列表状态显示
        self._update_plugin_list_status(plugin_id)
        
        # 更新状态监控的GUI状态
        if hasattr(self, 'status_monitor'):
            gui_status = "已启用" if plugin_id in self.plugin_ui_tabs else "未启用"
            self.status_monitor.update_plugin_gui_status(plugin_id, gui_status)
    
    def _uninstall_plugin(self, plugin):
        """执行插件卸载流程：停用、移除Tab、卸载、刷新UI与状态监控（后台执行卸载以防卡死）"""
        try:
            self._stop_plugin_and_remove_tab(plugin)
        except Exception:
            pass
        plugin_id = plugin.plugin_id
        plugin_name = plugin.name

        import threading
        from PySide6.QtCore import QMetaObject, Qt

        def _do_uninstall():
            try:
                try:
                    self.plugin_manager.uninstall_plugin(plugin_id)
                except Exception:
                    # 即使卸载失败也尝试刷新UI，避免界面卡住
                    pass
            finally:
                # 回到主线程收尾
                try:
                    # 记录要在主线程读取的上下文（必须先保存再调度UI刷新，避免竞态）
                    setattr(self, "_last_uninstalled_id", plugin_id)
                    setattr(self, "_last_uninstalled_name", plugin_name)
                    QMetaObject.invokeMethod(self, "_finish_uninstall_ui", Qt.QueuedConnection)
                except Exception:
                    # 兜底：直接在此线程做部分清理（不涉及Qt对象遍历）
                    try:
                        self.plugin_manager.plugins.pop(plugin_id, None)
                    except Exception:
                        pass

        threading.Thread(target=_do_uninstall, daemon=True).start()

    def _update_plugin(self, plugin):
        """更新插件：停用并移除Tab → 重新导入 → 刷新 UI/列表/状态监控。

        保留参数配置（通过 ConfigManager 持久化），不删除任何文件。
        """
        try:
            # 记录当前是否已启用GUI Tab，更新完成后尝试恢复
            plugin_id = plugin.plugin_id
            had_tab = plugin_id in getattr(self, 'plugin_ui_tabs', {})
            # 停止并移除旧Tab
            self._stop_plugin_and_remove_tab(plugin)
        except Exception:
            pass

        import threading
        from PySide6.QtCore import QMetaObject, Qt

        def _do_update():
            success = False
            try:
                success = bool(self.plugin_manager.update_plugin(plugin_id))
            except Exception:
                success = False
            finally:
                try:
                    setattr(self, "_last_updated_id", plugin_id)
                    setattr(self, "_last_updated_ok", success)
                    setattr(self, "_last_had_tab", had_tab)
                    QMetaObject.invokeMethod(self, "_finish_update_ui", Qt.QueuedConnection)
                except Exception:
                    pass

        threading.Thread(target=_do_update, daemon=True).start()

    @Slot()
    def _finish_update_ui(self):
        """主线程：完成更新后的界面刷新与对象替换。"""
        pid = getattr(self, "_last_updated_id", None)
        ok = bool(getattr(self, "_last_updated_ok", False))
        had_tab = bool(getattr(self, "_last_had_tab", False))
        if not pid:
            return
        # 替换左侧列表中该项的 plugin 引用
        try:
            new_plugin = self.plugin_manager.get_plugin(pid)
            if new_plugin:
                for i in range(self.plugin_list.count()):
                    item = self.plugin_list.item(i)
                    if hasattr(item, 'plugin') and item.plugin.plugin_id == pid:
                        item.plugin = new_plugin
                        # 立即更新该行状态文案
                        if hasattr(item, 'update_status'):
                            item.update_status(self)
                        break
        except Exception:
            pass

        # 若之前有Tab，则恢复展示新实例的Tab（不自动运行）
        try:
            if had_tab:
                p = self.plugin_manager.get_plugin(pid)
                if p:
                    self._show_plugin_tab(p)
        except Exception:
            pass

        # 刷新右侧面板（如果正在显示该插件的控制面板，则替换为最新实例）
        try:
            if self.right_layout.count() > 0:
                panel = self.right_layout.itemAt(0).widget()
                if panel and hasattr(panel, 'plugin') and getattr(panel.plugin, 'plugin_id', None) == pid:
                    # 重新构建右侧面板为新实例
                    for i in reversed(range(self.right_layout.count())):
                        w = self.right_layout.itemAt(i).widget()
                        if w:
                            w.setParent(None)
                    new_panel = PluginControlPanel(new_plugin, self.config_manager, self, self.right_widget)
                    self.right_layout.addWidget(new_panel)
        except Exception:
            pass

        # 刷新状态监控（确保状态行存在）
        try:
            if hasattr(self, 'status_monitor') and self.status_monitor:
                # 如果该插件未被记录，补充一行
                if pid not in self.status_monitor.plugin_status_map and new_plugin:
                    self.status_monitor.add_plugin(pid, new_plugin.name)
                # 同步状态
                self.status_monitor.update_plugin_status(pid, "已停止" if not new_plugin or not new_plugin.is_running else "运行中")
        except Exception:
            pass

        # 用户提示
        try:
            if ok:
                QMessageBox.information(self, "更新成功", f"插件 '{new_plugin.name if new_plugin else pid}' 已更新")
            else:
                QMessageBox.critical(self, "更新失败", f"插件 '{pid}' 更新失败")
        except Exception:
            pass

    @Slot()
    def _finish_uninstall_ui(self):
        """主线程：完成卸载后的界面刷新"""
        plugin_id = getattr(self, "_last_uninstalled_id", None)
        plugin_name = getattr(self, "_last_uninstalled_name", "插件")
        # 从状态监控移除
        try:
            if hasattr(self, 'status_monitor') and plugin_id is not None:
                self.status_monitor.remove_plugin(plugin_id)
        except Exception:
            pass
        # 从左侧列表移除对应项
        try:
            if plugin_id is not None:
                removed_row = -1
                for i in range(self.plugin_list.count()):
                    item = self.plugin_list.item(i)
                    if hasattr(item, 'plugin') and item.plugin.plugin_id == plugin_id:
                        self.plugin_list.takeItem(i)
                        removed_row = i
                        break
        except Exception:
            pass
        # 清空右侧面板
        try:
            for i in reversed(range(self.right_layout.count())):
                w = self.right_layout.itemAt(i).widget()
                if w:
                    w.setParent(None)
            self.right_layout.addWidget(QLabel("请选择一个插件查看详情"))
        except Exception:
            pass
        # 更新可用状态列表
        try:
            self._refresh_all_plugin_list_status()
            self._refresh_right_panel_buttons()
        except Exception:
            pass
        # 若列表仍有插件：自动选择一个（优先选择被移除位置的后继项），并构建右侧面板
        try:
            count = self.plugin_list.count()
            if count > 0:
                idx = 0
                try:
                    if 'removed_row' in locals() and removed_row >= 0:
                        idx = min(removed_row, count - 1)
                except Exception:
                    idx = 0
                self.plugin_list.setCurrentRow(idx)
                # 兜底：确保右侧面板同步
                try:
                    current_item = self.plugin_list.item(idx)
                    if current_item:
                        self.on_plugin_selected(current_item, None)
                except Exception:
                    pass
        except Exception:
            pass
        # 提示
        try:
            QMessageBox.information(self, "卸载成功", f"插件 '{plugin_name}' 已卸载")
        except Exception:
            pass
    
    def _update_plugin_list_status(self, plugin_id):
        """更新插件列表中指定插件的状态显示"""
        for i in range(self.plugin_list.count()):
            item = self.plugin_list.item(i)
            if item.plugin.plugin_id == plugin_id:
                item.update_status(self)  # 传入主窗口引用
                break
    
    def _stop_plugin_and_remove_tab(self, plugin):
        """停用插件并移除Tab页面（强制终止）"""
        if hasattr(plugin, 'kill'):
            plugin.kill()
        else:
            plugin.stop(wait=False)
        
        # 移除对应的Tab页面
        plugin_id = plugin.plugin_id
        if plugin_id in self.plugin_ui_tabs:
            widget, tab_index = self.plugin_ui_tabs.pop(plugin_id)
            # 移除对应tab（防止索引变化，重新查找当前index）
            for i in range(self.tab_widget.count()):
                if self.tab_widget.widget(i) is widget:
                    self.tab_widget.removeTab(i)
                    break
            # 清理通用插件的引用
            if hasattr(plugin, '_generic_widget'):
                try:
                    delattr(plugin, '_generic_widget')
                except Exception:
                    pass
    
    def _start_plugin_with_params(self, plugin):
        """使用当前参数启动插件"""
        # 加载保存的参数
        saved_params = self.config_manager.load_plugin_config(plugin.plugin_id, {})

        # 计算默认参数：优先使用插件对象已有的 parameters_values，其次从 parameters 定义的 value 构建
        default_params = {}
        if hasattr(plugin, 'parameters_values') and isinstance(plugin.parameters_values, dict):
            default_params = dict(plugin.parameters_values)
        else:
            # 从参数定义提取默认值
            try:
                param_defs = getattr(plugin, 'parameters', {}) or {}
                if isinstance(param_defs, dict):
                    for name, info in param_defs.items():
                        if isinstance(info, dict) and 'value' in info:
                            default_params[name] = info.get('value')
            except Exception:
                default_params = {}

        # 合并：已保存参数覆盖默认参数
        merged_params = {**default_params, **(saved_params or {})}

        # 写回到插件实例
        if not hasattr(plugin, 'parameters_values'):
            setattr(plugin, 'parameters_values', merged_params)
        else:
            plugin.parameters_values = merged_params

        logger.info(f"启动插件 {plugin.plugin_id} 使用参数: {merged_params}")
        # 启动前：清空插件与界面日志
        try:
            if hasattr(plugin, 'log_history'):
                plugin.log_history = []
        except Exception:
            pass
        try:
            if hasattr(plugin, '_generic_widget') and plugin._generic_widget and hasattr(plugin._generic_widget, 'clear_log'):
                plugin._generic_widget.clear_log()
        except Exception:
            pass
        # 启动插件
        plugin.start()
    
    def _save_plugin_parameters(self, plugin_id, parameters):
        """保存插件参数值（与定义覆盖解耦）"""
        # 读取现有配置，兼容旧格式（旧格式=纯 values 字典）
        cfg = {}
        try:
            cfg = self.config_manager.load_plugin_config(plugin_id, {})
            if not isinstance(cfg, dict):
                cfg = {}
        except Exception:
            cfg = {}
        # 如果旧格式（没有 __definitions__ 且 cfg 看起来是 values），为了兼容，直接覆盖为 values
        if '__definitions__' in cfg:
            cfg['__values__'] = dict(parameters or {})
        else:
            # 旧格式：仍按旧行为保存为纯 values
            cfg = dict(parameters or {})
        self.config_manager.save_plugin_config(plugin_id, cfg)
        # 通知插件参数已更新
        plugin = self.plugin_manager.get_plugin(plugin_id)
        if plugin and hasattr(plugin, 'parameters_values'):
            plugin.parameters_values = parameters

    def _save_plugin_param_definitions(self, plugin_id, definitions: dict):
        """保存参数定义覆盖到插件独立配置 (__definitions__)"""
        cfg = {}
        try:
            cfg = self.config_manager.load_plugin_config(plugin_id, {})
            if not isinstance(cfg, dict):
                cfg = {}
        except Exception:
            cfg = {}
        # 保留可能已有的值
        if '__definitions__' in cfg:
            values = cfg.get('__values__', {})
        else:
            # 旧格式，cfg 即为 values
            values = dict(cfg)
            cfg = {}
        cfg['__definitions__'] = dict(definitions or {})
        # 仍然把现有的 values 放回去
        cfg['__values__'] = values
        self.config_manager.save_plugin_config(plugin_id, cfg)
    
    def on_plugin_error(self, plugin_id, error_message):
        """插件错误回调"""
        plugin = self.plugin_manager.get_plugin(plugin_id)
        if plugin:
            QMessageBox.warning(self, "插件错误", f"插件 {plugin.name} 发生错误:\n{error_message}")
    
    def on_plugin_output(self, plugin_id, output):
        """插件输出回调"""
        plugin = self.plugin_manager.get_plugin(plugin_id)
        if not plugin:
            return
        
        updated_in_right_panel = False
        # 如果当前右侧窗口中有插件控制面板，且是对应插件的，更新日志
        if self.right_layout.count() > 0:
            widget = self.right_layout.itemAt(0).widget()
            if widget and hasattr(widget, 'plugin') and getattr(widget.plugin, 'plugin_id', None) == plugin_id:
                if hasattr(widget, 'on_output_generated') and callable(getattr(widget, 'on_output_generated')):
                    try:
                        widget.on_output_generated(plugin_id, output)
                        updated_in_right_panel = True
                    except Exception:
                        # 如果右侧控件处理失败，回退到通用日志窗口
                        updated_in_right_panel = False

        # 更新插件tab中的日志（如果存在）
        # 无论右侧面板是否更新，都要更新插件tab中的日志，确保tab中能看到日志
        if hasattr(plugin, '_generic_widget') and plugin._generic_widget:
            try:
                plugin._generic_widget.append_log(output)
            except Exception:
                pass

    def on_plugin_input_requested(self, plugin_id: str, prompt: str, qobj, password: bool, default_text: str):
        """处理插件输入请求：不弹窗，提示用户使用日志上方输入框提交。"""
        try:
            plugin = self.plugin_manager.get_plugin(plugin_id)
            if plugin:
                # 若插件已停止或已取消输入，则忽略此次请求，避免停止后仍不断提示输入
                try:
                    if (not plugin.is_running) or getattr(plugin, '_input_canceled', False) or plugin.is_stopped():
                        return
                except Exception:
                    pass
                # 尝试聚焦对应界面的输入框
                try:
                    # 如果是通用插件界面
                    if hasattr(plugin, '_generic_widget') and plugin._generic_widget:
                        gw = plugin._generic_widget
                        if hasattr(gw, 'prepare_for_input'):
                            gw.prepare_for_input(prompt or "", default_text or "", password)
                    # 如果是控制面板在右侧
                    if hasattr(self, 'right_layout') and self.right_layout.count() > 0:
                        panel = self.right_layout.itemAt(0).widget()
                        if panel and hasattr(panel, 'plugin') and getattr(panel.plugin, 'plugin_id', None) == plugin_id:
                            if hasattr(panel, 'prepare_for_input'):
                                panel.prepare_for_input(prompt or "", default_text or "", password)
                except Exception:
                    pass
        except Exception:
            pass

    def submit_manual_input(self, plugin_id: str, text: str):
        """从日志上方输入框手动提交输入给等待中的脚本。"""
        try:
            plugin = self.plugin_manager.get_plugin(plugin_id)
            if not plugin:
                return
            q = getattr(plugin, "_pending_input_queue", None)
            if q is None:
                # 仅当该插件确实正在等待 stdin 时，才允许回退投递
                if getattr(plugin, "_waiting_on_stdin", False):
                    try:
                        # 优先通过子进程输入流（用于指定解释器运行）
                        input_stream = getattr(plugin, "_input_stream", None)
                        if input_stream is not None and hasattr(input_stream, "put_text"):
                            try:
                                input_stream.put_text(text or "")
                                plugin.log_output("已提交手动输入到标准输入。")
                                return
                            except Exception:
                                pass
                        # 兼容旧的线程内 stdin 队列路径
                        stdin_q = getattr(plugin, "_stdin_queue", None)
                        if stdin_q is not None:
                            # 防止队列已满导致 UI 阻塞，先尝试清空再非阻塞投递
                            try:
                                while True:
                                    stdin_q.get_nowait()
                            except Exception:
                                pass
                            try:
                                stdin_q.put_nowait(text or "")
                            except Exception as _ex_inner:
                                # 如果依旧失败，降级为带超时的 put，避免无限阻塞
                                try:
                                    stdin_q.put(text or "", timeout=0.2)
                                except Exception:
                                    try:
                                        plugin.log_output(f"提交手动输入失败(队列占用): {_ex_inner}")
                                    except Exception:
                                        pass
                            plugin.log_output("已提交手动输入到标准输入。")
                        else:
                            plugin.log_output("当前没有待输入请求，已忽略手动输入。")
                    except Exception as _ex:
                        try:
                            plugin.log_output(f"提交手动输入失败: {_ex}")
                        except Exception:
                            pass
                else:
                    plugin.log_output("当前插件没有等待输入，已忽略手动输入。")
                return
            try:
                # 防止阻塞：用 put_nowait，必要时退化为短超时
                try:
                    q.put_nowait(text or "")
                except Exception as _ex_q:
                    try:
                        q.put(text or "", timeout=0.2)
                    except Exception:
                        try:
                            plugin.log_output(f"提交手动输入失败(队列繁忙): {_ex_q}")
                        except Exception:
                            pass
                # 不在这里清理，由 request_input 返回后清理
                plugin.log_output("已提交手动输入。")
            except Exception as ex:
                plugin.log_output(f"提交手动输入失败: {ex}")
        except Exception:
            pass
    
    def load_window_config(self):
        """加载窗口配置"""
        window_config = self.config_manager.get_window_config()
        width = window_config.get('width', 1024)
        height = window_config.get('height', 768)
        maximized = window_config.get('maximized', False)
        
        self.resize(width, height)
        if maximized:
            self.showMaximized()
    
    def closeEvent(self, event):
        """窗口关闭事件"""
        # 保存窗口配置
        maximized = self.isMaximized()
        if not maximized:
            size = self.size()
            self.config_manager.update_window_size(size.width(), size.height(), False)
        else:
            # 如果窗口最大化，使用正常大小时的配置
            window_config = self.config_manager.get_window_config()
            self.config_manager.update_window_size(
                window_config.get('width', 1024),
                window_config.get('height', 768),
                True
            )
        
        # 先停止状态监控的定时器，避免关闭过程中继续刷新
        try:
            if hasattr(self, 'status_monitor') and hasattr(self.status_monitor, 'timer') and self.status_monitor.timer:
                self.status_monitor.timer.stop()
        except Exception:
            pass

        # 非阻塞地停止所有插件，避免在输入/阻塞时卡顿
        try:
            self.plugin_manager.stop_all_plugins(wait=False)
        except Exception:
            pass
        # 兜底：逐个强制终止，确保快速退出
        try:
            for p in self.plugin_manager.get_all_plugins():
                try:
                    if hasattr(p, 'kill'):
                        p.kill()
                    else:
                        p.stop(wait=False)
                except Exception:
                    pass
        except Exception:
            pass
        
        event.accept()
        
    def on_plugin_selected_in_monitor(self, plugin_id):
        """在状态监控中选择插件的回调"""
        # 选中对应插件
        for i in range(self.plugin_list.count()):
            item = self.plugin_list.item(i)
            if item.plugin.plugin_id == plugin_id:
                self.plugin_list.setCurrentItem(item)
                self.on_plugin_selected(item, None)
                break