import os
import sys
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
    QFileDialog, QDialog, QLineEdit, QTextEdit, QDialogButtonBox,
    QGroupBox, QFormLayout, QComboBox, QProgressDialog
)
from PySide6.QtCore import Qt, Signal, QThread
from app.python_env_manager import PythonEnvironmentManager
import logging

logger = logging.getLogger(__name__)


class PythonEnvironmentSearchThread(QThread):
    """在后台线程中搜索Python环境"""
    search_finished = Signal(list)  # 传递找到的环境列表
    
    def __init__(self, env_manager):
        super().__init__()
        self.env_manager = env_manager
    
    def run(self):
        try:
            found_envs = self.env_manager.search_python_environments()
            self.search_finished.emit(found_envs)
        except Exception as e:
            logger.error(f"搜索Python环境失败: {e}")
            self.search_finished.emit([])


class PythonEnvironmentDialog(QDialog):
    """添加/编辑Python环境对话框"""
    
    def __init__(self, parent=None, env_data=None):
        super().__init__(parent)
        self.env_data = env_data
        self.setWindowTitle("添加Python环境" if env_data is None else "编辑Python环境")
        self.setMinimumWidth(500)
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        form = QFormLayout()
        
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("例如: Python 3.11")
        form.addRow("名称:", self.name_edit)
        
        path_layout = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("选择Python解释器路径")
        browse_btn = QPushButton("浏览...")
        browse_btn.clicked.connect(self.browse_python_path)
        path_layout.addWidget(self.path_edit)
        path_layout.addWidget(browse_btn)
        form.addRow("Python解释器路径:", path_layout)
        
        self.description_edit = QTextEdit()
        self.description_edit.setMaximumHeight(80)
        self.description_edit.setPlaceholderText("可选描述信息")
        form.addRow("描述:", self.description_edit)
        
        layout.addLayout(form)
        
        # 如果正在编辑，填充现有数据
        if self.env_data:
            self.name_edit.setText(self.env_data.get('name', ''))
            self.path_edit.setText(self.env_data.get('path', ''))
            self.description_edit.setPlainText(self.env_data.get('description', ''))
        
        # 按钮
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def browse_python_path(self):
        """浏览选择Python解释器路径"""
        if sys.platform == 'win32':
            path, _ = QFileDialog.getOpenFileName(
                self, "选择Python解释器", "", "可执行文件 (*.exe);;所有文件 (*.*)"
            )
        else:
            path, _ = QFileDialog.getOpenFileName(
                self, "选择Python解释器", "", "所有文件 (*)"
            )
        if path:
            self.path_edit.setText(path)
    
    def get_environment_data(self):
        """获取环境数据"""
        return {
            'name': self.name_edit.text().strip(),
            'path': self.path_edit.text().strip(),
            'description': self.description_edit.toPlainText().strip()
        }


class PythonEnvironmentSelectDialog(QDialog):
    """从搜索结果中选择Python环境对话框"""
    
    def __init__(self, found_environments, parent=None):
        super().__init__(parent)
        self.found_environments = found_environments
        self.selected_environments = []
        self.setWindowTitle("选择要导入的Python环境")
        self.setMinimumWidth(700)
        self.setMinimumHeight(400)
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        layout.addWidget(QLabel(f"找到 {len(self.found_environments)} 个Python环境，请选择要导入的:"))
        
        # 表格显示找到的环境
        self.table = QTableWidget(len(self.found_environments), 3)
        self.table.setHorizontalHeaderLabels(["名称", "路径", "版本"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.MultiSelection)
        
        # 填充数据
        for i, env in enumerate(self.found_environments):
            self.table.setItem(i, 0, QTableWidgetItem(env.get('name', '')))
            path_item = QTableWidgetItem(env.get('path', ''))
            path_item.setToolTip(env.get('path', ''))
            self.table.setItem(i, 1, path_item)
            self.table.setItem(i, 2, QTableWidgetItem(env.get('version', '')))
            # 默认选中所有
            self.table.selectRow(i)
        
        layout.addWidget(self.table)
        
        # 按钮
        button_layout = QHBoxLayout()
        select_all_btn = QPushButton("全选")
        select_all_btn.clicked.connect(lambda: self.table.selectAll())
        deselect_all_btn = QPushButton("全不选")
        deselect_all_btn.clicked.connect(lambda: self.table.clearSelection())
        
        button_layout.addWidget(select_all_btn)
        button_layout.addWidget(deselect_all_btn)
        button_layout.addStretch()
        
        layout.addLayout(button_layout)
        
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.on_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def on_accept(self):
        """接受选择"""
        selected_rows = set()
        for item in self.table.selectedItems():
            selected_rows.add(item.row())
        
        self.selected_environments = [
            self.found_environments[row] for row in selected_rows
        ]
        self.accept()
    
    def get_selected_environments(self):
        """获取选中的环境"""
        return self.selected_environments


class PythonEnvironmentWidget(QWidget):
    """Python环境管理组件"""
    
    environment_changed = Signal()  # 环境列表变化时发出信号
    
    def __init__(self, config_manager, parent=None):
        super().__init__(parent)
        self.config_manager = config_manager
        self.env_manager = PythonEnvironmentManager(config_manager)
        self.init_ui()
        self.refresh_table()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # 说明
        info_label = QLabel("管理Python解释器环境，插件可以选择使用指定的Python解释器运行。")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        # 环境列表表格
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["名称", "路径", "版本", "状态", "描述"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.ExtendedSelection)  # 允许多选
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table)
        
        # 按钮组
        button_layout = QHBoxLayout()
        
        self.add_btn = QPushButton("添加环境")
        self.add_btn.clicked.connect(self.on_add_environment)
        
        self.edit_btn = QPushButton("编辑")
        self.edit_btn.clicked.connect(self.on_edit_environment)
        self.edit_btn.setEnabled(False)
        
        self.remove_btn = QPushButton("删除")
        self.remove_btn.clicked.connect(self.on_remove_environment)
        self.remove_btn.setEnabled(False)
        
        self.search_btn = QPushButton("自动搜索环境")
        self.search_btn.clicked.connect(self.on_search_environments)
        
        button_layout.addWidget(self.add_btn)
        button_layout.addWidget(self.edit_btn)
        button_layout.addWidget(self.remove_btn)
        button_layout.addWidget(self.search_btn)
        button_layout.addStretch()
        
        layout.addLayout(button_layout)
        
        # 连接表格选择变化信号
        self.table.selectionModel().selectionChanged.connect(self.on_selection_changed)
    
    def _check_environment_valid(self, python_path: str) -> bool:
        """检查Python环境是否有效"""
        if not python_path or not os.path.exists(python_path):
            return False
        try:
            import subprocess
            result = subprocess.run(
                [python_path, '--version'],
                capture_output=True,
                text=True,
                timeout=3
            )
            return result.returncode == 0
        except Exception:
            return False
    
    def on_selection_changed(self):
        """表格选择变化"""
        has_selection = len(self.table.selectedItems()) > 0
        self.edit_btn.setEnabled(has_selection)
        self.remove_btn.setEnabled(has_selection)
    
    def refresh_table(self):
        """刷新环境列表"""
        self.table.setRowCount(0)
        environments = self.env_manager.get_all_environments()
        
        # 确保environments是dict类型
        if not isinstance(environments, dict):
            environments = {}
        
        for env_id, env_data in environments.items():
            row = self.table.rowCount()
            self.table.insertRow(row)
            
            # 存储env_id到item中
            name_item = QTableWidgetItem(env_data.get('name', ''))
            name_item.setData(Qt.UserRole, env_id)
            self.table.setItem(row, 0, name_item)
            
            path_item = QTableWidgetItem(env_data.get('path', ''))
            path_item.setToolTip(env_data.get('path', ''))
            self.table.setItem(row, 1, path_item)
            
            self.table.setItem(row, 2, QTableWidgetItem(env_data.get('version', '')))
            
            # 检查环境是否有效
            env_path = env_data.get('path', '')
            is_valid = self._check_environment_valid(env_path)
            status_item = QTableWidgetItem("有效" if is_valid else "无效")
            status_item.setForeground(Qt.GlobalColor.green if is_valid else Qt.GlobalColor.red)
            self.table.setItem(row, 3, status_item)
            
            self.table.setItem(row, 4, QTableWidgetItem(env_data.get('description', '')))
    
    def on_add_environment(self):
        """添加环境"""
        dialog = PythonEnvironmentDialog(self)
        if dialog.exec():
            data = dialog.get_environment_data()
            if not data['name']:
                QMessageBox.warning(self, "错误", "请输入环境名称")
                return
            if not data['path']:
                QMessageBox.warning(self, "错误", "请选择Python解释器路径")
                return
            
            success, message = self.env_manager.add_environment(
                data['name'], data['path'], data['description']
            )
            if success:
                self.refresh_table()
                self.environment_changed.emit()
                QMessageBox.information(self, "成功", message)
            else:
                QMessageBox.warning(self, "错误", message)
    
    def on_edit_environment(self):
        """编辑环境"""
        selected_items = self.table.selectedItems()
        if not selected_items:
            return
        
        row = selected_items[0].row()
        env_id_item = self.table.item(row, 0)
        env_id = env_id_item.data(Qt.UserRole)
        
        env_data = self.env_manager.get_environment(env_id)
        if not env_data:
            return
        
        dialog = PythonEnvironmentDialog(self, env_data)
        if dialog.exec():
            data = dialog.get_environment_data()
            if not data['name']:
                QMessageBox.warning(self, "错误", "请输入环境名称")
                return
            if not data['path']:
                QMessageBox.warning(self, "错误", "请选择Python解释器路径")
                return
            
            success, message = self.env_manager.update_environment(
                env_id, data['name'], data['path'], data['description']
            )
            if success:
                self.refresh_table()
                self.environment_changed.emit()
                QMessageBox.information(self, "成功", message)
            else:
                QMessageBox.warning(self, "错误", message)
    
    def on_remove_environment(self):
        """删除环境（支持多选）"""
        selected_items = self.table.selectedItems()
        if not selected_items:
            return
        
        # 获取所有选中的行（去重）
        selected_rows = set()
        for item in selected_items:
            selected_rows.add(item.row())
        
        if not selected_rows:
            return
        
        # 收集要删除的环境信息
        envs_to_delete = []
        for row in selected_rows:
            env_id_item = self.table.item(row, 0)
            if env_id_item:
                env_id = env_id_item.data(Qt.UserRole)
                env_name = env_id_item.text()
                envs_to_delete.append((env_id, env_name))
        
        if not envs_to_delete:
            return
        
        # 确认对话框
        if len(envs_to_delete) == 1:
            message = f"确定要删除Python环境 '{envs_to_delete[0][1]}' 吗？"
        else:
            message = f"确定要删除选中的 {len(envs_to_delete)} 个Python环境吗？"
        
        reply = QMessageBox.question(
            self, "确认删除",
            message,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            deleted_count = 0
            failed_count = 0
            for env_id, env_name in envs_to_delete:
                if self.env_manager.remove_environment(env_id):
                    deleted_count += 1
                else:
                    failed_count += 1
            
            if deleted_count > 0:
                self.refresh_table()
                self.environment_changed.emit()
            
            if failed_count > 0:
                QMessageBox.warning(self, "部分删除失败", f"成功删除 {deleted_count} 个环境，{failed_count} 个删除失败（可能是默认环境）")
            else:
                if len(envs_to_delete) == 1:
                    QMessageBox.information(self, "成功", "已删除")
                else:
                    QMessageBox.information(self, "成功", f"已删除 {deleted_count} 个环境")
    
    def on_search_environments(self):
        """自动搜索环境"""
        self.search_btn.setEnabled(False)
        self.search_btn.setText("搜索中...")
        
        # 创建进度对话框
        progress = QProgressDialog("正在搜索Python环境...", "取消", 0, 0, self)
        progress.setWindowModality(Qt.WindowModal)
        progress.setCancelButton(None)  # 不允许取消
        progress.show()
        
        # 在后台线程中搜索
        self.search_thread = PythonEnvironmentSearchThread(self.env_manager)
        self.search_thread.search_finished.connect(
            lambda envs: self.on_search_finished(envs, progress)
        )
        self.search_thread.start()
    
    def on_search_finished(self, found_envs, progress):
        """搜索完成"""
        progress.close()
        self.search_btn.setEnabled(True)
        self.search_btn.setText("自动搜索环境")
        
        if not found_envs:
            QMessageBox.information(self, "搜索结果", "未找到Python环境")
            return
        
        # 过滤已存在的环境
        existing_paths = {
            env['path'] for env in self.env_manager.get_all_environments().values()
        }
        new_envs = [
            env for env in found_envs
            if os.path.normpath(env['path']) not in existing_paths
        ]
        
        if not new_envs:
            QMessageBox.information(self, "搜索结果", "所有找到的环境都已添加")
            return
        
        # 显示选择对话框
        dialog = PythonEnvironmentSelectDialog(new_envs, self)
        if dialog.exec():
            selected = dialog.get_selected_environments()
            added_count = 0
            for env in selected:
                success, message = self.env_manager.add_environment(
                    env['name'], env['path'], env['description']
                )
                if success:
                    added_count += 1
            
            if added_count > 0:
                self.refresh_table()
                self.environment_changed.emit()
                QMessageBox.information(self, "成功", f"已添加 {added_count} 个Python环境")
            else:
                QMessageBox.warning(self, "错误", "添加环境失败")
    
    def get_environment_manager(self):
        """获取环境管理器"""
        return self.env_manager

