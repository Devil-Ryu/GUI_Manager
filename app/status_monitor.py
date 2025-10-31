from PySide6.QtWidgets import (
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget, 
    QHeaderView, QLabel, QPushButton, QHBoxLayout, QApplication
)
from PySide6.QtCore import Qt, Signal, QTimer, QDateTime
from PySide6.QtGui import QColor, QFont, QIcon, QPalette
import time
from enum import Enum


class PluginStatus(Enum):
    """插件状态枚举"""
    STOPPED = "已停止"
    RUNNING = "运行中"
    PAUSED = "已暂停"
    ERROR = "错误"
    STARTING = "启动中"
    STOPPING = "停止中"
    LOADING = "加载中"


class PluginStatusItem(QWidget):
    """单个插件的状态显示项"""
    
    status_changed = Signal(str, str)  # 插件ID, 新状态
    
    def __init__(self, plugin_id, plugin_name, parent=None):
        super().__init__(parent)
        self.plugin_id = plugin_id
        self.plugin_name = plugin_name
        self.status = PluginStatus.STOPPED
        self.last_updated = time.time()
        self.start_time = None
        self.running_time = 0
        self.error_message = None
        
        self.init_ui()
    
    def init_ui(self):
        """初始化界面"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 2, 5, 2)
        
        # 插件名称
        self.name_label = QLabel(self.plugin_name)
        self.name_label.setMinimumWidth(150)
        self.name_label.setMaximumWidth(200)
        
        # 状态标签
        self.status_label = QLabel(self.status.value)
        self.status_label.setMinimumWidth(80)
        self.update_status_display()
        
        # 运行时间
        self.time_label = QLabel("00:00:00")
        self.time_label.setMinimumWidth(80)
        
        # 详细信息按钮
        self.details_button = QPushButton("详情")
        self.details_button.setFixedSize(60, 24)
        self.details_button.clicked.connect(self.show_details)
        
        # 添加到布局
        layout.addWidget(self.name_label)
        layout.addWidget(self.status_label)
        layout.addWidget(self.time_label)
        layout.addWidget(self.details_button)
        layout.addStretch()
    
    def set_status(self, status, error_message=None):
        """设置插件状态"""
        self.status = status
        self.error_message = error_message
        self.last_updated = time.time()
        
        # 处理启动和停止时间
        if status == PluginStatus.RUNNING and self.start_time is None:
            self.start_time = time.time()
        elif status == PluginStatus.STOPPED:
            if self.start_time is not None:
                self.running_time += time.time() - self.start_time
                self.start_time = None
        
        self.update_status_display()
        self.status_changed.emit(self.plugin_id, self.status.value)
    
    def update_status_display(self):
        """更新状态显示"""
        # 更新状态文本和颜色
        self.status_label.setText(self.status.value)
        
        # 设置状态颜色
        color_map = {
            PluginStatus.STOPPED: QColor(169, 169, 169),  # 灰色
            PluginStatus.RUNNING: QColor(0, 128, 0),      # 绿色
            PluginStatus.PAUSED: QColor(255, 165, 0),     # 橙色
            PluginStatus.ERROR: QColor(255, 0, 0),        # 红色
            PluginStatus.STARTING: QColor(70, 130, 180),  # 钢蓝色
            PluginStatus.STOPPING: QColor(70, 130, 180),  # 钢蓝色
            PluginStatus.LOADING: QColor(128, 128, 255)   # 中紫色
        }
        
        color = color_map.get(self.status, QColor(0, 0, 0))
        self.status_label.setStyleSheet(f"color: {color.name()}; font-weight: bold;")
    
    def update_time(self):
        """更新运行时间显示"""
        if self.status == PluginStatus.RUNNING and self.start_time is not None:
            total_time = self.running_time + (time.time() - self.start_time)
        else:
            total_time = self.running_time
        
        hours, remainder = divmod(int(total_time), 3600)
        minutes, seconds = divmod(remainder, 60)
        
        time_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        self.time_label.setText(time_str)
    
    def show_details(self):
        """显示插件详细信息"""
        # 这里可以扩展为显示详细的状态对话框
        # 目前简单输出到控制台作为示例
        print(f"插件详情: {self.plugin_name}")
        print(f"  ID: {self.plugin_id}")
        print(f"  状态: {self.status.value}")
        print(f"  运行时间: {self.time_label.text()}")
        print(f"  最后更新: {QDateTime.fromTime_t(int(self.last_updated)).toString()}")
        if self.error_message:
            print(f"  错误信息: {self.error_message}")


class StatusMonitorWidget(QWidget):
    """插件状态监控窗口部件"""
    
    plugin_selected = Signal(str)  # 选择插件信号
    status_updated = Signal(str, str)  # 状态更新信号
    
    def __init__(self, plugin_manager=None):
        """初始化状态监控窗口"""
        super().__init__()
        self.plugin_manager = plugin_manager
        self.plugin_status_map = {}
        # 检测系统主题
        self.is_dark_theme = self._detect_system_theme()
        self.init_ui()
        self.start_time_updater()
        # 应用主题
        self._apply_theme()
    
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
    
    def _apply_theme(self):
        """应用检测到的主题 - 现在使用原生样式"""
        # 由于使用原生样式，无需设置dark属性或修改控件颜色
        pass
    
    def init_ui(self):
        """初始化界面"""
        layout = QVBoxLayout(self)
        
        # 标题
        title_label = QLabel("插件运行状态监控")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setFont(QFont("Arial", 12, QFont.Bold))
        
        # 状态表
        self.status_table = QTableWidget()
        self.status_table.setColumnCount(5)
        self.status_table.setHorizontalHeaderLabels(["插件名称", "GUI状态", "运行时间", "GUI操作", "任务操作"])
        self.status_table.setAlternatingRowColors(True)
        self.status_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.status_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.status_table.setSelectionMode(QTableWidget.SingleSelection)
        
        # 设置表头样式
        header = self.status_table.horizontalHeader()
        # 填满可用宽度：前3列自适应拉伸，操作列固定
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.Fixed)
        header.setSectionResizeMode(4, QHeaderView.Fixed)
        header.setStretchLastSection(False)
        header.setDefaultAlignment(Qt.AlignLeft)
        
        # 设置行高
        self.status_table.verticalHeader().setDefaultSectionSize(30)
        
        # 设置操作列固定宽度
        self.status_table.setColumnWidth(3, 90)
        self.status_table.setColumnWidth(4, 90)
        
        # 不设置自定义样式，使用原生样式
        
        # 添加到布局
        layout.addWidget(title_label)
        layout.addWidget(self.status_table, 1)  # 设置伸展因子
        
        # 状态栏
        self.status_bar = QLabel("就绪")
        layout.addWidget(self.status_bar)
    
    def start_time_updater(self):
        """启动时间更新定时器"""
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_all_times)
        self.timer.start(1000)  # 每秒更新一次
    
    def add_plugin(self, plugin_id, plugin_name):
        """添加插件到监控"""
        if plugin_id not in self.plugin_status_map:
            # 创建状态项
            status_item = PluginStatusItem(plugin_id, plugin_name)
            status_item.status_changed.connect(self.on_plugin_status_changed)
            self.plugin_status_map[plugin_id] = status_item
            
            # 添加到表格
            row_position = self.status_table.rowCount()
            self.status_table.insertRow(row_position)
            
            # 创建表格项
            name_item = QTableWidgetItem(plugin_name)
            name_item.setData(Qt.UserRole, plugin_id)
            name_item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            
            # GUI状态项
            gui_status_item = QTableWidgetItem("未启用")
            gui_status_item.setFlags(Qt.ItemIsEnabled)
            gui_status_item.setForeground(QColor(169, 169, 169))
            
            # 将第3列用于显示运行时间
            time_item = QTableWidgetItem("00:00:00")
            time_item.setFlags(Qt.ItemIsEnabled)
            
            # GUI操作按钮（开启/关闭）
            stop_gui_widget = QWidget()
            stop_gui_layout = QHBoxLayout(stop_gui_widget)
            stop_gui_layout.setContentsMargins(0, 0, 0, 0)
            stop_gui_button = QPushButton("开启GUI")
            stop_gui_button.setFixedSize(70, 24)
            stop_gui_button.clicked.connect(lambda: self.toggle_gui(plugin_id))
            stop_gui_layout.addWidget(stop_gui_button)
            
            # 任务操作按钮（运行/停止）
            stop_task_widget = QWidget()
            stop_task_layout = QHBoxLayout(stop_task_widget)
            stop_task_layout.setContentsMargins(0, 0, 0, 0)
            stop_task_button = QPushButton("运行任务")
            stop_task_button.setFixedSize(70, 24)
            stop_task_button.clicked.connect(lambda: self.toggle_task(plugin_id))
            stop_task_layout.addWidget(stop_task_button)
            
            # 设置表格项
            self.status_table.setItem(row_position, 0, name_item)
            self.status_table.setItem(row_position, 1, gui_status_item)
            self.status_table.setItem(row_position, 2, time_item)
            self.status_table.setCellWidget(row_position, 3, stop_gui_widget)
            self.status_table.setCellWidget(row_position, 4, stop_task_widget)
            
            # 连接选择信号
            self.status_table.cellClicked.connect(self.on_cell_clicked)
            
            self.update_status_bar()

    def set_order(self, plugin_ids):
        """按给定的插件ID顺序重建表格行，不改变各插件的状态与计时等信息。"""
        if not isinstance(plugin_ids, (list, tuple)):
            return
        # 先记录当前GUI状态文本，便于还原
        gui_status_map = {}
        try:
            for row in range(self.status_table.rowCount()):
                item = self.status_table.item(row, 0)
                if not item:
                    continue
                pid = item.data(Qt.UserRole)
                gui_item = self.status_table.item(row, 1)
                gui_text = gui_item.text() if gui_item else "未启用"
                gui_status_map[pid] = gui_text
        except Exception:
            gui_status_map = {}

        # 清空现有行（不清空 plugin_status_map）
        try:
            while self.status_table.rowCount() > 0:
                self.status_table.removeRow(0)
        except Exception:
            pass

        # 按顺序重新插入行
        for pid in plugin_ids:
            if pid not in self.plugin_status_map:
                continue
            status_item = self.plugin_status_map[pid]
            row_position = self.status_table.rowCount()
            self.status_table.insertRow(row_position)

            # 名称列
            name_item = QTableWidgetItem(status_item.plugin_name)
            name_item.setData(Qt.UserRole, pid)
            name_item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)

            # GUI状态列
            gui_status_item = QTableWidgetItem(gui_status_map.get(pid, "未启用"))
            gui_status_item.setFlags(Qt.ItemIsEnabled)
            from PySide6.QtGui import QColor as _QColor
            gui_color_map = {
                "未启用": _QColor(169, 169, 169),
                "已启用": _QColor(0, 128, 0),
                "运行中": _QColor(0, 128, 0),
                "已停止": _QColor(255, 0, 0)
            }
            gui_status_item.setForeground(gui_color_map.get(gui_status_item.text(), _QColor(0, 0, 0)))

            # 运行时间列
            time_item = QTableWidgetItem(status_item.time_label.text())
            time_item.setFlags(Qt.ItemIsEnabled)

            # GUI操作
            stop_gui_widget = QWidget()
            stop_gui_layout = QHBoxLayout(stop_gui_widget)
            stop_gui_layout.setContentsMargins(0, 0, 0, 0)
            stop_gui_button = QPushButton("关闭GUI" if gui_status_item.text() == "已启用" else "开启GUI")
            stop_gui_button.setFixedSize(70, 24)
            stop_gui_button.clicked.connect(lambda _, xpid=pid: self.toggle_gui(xpid))
            stop_gui_layout.addWidget(stop_gui_button)

            # 任务操作
            stop_task_widget = QWidget()
            stop_task_layout = QHBoxLayout(stop_task_widget)
            stop_task_layout.setContentsMargins(0, 0, 0, 0)
            stop_task_button = QPushButton("停止任务" if status_item.status.value == "运行中" else "运行任务")
            stop_task_button.setFixedSize(70, 24)
            stop_task_button.clicked.connect(lambda _, xpid=pid: self.toggle_task(xpid))
            stop_task_layout.addWidget(stop_task_button)

            # 写入表格
            self.status_table.setItem(row_position, 0, name_item)
            self.status_table.setItem(row_position, 1, gui_status_item)
            self.status_table.setItem(row_position, 2, time_item)
            self.status_table.setCellWidget(row_position, 3, stop_gui_widget)
            self.status_table.setCellWidget(row_position, 4, stop_task_widget)

        # 重新连接表格点击（若被清理）
        try:
            self.status_table.cellClicked.connect(self.on_cell_clicked)
        except Exception:
            pass
        self.update_status_bar()
    
    def remove_plugin(self, plugin_id):
        """从监控中移除插件"""
        if plugin_id in self.plugin_status_map:
            # 查找并移除表格行
            for row in range(self.status_table.rowCount()):
                item = self.status_table.item(row, 0)
                if item and item.data(Qt.UserRole) == plugin_id:
                    self.status_table.removeRow(row)
                    break
            
            # 从映射中删除
            del self.plugin_status_map[plugin_id]
            self.update_status_bar()
    
    def update_plugin_status(self, plugin_id, status, error_message=None):
        """更新插件状态"""
        if plugin_id in self.plugin_status_map:
            # 转换英文状态为中文
            status_mapping = {
                "running": "运行中",
                "stopped": "已停止",
                "paused": "已暂停",
                "error": "错误"
            }
            # 使用映射转换状态，如果没有映射则保持原样
            if status.lower() in status_mapping:
                status = status_mapping[status.lower()]
            
            status_item = self.plugin_status_map[plugin_id]
            status_enum = StatusMonitorWidget.get_status_enum(status)
            status_item.set_status(status_enum, error_message)
            
            # 更新表格显示
            for row in range(self.status_table.rowCount()):
                item = self.status_table.item(row, 0)
                if item and item.data(Qt.UserRole) == plugin_id:
                    # 同步更新“任务操作”列按钮文本（索引4）
                    task_widget = self.status_table.cellWidget(row, 4)
                    if task_widget:
                        btns = task_widget.findChildren(QPushButton)
                        if btns:
                            btns[0].setText("停止任务" if status == "运行中" else "运行任务")
                    break
            
            self.update_status_bar()
    
    def update_plugin_gui_status(self, plugin_id, gui_status):
        """更新插件GUI状态"""
        if plugin_id in self.plugin_status_map:
            # 更新表格显示
            for row in range(self.status_table.rowCount()):
                item = self.status_table.item(row, 0)
                if item and item.data(Qt.UserRole) == plugin_id:
                    gui_status_item = self.status_table.item(row, 1)
                    gui_status_item.setText(gui_status)
                    
                    # 设置GUI状态颜色
                    color_map = {
                        "未启用": QColor(169, 169, 169),
                        "已启用": QColor(0, 128, 0),  # 改为绿色
                        "运行中": QColor(0, 128, 0),
                        "已停止": QColor(255, 0, 0)
                    }
                    gui_status_item.setForeground(color_map.get(gui_status, QColor(0, 0, 0)))
                    # 同步更新“GUI操作”列按钮文本（索引3）
                    gui_widget = self.status_table.cellWidget(row, 3)
                    if gui_widget:
                        btns = gui_widget.findChildren(QPushButton)
                        if btns:
                            btns[0].setText("关闭GUI" if gui_status == "已启用" else "开启GUI")
                    break
    
    def update_all_times(self):
        """更新所有插件的运行时间显示"""
        for plugin_id, status_item in self.plugin_status_map.items():
            status_item.update_time()
            
            # 更新表格显示（第2列为运行时间）
            for row in range(self.status_table.rowCount()):
                item = self.status_table.item(row, 0)
                if item and item.data(Qt.UserRole) == plugin_id:
                    time_item = self.status_table.item(row, 2)
                    if time_item:
                        time_item.setText(status_item.time_label.text())
                    break
    
    def stop_gui(self, plugin_id):
        """停止插件GUI（移除Tab）"""
        if self.plugin_manager:
            plugin = self.plugin_manager.get_plugin(plugin_id)
            if plugin:
                # 通过主窗口移除Tab
                main_window = self.parent()
                while main_window and not hasattr(main_window, '_remove_plugin_tab'):
                    main_window = main_window.parent()
                if main_window and hasattr(main_window, '_remove_plugin_tab'):
                    main_window._remove_plugin_tab(plugin)
                    # 更新GUI状态
                    self.update_plugin_gui_status(plugin_id, "未启用")
    
    def start_gui(self, plugin_id):
        """开启插件GUI（创建Tab）"""
        if self.plugin_manager:
            plugin = self.plugin_manager.get_plugin(plugin_id)
            if plugin:
                main_window = self.parent()
                while main_window and not hasattr(main_window, '_show_plugin_tab'):
                    main_window = main_window.parent()
                if main_window and hasattr(main_window, '_show_plugin_tab'):
                    main_window._show_plugin_tab(plugin)
                    self.update_plugin_gui_status(plugin_id, "已启用")
    
    def toggle_gui(self, plugin_id):
        """切换GUI：未启用→开启，已启用→关闭"""
        # 依据当前GUI状态列判断
        for row in range(self.status_table.rowCount()):
            item = self.status_table.item(row, 0)
            if item and item.data(Qt.UserRole) == plugin_id:
                gui_status_item = self.status_table.item(row, 1)
                current = gui_status_item.text() if gui_status_item else "未启用"
                if current == "已启用":
                    self.stop_gui(plugin_id)
                else:
                    self.start_gui(plugin_id)
                break
    
    def stop_task(self, plugin_id):
        """停止插件任务（停止运行）"""
        if self.plugin_manager:
            plugin = self.plugin_manager.get_plugin(plugin_id)
            if plugin:
                if hasattr(plugin, 'kill'):
                    plugin.kill()
                else:
                    plugin.stop(wait=False)
                # 状态更新会通过信号自动处理
    
    def start_task(self, plugin_id):
        """启动插件任务（开始运行）"""
        if self.plugin_manager:
            plugin = self.plugin_manager.get_plugin(plugin_id)
            if plugin:
                # 优先通过主窗口以便注入参数
                main_window = self.parent()
                while main_window and not hasattr(main_window, '_start_plugin_with_params'):
                    main_window = main_window.parent()
                if main_window and hasattr(main_window, '_start_plugin_with_params') and (not plugin.has_ui and getattr(plugin, 'parameters', {}) is not None):
                    main_window._start_plugin_with_params(plugin)
                else:
                    plugin.start()
                # 运行状态会通过信号更新
    
    def toggle_task(self, plugin_id):
        """切换任务运行状态：停止↔运行"""
        if self.plugin_manager:
            plugin = self.plugin_manager.get_plugin(plugin_id)
            if plugin:
                if plugin.is_running:
                    self.stop_task(plugin_id)
                else:
                    self.start_task(plugin_id)
    
    def show_plugin_details(self, plugin_id):
        """显示插件详细信息"""
        if plugin_id in self.plugin_status_map:
            self.plugin_status_map[plugin_id].show_details()
    
    def on_plugin_status_changed(self, plugin_id, status):
        """插件状态改变回调"""
        self.status_updated.emit(plugin_id, status)
        self.update_status_bar()
    
    def on_cell_clicked(self, row, column):
        """表格单元格点击事件"""
        if column == 0:  # 点击插件名称时
            plugin_id = self.status_table.item(row, 0).data(Qt.UserRole)
            self.plugin_selected.emit(plugin_id)
    
    def update_status_bar(self):
        """更新状态栏信息"""
        total = len(self.plugin_status_map)
        running = sum(1 for s in self.plugin_status_map.values() if s.status == PluginStatus.RUNNING)
        paused = sum(1 for s in self.plugin_status_map.values() if s.status == PluginStatus.PAUSED)
        error = sum(1 for s in self.plugin_status_map.values() if s.status == PluginStatus.ERROR)
        stopped = sum(1 for s in self.plugin_status_map.values() if s.status == PluginStatus.STOPPED)
        
        status_text = f"总插件数: {total}, 运行中: {running}, 已暂停: {paused}, 错误: {error}, 已停止: {stopped}"
        self.status_bar.setText(status_text)
    
    @staticmethod
    def get_status_enum(status_str):
        """将状态字符串转换为枚举"""
        for status in PluginStatus:
            if status.value == status_str:
                return status
        return PluginStatus.STOPPED