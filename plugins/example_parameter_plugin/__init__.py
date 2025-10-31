from app.plugin_manager import BasePlugin
import time
import random
import logging

logger = logging.getLogger(__name__)

class ExampleParameterPlugin(BasePlugin):
    """
    带参数的示例无界面插件
    这个插件展示了如何定义参数并使用它们
    """
    
    def __init__(self, plugin_id, config_manager=None):
        super().__init__(plugin_id, config_manager)
        self.parameters_values = {}
    
    @property
    def name(self):
        return "参数示例插件(无界面)"
    
    @property
    def description(self):
        return "这是一个带参数的无界面插件，根据参数值生成输出。"
    
    @property
    def parameters(self):
        """定义插件参数"""
        return {
            "interval": {
                "type": "float",
                "label": "生成间隔(秒)",
                "description": "每次生成数据的时间间隔",
                "value": 1.0,
                "min": 0.1,
                "max": 10.0,
                "decimals": 1
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
            "min_value": {
                "type": "integer",
                "label": "最小值",
                "description": "随机数的最小值",
                "value": 1,
                "min": 1,
                "max": 1000
            },
            "max_value": {
                "type": "integer",
                "label": "最大值",
                "description": "随机数的最大值",
                "value": 100,
                "min": 1,
                "max": 10000
            },
            "enable_logging": {
                "type": "boolean",
                "label": "启用日志",
                "description": "是否启用详细日志输出",
                "value": True
            }
        }
    
    def run(self):
        """插件的主要运行逻辑"""
        # 输出当前参数值
        if hasattr(self, 'parameters_values') and self.parameters_values:
            self.log_output(f"当前参数: {self.parameters_values}")
        else:
            self.log_output("没有收到参数，使用默认值")
        
        while not self.is_stopped():
            try:
                # 获取参数值（如果没有参数则使用默认值）
                interval = 1.0
                output_type = "numbers"
                min_value = 1
                max_value = 100
                enable_logging = True
                
                if hasattr(self, 'parameters_values'):
                    params = self.parameters_values
                    interval = params.get('interval', 1.0)
                    output_type = params.get('output_type', 'numbers')
                    min_value = params.get('min_value', 1)
                    max_value = params.get('max_value', 100)
                    enable_logging = params.get('enable_logging', True)
                
                # 根据参数生成输出
                if output_type == "numbers":
                    # 确保min_value <= max_value
                    if min_value > max_value:
                        min_value, max_value = max_value, min_value
                    value = random.randint(min_value, max_value)
                    output = f"生成的随机数: {value}"
                elif output_type == "strings":
                    chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
                    length = random.randint(5, 15)
                    value = ''.join(random.choice(chars) for _ in range(length))
                    output = f"生成的随机字符串: {value}"
                else:  # datetime
                    from datetime import datetime
                    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                    output = f"当前时间: {current_time}"
                
                # 输出结果
                self.log_output(output)
                
                # 如果启用了详细日志
                if enable_logging:
                    self.log_output(f"使用参数: interval={interval}, type={output_type}, min={min_value}, max={max_value}")
                
                # 等待指定的间隔
                time.sleep(interval)
                
            except Exception as e:
                self.log_output(f"工作线程错误: {str(e)}")
                time.sleep(1.0)