import logging

# 配置日志记录
logger = logging.getLogger(__name__)
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
                            QFileDialog, QLineEdit, QCheckBox, QComboBox, QGroupBox,
                            QTextEdit, QGridLayout, QMessageBox, QScrollArea, QWidget,
                            QToolButton, QSizePolicy, QFrame)
from PySide6.QtCore import Qt, Signal
import os
import re
import ast
import importlib.util

class ParameterConfigWidget(QGroupBox):
    """参数配置小部件，用于配置单个参数"""
    
    param_removed = Signal(int)
    
    def __init__(self, index, parent=None):
        super().__init__(f"参数 {index + 1}", parent)
        self.index = index
        self.init_ui()
    
    def init_ui(self):
        """初始化参数配置UI"""
        layout = QGridLayout(self)
        
        # 参数名称
        layout.addWidget(QLabel("参数名称:"), 0, 0)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("例如: interval")
        layout.addWidget(self.name_edit, 0, 1)
        
        # 参数类型
        layout.addWidget(QLabel("参数类型:"), 1, 0)
        self.type_combo = QComboBox()
        self.type_combo.addItems(["string", "integer", "float", "boolean", "select"])
        self.type_combo.currentTextChanged.connect(self.on_type_changed)
        layout.addWidget(self.type_combo, 1, 1)
        
        # 参数标签
        layout.addWidget(QLabel("显示标签:"), 2, 0)
        self.label_edit = QLineEdit()
        self.label_edit.setPlaceholderText("例如: 时间间隔")
        layout.addWidget(self.label_edit, 2, 1)
        
        # 参数描述
        layout.addWidget(QLabel("参数描述:"), 3, 0)
        self.description_edit = QTextEdit()
        self.description_edit.setPlaceholderText("参数的详细描述")
        self.description_edit.setMinimumHeight(60)
        layout.addWidget(self.description_edit, 3, 1)
        
        # 默认值
        layout.addWidget(QLabel("默认值:"), 4, 0)
        self.value_edit = QLineEdit()
        layout.addWidget(self.value_edit, 4, 1)
        
        # 最小值/最大值（仅对数字类型显示）
        self.min_max_widget = QWidget()
        self.min_max_layout = QHBoxLayout(self.min_max_widget)
        self.min_edit = QLineEdit()
        self.min_edit.setPlaceholderText("最小值")
        self.max_edit = QLineEdit()
        self.max_edit.setPlaceholderText("最大值")
        self.min_max_layout.addWidget(QLabel("最小值:"))
        self.min_max_layout.addWidget(self.min_edit)
        self.min_max_layout.addWidget(QLabel("最大值:"))
        self.min_max_layout.addWidget(self.max_edit)
        layout.addWidget(self.min_max_widget, 5, 0, 1, 2)
        self.min_max_widget.hide()
        
        # 选项（仅对select类型显示）
        self.options_widget = QWidget()
        self.options_layout = QVBoxLayout(self.options_widget)
        self.options_edit = QTextEdit()
        self.options_edit.setPlaceholderText("每行一个选项，格式：值,标签\n例如:\nnumbers,随机数\nstrings,随机字符串")
        self.options_edit.setMinimumHeight(80)
        self.options_layout.addWidget(QLabel("选项列表:"))
        self.options_layout.addWidget(self.options_edit)
        layout.addWidget(self.options_widget, 6, 0, 1, 2)
        self.options_widget.hide()
        
        # 移除按钮
        remove_button = QPushButton("移除参数")
        remove_button.clicked.connect(self.remove)
        layout.addWidget(remove_button, 7, 0, 1, 2)
        layout.setAlignment(remove_button, Qt.AlignRight)
    
    def on_type_changed(self, param_type):
        """处理参数类型变化"""
        # 隐藏所有特殊配置
        self.min_max_widget.hide()
        self.options_widget.hide()
        
        # 根据类型显示相应的配置
        if param_type in ["integer", "float"]:
            self.min_max_widget.show()
        elif param_type == "select":
            self.options_widget.show()
    
    def update_index(self, new_index):
        """更新参数索引"""
        self.index = new_index
        self.setTitle(f"参数 {new_index + 1}")
    
    def remove(self):
        """移除当前参数"""
        self.param_removed.emit(self.index)
        self.deleteLater()
    
    def get_parameter_config(self):
        """获取参数配置"""
        param_type = self.type_combo.currentText()
        config = {
            "name": self.name_edit.text(),
            "type": param_type,
            "label": self.label_edit.text(),
            "description": self.description_edit.toPlainText(),
        }
        
        # 处理默认值
        value_str = self.value_edit.text()
        if param_type == "integer":
            config["value"] = int(value_str) if value_str.isdigit() else 0
            # 添加最小值/最大值
            if self.min_edit.text().isdigit():
                config["min"] = int(self.min_edit.text())
            if self.max_edit.text().isdigit():
                config["max"] = int(self.max_edit.text())
        elif param_type == "float":
            try:
                config["value"] = float(value_str)
            except ValueError:
                config["value"] = 0.0
            # 添加最小值/最大值
            try:
                config["min"] = float(self.min_edit.text()) if self.min_edit.text() else None
            except ValueError:
                config["min"] = None
            try:
                config["max"] = float(self.max_edit.text()) if self.max_edit.text() else None
            except ValueError:
                config["max"] = None
        elif param_type == "boolean":
            config["value"] = value_str.lower() == "true" or value_str == "1"
        elif param_type == "select":
            # 解析选项列表：支持
            # 1) 值,标签
            # 2) 仅值（标签=值）
            options_text = self.options_edit.toPlainText().strip()
            options = []
            for raw in options_text.split('\n'):
                line = raw.strip()
                if not line:
                    continue
                if ',' in line:
                    v, lbl = line.split(',', 1)
                    options.append((v.strip(), lbl.strip()))
                else:
                    options.append((line, line))
            config["options"] = options
            config["value"] = options[0][0] if options else ""
        else:  # string
            config["value"] = value_str
        
        return config

class PluginImportDialog(QDialog):
    """插件导入对话框，用于导入现有的插件"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("导入插件")
        self.setMinimumWidth(600)
        self.setMinimumHeight(500)
        
        # 存储用户选择的插件信息
        self.plugin_info = {
            "folder_path": "",
            "has_ui": False,
            "plugin_entry": "",
            "plugin_name": "",
            "plugin_id": "",
            "parameters": []
        }
        # 更新模式下冻结名称与ID（防止选择新文件夹时被覆盖）
        self._freeze_identity: bool = False
        # 更新场景下的首选入口文件与函数名（由外部设置）
        self._preferred_entry_basename: str | None = None
        self._preferred_function_name: str | None = None
        
        self.init_ui()
    # 更新场景：锁定名称与ID，防止在选择新文件夹时被自动覆盖
    def set_update_identity(self, name: str, plugin_id: str):
        try:
            self.plugin_name_edit.setText(str(name or ""))
            self.plugin_id_edit.setText(str(plugin_id or ""))
            # 标记ID为用户已编辑，阻止自动生成逻辑
            self._plugin_id_user_edited = True
            # 冻结标记：browse_folder/update_plugin_id 不再自动更改（但用户可手动编辑）
            self._freeze_identity = True
        except Exception:
            pass

    # 供“更新插件”时预先指定入口文件与函数，以便在选择文件夹后自动选中
    def set_preferred_entry_and_function(self, entry_basename: str | None, function_name: str | None):
        try:
            self._preferred_entry_basename = entry_basename
            self._preferred_function_name = function_name
        except Exception:
            self._preferred_entry_basename = entry_basename
            self._preferred_function_name = function_name
    
    def init_ui(self):
        """初始化对话框UI"""
        main_layout = QVBoxLayout(self)
        
        # 插件源文件夹选择∑∑
        folder_group = QGroupBox("选择插件源文件夹")
        folder_layout = QHBoxLayout()
        self.folder_path_edit = QLineEdit()
        self.folder_path_edit.setReadOnly(True)
        # self.folder_path_edit.setMaximumHeight(60)  # 限制高度
        browse_button = QPushButton("浏览...")
        # browse_button.setMaximumHeight(60)  # 限制高度
        browse_button.clicked.connect(self.browse_folder)
        folder_layout.addWidget(self.folder_path_edit)
        folder_layout.addWidget(browse_button)
        folder_group.setLayout(folder_layout)
        folder_group.setMaximumHeight(120)  # 限制整个组的高度
        main_layout.addWidget(folder_group)
        
        # 插件基本信息
        info_group = QGroupBox("插件基本信息")
        info_layout = QGridLayout()
        
        # 插件名称
        info_layout.addWidget(QLabel("插件名称:"), 0, 0)
        self.plugin_name_edit = QLineEdit()
        info_layout.addWidget(self.plugin_name_edit, 0, 1)
        
        # 插件ID
        info_layout.addWidget(QLabel("插件ID(插件唯一标识):"), 1, 0)
        self.plugin_id_edit = QLineEdit()
        # 允许用户手动修改插件ID；仅在用户未手动修改前根据名称自动生成
        self._plugin_id_user_edited = False
        self.plugin_id_edit.textEdited.connect(self.on_plugin_id_edited)
        info_layout.addWidget(self.plugin_id_edit, 1, 1)
        
        # 程序入口文件选择
        entry_file_layout = QHBoxLayout()
        entry_file_layout.addWidget(QLabel("入口文件:"))
        self.plugin_entry_combo = QComboBox()
        self.plugin_entry_combo.setPlaceholderText("选择Python文件...")
        self.plugin_entry_combo.currentTextChanged.connect(self.on_entry_file_changed)
        entry_file_layout.addWidget(self.plugin_entry_combo)
        info_layout.addLayout(entry_file_layout, 2, 0, 1, 2)
        
        # 入口函数选择
        entry_func_layout = QHBoxLayout()
        entry_func_layout.addWidget(QLabel("入口函数:"))
        self.plugin_func_combo = QComboBox()
        self.plugin_func_combo.setPlaceholderText("选择函数...")
        entry_func_layout.addWidget(self.plugin_func_combo)
        info_layout.addLayout(entry_func_layout, 3, 0, 1, 2)

        # 插件类型选择（移动到入口函数下一行）
        info_layout.addWidget(QLabel("插件类型:"), 4, 0)
        self.plugin_type_combo = QComboBox()
        self.plugin_type_combo.addItems(["无界面插件", "有界面插件"])
        self.plugin_type_combo.currentIndexChanged.connect(self.on_plugin_type_changed)
        info_layout.addWidget(self.plugin_type_combo, 4, 1)
        
        # 初始设置插件类型（无界面插件）
        self.on_plugin_type_changed(0)
        
        info_group.setLayout(info_layout)
        main_layout.addWidget(info_group)
        
        # 参数配置（仅对无界面插件显示）
        self.params_group = QGroupBox("插件参数配置")
        self.params_layout = QVBoxLayout()
        
        # 参数列表区域
        self.params_scroll_area = QScrollArea()
        self.params_scroll_widget = QWidget()
        self.params_list_layout = QVBoxLayout(self.params_scroll_widget)
        # 参数列表顶对齐，避免垂直居中
        try:
            self.params_list_layout.setAlignment(Qt.AlignTop)
            self.params_scroll_area.setAlignment(Qt.AlignTop)
        except Exception:
            pass
        self.params_scroll_area.setWidget(self.params_scroll_widget)
        self.params_scroll_area.setWidgetResizable(True)
        
        # 添加参数按钮
        add_param_button = QPushButton("添加参数")
        add_param_button.clicked.connect(self.add_parameter)
        
        self.params_layout.addWidget(self.params_scroll_area)
        # 整个参数区也保持顶对齐
        try:
            self.params_layout.setAlignment(Qt.AlignTop)
        except Exception:
            pass
        self.params_layout.addWidget(add_param_button)
        self.params_group.setLayout(self.params_layout)
        
        # 初始显示参数配置（因为默认是无界面插件）
        self.params_group.setVisible(True)
        
        main_layout.addWidget(self.params_group)
        
        # 按钮区域
        buttons_layout = QHBoxLayout()
        self.import_button = QPushButton("导入")
        self.import_button.clicked.connect(self.accept)
        self.import_button.setEnabled(False)  # 初始禁用
        cancel_button = QPushButton("取消")
        cancel_button.clicked.connect(self.reject)
        
        buttons_layout.addStretch()
        buttons_layout.addWidget(self.import_button)
        buttons_layout.addWidget(cancel_button)
        
        main_layout.addLayout(buttons_layout)
        
        # 连接信号
        self.plugin_name_edit.textChanged.connect(self.update_plugin_id)
        self.folder_path_edit.textChanged.connect(self.validate_input)
        self.plugin_name_edit.textChanged.connect(self.validate_input)
        self.plugin_entry_combo.currentTextChanged.connect(self.validate_input)
        self.plugin_func_combo.currentTextChanged.connect(self.validate_input)

        # 默认添加一个测试参数（针对无界面插件）
        # 当前默认插件类型索引为0（无界面），在 on_plugin_type_changed(0) 后 params_group 已配置
        if self.plugin_info.get('has_ui') is False:
            test_widget = self.add_parameter()
            # 设置测试参数的默认值
            if test_widget:
                test_widget.name_edit.setText("test_param")
                test_widget.type_combo.setCurrentText("integer")
                test_widget.label_edit.setText("测试参数")
                test_widget.value_edit.setText("1")
            logger.info("已添加默认测试参数")
            # 重新校验
            self.validate_input()
    
    def browse_folder(self):
        """浏览并选择插件源文件夹"""
        folder_path = QFileDialog.getExistingDirectory(self, "选择插件源文件夹")
        if folder_path:
            self.folder_path_edit.setText(folder_path)
            # 尝试从文件夹名推断插件名称（更新模式下不覆盖）
            if not self._freeze_identity:
                folder_name = os.path.basename(folder_path)
                friendly_name = re.sub(r'[-_]', ' ', folder_name).title()
                self.plugin_name_edit.setText(friendly_name)
            
            # 自动发现Python文件
            self.discover_python_files(folder_path)
    
    def discover_python_files(self, folder_path):
        """发现文件夹中的Python文件"""
        self.plugin_entry_combo.clear()
        self.plugin_func_combo.clear()
        
        try:
            # 查找所有.py文件
            py_files = []
            for file_name in os.listdir(folder_path):
                if file_name.endswith('.py') and not file_name.startswith('__'):
                    py_files.append(file_name)
            
            if py_files:
                self.plugin_entry_combo.addItems(py_files)
                # 优先选择首选入口文件，否则默认第一个
                chosen = None
                try:
                    if self._preferred_entry_basename and self._preferred_entry_basename in py_files:
                        chosen = self._preferred_entry_basename
                except Exception:
                    chosen = None
                if not chosen and py_files:
                    chosen = py_files[0]
                if chosen:
                    self.plugin_entry_combo.setCurrentText(chosen)
                    self.on_entry_file_changed(chosen)
            else:
                self.plugin_entry_combo.addItem("未找到Python文件")
                
        except Exception as e:
            logger.error(f"发现Python文件失败: {e}")
            self.plugin_entry_combo.addItem("发现文件失败")
    
    def on_entry_file_changed(self, file_name):
        """当入口文件改变时，解析其中的函数"""
        self.plugin_func_combo.clear()
        
        if not file_name or file_name in ["未找到Python文件", "发现文件失败"]:
            return
            
        folder_path = self.folder_path_edit.text()
        if not folder_path:
            return
            
        file_path = os.path.join(folder_path, file_name)
        if not os.path.exists(file_path):
            return
            
        try:
            # 解析Python文件中的函数
            functions = self.parse_python_functions(file_path)
            
            if functions:
                for func_name, func_info in functions.items():
                    display_text = f"{func_name} ({func_info['type']})"
                    self.plugin_func_combo.addItem(display_text, func_name)
                
                # 优先选择首选函数名，否则默认第一个
                preferred_set = False
                try:
                    if self._preferred_function_name:
                        # 通过 data 精确匹配函数名
                        for i in range(self.plugin_func_combo.count()):
                            if self.plugin_func_combo.itemData(i) == self._preferred_function_name:
                                self.plugin_func_combo.setCurrentIndex(i)
                                preferred_set = True
                                break
                except Exception:
                    preferred_set = False
                if not preferred_set and functions:
                    first_func = list(functions.keys())[0]
                    self.plugin_func_combo.setCurrentText(f"{first_func} ({functions[first_func]['type']})")
            else:
                self.plugin_func_combo.addItem("未找到可用函数")
                
        except Exception as e:
            logger.error(f"解析函数失败: {e}")
            self.plugin_func_combo.addItem("解析失败")
    
    def parse_python_functions(self, file_path):
        """解析Python文件中的函数和类方法"""
        functions = {}
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 使用AST解析Python代码
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    # 普通函数
                    func_name = node.name
                    if not func_name.startswith('_'):  # 跳过私有函数
                        functions[func_name] = {
                            'type': 'function',
                            'line': node.lineno,
                            'args': [arg.arg for arg in node.args.args]
                        }
                
                elif isinstance(node, ast.ClassDef):
                    # 类中的方法
                    class_name = node.name
                    for item in node.body:
                        if isinstance(item, ast.FunctionDef):
                            method_name = item.name
                            if not method_name.startswith('_'):  # 跳过私有方法
                                full_name = f"{class_name}.{method_name}"
                                functions[full_name] = {
                                    'type': 'method',
                                    'line': item.lineno,
                                    'class': class_name,
                                    'args': [arg.arg for arg in item.args.args]
                                }
            
            # 优先推荐常用函数名
            priority_functions = ['main', 'run', 'process_data', 'start', 'execute']
            sorted_functions = {}
            
            # 先添加优先函数
            for priority_func in priority_functions:
                if priority_func in functions:
                    sorted_functions[priority_func] = functions[priority_func]
            
            # 再添加其他函数
            for func_name, func_info in functions.items():
                if func_name not in sorted_functions:
                    sorted_functions[func_name] = func_info
            
            return sorted_functions
            
        except Exception as e:
            logger.error(f"解析Python文件失败: {e}")
            return {}
    
    def update_plugin_id(self):
        """根据插件名称自动生成插件ID（仅在用户未手动编辑ID时）"""
        if getattr(self, '_freeze_identity', False):
            return
        if getattr(self, '_plugin_id_user_edited', False):
            return
        plugin_name = self.plugin_name_edit.text() or ''
        # 先尝试ASCII化（去除非ASCII字符），不足则回退到通用规则
        ascii_base = plugin_name.encode('ascii', 'ignore').decode('ascii')
        base = ascii_base if ascii_base.strip() else plugin_name
        # 统一小写，空白转下划线
        base = re.sub(r"\s+", "_", base.lower())
        # 过滤非法字符，仅保留字母数字下划线和连字符
        plugin_id = re.sub(r"[^a-z0-9_-]", "_", base)
        # 去除多余下划线
        plugin_id = re.sub(r"_+", "_", plugin_id).strip('_')
        # 不能以数字开头，必要时加前缀
        if plugin_id and plugin_id[0].isdigit():
            plugin_id = f"p_{plugin_id}"
        # 若仍为空，使用基于长度的占位ID
        if not plugin_id:
            plugin_id = "plugin_" + str(abs(hash(plugin_name)) % 100000)
        self.plugin_id_edit.setText(plugin_id)

    def on_plugin_id_edited(self, _text):
        """标记用户已手动编辑ID，并做一次轻量校验显示"""
        self._plugin_id_user_edited = True
        # 不强行改写，只做提示性清理：显示时移除首尾空格
        curr = self.plugin_id_edit.text().strip()
        if curr != self.plugin_id_edit.text():
            self.plugin_id_edit.setText(curr)
    
    def on_plugin_type_changed(self, index):
        """处理插件类型变化"""
        has_ui = index == 1  # 索引0是无界面，索引1是有界面
        # 对所有插件类型都显示入口文件选择
        self.plugin_entry_combo.setVisible(True)
        self.plugin_func_combo.setVisible(True)
        
        # 根据插件类型显示/隐藏参数配置区域
        if hasattr(self, 'params_group'):
            # 只有无界面插件才显示参数配置
            self.params_group.setVisible(not has_ui)
            logger.info(f"插件类型变化: has_ui={has_ui}, 参数组可见性={not has_ui}")
        
        self.plugin_info["has_ui"] = has_ui
        self.validate_input()
    
    def add_parameter(self):
        """添加新的参数配置（折叠分组 + ParameterConfigWidget），与插件Tab页保持一致"""
        index = len(self.plugin_info.get("parameters", []))

        # 外层容器
        container = QWidget(self)
        v = QVBoxLayout(container)
        v.setContentsMargins(0, 0, 0, 0)

        # 折叠头
        header = QToolButton()
        header.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        header.setArrowType(Qt.DownArrow)
        header.setText(f"参数 {index + 1}")
        header.setCheckable(True)
        header.setChecked(True)
        header.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        v.addWidget(header)

        # 内容区
        content = QFrame()
        content.setFrameShape(QFrame.NoFrame)
        vl = QVBoxLayout(content)
        vl.setContentsMargins(8, 4, 8, 8)
        param_widget = ParameterConfigWidget(index, content)
        vl.addWidget(param_widget)
        v.addWidget(content)

        def toggle(expanded: bool):
            content.setVisible(expanded)
            header.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)
        header.toggled.connect(toggle)
        toggle(True)

        # 放入列表布局
        self.params_list_layout.addWidget(container)

        # 初始化空参数对象（供外部读取、兼容旧逻辑）
        self.plugin_info.setdefault("parameters", []).append({
            "name": "",
            "type": "string",
            "label": "",
            "description": "",
            "value": "",
            "min": None,
            "max": None,
            "options": []
        })

        # 连接校验信号
        param_widget.name_edit.textChanged.connect(self.validate_input)
        param_widget.type_combo.currentTextChanged.connect(self.validate_input)
        param_widget.label_edit.textChanged.connect(self.validate_input)

        # 转发删除：移除整个分组容器
        def _on_removed(idx):
            self.on_parameter_removed(idx)
        param_widget.param_removed.connect(_on_removed)

        return param_widget
    
    def on_parameter_removed(self, index):
        """处理参数移除事件：删除折叠分组容器并重建索引与标题"""
        try:
            if 0 <= index < len(self.plugin_info["parameters"]):
                del self.plugin_info["parameters"][index]
        except Exception:
            pass

        # 从布局中找到第 index 个分组容器并删除
        try:
            count = self.params_list_layout.count()
            to_delete = None
            # 遍历容器按顺序计数（只计数包含 ParameterConfigWidget 的容器）
            seen = -1
            for i in range(count):
                item = self.params_list_layout.itemAt(i)
                container = item.widget()
                if not isinstance(container, QWidget):
                    continue
                cfg = container.findChild(ParameterConfigWidget)
                if cfg:
                    seen += 1
                    if seen == index:
                        to_delete = container
                        break
            if to_delete:
                to_delete.setParent(None)
                to_delete.deleteLater()
        except Exception:
            pass

        # 重建索引与分组标题
        try:
            new_idx = 0
            for i in range(self.params_list_layout.count()):
                item = self.params_list_layout.itemAt(i)
                container = item.widget()
                if not isinstance(container, QWidget):
                    continue
                cfg = container.findChild(ParameterConfigWidget)
                if cfg:
                    cfg.update_index(new_idx)
                    # 更新折叠头文字
                    try:
                        header = None
                        if hasattr(container, 'layout'):
                            lay = container.layout()
                            if lay and lay.count() > 0:
                                maybe_btn = lay.itemAt(0).widget()
                                if isinstance(maybe_btn, QToolButton):
                                    header = maybe_btn
                        if header:
                            name_text = cfg.name_edit.text() or f"参数 {new_idx + 1}"
                            header.setText(f"参数 {new_idx + 1}: {name_text}")
                    except Exception:
                        pass
                    new_idx += 1
        except Exception:
            pass

        # 重新验证
        self.validate_input()
    
    def validate_input(self):
        """验证用户输入是否有效"""
        is_valid = False
        
        # 检查必要字段
        # 无论插件类型如何，都要求选择入口文件和函数
        if (self.folder_path_edit.text() and 
            self.plugin_name_edit.text() and 
            self.plugin_id_edit.text() and 
            self.plugin_entry_combo.currentText() and
            self.plugin_func_combo.currentText() and
            self.plugin_entry_combo.currentText() not in ["未找到Python文件", "发现文件失败"] and
            self.plugin_func_combo.currentText() not in ["未找到可用函数", "解析失败"]):
            
            # 默认参数配置有效
            params_valid = True
            
            # 只有在存在参数时才进行参数验证
            if hasattr(self, 'params_list_layout') and self.plugin_info.get('has_ui') is False:
                # 遍历每个分组容器，提取内部的 ParameterConfigWidget
                param_count = 0
                for i in range(self.params_list_layout.count()):
                    item = self.params_list_layout.itemAt(i)
                    container = item.widget()
                    if not isinstance(container, QWidget):
                        continue
                    w = container.findChild(ParameterConfigWidget)
                    if not isinstance(w, ParameterConfigWidget):
                        continue
                    param_count += 1
                    param_config = w.get_parameter_config()
                    if not param_config.get('name') or not param_config.get('type') or not param_config.get('label'):
                        params_valid = False
                        break
                logger.info(f"在validate_input中找到的参数小部件数量: {param_count}")
            
            is_valid = params_valid  # 只有当参数配置也有效时才认为整体有效
        
        # 检查import_button属性是否存在
        if hasattr(self, 'import_button'):
            self.import_button.setEnabled(is_valid)
    
    def accept(self):
        """处理导入按钮点击事件"""
        # 更新插件信息
        self.plugin_info["folder_path"] = self.folder_path_edit.text()
        self.plugin_info["plugin_name"] = self.plugin_name_edit.text()
        # 最终写入前做一次严格清理，避免中文或非法字符导致后续问题
        final_id = self.plugin_id_edit.text() or ''
        final_ascii = final_id.encode('ascii', 'ignore').decode('ascii')
        base = final_ascii if final_ascii.strip() else final_id
        base = re.sub(r"\s+", "_", base.lower())
        final_id = re.sub(r"[^a-z0-9_-]", "_", base)
        final_id = re.sub(r"_+", "_", final_id).strip('_')
        if not final_id:
            final_id = "plugin_" + str(abs(hash(self.plugin_info["plugin_name"])) % 100000)
        if final_id[0].isdigit():
            final_id = f"p_{final_id}"
        self.plugin_info["plugin_id"] = final_id
        self.plugin_info["plugin_entry"] = self.plugin_entry_combo.currentText()
        self.plugin_info["plugin_function"] = self.plugin_func_combo.currentData()
        
        # 重新构建参数列表，确保与UI中的参数小部件完全同步（折叠分组模型）
        # 只有无界面插件才需要处理参数
        if self.plugin_info.get('has_ui') is False:
            # 遍历每个分组容器
            found = []
            for i in range(self.params_list_layout.count()):
                item = self.params_list_layout.itemAt(i)
                container = item.widget()
                if not isinstance(container, QWidget):
                    continue
                w = container.findChild(ParameterConfigWidget)
                if isinstance(w, ParameterConfigWidget):
                    found.append(w)
            logger.info(f"在accept中找到的参数小部件数量: {len(found)}")
            self.plugin_info["parameters"] = []
            # 验证并收集所有参数的配置
            for w in found:
                param_config = w.get_parameter_config()
                if not param_config.get('name') or not param_config.get('type') or not param_config.get('label'):
                    QMessageBox.warning(self, "参数配置不完整", "请确保所有参数都有名称、类型和标签")
                    return
                self.plugin_info["parameters"].append(param_config)
        else:
            # 有界面插件不需要参数
            self.plugin_info["parameters"] = []
        
        # 参数验证通过，继续导入
        logger.info(f"最终参数列表: {self.plugin_info['parameters']}")
        super().accept()
    
    def get_plugin_info(self):
        """获取用户配置的插件信息"""
        return self.plugin_info