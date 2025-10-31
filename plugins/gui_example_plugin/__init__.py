import time
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QTextEdit, QProgressBar, QGroupBox, QLineEdit,
    QSpinBox, QDoubleSpinBox, QComboBox
)
from PySide6.QtCore import Qt, QThread, Signal
from app.plugin_manager import BaseUIPlugin


class WorkerThread(QThread):
    """工作线程，用于执行耗时操作"""
    
    progress_updated = Signal(int)
    log_updated = Signal(str)
    task_completed = Signal()
    
    def __init__(self, task_type, iterations, delay, parent=None):
        super().__init__(parent)
        self.task_type = task_type
        self.iterations = iterations
        self.delay = delay
        self._stop_requested = False
    
    def stop(self):
        """停止线程"""
        self._stop_requested = True
    
    def run(self):
        """线程运行函数"""
        self.log_updated.emit(f"开始执行任务: {self.task_type}")
        self.log_updated.emit(f"总迭代次数: {self.iterations}, 每次延迟: {self.delay}秒")
        
        for i in range(1, self.iterations + 1):
            if self._stop_requested:
                self.log_updated.emit("任务已取消")
                return
            
            # 模拟工作
            time.sleep(self.delay)
            
            # 更新进度
            progress = int((i / self.iterations) * 100)
            self.progress_updated.emit(progress)
            self.log_updated.emit(f"完成迭代 {i}/{self.iterations} ({progress}%)")
        
        self.log_updated.emit("任务完成")
        self.task_completed.emit()


class GUIExamplePlugin(BaseUIPlugin):
    """带界面的示例插件"""
    
    def __init__(self, plugin_id, config_manager=None, parent=None):
        super().__init__(plugin_id, config_manager, parent)
        
        # 任务配置
        self.task_type = "count"
        self.iterations = 10
        self.delay = 1.0
        
        # 任务状态
        self.task_running = False
        self.current_progress = 0
        self.worker_thread = None
        
        # 创建配置
        self.config = {
            "task_type": self.task_type,
            "iterations": self.iterations,
            "delay": self.delay
        }
        
        # 加载配置
        if self.config_manager:
            loaded_config = self.config_manager.load_plugin_config(self.plugin_id, self.config)
            self.task_type = loaded_config.get('task_type', self.task_type)
            self.iterations = loaded_config.get('iterations', self.iterations)
            self.delay = loaded_config.get('delay', self.delay)
        
    @property
    def name(self):
        """插件名称"""
        return "GUI示例插件"
        
    @property
    def description(self):
        """插件描述"""
        return "一个带界面的示例插件，演示如何在插件中使用Qt界面元素"
    
    def init_ui(self):
        """初始化插件界面"""
        # 确保widget已创建
        if self.widget is None:
            return
            
        # 设置窗口标题
        self.widget.setWindowTitle(self.name)
        
        # 主布局
        main_layout = QVBoxLayout(self.widget)
        
        # 任务配置组
        config_group = QGroupBox("任务配置")
        config_layout = QVBoxLayout()
        
        # 任务类型选择
        type_layout = QHBoxLayout()
        type_layout.addWidget(QLabel("任务类型:"))
        self.task_type_combo = QComboBox()
        self.task_type_combo.addItems(["模拟计算任务", "数据处理任务", "网络请求任务"])
        type_layout.addWidget(self.task_type_combo)
        type_layout.addStretch()
        
        # 迭代次数
        iterations_layout = QHBoxLayout()
        iterations_layout.addWidget(QLabel("迭代次数:"))
        self.iterations_spin = QSpinBox()
        self.iterations_spin.setRange(1, 100)
        self.iterations_spin.setValue(10)
        iterations_layout.addWidget(self.iterations_spin)
        iterations_layout.addStretch()
        
        # 延迟时间
        delay_layout = QHBoxLayout()
        delay_layout.addWidget(QLabel("每次延迟(秒):"))
        self.delay_spin = QDoubleSpinBox()
        self.delay_spin.setRange(0.1, 5.0)
        self.delay_spin.setDecimals(1)
        self.delay_spin.setValue(0.5)
        delay_layout.addWidget(self.delay_spin)
        delay_layout.addStretch()
        
        # 添加到配置布局
        config_layout.addLayout(type_layout)
        config_layout.addLayout(iterations_layout)
        config_layout.addLayout(delay_layout)
        config_group.setLayout(config_layout)
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        
        # 控制按钮
        button_layout = QHBoxLayout()
        self.start_task_button = QPushButton("开始任务")
        self.stop_task_button = QPushButton("停止任务")
        self.reset_button = QPushButton("重置")
        
        self.start_task_button.clicked.connect(self.start_task)
        self.stop_task_button.clicked.connect(self.stop_task)
        self.reset_button.clicked.connect(self.reset)
        
        self.stop_task_button.setEnabled(False)
        
        button_layout.addWidget(self.start_task_button)
        button_layout.addWidget(self.stop_task_button)
        button_layout.addWidget(self.reset_button)
        button_layout.addStretch()
        
        # 状态显示
        status_group = QGroupBox("任务状态")
        status_layout = QVBoxLayout()
        
        self.status_label = QLabel("就绪")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("font-weight: bold; color: blue;")
        
        status_layout.addWidget(self.status_label)
        status_group.setLayout(status_layout)
        
        # 日志输出
        log_group = QGroupBox("任务日志")
        log_layout = QVBoxLayout()
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setLineWrapMode(QTextEdit.NoWrap)
        
        log_layout.addWidget(self.log_text)
        log_group.setLayout(log_layout)
        
        # 添加到主布局
        main_layout.addWidget(config_group)
        main_layout.addWidget(self.progress_bar)
        main_layout.addLayout(button_layout)
        main_layout.addWidget(status_group)
        main_layout.addWidget(log_group, 1)
    
    def start_task(self):
        """开始任务"""
        # 禁用配置控件和启动按钮
        self.task_type_combo.setEnabled(False)
        self.iterations_spin.setEnabled(False)
        self.delay_spin.setEnabled(False)
        self.start_task_button.setEnabled(False)
        self.stop_task_button.setEnabled(True)
        
        # 更新状态
        self.status_label.setText("任务运行中")
        self.status_label.setStyleSheet("font-weight: bold; color: green;")
        self.progress_bar.setValue(0)
        
        # 创建并启动工作线程
        task_type = self.task_type_combo.currentText()
        iterations = self.iterations_spin.value()
        delay = self.delay_spin.value()
        
        # 使用self.widget作为worker线程的父对象，确保是QObject类型
        self.worker_thread = WorkerThread(task_type, iterations, delay, self.widget)
        self.worker_thread.progress_updated.connect(self.update_progress)
        self.worker_thread.log_updated.connect(self.add_log)
        self.worker_thread.task_completed.connect(self.task_completed)
        self.worker_thread.finished.connect(self.thread_finished)
        self.worker_thread.start()
        
        # 同时发送日志到主程序
        self.log_output(f"开始执行{task_type}")
    
    def stop_task(self):
        """停止任务"""
        if self.worker_thread and self.worker_thread.isRunning():
            self.worker_thread.stop()
            self.status_label.setText("正在停止任务...")
            self.status_label.setStyleSheet("font-weight: bold; color: orange;")
            self.log_output("停止任务请求已发送")
    
    def reset(self):
        """重置界面"""
        # 确保线程已经停止
        if self.worker_thread and self.worker_thread.isRunning():
            self.stop_task()
            self.worker_thread.wait()
        
        # 重置UI状态
        self.task_type_combo.setEnabled(True)
        self.iterations_spin.setEnabled(True)
        self.delay_spin.setEnabled(True)
        self.start_task_button.setEnabled(True)
        self.stop_task_button.setEnabled(False)
        
        self.status_label.setText("就绪")
        self.status_label.setStyleSheet("font-weight: bold; color: blue;")
        self.progress_bar.setValue(0)
        self.log_text.clear()
        
        self.log_output("插件界面已重置")
    
    def update_progress(self, progress):
        """更新进度条"""
        self.progress_bar.setValue(progress)
    
    def add_log(self, message):
        """添加日志信息"""
        self.log_text.append(message)
        # 同时将日志发送到插件管理器，确保在插件管理页面也能看到这些日志
        self.log_output(message)
    
    def task_completed(self):
        """任务完成回调"""
        self.status_label.setText("任务已完成")
        self.status_label.setStyleSheet("font-weight: bold; color: purple;")
        self.log_output("任务执行完成")
    
    def thread_finished(self):
        """线程结束回调"""
        # 重新启用控件
        self.task_type_combo.setEnabled(True)
        self.iterations_spin.setEnabled(True)
        self.delay_spin.setEnabled(True)
        self.start_task_button.setEnabled(True)
        self.stop_task_button.setEnabled(False)
        
        # 清理线程
        self.worker_thread = None
    
    def run(self):
        """插件的主要运行逻辑 - 由BasePlugin调用"""
        self.log_output("GUI示例插件启动")
        
        # 在UI插件中，我们主要依赖用户交互
        # 这里我们可以执行一些初始化操作
        
        # 加载插件配置
        plugin_config = self.config_manager.load_plugin_config(
            self.plugin_id,
            {
                "last_task_type": 0,
                "last_iterations": 10,
                "last_delay": 0.5
            }
        )
        
        # 应用保存的配置
        self.task_type_combo.setCurrentIndex(plugin_config.get("last_task_type", 0))
        self.iterations_spin.setValue(plugin_config.get("last_iterations", 10))
        self.delay_spin.setValue(plugin_config.get("last_delay", 0.5))
        
        # 由于是UI插件，这里不需要持续运行的循环
        # 我们只需要等待停止信号
        while not self.is_stopped():
            time.sleep(0.1)
        
        # 保存当前配置
        plugin_config = {
            "last_task_type": self.task_type_combo.currentIndex(),
            "last_iterations": self.iterations_spin.value(),
            "last_delay": self.delay_spin.value()
        }
        self.config_manager.save_plugin_config(self.plugin_id, plugin_config)
        
        # 停止任务（如果正在运行）
        self.stop_task()
        
        self.log_output("GUI示例插件停止")
    
    def closeEvent(self, event):
        """窗口关闭事件"""
        self.stop_task()
        event.accept()