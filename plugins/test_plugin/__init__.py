from app.plugin_manager import BasePlugin

import logging
import time
import os
import sys
import importlib.util
import inspect

logger = logging.getLogger(__name__)

class TestpluginPlugin(BasePlugin):
    """Test Plugin1
    这是通过插件导入功能创建的插件类"""

    def __init__(self, plugin_id, config_manager=None):
        """初始化插件"""
        # 添加初始化代码
        super().__init__(plugin_id, config_manager)
        # 存储参数值
        self.parameters_values = {
            'test_param': 1
        }
        self._entry_module_path = os.path.join(os.path.dirname(__file__), 'test.py')
        self._entry_module_name = 'test'
        self._entry_function_name = 'testB'

    @property
    def name(self):
        return "Test Plugin1"

    @property
    def description(self):
        return "Test Plugin1的描述"
        
    @property
    def has_ui(self):
        return False
    @property
    def parameters(self):
        """插件参数定义"""
        return {
        'test_param': {'type': 'integer', 'label': '测试参数', 'description': '', 'value': 1}
        }

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
                        # 注意：这里是在生成器模板字符串中，需要双反斜杠以在生成的插件代码中保留 "\n"
                        preview = "\n".join(lines[-15:])
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
