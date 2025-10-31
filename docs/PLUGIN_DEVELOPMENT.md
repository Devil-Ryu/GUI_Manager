# 插件开发指南

本指南介绍如何为 GUI_Manager 开发插件（无界面插件 BasePlugin、带界面插件 BaseUIPlugin），以及参数、配置、日志与生命周期等要点。

适用环境：Python 3.10+，PySide6（版本以 `requirements.txt` 为准）。

## 插件架构概述

GUI_Manager使用插件化架构，支持两种类型的插件：

1. **普通插件(BasePlugin)**：没有用户界面的后台服务插件
2. **UI插件(BaseUIPlugin)**：带有图形用户界面的插件

## 插件基础结构

每个插件必须：

1. 位于 `GUI_Manager/plugins/` 目录下的独立子目录
2. 包含 `__init__.py`，定义继承自 `BasePlugin` 或 `BaseUIPlugin` 的插件类
3. 实现必要抽象方法；插件 ID 由类构造时传入（由系统管理）

命名建议：
- 目录名使用小写加下划线，如 `my_cool_plugin`
- 类名使用帕斯卡命名，如 `MyCoolPlugin`
- 避免与现有插件 ID 重名

对于无界面插件，可通过 `parameters` 属性定义参数，系统会自动生成通用参数界面并持久化参数值。参数值在运行时可通过 `self.parameters_values` 或辅助方法获取。

## 插件目录结构

```
plugins/
├── your_plugin_name/       # 插件目录名
│   ├── __init__.py         # 插件主文件，包含插件类定义
│   └── [其他辅助文件]       # 可选的其他模块、资源文件等
```

## 开发普通插件（BasePlugin）

### 基本步骤

1. 创建插件目录和`__init__.py`文件
2. 导入必要的基类
3. 定义插件类，继承自`BasePlugin`
4. 实现必要的方法和属性

### 示例代码（最小实现）

#### 基本无界面插件

```python
import time
from GUI_Manager.app.plugin_manager import BasePlugin

class MyPlugin(BasePlugin):
    """我的自定义插件"""
    
    @property
    def name(self):
        """插件名称"""
        return "我的插件"
    
    @property
    def description(self):
        """插件描述"""
        return "这是一个自定义的普通插件示例"
    
    def run(self):
        """插件的主要运行逻辑"""
        self.log_output("我的插件开始运行...")
        
        # 加载插件配置（如果需要）
        plugin_config = self.config_manager.load_plugin_config(
            self.plugin_id,
            {"interval": 1.0}
        )
        
        interval = plugin_config.get("interval", 1.0)
        
        # 主循环
        count = 0
        while not self.is_stopped():
            # 执行插件逻辑
            self.log_output(f"执行第 {count+1} 次操作")
            count += 1
            
            # 检查停止信号
            for _ in range(int(interval * 10)):
                if self.is_stopped():
                    break
                time.sleep(0.1)
            
            if self.is_stopped():
                break
        
        self.log_output("我的插件停止运行")
```

要点：
- 请确保循环中定期检查 `self.is_stopped()`，避免阻塞退出
- 如需访问配置，统一使用 `self.config_manager`

#### 带参数示例（会在通用参数面板中呈现）

```python
import time
import random
from GUI_Manager.app.plugin_manager import BasePlugin

class MyParameterPlugin(BasePlugin):
    """带参数的自定义插件"""
    
    @property
    def name(self):
        """插件名称"""
        return "参数示例插件"
    
    @property
    def description(self):
        """插件描述"""
        return "这是一个带参数的普通插件示例"
    
    @property
    def parameters(self):
        """定义插件参数
        
        返回参数定义字典，格式如下：
        {
            "param_name": {
                "type": "string|integer|float|boolean|select|datetime|file",
                "label": "参数显示名称",
                "description": "参数描述",
                "value": 默认值,
                "min": 最小值(可选),
                "max": 最大值(可选),
                "options": 选项列表(select类型时使用)
            }
        }
        """
        return {
            "interval": {
                "type": "float",
                "label": "更新间隔",
                "description": "数据更新的时间间隔(秒)",
                "value": 1.0,
                "min": 0.1,
                "max": 10.0
            },
            "output_type": {
                "type": "select",
                "label": "输出类型",
                "description": "选择输出的内容类型",
                "value": "numbers",
                "options": [
                    ("numbers", "随机数"),
                    ("strings", "随机字符串"),
                    ("datetime", "当前时间")
                ]
            },
            "enable_logging": {
                "type": "boolean",
                "label": "启用详细日志",
                "description": "是否输出详细的日志信息",
                "value": True
            }
        }
    
    def run(self):
        """插件的主要运行逻辑"""
        self.log_output("参数插件开始运行...")
        
        # 检查是否有传入的参数
        if hasattr(self, 'parameters_values') and self.parameters_values:
            self.log_output(f"接收到参数: {self.parameters_values}")
        
        # 主循环
        count = 0
        while not self.is_stopped():
            # 获取参数值（如果没有参数则使用默认值）
            interval = self.parameters_values.get('interval', 1.0) if hasattr(self, 'parameters_values') else 1.0
            output_type = self.parameters_values.get('output_type', 'numbers') if hasattr(self, 'parameters_values') else 'numbers'
            enable_logging = self.parameters_values.get('enable_logging', True) if hasattr(self, 'parameters_values') else True
            
            # 基于参数执行不同的逻辑
            output_content = ""
            if output_type == "numbers":
                output_content = f"随机数: {random.randint(1, 100)}"
            elif output_type == "strings":
                output_content = f"随机字符串: {random.choice(['apple', 'banana', 'cherry', 'date', 'elderberry'])}"
            elif output_type == "datetime":
                output_content = f"当前时间: {time.strftime('%Y-%m-%d %H:%M:%S')}"
            
            self.log_output(f"执行第 {count+1} 次操作 - {output_content}")
            count += 1
            
            if enable_logging:
                self.log_output(f"详细信息: 当前间隔={interval}秒, 输出类型={output_type}")
            
        # 检查停止信号
            for _ in range(int(interval * 10)):
                if self.is_stopped():
                    break
                time.sleep(0.1)
            
            if self.is_stopped():
                break
        
        self.log_output("参数插件停止运行")
```

## 开发 UI 插件（BaseUIPlugin）

### 基本步骤

1. 创建插件目录和`__init__.py`文件
2. 导入必要的基类和PySide6组件
3. 定义插件类，继承自`BaseUIPlugin`
4. 实现必要的方法和属性
5. 实现`init_ui()`方法来创建用户界面（在 UI 线程创建与布局）

### 示例代码

```python
import time
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QGroupBox, QComboBox, QSpinBox
)
from GUI_Manager.app.plugin_manager import BaseUIPlugin

class MyUIPlugin(BaseUIPlugin):
    """我的自定义UI插件"""
    
    def __init__(self, plugin_id, config_manager=None, parent=None):
        super().__init__(plugin_id, config_manager, parent)
        
        # 插件配置和状态
        self.task_count = 0
        self.is_task_running = False
    
    @property
    def name(self):
        """插件名称"""
        return "我的UI插件"
    
    @property
    def description(self):
        """插件描述"""
        return "这是一个带用户界面的插件示例"
    
    def init_ui(self):
        """初始化插件界面"""
        # 设置窗口标题
        self.widget.setWindowTitle(self.name)
        
        # 主布局
        main_layout = QVBoxLayout(self.widget)
        
        # 任务配置组
        config_group = QGroupBox("任务配置")
        config_layout = QVBoxLayout()
        
        # 添加UI元素
        self.status_label = QLabel("就绪")
        config_layout.addWidget(self.status_label)
        
        # 控制按钮
        control_layout = QHBoxLayout()
        self.start_button = QPushButton("开始任务")
        self.start_button.clicked.connect(self.on_start_clicked)
        control_layout.addWidget(self.start_button)
        
        config_layout.addLayout(control_layout)
        config_group.setLayout(config_layout)
        
        main_layout.addWidget(config_group)
        main_layout.addStretch()
    
    def on_start_clicked(self):
        """开始任务按钮点击事件"""
        if not self.is_task_running:
            self.is_task_running = True
            self.start_button.setText("停止任务")
            self.task_count += 1
            self.status_label.setText(f"执行任务 #{self.task_count}")
            self.log_output(f"开始执行任务 #{self.task_count}")
        else:
            self.is_task_running = False
            self.start_button.setText("开始任务")
            self.status_label.setText("就绪")
            self.log_output(f"任务 #{self.task_count} 已停止")
    
    def run(self):
        """插件的主要运行逻辑"""
        self.log_output("UI插件开始运行")
        
        # 在UI插件中，主要依赖用户交互
        # 这里我们可以执行一些初始化操作
        
        # 等待停止信号
        while not self.is_stopped():
            time.sleep(0.1)
        
        # 停止任务（如果正在运行）
        if self.is_task_running:
            self.is_task_running = False
        
        self.log_output("UI插件停止运行")
```

UI 规范：
- 在 `init_ui()` 中完成控件创建、布局与信号连接，不在构造器中创建 Qt 控件
- 耗时操作放在工作线程中，使用信号槽反馈到 UI
- 文本、按钮命名清晰，必要时增加状态标签

## 插件生命周期

1. **初始化**：插件实例创建，`__init__`方法被调用
2. **UI初始化**（仅UI插件）：`init_ui`方法被调用，创建界面组件
3. **启动**：插件被启动时，`start`方法被调用，启动独立线程运行`run`方法
4. **运行**：`run`方法在独立线程中执行，包含插件的主要逻辑
5. **停止**：插件被停止时，`stop`方法被调用，设置停止信号
6. **清理**：插件停止后，释放资源

线程注意：不要在工作线程直接触碰 Qt 控件；如需更新 UI，请通过信号在主线程执行。

## 配置管理（ConfigManager）

插件可以使用 `self.config_manager` 管理配置：

```python
# 加载配置（如果不存在则使用默认配置）
plugin_config = self.config_manager.load_plugin_config(
    self.plugin_id,
    {"key1": "value1", "key2": 100}
)

# 使用配置值
value1 = plugin_config.get("key1")

# 保存配置
self.config_manager.save_plugin_config(
    self.plugin_id,
    {"key1": "new_value", "key2": 200}
)
```

默认配置推荐与版本字段：建议在默认配置中加入 `version` 字段，便于后续迁移。

## 日志与输出（主界面与状态监控可见）

插件可以使用`log_output`方法记录信息，这些信息会显示在主程序的状态监控中：

```python
# 记录普通信息
self.log_output("这是一条普通信息")

# 记录错误信息
self.log_output(f"错误: {error_message}")

# 记录状态更新
self.log_output(f"状态更新: {new_status}")
```

严重错误建议同时记录到独立日志文件或附带 traceback，利于排查。

## 信号与通信

插件可以使用内置的信号系统与主程序通信：

```python
# 发送状态变更信号
self.signals.status_changed.emit(self.plugin_id, "running")

# 发送错误信号
self.signals.error_occurred.emit(self.plugin_id, "发生错误")

# 发送输出信号（等同于log_output）
self.signals.output_generated.emit(self.plugin_id, "输出内容")
```

信号语义应尽量稳定，便于主程序与其它工具消费。

## 避免常见陷阱

1. **长时间阻塞**：不要在`run`方法中执行长时间阻塞操作，应定期检查`is_stopped()`
2. **UI线程操作**：不要在工作线程中直接操作UI元素，使用Qt的信号槽机制
3. **资源泄漏**：确保在插件停止时正确释放所有资源
4. **异常处理**：妥善处理所有可能的异常，避免插件崩溃影响主程序
5. **参数处理**：对于带参数的无界面插件，确保在使用参数前检查`parameters_values`属性是否存在，并提供合理的默认值
6. **资源文件**：若依赖资源（图片、UI 文件），请使用相对路径并确保随插件目录一并分发
7. **异常控制**：不要吞掉异常；必要时将关键信息输出到状态监控或日志

## 测试插件

1. 创建插件目录和文件
2. 实现插件逻辑
3. 启动主程序，检查插件是否正确加载
4. 使用状态监控查看插件输出和状态
5. 对于参数插件，验证参数变更是否实时生效或在下一周期加载

## 调试技巧

1. 使用`log_output`记录关键信息
2. 查看主程序日志文件
3. 对于UI插件，可以添加调试按钮或输出到控制台
4. 对于带参数的无界面插件，可以在启动时记录当前参数值，方便调试
5. 使用最小可复现入口（小函数/小类）验证导入路径是否正确

## 最佳实践

1. 插件应有清晰的名称和描述
2. 妥善处理配置的加载和保存
3. 定期检查停止信号，确保插件可以正常停止
4. 提供有用的日志信息，便于调试和监控
5. UI插件应设计简洁直观的界面
6. 对于无界面插件，尽量使用`parameters`属性定义可配置项，提供良好的用户体验
7. 为参数提供合理的默认值和详细的描述，帮助用户理解参数的用途
8. 在启动时检查和记录当前参数值，方便调试和问题排查
9. 对外暴露的 API（如信号名、参数键）保持向后兼容

## 示例插件

项目中提供了两个示例插件，可以作为参考：

1. `plugins/example_parameter_plugin`：带参数无界面插件示例
2. `plugins/gui_example_plugin`：UI 插件示例

## 常见问题（FAQ）

**Q: 插件内部导入本目录模块失败（No module named ...）？**
A: 通过“导入插件”创建的插件，运行入口模块前会把插件目录临时加入 `sys.path`，同级导入应可用；如果你手动编写插件，请确保被导入模块与入口模块在同一目录或正确的包结构中。

**Q: UI 插件何时创建 UI？**
A: `BaseUIPlugin` 会在 `create_ui()` 时创建/返回 `self.widget`，不要在构造函数提前创建 Qt 组件。

**Q: 长时间任务如何避免阻塞？**
A: 在 `run()` 中循环处理，定期检查 `is_stopped()`；避免在 UI 线程执行耗时操作。

**Q: 插件加载失败怎么办？**
A: 检查日志文件，确保插件类正确继承了基类，并且实现了所有必要的方法。

**Q: 如何保存插件配置？**
A: 使用`self.config_manager.save_plugin_config()`方法保存配置。

**Q: 插件如何接收停止信号？**
A: 在`run`方法中定期调用`self.is_stopped()`检查是否收到停止信号。

**Q: UI插件中如何更新界面？**
A: 使用Qt的信号槽机制，或确保在UI线程中更新界面元素。

**Q: 插件之间可以通信吗？**
A: 目前插件系统没有直接的插件间通信机制，但可以通过共享配置或使用第三方消息队列实现。