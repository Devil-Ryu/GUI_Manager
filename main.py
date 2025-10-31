import sys
import os
import logging
import traceback
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import Qt

# 配置日志
log_dir = os.path.join(os.path.expanduser('~'), '.config', 'GUI_Manager')
# 创建日志目录（如果不存在）
os.makedirs(log_dir, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(log_dir, 'app.log')),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 添加项目根目录到系统路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config_manager import ConfigManager
from app.plugin_manager import PluginManager
from app.main_window import MainWindow


def main():
    """主程序入口"""
    # 创建应用程序实例
    app = QApplication(sys.argv)
    app.setApplicationName("Python脚本管理工具")
    app.setOrganizationName("GUI_Manager")
    
    # 设置中文字体支持
    font = app.font()
    font.setFamily("SimHei")  # 使用黑体作为默认字体
    app.setFont(font)
    
    try:
        # 初始化配置管理器
        config_manager = ConfigManager()
        logger.info("配置管理器初始化成功")
        
        # 获取插件目录
        plugins_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "plugins")
        
        # 初始化插件管理器
        plugin_manager = PluginManager(plugins_dir, config_manager)
        logger.info("插件管理器初始化成功")
        
        # 加载插件
        loaded_count = plugin_manager.load_plugins()
        logger.info(f"成功加载 {loaded_count} 个插件")
        
        # 创建主窗口
        main_window = MainWindow(plugin_manager, config_manager)
        main_window.show()
        logger.info("主窗口创建并显示")
        # 自动启动逻辑已移至 MainWindow._auto_start_plugins，避免与新勾选逻辑冲突
        
        # 运行应用程序
        logger.info("应用程序开始运行")
        sys.exit(app.exec())
        
    except Exception as e:
        logger.error(f"应用程序启动失败: {str(e)}")
        logger.error(traceback.format_exc())
        
        # 显示错误对话框
        error_msg = QMessageBox()
        error_msg.setIcon(QMessageBox.Critical)
        error_msg.setWindowTitle("应用程序启动失败")
        error_msg.setText(f"应用程序启动时发生错误:\n{str(e)}")
        error_msg.setDetailedText(traceback.format_exc())
        error_msg.exec()
        
        sys.exit(1)


if __name__ == "__main__":
    main()