import os
import shutil
import json
from PySide6.QtWidgets import QMessageBox
import logging

logger = logging.getLogger(__name__)

class PluginImporter:
    """插件导入处理器，负责将外部插件导入到系统中"""
    
    def __init__(self, plugins_dir):
        self.plugins_dir = plugins_dir
    
    def import_plugin(self, plugin_info):
        """
        导入插件
        
        Args:
            plugin_info: 插件信息
            
        Returns:
            tuple: (success, error_message) - 成功状态和错误信息
        """
        try:
            # 提取插件信息
            plugin_id = plugin_info["plugin_id"]
            plugin_name = plugin_info["plugin_name"]
            has_ui = plugin_info["has_ui"]
            parameters = plugin_info.get("parameters", [])  # 安全获取参数列表，默认为空列表
            plugin_entry = plugin_info["plugin_entry"]
            plugin_function = plugin_info.get("plugin_function", "main")  # 获取选择的入口函数
            folder_path = plugin_info["folder_path"]
            
            # 确定插件类型和基础类
            if has_ui:
                base_class = "BaseUIPlugin"
                additional_imports = """from PySide6.QtWidgets import QVBoxLayout, QLabel, QWidget
from PySide6.QtCore import Qt"""
            else:
                base_class = "BasePlugin"
                additional_imports = ""
            
            # 创建插件目录
            plugin_dir = os.path.join(self.plugins_dir, plugin_id)
            os.makedirs(plugin_dir, exist_ok=True)

            # 支持“就地更新”：当导入来源目录就是目标插件目录时，跳过复制，仅更新元数据与入口声明
            in_place_update = False
            try:
                in_place_update = os.path.samefile(folder_path, plugin_dir)
            except Exception:
                in_place_update = False

            if not in_place_update:
                # 复制源文件到插件目录（递归复制，保留子目录），排除隐藏项和__pycache__
                try:
                    for root, dirs, files in os.walk(folder_path):
                        # 过滤不需要的目录
                        dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__pycache__']
                        # 计算相对路径
                        rel_root = os.path.relpath(root, folder_path)
                        target_root = os.path.join(plugin_dir, rel_root) if rel_root != '.' else plugin_dir
                        os.makedirs(target_root, exist_ok=True)
                        for file_name in files:
                            if file_name.startswith('.'):
                                continue
                            src_file = os.path.join(root, file_name)
                            dst_file = os.path.join(target_root, file_name)
                            shutil.copy2(src_file, dst_file)
                except Exception as e:
                    error_msg = f"复制插件文件失败: {str(e)}"
                    logger.error(error_msg)
                    return False, error_msg

            # 确保入口文件存在（就地更新未复制时也需校验）
            try:
                entry_file_path = os.path.join(plugin_dir, plugin_entry)
                if not os.path.exists(entry_file_path):
                    with open(entry_file_path, 'w', encoding='utf-8') as f:
                        f.write("# 插件入口文件")
            except Exception:
                pass
            
            # 生成__init__.py文件
            init_file_path = os.path.join(plugin_dir, "__init__.py")
            self._generate_plugin_init_file(init_file_path, plugin_info, base_class, additional_imports)
            
            # 创建配置文件
            config_file_path = os.path.join(plugin_dir, "config.json")
            with open(config_file_path, 'w', encoding='utf-8') as f:
                json.dump({
                    "plugin_id": plugin_id,
                    "plugin_name": plugin_name,
                    "has_ui": has_ui,
                    "plugin_entry": plugin_entry,
                    "plugin_function": plugin_function,  # 保存入口函数信息
                    "parameters": parameters  # 保存参数信息到配置文件
                }, f, indent=4, ensure_ascii=False)
            
            return True, ""
        except Exception as e:
            error_msg = f"导入插件时发生错误: {str(e)}"
            logger.error(error_msg)
            return False, error_msg
    
    def _generate_plugin_init_file(self, file_path, plugin_info, base_class, additional_imports):
        """
        生成插件的__init__.py文件
        
        Args:
            file_path: 文件路径
            plugin_info: 插件信息
            base_class: 基础类名
            additional_imports: 额外的导入语句
        """
        # 提取插件信息
        plugin_name = plugin_info["plugin_name"]
        plugin_id = plugin_info["plugin_id"]
        has_ui = plugin_info["has_ui"]
        plugin_entry = plugin_info["plugin_entry"]
        plugin_function = plugin_info.get("plugin_function", "main")  # 获取选择的入口函数
        parameters = plugin_info.get("parameters", [])  # 安全获取参数列表，默认为空列表
        logger.warning(f"parameters: {parameters}")
        logger.warning(f"plugin_function: {plugin_function}")
        
        # 确保has_ui是Python的布尔值格式
        has_ui_python = str(has_ui).replace('true', 'True').replace('false', 'False')
        
        # 开始构建__init__.py文件内容
        init_content = f"""from app.plugin_manager import {base_class}
{additional_imports}
import logging
import time
import os
import sys
import importlib.util
import inspect

logger = logging.getLogger(__name__)

"""
        
        # 构建插件类
        init_content += f"class {plugin_id.replace('_', '').title()}{base_class.split('Base')[-1]}({base_class}):\n"
        init_content += f"    \"\"\"{plugin_name}\n"
        init_content += f"    这是通过插件导入功能创建的插件类\"\"\"\n\n"
        init_content += f"    def __init__(self, plugin_id, config_manager=None):\n"
        init_content += f"        \"\"\"初始化插件\"\"\"\n"
        init_content += f"        # 添加初始化代码\n"
        
        # 添加初始化代码
        if has_ui:
            init_content += f"        super().__init__(plugin_id, config_manager)\n"
            init_content += f"        # UI插件初始化代码\n"
            init_content += f"        self.init_ui()\n\n"
            init_content += f"    def init_ui(self):\n"
            init_content += f"        \"\"\"\n"
            init_content += f"        初始化插件UI界面\n"
            init_content += f"        \"\"\"\n"
            init_content += f"        # GUI插件的UI创建延迟到create_ui方法中\n"
            init_content += f"        # 这里只做基本的初始化\n"
            init_content += f"        pass\n"
        else:
            init_content += f"        super().__init__(plugin_id, config_manager)\n"
            init_content += f"        # 存储参数值\n"
            init_content += f"        self.parameters_values = {{\n"
            # 总是初始化parameters_values字典，即使parameters为空
            # 安全检查parameters是否为列表
            if isinstance(parameters, list) and parameters:  # 只有当参数列表非空时才添加参数
                for i, param in enumerate(parameters):
                    # 安全检查确保参数字典有必要的键
                    if isinstance(param, dict) and 'name' in param:
                        value = param.get('value', '')
                        # 处理不同类型的默认值
                        if isinstance(value, str):
                            value_str = f'\"{value}\"'
                        elif isinstance(value, bool):
                            # 确保布尔值使用Python正确的格式（首字母大写）
                            value_str = str(value).replace('true', 'True').replace('false', 'False')
                        else:
                            value_str = str(value)
                        init_content += f"            '{param['name']}': {value_str}"
                        if i < len(parameters) - 1:
                            init_content += ","
                        init_content += "\n"
            init_content += f"        }}\n"
        
        # 记录入口文件名和函数名，供运行时加载（所有插件都需要）
        entry_module_name = os.path.splitext(plugin_entry)[0]
        init_content += f"        self._entry_module_path = os.path.join(os.path.dirname(__file__), '{plugin_entry}')\n"
        init_content += f"        self._entry_module_name = '{entry_module_name}'\n"
        init_content += f"        self._entry_function_name = '{plugin_function}'\n"
        
        # 添加名称和描述属性
        init_content += f"""
    @property
    def name(self):
        return "{plugin_name}"

    @property
    def description(self):
        return "{plugin_name}的描述"
        
    @property
    def has_ui(self):
        return {has_ui_python}
"""
        
        # 为GUI插件添加create_ui方法
        if has_ui:
            init_content += f"""
    def create_ui(self, parent=None):
        \"\"\"创建插件UI\"\"\"
        try:
            # 导入必要的PySide6组件
            from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QGroupBox
            from PySide6.QtCore import Qt
            
            # 尝试导入并使用插件的原有界面
            import sys
            import os
            plugin_dir = os.path.dirname(os.path.abspath(__file__))
            if plugin_dir not in sys.path:
                sys.path.insert(0, plugin_dir)
            
            # 尝试导入插件的入口模块
            try:
                entry_module = importlib.import_module(os.path.splitext('{plugin_entry}')[0])
                
                # 尝试多种方式获取GUI类
                gui_class = None
                
                # 方式1: 直接导入入口函数
                if hasattr(entry_module, '{plugin_function}'):
                    entry_func = getattr(entry_module, '{plugin_function}')
                    if inspect.isclass(entry_func):
                        gui_class = entry_func
                
                # 方式2: 查找常见的GUI类名
                if gui_class is None:
                    common_gui_classes = ['MainWindow', 'Window', 'Dialog', 'Widget', 'App']
                    for class_name in common_gui_classes:
                        if hasattr(entry_module, class_name):
                            potential_class = getattr(entry_module, class_name)
                            if inspect.isclass(potential_class):
                                gui_class = potential_class
                                break
                
                # 方式3: 查找所有类并选择最可能的GUI类
                if gui_class is None:
                    for name, obj in inspect.getmembers(entry_module, inspect.isclass):
                        # 跳过内置类和导入的类
                        if (name.startswith('Q') or 
                            name in ['object', 'Exception', 'BaseException'] or
                            obj.__module__ != entry_module.__name__):
                            continue
                        # 检查是否是GUI相关的类
                        if any(keyword in name.lower() for keyword in ['window', 'dialog', 'widget', 'main', 'app']):
                            gui_class = obj
                            break
                
                if gui_class is not None:
                    # 创建原有界面的实例
                    self.main_window = gui_class()
                    
                    # 创建一个GroupBox包装器，使界面更美观
                    from PySide6.QtWidgets import QGroupBox
                    group_box = QGroupBox(f"{{self.name}} 界面", parent)
                    group_box.setStyleSheet('''
                        QGroupBox {{
                            font-weight: bold;
                            border: 2px solid #cccccc;
                            border-radius: 8px;
                            margin-top: 10px;
                            padding-top: 10px;
                        }}
                        QGroupBox::title {{
                            subcontrol-origin: margin;
                            left: 10px;
                            padding: 0 5px 0 5px;
                        }}
                    ''')
                    
                    layout = QVBoxLayout(group_box)
                    layout.setContentsMargins(10, 15, 10, 10)  # 设置合适的边距
                    
                    # 将原有界面的centralwidget添加到我们的布局中
                    if hasattr(self.main_window, 'centralwidget'):
                        layout.addWidget(self.main_window.centralwidget)
                    else:
                        # 如果没有centralwidget，直接使用主窗口
                        layout.addWidget(self.main_window)
                    
                    return group_box
                else:
                    # 如果找不到GUI类，回退到简单界面
                    raise ImportError("未找到GUI类")
                    
            except ImportError as import_err:
                logger.warning(f"无法导入原有界面: {{import_err}}")
                # 回退到简单界面，也使用GroupBox包装
                from PySide6.QtWidgets import QGroupBox
                group_box = QGroupBox(f"{{self.name}} 界面", parent)
                group_box.setStyleSheet('''
                    QGroupBox {{
                        font-weight: bold;
                        border: 2px solid #cccccc;
                        border-radius: 8px;
                        margin-top: 10px;
                        padding-top: 10px;
                    }}
                    QGroupBox::title {{
                        subcontrol-origin: margin;
                        left: 10px;
                        padding: 0 5px 0 5px;
                    }}
                ''')
                
                layout = QVBoxLayout(group_box)
                layout.setContentsMargins(10, 15, 10, 10)
                
                label = QLabel(f"{{self.name}} 插件")
                label.setAlignment(Qt.AlignCenter)
                label.setStyleSheet("font-size: 16px; font-weight: bold; padding: 20px;")
                layout.addWidget(label)
                
                info_label = QLabel("这是一个GUI插件，正在开发中...")
                info_label.setAlignment(Qt.AlignCenter)
                info_label.setStyleSheet("color: gray; padding: 10px;")
                layout.addWidget(info_label)
                
                layout.addStretch()
                return group_box
            
        except Exception as e:
            logger.error(f"创建{{self.name}} UI失败: {{str(e)}}")
            # 回退到简单标签，也使用GroupBox包装
            try:
                from PySide6.QtWidgets import QGroupBox
                group_box = QGroupBox(f"{{self.name}} 界面", parent)
                group_box.setStyleSheet('''
                    QGroupBox {{
                        font-weight: bold;
                        border: 2px solid #ff6b6b;
                        border-radius: 8px;
                        margin-top: 10px;
                        padding-top: 10px;
                    }}
                    QGroupBox::title {{
                        subcontrol-origin: margin;
                        left: 10px;
                        padding: 0 5px 0 5px;
                        color: #ff6b6b;
                    }}
                ''')
                
                layout = QVBoxLayout(group_box)
                layout.setContentsMargins(10, 15, 10, 10)
                
                error_label = QLabel(f"{{self.name}}界面加载失败: {{str(e)}}")
                error_label.setAlignment(Qt.AlignCenter)
                error_label.setStyleSheet("color: #ff6b6b; padding: 10px;")
                layout.addWidget(error_label)
                
                return group_box
            except Exception:
                # 如果连GroupBox都无法创建，返回None
                return None
"""
            
            # 为GUI插件添加run方法
            init_content += """
    def run(self):
        \"\"\"运行插件\"\"\"
        # GUI插件通常不需要在后台运行，UI界面就是主要功能
        # 这里可以添加一些初始化或后台任务
        logger.info(f\"插件 {{self.plugin_id}} 开始运行\")
        
        # 如果需要持续运行，可以使用循环
        # while not self.is_stopped():
        #     # 执行一些后台任务
        #     time.sleep(1)
        
        # 对于GUI插件，通常run方法执行完毕后插件就\"完成\"了
        logger.info(f\"插件 {{self.plugin_id}} 运行完成\")
    
    def stop(self):
        \"\"\"停止插件\"\"\"
        # 如果MainWindow存在，调用其关闭方法
        if hasattr(self, 'main_window') and self.main_window:
            try:
                if hasattr(self.main_window, 'closeEvent'):
                    self.main_window.closeEvent(None)
                elif hasattr(self.main_window, 'close'):
                    self.main_window.close()
            except Exception as e:
                logger.error(f\"停止{{self.name}}插件时出错: {{str(e)}}\")
        
        # 调用父类的stop方法
        super().stop()
"""
        
        # 对于无界面插件，总是添加parameters属性，即使参数为空
        if not has_ui:
            init_content += "    @property\n"
            init_content += "    def parameters(self):\n"
            init_content += "        \"\"\"插件参数定义\"\"\"\n"
            init_content += "        return {\n"
            
            # 安全检查parameters是否为列表
            if isinstance(parameters, list) and parameters:  # 只有当参数列表非空时才添加参数定义
                for i, param in enumerate(parameters):
                    # 安全检查确保param是字典且有必要的键
                    if isinstance(param, dict) and 'name' in param:
                        param_name = param["name"]
                        # 构建参数定义字典，添加默认值以防键不存在
                        param_def = {
                            "type": param.get("type", "string"),
                            "label": param.get("label", param_name),
                            "description": param.get("description", ""),
                            "value": param.get("value", "")
                        }
                        
                        # 添加特定类型的参数属性，增加安全检查
                        param_type = param.get("type", "")
                        if param_type in ["integer", "float"]:
                            if "min" in param and param["min"] is not None:
                                param_def["min"] = param["min"]
                            if "max" in param and param["max"] is not None:
                                param_def["max"] = param["max"]
                        elif param_type == "select" and "options" in param:
                            param_def["options"] = param["options"]
                        
                        # 转换为Python字典字符串
                        param_def_str = f"        '{param_name}': {str(param_def)}"
                        init_content += param_def_str
                        if i < len(parameters) - 1:
                            init_content += ","
                        init_content += "\n"
            
            init_content += "        }\n"
        
        # 添加run方法（仅对无界面插件）
        if not has_ui:
            init_content += """
    def run(self):
        # 插件的主要运行逻辑
        try:
            # 获取参数值
            params = getattr(self, 'parameters_values', {})
            self.log_output(f"获取到的参数: {params}")

            # 动态导入入口模块
            try:
                spec = importlib.util.spec_from_file_location(self._entry_module_name, self._entry_module_path)
                if spec is None or spec.loader is None:
                    raise ImportError("无法创建入口模块规范")
                module = importlib.util.module_from_spec(spec)
                # 确保入口模块所在目录在sys.path中，支持其相对导入
                plugin_dir = os.path.dirname(self._entry_module_path)
                need_pop = False
                if plugin_dir and plugin_dir not in sys.path:
                    sys.path.insert(0, plugin_dir)
                    need_pop = True
                
                # 输出由全局线程感知stdout代理处理，这里直接执行模块即可
                spec.loader.exec_module(module)
                # 清理插入的路径
                if need_pop and sys.path and sys.path[0] == plugin_dir:
                    sys.path.pop(0)
                    
            except Exception as e:
                self.log_output(f"入口模块加载失败: {e}")
                # 进入保底循环，避免直接退出
                while not self.is_stopped():
                    time.sleep(1)
                return

            # 选择可调用入口函数
            entry_func = None
            target_function = self._entry_function_name  # 使用选择的入口函数
            
            # 处理类方法的情况（如 ClassName.method_name）
            if '.' in target_function:
                class_name, method_name = target_function.split('.', 1)
                if hasattr(module, class_name):
                    cls = getattr(module, class_name)
                    try:
                        import inspect as _inspect
                    except Exception:
                        _inspect = None
                    # 仅当确定为类时再实例化
                    if (_inspect is None) or (_inspect and _inspect.isclass(cls)):
                        # 先尝试绑定到实例（适用于普通实例方法）
                        try:
                            instance = cls()
                            if hasattr(instance, method_name) and callable(getattr(instance, method_name)):
                                entry_func = getattr(instance, method_name)
                        except Exception as e:
                            self.log_output(f"创建类实例失败: {e}")
                            entry_func = None
                    else:
                        self.log_output(f"目标 '{class_name}' 不是类，类型为: {type(cls)}")
                    # 若实例化失败或未取到可调用，再尝试从类对象获取（适用于 @classmethod/@staticmethod）
                    if entry_func is None and hasattr(cls, method_name) and callable(getattr(cls, method_name)):
                        entry_func = getattr(cls, method_name)
            else:
                # 普通函数
                if hasattr(module, target_function) and callable(getattr(module, target_function)):
                    entry_func = getattr(module, target_function)

            if entry_func is None:
                try:
                    self.log_output(f"未在入口模块中找到可调用的入口函数: {target_function}")
                    # 打印模块中可用的可调用名称，辅助诊断
                    available = []
                    try:
                        for _n, _o in module.__dict__.items():
                            try:
                                if callable(_o):
                                    available.append(_n)
                            except Exception:
                                pass
                        if available:
                            self.log_output(f"模块中可调用成员: {', '.join(sorted(available)[:20])}")
                    except Exception:
                        pass
                except Exception:
                    pass
                while not self.is_stopped():
                    time.sleep(1)
                return

            # 调用入口函数（更稳健：优先无参，其次传入 dict，最后 **kwargs）
            try:
                result = None
                try:
                    # 1) 优先尝试无参调用，兼容 def main():
                    self.log_output(f"准备调用入口: {target_function} -> 无参方式")
                    result = entry_func()
                except TypeError:
                    # 2) 尝试以单一参数传入 dict，兼容 def main(params):
                    try:
                        self.log_output(f"准备调用入口: {target_function} -> 单参数 dict 方式")
                        result = entry_func(params)
                    except TypeError:
                        # 3) 尝试以关键字参数传入，兼容 def main(**kwargs):
                        if isinstance(params, dict):
                            try:
                                self.log_output(f"准备调用入口: {target_function} -> **kwargs 方式")
                                result = entry_func(**params)
                            except TypeError as te:
                                # 抛出以进入统一错误处理
                                raise te
                        else:
                            # params 非 dict，已无法 ** 展开，抛出进入统一错误处理
                            raise
            except Exception as e:
                # 输出详细堆栈，便于定位例如 super(type, obj) 等错误来源
                try:
                    import traceback as _tb
                    self.log_output(f"调用入口函数失败: {e}")
                    tb = _tb.format_exc()
                    if isinstance(tb, str) and tb.strip():
                        # 仅截取前若干行，避免过长刷屏
                        lines = tb.strip().splitlines()
                        # 注意：这里是在生成器模板字符串中，需要双反斜杠以在生成的插件代码中保留 "\\n"
                        preview = "\\n".join(lines[-15:])
                        self.log_output(preview)
                except Exception:
                    self.log_output(f"调用入口函数失败: {e}")
                while not self.is_stopped():
                    time.sleep(1)
                return

            # 处理函数返回结果
            try:
                if hasattr(result, '__iter__') and not isinstance(result, (str, bytes, dict)):
                    # 可迭代结果，逐条输出
                    for item in result:
                        if self.is_stopped():
                            break
                        self.log_output(str(item))
                    # 迭代完成后，函数执行完毕
                    self.log_output("入口函数执行完毕")
                else:
                    # 非迭代返回，函数执行完毕
                    self.log_output("入口函数执行完毕")
            except Exception as e:
                self.log_output(f"处理入口函数返回结果失败: {e}")
            
            # 函数执行完毕，插件自动停止
            self.log_output("插件运行完成，自动停止")

            # 不做任何全局输入钩子恢复，因为我们未更改全局输入。

        except Exception as e:
            self.log_output(f"运行时错误: {str(e)}")
"""
        
        # 写入文件
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(init_content)