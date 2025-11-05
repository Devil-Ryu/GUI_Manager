import os
import sys
import subprocess
import platform
import logging
from pathlib import Path
from typing import List, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class PythonEnvironmentManager:
    """Python环境管理器，负责管理Python解释器配置"""
    
    def __init__(self, config_manager=None):
        self.config_manager = config_manager
        self.environments: Dict[str, Dict] = {}  # {env_id: {name, path, version, description}}
        self._load_environments()
    
    def _load_environments(self):
        """从配置加载Python环境列表"""
        if self.config_manager:
            envs = self.config_manager.get_python_environments()
            # 确保envs是dict类型
            if isinstance(envs, dict):
                self.environments = envs
            elif isinstance(envs, list):
                # 兼容旧格式：如果是list，转换为dict
                self.environments = {}
                for i, env in enumerate(envs):
                    env_id = f"env_{i}"
                    if isinstance(env, dict):
                        self.environments[env_id] = env
            else:
                self.environments = {}
            
            # 如果环境列表为空，添加当前Python解释器作为默认
            if not self.environments:
                self._add_current_python()
        else:
            # 如果没有配置管理器，添加当前Python解释器作为默认
            self._add_current_python()
    
    def _add_current_python(self):
        """添加当前Python解释器作为默认环境"""
        current_path = sys.executable
        if current_path:
            # 若为打包后的可执行文件（PyInstaller 等），不要作为可选解释器加入，避免递归启动
            try:
                if getattr(sys, 'frozen', False):
                    return
                base = os.path.basename(current_path).lower()
                if not self._is_valid_python_interpreter(current_path):
                    return
            except Exception:
                pass
            env_id = "default"
            try:
                version = self._get_python_version(current_path)
                self.environments[env_id] = {
                    'name': '当前Python解释器',
                    'path': current_path,
                    'version': version,
                    'description': f'当前运行环境 ({version})'
                }
                if self.config_manager:
                    self.config_manager.save_python_environments(self.environments)
            except Exception as e:
                logger.error(f"添加当前Python解释器失败: {e}")
    
    def _get_python_version(self, python_path: str) -> str:
        """获取Python解释器的版本号"""
        try:
            result = subprocess.run(
                [python_path, '--version'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                return result.stdout.strip()
            return "未知版本"
        except Exception as e:
            logger.error(f"获取Python版本失败 {python_path}: {e}")
            return "未知版本"
    
    def add_environment(self, name: str, path: str, description: str = "") -> Tuple[bool, str]:
        """添加Python环境
        
        Returns:
            (success, message)
        """
        if not os.path.exists(path):
            return False, f"路径不存在: {path}"
        
        # 检查是否为有效的Python解释器
        if not self._is_valid_python_interpreter(path):
            return False, "指定的路径不是有效的Python解释器"
        
        # 验证是否为Python解释器
        try:
            version = self._get_python_version(path)
            if "Python" not in version and "python" not in version.lower():
                return False, "指定的文件不是有效的Python解释器"
        except Exception as e:
            return False, f"验证Python解释器失败: {e}"
        
        # 生成环境ID
        env_id = f"env_{len(self.environments)}"
        # 确保ID唯一
        while env_id in self.environments:
            env_id = f"env_{len(self.environments)}"
        
        self.environments[env_id] = {
            'name': name,
            'path': path,
            'version': version,
            'description': description or f'{name} ({version})'
        }
        
        # 保存配置
        if self.config_manager:
            self.config_manager.save_python_environments(self.environments)
        
        logger.info(f"添加Python环境: {name} ({path})")
        return True, "添加成功"
    
    def remove_environment(self, env_id: str) -> bool:
        """删除Python环境"""
        if env_id in self.environments:
            # 不允许删除默认环境
            if env_id == "default":
                return False
            del self.environments[env_id]
            if self.config_manager:
                self.config_manager.save_python_environments(self.environments)
            logger.info(f"删除Python环境: {env_id}")
            return True
        return False
    
    def update_environment(self, env_id: str, name: str = None, path: str = None, description: str = None) -> Tuple[bool, str]:
        """更新Python环境信息"""
        if env_id not in self.environments:
            return False, "环境不存在"
        
        env = self.environments[env_id]
        
        if name is not None:
            env['name'] = name
        if description is not None:
            env['description'] = description
        if path is not None:
            # 验证新路径
            if not os.path.exists(path):
                return False, f"路径不存在: {path}"
            try:
                version = self._get_python_version(path)
                env['path'] = path
                env['version'] = version
            except Exception as e:
                return False, f"验证Python解释器失败: {e}"
        
        if self.config_manager:
            self.config_manager.save_python_environments(self.environments)
        
        return True, "更新成功"
    
    def get_environment(self, env_id: str) -> Optional[Dict]:
        """获取指定环境信息"""
        return self.environments.get(env_id)
    
    def get_all_environments(self) -> Dict[str, Dict]:
        """获取所有环境"""
        # 确保返回的是dict类型
        if isinstance(self.environments, dict):
            return self.environments.copy()
        else:
            return {}
    
    def get_environment_path(self, env_id: str) -> Optional[str]:
        """获取指定环境的Python解释器路径"""
        env = self.environments.get(env_id)
        if env:
            return env['path']
        return None
    
    def search_python_environments(self) -> List[Dict]:
        """自动搜索系统中的Python环境
        
        Returns:
            List of found environments: [{name, path, version, description}]
        """
        found_envs = []
        
        # 搜索常见路径
        search_paths = []
        
        if platform.system() == 'Windows':
            # Windows常见路径
            program_files = os.environ.get('ProgramFiles', 'C:\\Program Files')
            program_files_x86 = os.environ.get('ProgramFiles(x86)', 'C:\\Program Files (x86)')
            local_appdata = os.environ.get('LOCALAPPDATA', '')
            appdata = os.environ.get('APPDATA', '')
            
            # Python官方安装路径
            search_paths.extend([
                os.path.join(program_files, 'Python*'),
                os.path.join(program_files_x86, 'Python*'),
            ])
            
            # 用户目录下的Python
            if local_appdata:
                search_paths.append(os.path.join(local_appdata, 'Programs', 'Python'))
            
            # Anaconda/Miniconda
            search_paths.extend([
                os.path.join(os.environ.get('USERPROFILE', ''), 'Anaconda*'),
                os.path.join(os.environ.get('USERPROFILE', ''), 'miniconda*'),
                os.path.join(local_appdata, 'Continuum', 'anaconda*'),
                os.path.join(local_appdata, 'Continuum', 'miniconda*'),
            ])
            
            # Pyenv
            if os.environ.get('PYENV_ROOT'):
                search_paths.append(os.path.join(os.environ['PYENV_ROOT'], 'versions', '*'))
            
        else:
            # Unix-like系统
            # 系统Python
            search_paths.extend([
                '/usr/bin/python*',
                '/usr/local/bin/python*',
            ])
            
            # 用户目录
            home = os.path.expanduser('~')
            search_paths.extend([
                os.path.join(home, '.pyenv', 'versions', '*'),
                os.path.join(home, '.local', 'bin', 'python*'),
            ])
            
            # Anaconda/Miniconda
            search_paths.extend([
                os.path.join(home, 'anaconda*'),
                os.path.join(home, 'miniconda*'),
                '/opt/anaconda*',
                '/opt/miniconda*',
            ])
        
        # 从PATH中查找
        path_env = os.environ.get('PATH', '')
        for path_dir in path_env.split(os.pathsep):
            if path_dir:
                if platform.system() == 'Windows':
                    search_paths.append(os.path.join(path_dir, 'python.exe'))
                else:
                    search_paths.append(os.path.join(path_dir, 'python*'))
        
        # 搜索并验证
        checked_paths = set()
        for pattern in search_paths:
            try:
                import glob
                matches = glob.glob(pattern)
                for match in matches:
                    if match in checked_paths:
                        continue
                    checked_paths.add(match)
                    
                    # 检查是否为Python解释器
                    if os.path.isfile(match):
                        python_path = match
                    elif os.path.isdir(match):
                        # 可能是Python安装目录，查找python可执行文件
                        if platform.system() == 'Windows':
                            python_path = os.path.join(match, 'python.exe')
                        else:
                            python_path = os.path.join(match, 'bin', 'python3')
                            if not os.path.exists(python_path):
                                python_path = os.path.join(match, 'bin', 'python')
                            if not os.path.exists(python_path):
                                continue
                    else:
                        continue
                    
                    if not os.path.exists(python_path):
                        continue
                    
                    # 过滤当前可执行文件，避免递归调用自身
                    try:
                        if os.path.samefile(match if os.path.isfile(match) else python_path, sys.executable):
                            continue
                    except Exception:
                        pass

                    # 验证并获取版本
                    try:
                        if not self._is_valid_python_interpreter(python_path):
                            continue
                        version = self._get_python_version(python_path)
                        if "Python" in version or "python" in version.lower():
                            # 生成环境名称
                            env_name = os.path.basename(os.path.dirname(python_path))
                            if not env_name or env_name in ['bin', 'Scripts']:
                                env_name = os.path.basename(os.path.dirname(os.path.dirname(python_path)))
                            
                            found_envs.append({
                                'name': env_name,
                                'path': python_path,
                                'version': version,
                                'description': f'{env_name} ({version})'
                            })
                    except Exception:
                        continue
            except Exception as e:
                logger.debug(f"搜索路径 {pattern} 时出错: {e}")
                continue
        
        # 去重（基于路径）
        unique_envs = []
        seen_paths = set()
        for env in found_envs:
            normalized_path = os.path.normpath(env['path'])
            if normalized_path not in seen_paths:
                seen_paths.add(normalized_path)
                unique_envs.append(env)
        
        return unique_envs

    def _is_valid_python_interpreter(self, path: str) -> bool:
        """判断给定路径是否为可用的 Python 解释器。

        - 过滤打包后的 GUI 可执行文件（如 app.exe）
        - Windows: 只允许 python.exe / pythonw.exe
        - Unix: 需要可执行，且文件名形如 python / python3 / python3.x
        """
        if not path or not os.path.exists(path):
            return False
        try:
            base = os.path.basename(path).lower()
            # 屏蔽当前应用可执行文件
            try:
                if os.path.samefile(path, sys.executable) and getattr(sys, 'frozen', False):
                    return False
            except Exception:
                pass
            if platform.system() == 'Windows':
                if base not in ("python.exe", "pythonw.exe"):
                    return False
                return True
            else:
                if not os.access(path, os.X_OK):
                    return False
                # 名称匹配 python, python3, python3.x
                if base.startswith("python"):
                    return True
                return False
        except Exception:
            return False

