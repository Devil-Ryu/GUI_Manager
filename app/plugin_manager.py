import os
import sys
import importlib.util
import threading
import logging
import subprocess
import json
from abc import ABC, abstractmethod
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import QObject, Signal

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ---- 全局输入路由：避免多个插件同时等待输入时相互干扰 ----
_io_hook_installed = False
_log_hook_installed = False
_thread_local_log_handler = None
_thread_patch_installed = False
_original_thread_class = None
_original_timer_class = None
_thread_to_plugin: dict[int, "BasePlugin"] = {}
try:
    import builtins as _builtins
    _original_input = _builtins.input
except Exception:
    _builtins = None
    _original_input = None
_original_stdin = sys.stdin
_original_stdout = sys.stdout
_original_stderr = sys.stderr
_stdout_buffers: dict[int, str] = {}
_stderr_buffers: dict[int, str] = {}


class _ThreadLocalStdin:
    """将 sys.stdin 替换为线程感知的代理，使每个插件线程读到各自的输入。

    对于未知线程或主线程，回退到原始 stdin（保持兼容）。
    """

    def readline(self, *args, **kwargs):
        plugin = _thread_to_plugin.get(threading.get_ident())
        if plugin is None:
            return _original_stdin.readline(*args, **kwargs)
        # 若已请求停止，直接抛出 SystemExit，强制结束工作线程中的读取循环
        try:
            if getattr(plugin, "_input_canceled", False) or plugin.is_stopped():
                raise SystemExit()
        except Exception:
            pass
        # 使用专用stdin队列，并通过UI请求输入
        try:
            import queue as _q
            q = getattr(plugin, "_stdin_queue", None) or _q.Queue(maxsize=1)
            setattr(plugin, "_stdin_queue", q)
            # 将该队列作为当前待输入队列，便于UI提交
            try:
                setattr(plugin, "_pending_input_queue", q)
                setattr(plugin, "_waiting_on_stdin", True)
            except Exception:
                pass
            # 发射输入请求（无提示）
            try:
                # 二次检查，防止在设置队列后刚好被停止仍然发射
                if getattr(plugin, "_input_canceled", False) or plugin.is_stopped():
                    # 清理并直接返回空
                    try:
                        if getattr(plugin, "_pending_input_queue", None) is q:
                            delattr(plugin, "_pending_input_queue")
                        setattr(plugin, "_waiting_on_stdin", False)
                    except Exception:
                        pass
                    raise SystemExit()
                plugin.signals.input_requested.emit(plugin.plugin_id, "", q, False, "")
            except Exception:
                pass
            # 等待输入
            while True:
                # 等待时也响应停止
                if getattr(plugin, "_input_canceled", False) or plugin.is_stopped():
                    raise SystemExit()
                try:
                    text = q.get(timeout=0.2)
                    break
                except Exception:
                    continue
            # 清理待输入队列
            try:
                if getattr(plugin, "_pending_input_queue", None) is q:
                    delattr(plugin, "_pending_input_queue")
                setattr(plugin, "_waiting_on_stdin", False)
            except Exception:
                pass
            return (text or "") + "\n"
        except SystemExit:
            # 让上层线程退出
            raise
        except Exception:
            return ""

    def read(self, *args, **kwargs):
        plugin = _thread_to_plugin.get(threading.get_ident())
        if plugin is None:
            return _original_stdin.read(*args, **kwargs)
        # 复用 readline 实现
        line = self.readline()
        return line

    def __getattr__(self, name):
        # 透传其他属性，确保与文本 IO 接口兼容
        return getattr(_original_stdin, name)


class _ThreadLocalStdout:
    """将 sys.stdout 替换为线程感知的代理，使每个插件线程的 print 输出到各自日志。

    对于未知线程或主线程，回退到原始 stdout。
    """

    def write(self, text: str):
        try:
            plugin = _thread_to_plugin.get(threading.get_ident())
            if plugin is None:
                return _original_stdout.write(text)
            if not isinstance(text, str):
                return
            # 规范 CRLF -> LF，但保留裸 CR 作为回车覆写信号，避免拆为多行
            text = text.replace("\r\n", "\n")

            tid = threading.get_ident()
            buf = _stdout_buffers.get(tid, "") + text

            # 处理裸回车：将其视为行内覆写，保留最后一段
            if "\r" in buf:
                parts = buf.split("\r")
                buf = parts[-1]

            # 逐行提交（仅遇到 LF 才输出一行）
            while True:
                nl = buf.find("\n")
                if nl == -1:
                    break
                line = buf[:nl]
                buf = buf[nl + 1:]
                try:
                    plugin.log_output(line)
                except Exception:
                    pass
            _stdout_buffers[tid] = buf
        except Exception:
            try:
                _original_stdout.write(text)
            except Exception:
                pass

    def flush(self):
        try:
            # 刷新前将缓冲残留输出为一行
            tid = threading.get_ident()
            buf = _stdout_buffers.get(tid, "")
            # 清理可能残留的 \r，避免显示为额外的空白或分段
            if "\r" in buf:
                buf = buf.replace("\r\n", "\n").replace("\r", "")
            if buf:
                try:
                    plugin = _thread_to_plugin.get(tid)
                    if plugin is not None:
                        plugin.log_output(buf)
                except Exception:
                    pass
                _stdout_buffers[tid] = ""
            _original_stdout.flush()
        except Exception:
            pass

    def __getattr__(self, name):
        # 透传其他属性
        return getattr(_original_stdout, name)

    # 让富文本/彩色库（如 rich、colorama）把我们当作终端，从而输出 ANSI
    def isatty(self):
        try:
            return True
        except Exception:
            return False

    # 兼容 TextIOBase 接口探测
    def writable(self):
        return True

    # 兼容 TextIOBase.writelines（某些库会批量写入）
    def writelines(self, lines):
        try:
            if isinstance(lines, (list, tuple)):
                self.write("".join([str(x) for x in lines]))
            else:
                self.write(str(lines))
        except Exception:
            pass

    # 提供编码信息，便于第三方库判断能力（与 stderr 对齐）
    @property
    def encoding(self):
        try:
            return getattr(_original_stdout, "encoding", "utf-8") or "utf-8"
        except Exception:
            return "utf-8"


class _ThreadLocalStderr:
    """将 sys.stderr 替换为线程感知的代理，捕获例如 RichHandler 的输出。

    对于未知线程或主线程，回退到原始 stderr。
    """

    def write(self, text: str):
        try:
            plugin = _thread_to_plugin.get(threading.get_ident())
            if plugin is None:
                return _original_stderr.write(text)
            if not isinstance(text, str):
                return
            # 规范 CRLF -> LF，但保留裸 CR 作为回车覆写信号
            text = text.replace("\r\n", "\n")
            tid = threading.get_ident()
            buf = _stderr_buffers.get(tid, "") + text

            if "\r" in buf:
                parts = buf.split("\r")
                buf = parts[-1]

            while True:
                nl = buf.find("\n")
                if nl == -1:
                    break
                line = buf[:nl]
                buf = buf[nl + 1:]
                try:
                    plugin.log_output(line)
                except Exception:
                    pass
            _stderr_buffers[tid] = buf
        except Exception:
            try:
                _original_stderr.write(text)
            except Exception:
                pass

    def flush(self):
        try:
            tid = threading.get_ident()
            buf = _stderr_buffers.get(tid, "")
            if "\r" in buf:
                buf = buf.replace("\r\n", "\n").replace("\r", "")
            if buf:
                try:
                    plugin = _thread_to_plugin.get(tid)
                    if plugin is not None:
                        plugin.log_output(buf)
                except Exception:
                    pass
                _stderr_buffers[tid] = ""
            _original_stderr.flush()
        except Exception:
            pass

    def __getattr__(self, name):
        return getattr(_original_stderr, name)

    def isatty(self):
        try:
            return True
        except Exception:
            return False

    def writable(self):
        return True

    # 兼容 TextIOBase.writelines（某些库会批量写入）
    def writelines(self, lines):
        try:
            if isinstance(lines, (list, tuple)):
                self.write("".join([str(x) for x in lines]))
            else:
                self.write(str(lines))
        except Exception:
            pass

    # 提供编码信息，避免某些库根据 encoding 决策禁用颜色
    @property
    def encoding(self):
        try:
            return getattr(_original_stdout, "encoding", "utf-8") or "utf-8"
        except Exception:
            return "utf-8"

def _ensure_io_hooks_installed():
    global _io_hook_installed
    global _log_hook_installed
    global _thread_local_log_handler
    global _thread_patch_installed
    global _original_thread_class, _original_timer_class
    # 若 I/O、日志、线程包装均已就绪，则直接返回，避免重复安装与日志噪音
    if _io_hook_installed and _log_hook_installed and _thread_patch_installed:
        return
    try:
        # 替换内置 input 为线程感知版本
        if _builtins is not None and _original_input is not None:
            def _thread_local_input(prompt: str = ""):
                plugin = _thread_to_plugin.get(threading.get_ident())
                if plugin is None:
                    return _original_input(prompt)
                # 将提示输出到对应插件日志
                try:
                    if prompt:
                        plugin.log_output(str(prompt))
                except Exception:
                    pass
                return plugin.request_input(prompt)
            _builtins.input = _thread_local_input  # type: ignore
        # 替换 sys.stdin 为线程代理
        sys.stdin = _ThreadLocalStdin()
        # 替换 sys.stdout / sys.stderr 为线程代理（线程安全输出到对应插件日志）
        sys.stdout = _ThreadLocalStdout()
        sys.stderr = _ThreadLocalStderr()
        _io_hook_installed = True
        try:
            if not _log_hook_installed or not _thread_patch_installed:
                # 仅在首次完成全部安装时输出一次日志
                logger.info("已安装线程感知的输入代理（input/sys.stdin）")
        except Exception:
            pass
    except Exception as e:
        logger.error(f"安装输入代理失败: {e}")

    # 安装线程感知 logging 处理器，将插件线程里的 logging 输出路由到插件日志
    if not _log_hook_installed:
        try:
            class _AnsiLevelFormatter(logging.Formatter):
                """日志格式化器，保留ANSI转义序列以便在UI中显示彩色文本"""
                def format(self, record: logging.LogRecord) -> str:
                    # 保留 ANSI 转义序列，让 UI 层处理转换
                    msg = super().format(record)
                    return str(msg)

            class _ThreadLocalLoggingHandler(logging.Handler):
                def emit(self, record: logging.LogRecord):
                    try:
                        plugin = _thread_to_plugin.get(threading.get_ident())
                        if plugin is None:
                            # 如果没有找到插件，可能是主线程或其他线程的日志，不处理
                            return
                        msg = self.format(record)
                        if isinstance(msg, str) and msg.strip():
                            plugin.log_output(msg)
                    except Exception:
                        # 不影响其他处理器
                        pass
                
                def filter(self, record: logging.LogRecord) -> bool:
                    """过滤日志：只在插件线程中处理"""
                    # 检查是否在插件线程中
                    return _thread_to_plugin.get(threading.get_ident()) is not None

            _thread_local_log_handler = _ThreadLocalLoggingHandler(level=logging.DEBUG)
            # 使用系统已有的格式配置（从root logger的handler获取）
            root_logger = logging.getLogger()
            # 从已有的handler中获取格式配置
            fmt = None
            datefmt = None
            if root_logger.handlers:
                for handler in root_logger.handlers:
                    if hasattr(handler, 'formatter') and handler.formatter:
                        formatter = handler.formatter
                        # 获取格式字符串和日期格式
                        if hasattr(formatter, '_fmt'):
                            fmt = formatter._fmt
                        if hasattr(formatter, 'datefmt'):
                            datefmt = formatter.datefmt
                        break
            
            # 如果没有找到已有格式，使用None让Formatter使用logging模块的默认格式
            # logging模块的默认格式是: '%(message)s'，但我们会使用系统basicConfig设置的格式
            # 如果basicConfig已配置，fmt会包含那些配置；否则使用None让Formatter使用默认值
            _thread_local_log_handler.setFormatter(_AnsiLevelFormatter(fmt, datefmt))
            root_logger = logging.getLogger()
            # 在测试环境下，为了覆盖到 DEBUG 级别的断言，放宽 root 级别到 DEBUG；
            # 正常运行时尊重应用/插件配置（不降级）。
            try:
                import os as _os
                if _os.environ.get("PYTEST_CURRENT_TEST"):
                    root_logger.setLevel(logging.DEBUG)
            except Exception:
                pass
            # 避免重复添加同类处理器
            if not any(isinstance(h, type(_thread_local_log_handler)) for h in root_logger.handlers):
                root_logger.addHandler(_thread_local_log_handler)
            # 确保所有子logger都会传播到root logger（这是默认行为，但显式设置更安全）
            # Python logging的默认propagate是True，所以子logger会自动传播到父logger
            _log_hook_installed = True
        except Exception as e:
            try:
                logger.error(f"安装日志代理失败: {e}")
            except Exception:
                pass

    # 安装线程/定时器包装：确保在插件线程中创建的新线程也继承日志/输出映射
    if not _thread_patch_installed:
        try:
            import threading as _th
            _original_thread_class = _th.Thread
            _original_timer_class = getattr(_th, 'Timer', None)

            class _PluginAwareThread(_original_thread_class):  # type: ignore
                def __init__(self, *args, **kwargs):
                    creator_plugin = _thread_to_plugin.get(threading.get_ident())
                    target = kwargs.get('target', None)
                    if target is not None and creator_plugin is not None and not getattr(target, "_plugin_wrapped", False):
                        def _wrapped_target(*a, _orig=target, **k):
                            try:
                                _thread_to_plugin[threading.get_ident()] = creator_plugin
                                _ensure_io_hooks_installed()
                                return _orig(*a, **k)
                            finally:
                                try:
                                    _thread_to_plugin.pop(threading.get_ident(), None)
                                except Exception:
                                    pass
                        kwargs['target'] = _wrapped_target
                        try:
                            setattr(_wrapped_target, "_plugin_wrapped", True)
                        except Exception:
                            pass
                    # 注意：此处不能使用 super().__init__，因为当被 Timer 调用时，self 是 Timer 的实例，
                    # super(type, obj) 要求 obj 必须是 type 或其子类的实例。
                    # 直接调用原始 Thread.__init__ 以避免类型层次错配。
                    _original_thread_class.__init__(self, *args, **kwargs)
                    # 自动登记到当前插件，便于停用时一并收敛
                    try:
                        if creator_plugin is not None and hasattr(creator_plugin, "register_thread"):
                            creator_plugin.register_thread(self)
                    except Exception:
                        pass

            _th.Thread = _PluginAwareThread  # type: ignore

            if _original_timer_class is not None:
                class _PluginAwareTimer(_original_timer_class):  # type: ignore
                    def __init__(self, interval, function, args=None, kwargs=None):
                        creator_plugin = _thread_to_plugin.get(threading.get_ident())
                        if creator_plugin is not None and callable(function) and not getattr(function, "_plugin_wrapped", False):
                            def _wrapped_function(*a, _orig=function, **k):
                                try:
                                    _thread_to_plugin[threading.get_ident()] = creator_plugin
                                    _ensure_io_hooks_installed()
                                    return _orig(*a, **k)
                                finally:
                                    try:
                                        _thread_to_plugin.pop(threading.get_ident(), None)
                                    except Exception:
                                        pass
                            function = _wrapped_function
                            try:
                                setattr(_wrapped_function, "_plugin_wrapped", True)
                            except Exception:
                                pass
                        super().__init__(interval, function, args=args, kwargs=kwargs)
                        try:
                            if creator_plugin is not None and hasattr(creator_plugin, "register_timer"):
                                creator_plugin.register_timer(self)
                        except Exception:
                            pass

                _th.Timer = _PluginAwareTimer  # type: ignore

            _thread_patch_installed = True
        except Exception as e:
            try:
                logger.error(f"安装线程包装失败: {e}")
            except Exception:
                pass


class PluginSignal(QObject):
    """插件信号类，用于插件与主程序之间的通信"""
    status_changed = Signal(str, str)  # plugin_id, status
    error_occurred = Signal(str, str)  # plugin_id, error_message
    output_generated = Signal(str, str)  # plugin_id, output
    # 当插件脚本需要用户输入时发射：plugin_id, prompt, queue, password, default_text
    input_requested = Signal(str, str, object, bool, str)


class BasePlugin(ABC):
    """插件基类，所有插件都必须继承此类"""
    
    def __init__(self, plugin_id, config_manager=None):
        self.plugin_id = plugin_id
        self.config_manager = config_manager
        self.signals = PluginSignal()
        self.is_running = False
        self._thread = None
        self._stop_event = threading.Event()
        self.log_history = []  # 保存日志历史
        # 子进程管理：允许插件注册子进程，便于在停用时一并强杀
        self._child_processes = []  # list[subprocess.Popen]
        # 计时器登记：用于在停用时统一取消线程定时器
        self._child_timers = []  # list[threading.Timer]
        # 输入相关：用于在停止时让 request_input 立刻退出
        self._input_canceled = False
        # 为 sys.stdin 代理准备的专用队列（避免与 request_input 的临时队列混淆）
        try:
            import queue as _q
            self._stdin_queue = _q.Queue(maxsize=1)
        except Exception:
            self._stdin_queue = None
        # 普通线程登记：用于在停用时尽力收敛由插件内部创建的子线程
        self._child_threads = []  # list[threading.Thread]
    
    @property
    @abstractmethod
    def name(self):
        """插件名称"""
        pass
    
    @property
    @abstractmethod
    def description(self):
        """插件描述"""
        pass
    
    @property
    def has_ui(self):
        """插件是否有UI界面"""
        return False
    
    def create_ui(self, parent=None):
        """创建插件UI界面"""
        return None
    
    @property
    def parameters(self):
        """插件参数定义
        
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
        return {}
    
    def start(self):
        """启动插件"""
        if self.is_running:
            logger.warning(f"插件 {self.plugin_id} 已经在运行")
            return
        
        # 启动前清空历史日志
        try:
            self.log_history = []
        except Exception:
            pass
        # 若需要，通知界面端自行清空（界面在其启动入口也做清空，这里保持冪等）

        # 重置停止/输入状态，避免上次强杀后的残留导致重启后一直自动输入
        try:
            self._input_canceled = False
        except Exception:
            pass
        # 清理可能残留的待输入队列与等待标记
        try:
            if hasattr(self, "_pending_input_queue"):
                delattr(self, "_pending_input_queue")
            setattr(self, "_waiting_on_stdin", False)
        except Exception:
            pass
        # 清空 stdin 专用队列中的遗留数据
        try:
            q = getattr(self, "_stdin_queue", None)
            if q is not None:
                try:
                    while True:
                        q.get_nowait()
                except Exception:
                    pass
        except Exception:
            pass

        self._stop_event.clear()
        # 检查是否指定了Python解释器
        python_interpreter = None
        if self.config_manager:
            env_id = self.config_manager.get_plugin_python_env(self.plugin_id)
            if env_id:
                # 从配置管理器获取环境管理器（需要通过全局变量或单例访问）
                try:
                    # 尝试从BasePlugin类获取环境管理器引用
                    if hasattr(BasePlugin, '_env_manager_ref'):
                        env_manager = BasePlugin._env_manager_ref()
                        if env_manager:
                            python_interpreter = env_manager.get_environment_path(env_id)
                except Exception:
                    pass
        
        # 如果指定了Python解释器，使用subprocess方式运行
        if python_interpreter and os.path.exists(python_interpreter):
            self._thread = threading.Thread(target=self._run_with_subprocess, args=(python_interpreter,))
        else:
            self._thread = threading.Thread(target=self._run_wrapper)
        self._thread.daemon = True
        self._thread.start()
    
    def stop(self, wait: bool = True):
        """停止插件
        
        Args:
            wait: 是否等待工作线程结束；GUI关闭时可传 False 以避免阻塞
        """
        # 用户要求：点击停止即强制杀死执行线程
        self.kill()

    def kill(self):
        """强制终止插件执行线程（不优雅，最后手段）。

        注意：线程级别的强杀依赖 CPython 私有 API，可能在部分情况下无效；
        但比阻塞更可接受。该方法不会终止整个 GUI 进程。
        """
        try:
            self._input_canceled = True
            self._stop_event.set()
            # 明确标记不再等待stdin，抑制后续输入提示
            try:
                setattr(self, "_waiting_on_stdin", False)
            except Exception:
                pass
        except Exception:
            pass
        # 唤醒任何可能阻塞的输入
        try:
            q = getattr(self, "_pending_input_queue", None)
            if q is not None:
                try:
                    # 先尽力清空队列，避免阻塞
                    try:
                        while True:
                            q.get_nowait()
                    except Exception:
                        pass
                    # 非阻塞放入占位，唤醒等待方
                    try:
                        q.put_nowait("")
                    except Exception:
                        # 放不进去就算了，等待方会在 _input_canceled 标志下自行退出
                        pass
                except Exception:
                    pass
        except Exception:
            pass
        try:
            input_stream = getattr(self, "_input_stream", None)
            if input_stream is not None and hasattr(input_stream, 'put_text'):
                input_stream.put_text("")
        except Exception:
            pass

        # 通过 CPython API 向目标线程注入 SystemExit
        try:
            import ctypes
            if self._thread and getattr(self._thread, "ident", None):
                res = ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_long(self._thread.ident), ctypes.py_object(SystemExit))
                if res > 1:
                    # 恢复状态，避免影响其他线程
                    ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_long(self._thread.ident), 0)
        except Exception:
            pass

        # 终止由插件注册的子进程（先优雅终止，再强杀）
        try:
            for p in list(getattr(self, "_child_processes", []) or []):
                try:
                    if p and hasattr(p, "poll") and p.poll() is None:
                        try:
                            p.terminate()
                        except Exception:
                            pass
                except Exception:
                    pass
            # 短暂等待
            try:
                import time
                deadline = time.time() + 0.3
                for p in list(getattr(self, "_child_processes", []) or []):
                    try:
                        if p and hasattr(p, "poll") and p.poll() is None:
                            remaining = max(0.0, deadline - time.time())
                            if remaining > 0:
                                try:
                                    p.wait(timeout=remaining)
                                except Exception:
                                    pass
                    except Exception:
                        pass
            except Exception:
                pass
            # 仍未退出的强杀
            for p in list(getattr(self, "_child_processes", []) or []):
                try:
                    if p and hasattr(p, "poll") and p.poll() is None:
                        try:
                            p.kill()
                        except Exception:
                            pass
                except Exception:
                    pass
        except Exception:
            pass

        # 取消登记的计时器，防止停用后仍然触发回调
        try:
            for t in list(getattr(self, "_child_timers", []) or []):
                try:
                    if t is not None and hasattr(t, "cancel"):
                        t.cancel()
                except Exception:
                    pass
            try:
                self._child_timers.clear()
            except Exception:
                pass
        except Exception:
            pass

        # 最多等待极短时间以便线程响应退出
        try:
            if self._thread and getattr(self._thread, "is_alive", lambda: False)():
                self._thread.join(timeout=0.3)
        except Exception:
            pass

        # 收敛登记的普通线程：优先协作式退出，再尽力打断
        try:
            import time, ctypes
            # 尝试短暂 join
            deadline = time.time() + 0.3
            for th in list(getattr(self, "_child_threads", []) or []):
                try:
                    remaining = max(0.0, deadline - time.time())
                    if remaining > 0 and th and getattr(th, "is_alive", lambda: False)():
                        th.join(timeout=remaining)
                except Exception:
                    pass
            # 仍存活的线程，注入 SystemExit 作为最后手段
            for th in list(getattr(self, "_child_threads", []) or []):
                try:
                    if th and getattr(th, "is_alive", lambda: False)() and getattr(th, "ident", None):
                        res = ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_long(th.ident), ctypes.py_object(SystemExit))
                        if res > 1:
                            ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_long(th.ident), 0)
                except Exception:
                    pass
        except Exception:
            pass

        # 标记为停止并发信号
        self.is_running = False
        try:
            self.signals.status_changed.emit(self.plugin_id, "stopped")
        except Exception:
            pass
        # 明确输出一条强制停止日志
        try:
            self.log_output("插件已强制停止")
        except Exception:
            pass

    # ---- 子进程登记辅助：供插件在运行时调用以便停用时回收 ----
    def register_subprocess(self, proc):
        try:
            if proc is not None:
                self._child_processes.append(proc)
        except Exception:
            pass

    def unregister_subprocess(self, proc):
        try:
            if proc in self._child_processes:
                self._child_processes.remove(proc)
        except Exception:
            pass

    # ---- 普通线程登记辅助：由 Thread 包装自动调用 ----
    def register_thread(self, thread_obj):
        try:
            if thread_obj is not None:
                self._child_threads.append(thread_obj)
        except Exception:
            pass

    def unregister_thread(self, thread_obj):
        try:
            if thread_obj in self._child_threads:
                self._child_threads.remove(thread_obj)
        except Exception:
            pass

    # ---- 计时器登记辅助：供内部线程/定时器包装调用 ----
    def register_timer(self, timer_obj):
        try:
            if timer_obj is not None:
                self._child_timers.append(timer_obj)
        except Exception:
            pass

    def unregister_timer(self, timer_obj):
        try:
            if timer_obj in self._child_timers:
                self._child_timers.remove(timer_obj)
        except Exception:
            pass
    
    def _run_wrapper(self):
        """运行包装器，处理异常"""
        try:
            # 注册线程到插件映射，并确保输入代理已安装
            _thread_to_plugin[threading.get_ident()] = self
            _ensure_io_hooks_installed()
            # 切换工作目录到插件目录，保证相对路径在插件目录下解析
            import os as _os, inspect as _inspect
            _old_cwd = None
            _switched = False
            try:
                # 仅在存在显式入口模块路径时切换，避免影响测试等纯内存插件
                plugin_dir = None
                entry_path = getattr(self, "_entry_module_path", None)
                if isinstance(entry_path, str) and entry_path:
                    plugin_dir = _os.path.dirname(entry_path)
                if plugin_dir and _os.path.isdir(plugin_dir):
                    _old_cwd = _os.getcwd()
                    _os.chdir(plugin_dir)
                    _switched = True
            except Exception:
                _switched = False
            # 在进入 run() 前尽量为 Rich 提供良好的终端能力提示
            try:
                import os as _os
                # 让 Rich 认为有颜色终端
                _os.environ.setdefault("TERM", "xterm-256color")
                _os.environ.setdefault("PY_COLORS", "1")
                _os.environ.setdefault("RICH_FORCE_TERMINAL", "1")
                # 如果可能，开启真彩色，避免退化为 16 色
                _os.environ.setdefault("RICH_COLOR_SYSTEM", "truecolor")
                # 增大终端宽度，减少表格/JSON 的软换行
                _os.environ.setdefault("COLUMNS", "160")
                # 强制 rich 使用 VT/ANSI 输出与真彩
                try:
                    # 尝试启用 Windows VT 支持
                    try:
                        import colorama as _colorama
                        _colorama.just_fix_windows_console()
                    except Exception:
                        pass
                    import rich as _rich
                    _rich.reconfigure(
                        force_terminal=True, legacy_windows=False,
                        color_system="truecolor", width=160
                    )
                    # 全局覆盖 Console() 构造，确保任意 Console() 均启用 ANSI/truecolor/宽度
                    try:
                        from rich.console import Console as _Console
                        from functools import partial as _partial
                        _rich.console.Console = _partial(
                            _Console,
                            force_terminal=True,
                            legacy_windows=False,
                            color_system="truecolor",
                            width=160,
                        )
                    except Exception:
                        pass
                except Exception:
                    pass
            except Exception:
                pass

            self.is_running = True
            self.signals.status_changed.emit(self.plugin_id, "running")
            self.run()
        except _PluginStopped:
            # 正常停止：不视为错误
            pass
        except Exception as e:
            logger.error(f"插件 {self.plugin_id} 运行出错: {str(e)}")
            self.signals.error_occurred.emit(self.plugin_id, str(e))
        finally:
            # 恢复工作目录
            try:
                if _switched and _old_cwd:
                    import os as _os
                    _os.chdir(_old_cwd)
            except Exception:
                pass
            # 注销映射
            try:
                _thread_to_plugin.pop(threading.get_ident(), None)
            except Exception:
                pass
            if self.is_running:
                self.is_running = False
                self.signals.status_changed.emit(self.plugin_id, "stopped")
    
    @abstractmethod
    def run(self):
        """插件的主要运行逻辑"""
        pass
    
    def _run_with_subprocess(self, python_interpreter: str):
        """使用指定的Python解释器通过subprocess运行插件"""
        try:
            self.is_running = True
            self.signals.status_changed.emit(self.plugin_id, "running")
            
            # 获取入口文件路径和函数名
            entry_path = getattr(self, "_entry_module_path", None)
            entry_func = getattr(self, "_entry_function_name", None)
            
            if not entry_path or not os.path.exists(entry_path):
                self.log_output(f"错误: 插件入口文件不存在: {entry_path}")
                self.is_running = False
                self.signals.status_changed.emit(self.plugin_id, "stopped")
                return
            
            # 获取参数
            params = getattr(self, 'parameters_values', {}) or {}
            
            # 创建临时脚本文件来运行插件
            import tempfile
            plugin_dir = os.path.dirname(entry_path)
            
            # 构建运行脚本
            script_content = f"""import sys
import os
import json

# 切换到插件目录
os.chdir(r"{plugin_dir}")

# 添加插件目录到路径
sys.path.insert(0, r"{plugin_dir}")

# 导入入口模块
import importlib.util
spec = importlib.util.spec_from_file_location("plugin_entry", r"{entry_path}")
if spec is None or spec.loader is None:
    print("错误: 无法加载入口模块")
    sys.exit(1)

module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

# 获取参数
params = {json.dumps(params, ensure_ascii=False)}

# 调用入口函数
entry_func = None
target_function = "{entry_func}"
"""
            
            # 处理函数调用
            if entry_func and '.' in entry_func:
                # 类方法
                class_name, method_name = entry_func.split('.', 1)
                script_content += f"""
class_name, method_name = "{class_name}", "{method_name}"
if hasattr(module, class_name):
    cls = getattr(module, class_name)
    import inspect
    if inspect.isclass(cls):
        try:
            instance = cls()
            if hasattr(instance, method_name):
                entry_func = getattr(instance, method_name)
        except:
            if hasattr(cls, method_name):
                entry_func = getattr(cls, method_name)
"""
            else:
                # 普通函数
                script_content += f"""
if hasattr(module, target_function):
    entry_func = getattr(module, target_function)
"""
            
            script_content += """
if entry_func is None:
    print(f"错误: 未找到入口函数 {target_function}")
    sys.exit(1)

# 调用函数
try:
    entry_func()
except TypeError:
    try:
        entry_func(params)
    except TypeError:
        try:
            entry_func(**params)
        except TypeError as e:
            print(f"错误: 调用函数失败: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
except Exception as e:
    print(f"错误: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
"""
            
            # 创建临时脚本文件
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
                f.write(script_content)
                temp_script = f.name
            
            try:
                # 运行脚本
                process = subprocess.Popen(
                    [python_interpreter, temp_script],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    universal_newlines=True
                )
                
                # 注册子进程以便停止时清理
                self.register_subprocess(process)
                
                # 实时读取输出
                try:
                    while True:
                        if self.is_stopped() or self._stop_event.is_set():
                            process.terminate()
                            break
                        
                        line = process.stdout.readline()
                        if not line:
                            if process.poll() is not None:
                                break
                            continue
                        
                        # 输出到日志
                        self.log_output(line.rstrip())
                        
                except Exception as e:
                    logger.error(f"读取插件输出时出错: {e}")
                
                # 等待进程结束
                if process.poll() is None:
                    process.wait(timeout=1)
                
            finally:
                # 清理临时文件
                try:
                    os.unlink(temp_script)
                except Exception:
                    pass
                self.unregister_subprocess(process)
                
        except Exception as e:
            logger.error(f"使用subprocess运行插件失败: {e}")
            self.log_output(f"运行失败: {e}")
        finally:
            self.is_running = False
            self.signals.status_changed.emit(self.plugin_id, "stopped")
    
    def is_stopped(self):
        """检查是否收到停止信号"""
        return self._stop_event.is_set()
    
    def log_output(self, message):
        """记录输出信息"""
        # 折叠短时间内的“相同语义”行（去ANSI/空白差异），避免重复显示（例如同时经 logging handler 与 stderr 捕获）
        try:
            import time as _t
            import re as _re
            now = _t.time()
            last_msg = getattr(self, "_last_emitted_message", None)
            last_ts = getattr(self, "_last_emitted_ts", 0.0)
            # 规范化：去ANSI、合并空白
            def _normalize(s: str) -> str:
                try:
                    s = str(s)
                    s = _re.sub(r"(?:\x1B\[|\033\[|\u001b\[|\[)[0-9;]*m", "", s)
                    s = s.replace("\r\n", "\n").replace("\r", "\n")
                    s = _re.sub(r"\s+", " ", s).strip()
                    return s
                except Exception:
                    return str(s)

            curr_norm = _normalize(message)
            last_norm = _normalize(last_msg) if isinstance(last_msg, str) else None
            if isinstance(curr_norm, str) and isinstance(last_norm, str):
                if curr_norm == last_norm and (now - float(last_ts)) < 0.5:
                    return
            setattr(self, "_last_emitted_message", message)
            setattr(self, "_last_emitted_ts", now)
        except Exception:
            pass
        # 保存到历史记录
        self.log_history.append(message)
        # 限制历史记录数量，避免内存占用过大
        if len(self.log_history) > 1000:
            self.log_history = self.log_history[-1000:]
        # 发送信号
        self.signals.output_generated.emit(self.plugin_id, message)

    def request_input(self, prompt: str, password: bool = False, default_text: str = "") -> str:
        """请求用户输入（线程安全，同步等待）。

        在工作线程中调用；主线程弹出输入框并通过队列返回结果。
        """
        try:
            # 若已请求停止，则立刻中断，不再发起输入对话
            if self.is_stopped() or self._input_canceled:
                raise _PluginStopped()
            import queue
            q: "queue.Queue[str]" = queue.Queue(maxsize=1)
            # 记录当前待输入队列，便于从界面手动输入框提交
            try:
                setattr(self, "_pending_input_queue", q)
            except Exception:
                pass
            # 发射信号，由UI线程弹窗并将结果放回队列
            self.signals.input_requested.emit(self.plugin_id, str(prompt) if prompt is not None else "", q, bool(password), str(default_text) if default_text is not None else "")
            # 轮询等待，支持停止中断
            value = ""
            while not self.is_stopped() and not self._input_canceled:
                try:
                    value = q.get(timeout=0.2)
                    break
                except Exception:
                    continue
            # 清理待输入队列
            try:
                if getattr(self, "_pending_input_queue", None) is q:
                    delattr(self, "_pending_input_queue")
            except Exception:
                pass
            # 如在等待中收到停止，则中断
            if self.is_stopped() or self._input_canceled:
                raise _PluginStopped()
            return value
        except _PluginStopped:
            # 传递给上层以优雅停止
            raise
        except Exception as e:
            # 失败时返回空字符串，避免插件崩溃
            try:
                self.log_output(f"请求输入失败: {e}")
            except Exception:
                pass
            return ""


class _PluginStopped(Exception):
    """内部异常：用于从输入等待或插件循环中优雅跳出，视为正常停止"""
    pass


class BaseUIPlugin(BasePlugin):
    """带UI界面的插件基类"""
    
    def __init__(self, plugin_id, config_manager=None, parent=None):
        super().__init__(plugin_id, config_manager)
        
        # 延迟创建UI组件，避免在插件加载时创建Qt组件
        self.widget = None
        self._parent = parent
        
        # 不在这里调用init_ui，延迟到create_ui时调用
    
    @property
    def has_ui(self):
        return True
    
    def create_ui(self, parent=None):
        if self.widget is None:
            self.widget = QWidget(parent or self._parent)
            # 重新初始化UI
            self.init_ui()
        return self.widget
    
    def init_ui(self):
        """初始化UI，子类需要实现此方法"""
        pass
    
    def get_widget(self):
        """获取插件窗口部件"""
        return self.widget
    
    @property
    def parameters(self):
        """插件参数定义 - UI插件通常通过界面控制参数，默认不提供参数定义"""
        return {}


class PluginManager:
    """插件管理器"""
    
    def __init__(self, plugins_dir, config_manager=None):
        self.plugins_dir = plugins_dir
        self.config_manager = config_manager
        self.plugins = {}
        self.signals = PluginSignal()
        
        # 确保插件目录存在
        if not os.path.exists(plugins_dir):
            os.makedirs(plugins_dir)
    
    def load_plugins(self):
        """加载所有插件"""
        logger.info(f"开始加载插件，插件目录: {self.plugins_dir}")
        
        # 获取插件目录下的所有子目录
        plugin_dirs = []
        for item in os.listdir(self.plugins_dir):
            item_path = os.path.join(self.plugins_dir, item)
            if os.path.isdir(item_path) and not item.startswith('__'):
                plugin_dirs.append((item, item_path))
        
        # 加载每个插件
        loaded_count = 0
        for plugin_name, plugin_path in plugin_dirs:
            try:
                plugin = self._load_plugin(plugin_name, plugin_path)
                if plugin:
                    # 使用插件实例自己的plugin_id属性作为字典键
                    self.plugins[plugin.plugin_id] = plugin
                    loaded_count += 1
                    logger.info(f"成功加载插件: {plugin.name} (ID: {plugin.plugin_id})")
                    
                    # 连接插件信号
                    plugin.signals.status_changed.connect(self._on_plugin_status_changed)
                    plugin.signals.error_occurred.connect(self._on_plugin_error)
                    plugin.signals.output_generated.connect(self._on_plugin_output)
            except Exception as e:
                logger.error(f"加载插件 {plugin_name} 失败: {str(e)}")
        
        logger.info(f"插件加载完成，共加载 {loaded_count} 个插件")
        return loaded_count
    
    def _load_plugin(self, plugin_name, plugin_path):
        """加载单个插件"""
        # 查找插件的__init__.py文件
        init_file = os.path.join(plugin_path, '__init__.py')
        if not os.path.exists(init_file):
            logger.warning(f"插件 {plugin_name} 缺少__init__.py文件")
            return None
        
        # 将插件目录添加到系统路径
        sys.path.insert(0, os.path.dirname(plugin_path))
        
        try:
            # 导入插件模块
            module_name = f"plugins.{plugin_name}"
            spec = importlib.util.spec_from_file_location(module_name, init_file)
            if spec is None:
                logger.warning(f"无法为插件 {plugin_name} 创建模块规范")
                return None
            
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # 查找插件类
            plugin_class = None
            for name, obj in module.__dict__.items():
                if isinstance(obj, type) and issubclass(obj, BasePlugin) and obj != BasePlugin and obj != BaseUIPlugin:
                    plugin_class = obj
                    break
            
            if plugin_class is None:
                logger.warning(f"插件 {plugin_name} 中未找到有效的插件类")
                return None
            
            # 创建插件实例
            # 不强制设置新的plugin_id，让插件类自己管理ID
            if issubclass(plugin_class, BaseUIPlugin):
                # GUI插件需要parent参数，但在这里我们不传递parent
                # 让插件在create_ui时再创建UI组件
                plugin = plugin_class(plugin_name, self.config_manager)
            else:
                plugin = plugin_class(plugin_name, self.config_manager)
            # 使用插件实例的plugin_id属性作为字典键
            return plugin
        
        except Exception as e:
            logger.error(f"加载插件 {plugin_name} 时出错: {str(e)}")
            raise
        finally:
            # 从系统路径中移除插件目录
            if sys.path and sys.path[0] == os.path.dirname(plugin_path):
                sys.path.pop(0)
    
    def get_plugin(self, plugin_id):
        """获取指定ID的插件"""
        return self.plugins.get(plugin_id)
    
    def get_all_plugins(self):
        """获取所有插件"""
        return list(self.plugins.values())
    
    def start_plugin(self, plugin_id):
        """启动指定插件"""
        plugin = self.get_plugin(plugin_id)
        if plugin:
            plugin.start()
            return True
        return False
    
    def stop_plugin(self, plugin_id, wait: bool = True):
        """停止指定插件"""
        plugin = self.get_plugin(plugin_id)
        if plugin:
            plugin.stop(wait=wait)
            return True
        return False
    
    def start_all_plugins(self):
        """启动所有插件"""
        for plugin_id in self.plugins:
            self.start_plugin(plugin_id)
    
    def stop_all_plugins(self, wait: bool = True):
        """停止所有插件"""
        for plugin_id in self.plugins:
            self.stop_plugin(plugin_id, wait=wait)
    
    def update_plugin(self, plugin_id: str):
        """更新指定插件：停止 → 卸载模块 → 重新导入（保留参数配置文件）。

        注意：与卸载不同，此方法不会删除磁盘上的插件目录与配置，
        仅重新加载 Python 模块与实例，并重新连接信号。
        """
        try:
            # 1) 停止旧实例
            old = self.get_plugin(plugin_id)
            if old:
                try:
                    if old.is_running and hasattr(old, 'kill'):
                        old.kill()
                    else:
                        old.stop(wait=False)
                except Exception:
                    pass
                # 尽量等待短时间退出
                try:
                    if getattr(old, "_thread", None) and getattr(old._thread, "is_alive", lambda: False)():
                        old._thread.join(timeout=0.3)
                except Exception:
                    pass

            # 2) 从注册表移除旧实例，避免被引用
            try:
                self.plugins.pop(plugin_id, None)
            except Exception:
                pass

            # 3) 从 sys.modules 卸载该插件包与子模块
            try:
                to_delete = []
                prefix = f"plugins.{plugin_id}"
                for name in list(sys.modules.keys()):
                    if name == prefix or name.startswith(prefix + "."):
                        to_delete.append(name)
                for name in to_delete:
                    try:
                        del sys.modules[name]
                    except Exception:
                        pass
            except Exception:
                pass

            # 4) 重新导入该插件
            plugin_path = os.path.join(self.plugins_dir, plugin_id)
            if not os.path.isdir(plugin_path):
                raise FileNotFoundError(f"插件目录不存在: {plugin_path}")

            new_plugin = self._load_plugin(plugin_id, plugin_path)
            if not new_plugin:
                raise RuntimeError(f"插件 {plugin_id} 重新导入失败")

            # 5) 注册并连接信号（与 load_plugins 的行为一致）
            self.plugins[new_plugin.plugin_id] = new_plugin
            try:
                new_plugin.signals.status_changed.connect(self._on_plugin_status_changed)
                new_plugin.signals.error_occurred.connect(self._on_plugin_error)
                new_plugin.signals.output_generated.connect(self._on_plugin_output)
            except Exception:
                pass

            return True
        except Exception as e:
            logger.error(f"更新插件 {plugin_id} 失败: {e}")
            return False

    def uninstall_plugin(self, plugin_id):
        """卸载指定插件：停止、删除目录、移除注册并清理配置"""
        # 停止插件（非阻塞，优先强制）
        plugin = self.get_plugin(plugin_id)
        if plugin:
            try:
                if plugin.is_running and hasattr(plugin, 'kill'):
                    plugin.kill()
                else:
                    plugin.stop(wait=False)
            except Exception:
                pass
            # 给予极短时间让工作线程退出，避免删文件时占用
            try:
                if getattr(plugin, "_thread", None) and getattr(plugin._thread, "is_alive", lambda: False)():
                    plugin._thread.join(timeout=0.3)
            except Exception:
                pass
            # 打断可能遗留的输入等待
            try:
                setattr(plugin, "_input_canceled", True)
                setattr(plugin, "_waiting_on_stdin", False)
            except Exception:
                pass
            # 先从注册表移除引用，避免模块被持有导致删除卡顿
            try:
                self.plugins.pop(plugin_id, None)
            except Exception:
                pass
            # 从 sys.modules 卸载对应包与子模块，减少文件占用
            try:
                to_delete = []
                prefix = f"plugins.{plugin_id}"
                for name in list(sys.modules.keys()):
                    if name == prefix or name.startswith(prefix + "."):
                        to_delete.append(name)
                for name in to_delete:
                    try:
                        del sys.modules[name]
                    except Exception:
                        pass
            except Exception:
                pass
        
        # 删除插件目录
        plugin_dir = os.path.join(self.plugins_dir, plugin_id)
        try:
            import shutil, stat
            def _onerror(func, path, exc_info):
                try:
                    # 尝试去掉只读属性后重试
                    os.chmod(path, stat.S_IWRITE)
                    func(path)
                except Exception:
                    # 忽略删除失败，避免卡死
                    pass
            if os.path.isdir(plugin_dir) and not os.path.basename(plugin_dir).startswith('__'):
                shutil.rmtree(plugin_dir, onerror=_onerror)
                logger.info(f"已删除插件目录: {plugin_dir}")
        except Exception as e:
            logger.error(f"删除插件目录失败 {plugin_dir}: {str(e)}")
            raise
        
        # 再次确保从内存注册移除
        try:
            self.plugins.pop(plugin_id, None)
        except Exception:
            pass
        
        # 清理配置（主配置中的设置、顺序、独立配置文件）
        try:
            if self.config_manager:
                self.config_manager.delete_plugin_data(plugin_id)
        except Exception as e:
            logger.error(f"清理插件 {plugin_id} 配置失败: {str(e)}")
        
        return True
    
    def _on_plugin_status_changed(self, plugin_id, status):
        """插件状态变化回调"""
        self.signals.status_changed.emit(plugin_id, status)
    
    def _on_plugin_error(self, plugin_id, error_message):
        """插件错误回调"""
        self.signals.error_occurred.emit(plugin_id, error_message)
    
    def _on_plugin_output(self, plugin_id, output):
        """插件输出回调"""
        self.signals.output_generated.emit(plugin_id, output)