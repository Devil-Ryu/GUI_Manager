from app.plugin_manager import BasePlugin
import threading
import time
import sched


class ValidationRunnerPlugin(BasePlugin):
    """验证用插件：同时启动 Timer、Thread 与 sched 三种后台任务

    预期行为：
    - 运行时打印三路心跳：_timer_tick, _thread_tick, _sched_job
    - 点击停止后，三路心跳均应在极短时间内停止
    """

    def __init__(self, plugin_id, config_manager=None):
        super().__init__(plugin_id, config_manager)
        # 计时器句柄（由全局 Timer 包装自动登记，但也保存在本地便于调试）
        self._timer = None
        # 普通工作线程
        self._worker_thread = None
        # sched 调度与其线程
        self._scheduler = None
        self._sched_thread = None

    @property
    def name(self):
        return "验证收敛插件"

    @property
    def description(self):
        return "同时验证 Timer、Thread、sched 三种后台任务在停用时的收敛情况"

    def _timer_fire(self):
        # 定时器回调：打印心跳并继续调度下一次
        try:
            if self.is_stopped():
                return
            self.log_output("_timer_tick")
            # 继续下一次（利用 threading.Timer 包装，自动登记到插件）
            self._timer = threading.Timer(0.6, self._timer_fire)
            self._timer.daemon = True
            self._timer.start()
        except Exception as e:
            self.log_output(f"timer 回调异常: {e}")

    def _worker_loop(self):
        # 普通线程循环：协作式退出
        while not self.is_stopped():
            self.log_output("_thread_tick")
            time.sleep(0.7)

    def _sched_loop(self):
        # sched 调度线程：协作式退出
        try:
            self._scheduler = sched.scheduler(time.time, time.sleep)

            def job():
                self.log_output("_sched_job")
                # 重新安排下一次
                try:
                    self._scheduler.enter(1.0, 1, job)
                except Exception:
                    pass

            # 首次安排
            self._scheduler.enter(1.0, 1, job)
            # 非阻塞运行，配合停止标志
            while not self.is_stopped():
                try:
                    self._scheduler.run(blocking=False)
                except Exception:
                    pass
                time.sleep(0.2)
        except Exception as e:
            self.log_output(f"sched 线程异常: {e}")

    def run(self):
        self.log_output("ValidationRunner 启动")

        # 1) 启动 Timer 心跳
        try:
            self._timer = threading.Timer(0.2, self._timer_fire)
            self._timer.daemon = True
            self._timer.start()
        except Exception as e:
            self.log_output(f"启动 Timer 失败: {e}")

        # 2) 启动普通工作线程
        try:
            self._worker_thread = threading.Thread(target=self._worker_loop)
            self._worker_thread.daemon = True
            self._worker_thread.start()
        except Exception as e:
            self.log_output(f"启动工作线程失败: {e}")

        # 3) 启动 sched 调度线程
        try:
            self._sched_thread = threading.Thread(target=self._sched_loop)
            self._sched_thread.daemon = True
            self._sched_thread.start()
        except Exception as e:
            self.log_output(f"启动 sched 线程失败: {e}")

        # 主循环：等待停止
        while not self.is_stopped():
            time.sleep(0.1)

        # 退出前的简短清理（框架会统一取消/终止，这里只是冪等补充）
        try:
            if self._timer is not None:
                try:
                    self._timer.cancel()
                except Exception:
                    pass
        except Exception:
            pass
        self.log_output("ValidationRunner 停止")


