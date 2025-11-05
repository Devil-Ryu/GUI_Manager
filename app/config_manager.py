import os
import yaml
import logging
from pathlib import Path

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class ConfigManager:
    """配置管理器，负责管理主程序和插件的配置"""
    
    def __init__(self, config_dir=None):
        # 默认配置目录
        if config_dir is None:
            # 在用户目录下创建配置文件夹
            if os.name == 'nt':  # Windows
                config_dir = os.path.join(os.path.expanduser('~'), 'AppData', 'Local', 'GUI_Manager', 'config')
            else:  # macOS, Linux
                config_dir = os.path.join(os.path.expanduser('~'), '.config', 'GUI_Manager')
        
        self.config_dir = config_dir
        self.main_config_file = os.path.join(config_dir, 'main_config.yaml')
        self.plugin_config_dir = os.path.join(config_dir, 'plugins')
        
        # 确保配置目录存在
        os.makedirs(self.config_dir, exist_ok=True)
        os.makedirs(self.plugin_config_dir, exist_ok=True)
        
        # 主配置
        self.main_config = self._load_main_config()
    
    def _load_main_config(self):
        """加载主配置文件"""
        default_config = {
            'plugin_settings': {},
            'plugin_list_order': [],
            'appearance': {
                'theme': 'default',
                'font_size': 12
            },
            'window': {
                'width': 1024,
                'height': 768,
                'maximized': False
            }
        }
        
        if os.path.exists(self.main_config_file):
            try:
                with open(self.main_config_file, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                    if config is None:
                        config = default_config
                    # 合并默认配置和加载的配置
                    return self._merge_configs(default_config, config)
            except Exception as e:
                logger.error(f"加载主配置文件失败: {str(e)}")
        
        # 如果配置文件不存在或加载失败，返回默认配置并保存
        self._save_main_config(default_config)
        return default_config
    
    def _save_main_config(self, config):
        """保存主配置文件"""
        try:
            with open(self.main_config_file, 'w', encoding='utf-8') as f:
                # 使用 safe_dump 并关闭 key 排序，严格保留插入顺序
                yaml.safe_dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
            logger.info(f"主配置已保存到 {self.main_config_file}")
        except Exception as e:
            logger.error(f"保存主配置文件失败: {str(e)}")
    
    def _merge_configs(self, default, custom):
        """合并配置字典"""
        if not isinstance(custom, dict):
            return default
        
        result = default.copy()
        for key, value in custom.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_configs(result[key], value)
            else:
                result[key] = value
        return result
    
    def save_main_config(self):
        """保存当前主配置"""
        self._save_main_config(self.main_config)
    
    def get_plugin_settings(self):
        """获取所有插件的设置"""
        return self.main_config.get('plugin_settings', {})
    
    def get_font_size(self):
        """获取字体大小设置"""
        return self.main_config.get('appearance', {}).get('font_size', 12)
    
    def set_font_size(self, font_size):
        """设置字体大小"""
        if 'appearance' not in self.main_config:
            self.main_config['appearance'] = {}
        self.main_config['appearance']['font_size'] = font_size
        self.save_main_config()

    def get_plugin_list_order(self):
        """获取可用插件列表的显示顺序（按 plugin_id 列表存储）"""
        return self.main_config.get('plugin_list_order', [])

    def set_plugin_list_order(self, order_list):
        """设置可用插件列表的显示顺序"""
        self.main_config['plugin_list_order'] = list(order_list) if order_list is not None else []
        self.save_main_config()
    
    def get_plugin_setting(self, plugin_id, key, default=None):
        """获取指定插件的指定设置"""
        plugin_settings = self.main_config.get('plugin_settings', {})
        if plugin_id in plugin_settings:
            return plugin_settings[plugin_id].get(key, default)
        return default
    
    def set_plugin_setting(self, plugin_id, key, value):
        """设置指定插件的指定设置"""
        if 'plugin_settings' not in self.main_config:
            self.main_config['plugin_settings'] = {}
        
        if plugin_id not in self.main_config['plugin_settings']:
            self.main_config['plugin_settings'][plugin_id] = {}
        
        self.main_config['plugin_settings'][plugin_id][key] = value
        self.save_main_config()
    
    def set_plugin_auto_start(self, plugin_id, auto_start):
        """设置插件是否随主程序自动启动"""
        self.set_plugin_setting(plugin_id, 'auto_start', auto_start)
    
    def is_plugin_auto_start(self, plugin_id):
        """检查插件是否设置为随主程序自动启动"""
        return self.get_plugin_setting(plugin_id, 'auto_start', False)
    
    def set_plugin_start_order(self, plugin_id, order):
        """设置插件的启动顺序"""
        self.set_plugin_setting(plugin_id, 'start_order', order)
    
    def get_plugin_start_order(self, plugin_id):
        """获取插件的启动顺序"""
        return self.get_plugin_setting(plugin_id, 'start_order', 999)  # 默认顺序为999
    
    def get_plugins_in_start_order(self, plugins):
        """按照启动顺序排序插件列表"""
        return sorted(plugins, key=lambda p: self.get_plugin_start_order(p.plugin_id))
    
    def load_plugin_config(self, plugin_id, default=None):
        """加载指定插件的配置文件"""
        if default is None:
            default = {}
        
        config_file = os.path.join(self.plugin_config_dir, f"{plugin_id}.yaml")
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                    if config is None:
                        return default
                    return self._merge_configs(default, config)
            except Exception as e:
                logger.error(f"加载插件 {plugin_id} 配置文件失败: {str(e)}")
        
        # 如果配置文件不存在，返回默认配置
        return default
    
    def save_plugin_config(self, plugin_id, config):
        """保存指定插件的配置文件"""
        config_file = os.path.join(self.plugin_config_dir, f"{plugin_id}.yaml")
        try:
            with open(config_file, 'w', encoding='utf-8') as f:
                # 使用 safe_dump 并关闭 key 排序，确保写入顺序即为显示顺序
                # 同时将元组序列化为列表，便于后续 safe_load 解析
                yaml.safe_dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
            logger.info(f"插件 {plugin_id} 配置已保存到 {config_file}")
        except Exception as e:
            logger.error(f"保存插件 {plugin_id} 配置文件失败: {str(e)}")
    
    def delete_plugin_config(self, plugin_id):
        """删除指定插件的独立配置文件 (plugins/{plugin_id}.yaml)"""
        config_file = os.path.join(self.plugin_config_dir, f"{plugin_id}.yaml")
        try:
            if os.path.exists(config_file):
                os.remove(config_file)
                logger.info(f"已删除插件 {plugin_id} 的配置文件 {config_file}")
        except Exception as e:
            logger.error(f"删除插件 {plugin_id} 配置文件失败: {str(e)}")
    
    def remove_plugin_from_list_order(self, plugin_id):
        """从可用插件显示顺序中移除指定插件ID"""
        try:
            order = self.get_plugin_list_order() or []
            if plugin_id in order:
                order = [pid for pid in order if pid != plugin_id]
                self.set_plugin_list_order(order)
        except Exception as e:
            logger.error(f"从显示顺序移除插件 {plugin_id} 失败: {str(e)}")
    
    def delete_plugin_settings(self, plugin_id):
        """删除主配置中的插件设置 (plugin_settings 下的条目)"""
        try:
            plugin_settings = self.main_config.get('plugin_settings', {})
            if plugin_id in plugin_settings:
                del plugin_settings[plugin_id]
                # 直接保存主配置
                self.save_main_config()
        except Exception as e:
            logger.error(f"删除插件 {plugin_id} 设置失败: {str(e)}")
    
    def delete_plugin_data(self, plugin_id):
        """删除与插件相关的所有持久化数据（设置、顺序、独立配置文件）"""
        self.delete_plugin_config(plugin_id)
        self.remove_plugin_from_list_order(plugin_id)
        self.delete_plugin_settings(plugin_id)
    
    def get_appearance_config(self):
        """获取外观配置"""
        return self.main_config.get('appearance', {})
    
    def set_appearance_config(self, appearance_config):
        """设置外观配置"""
        self.main_config['appearance'] = appearance_config
        self.save_main_config()

    def get_theme(self):
        """获取主题设置: 'light' | 'dark' | 'default'"""
        return self.main_config.get('appearance', {}).get('theme', 'default')

    def set_theme(self, theme):
        """设置主题: 'light' | 'dark' | 'default'"""
        if 'appearance' not in self.main_config:
            self.main_config['appearance'] = {}
        self.main_config['appearance']['theme'] = theme
        self.save_main_config()
    
    def get_window_config(self):
        """获取窗口配置"""
        return self.main_config.get('window', {})
    
    def set_window_config(self, window_config):
        """设置窗口配置"""
        self.main_config['window'] = window_config
        self.save_main_config()
    
    def update_window_size(self, width, height, maximized=False):
        """更新窗口大小配置"""
        window_config = self.get_window_config()
        window_config['width'] = width
        window_config['height'] = height
        window_config['maximized'] = maximized
        self.set_window_config(window_config)
    
    def get_python_environments(self):
        """获取Python环境配置"""
        return self.main_config.get('python_environments', {})
    
    def save_python_environments(self, environments):
        """保存Python环境配置"""
        self.main_config['python_environments'] = environments
        self.save_main_config()
    
    def get_plugin_python_env(self, plugin_id):
        """获取插件使用的Python环境ID"""
        return self.get_plugin_setting(plugin_id, 'python_env_id', None)
    
    def set_plugin_python_env(self, plugin_id, env_id):
        """设置插件使用的Python环境ID"""
        self.set_plugin_setting(plugin_id, 'python_env_id', env_id)