def testRich():
    """使用 rich 进行彩色打印测试，包括日志打印、prompt 输入等"""
    from rich.console import Console
    from rich import print as rprint
    from rich.logging import RichHandler
    from rich.prompt import Prompt, Confirm, IntPrompt
    from rich.table import Table
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich.markdown import Markdown
    import logging
    import time
    
    # 初始化 Console
    console = Console()
    
    # 测试基本彩色打印
    console.print("[bold red]红色粗体文本[/bold red]")
    console.print("[bold green]绿色粗体文本[/bold green]")
    console.print("[bold blue]蓝色粗体文本[/bold blue]")
    console.print("[bold yellow]黄色粗体文本[/bold yellow]")
    console.print("[bold magenta]紫色粗体文本[/bold magenta]")
    console.print("[bold cyan]青色粗体文本[/bold cyan]")
    
    # 测试 rprint (rich 的 print 函数)
    rprint("[bold]使用 rprint 打印[/bold]")
    rprint("[red]红色文本[/red] [green]绿色文本[/green] [blue]蓝色文本[/blue]")
    
    # 测试日志打印（使用 rich.logging）
    console.print("\n[bold cyan]=== 测试 Rich 日志打印 ===[/bold cyan]")
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, rich_tracebacks=True)]
    )
    
    logger = logging.getLogger("test_plugin")
    logger.debug("这是 DEBUG 级别的日志")
    logger.info("这是 INFO 级别的日志")
    logger.warning("这是 WARNING 级别的日志")
    logger.error("这是 ERROR 级别的日志")
    logger.critical("这是 CRITICAL 级别的日志")
    
    # 测试表格
    console.print("\n[bold cyan]=== 测试 Rich 表格 ===[/bold cyan]")
    table = Table(title="测试表格")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("名称", style="magenta")
    table.add_column("状态", style="green")
    table.add_column("分数", justify="right", style="yellow")
    
    table.add_row("1", "张三", "运行中", "95")
    table.add_row("2", "李四", "已停止", "87")
    table.add_row("3", "王五", "运行中", "92")
    
    console.print(table)
    
    # 测试面板
    console.print("\n[bold cyan]=== 测试 Rich 面板 ===[/bold cyan]")
    panel = Panel(
        "[bold yellow]这是一个面板内容[/bold yellow]\n"
        "可以包含多行文本\n"
        "支持 [red]彩色[/red] [green]文本[/green]",
        title="[bold blue]测试面板[/bold blue]",
        border_style="green"
    )
    console.print(panel)
    
    # 测试 Markdown
    console.print("\n[bold cyan]=== 测试 Rich Markdown ===[/bold cyan]")
    markdown = Markdown("""
# 标题 1

## 标题 2

这是一个 **粗体** 文本，这是一个 *斜体* 文本。

- 列表项 1
- 列表项 2
- 列表项 3

```python
print("代码块示例")
```
    """)
    console.print(markdown)
    
    # 测试进度条
    console.print("\n[bold cyan]=== 测试 Rich 进度条 ===[/bold cyan]")
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        task = progress.add_task("[cyan]正在处理...", total=10)
        for i in range(10):
            time.sleep(0.2)
            progress.update(task, advance=1)
    
    console.print("[green]进度完成！[/green]")
    
    # 测试 Prompt 输入
    console.print("\n[bold cyan]=== 测试 Rich Prompt 输入 ===[/bold cyan]")
    
    # 文本输入
    name = input("请输入您的姓名（或直接回车跳过）: ")
    if name:
        console.print(f"[green]您输入的姓名是: {name}[/green]")
    else:
        console.print("[yellow]未输入姓名，使用默认值: Guest[/yellow]")
        name = "Guest"
    
    # 整数输入
    try:
        age = input("请输入您的年龄（或直接回车跳过）: ")
        if age:
            age = int(age)
            console.print(f"[green]您输入的年龄是: {age}[/green]")
        else:
            console.print("[yellow]未输入年龄，使用默认值: 25[/yellow]")
            age = 25
    except ValueError:
        console.print("[red]年龄输入无效，使用默认值: 25[/red]")
        age = 25
    
    # 确认输入
    try:
        answer = input("是否继续测试？(y/n，或直接回车跳过): ")
        if answer:
            if answer.lower() in ['y', 'yes']:
                console.print("[green]您选择继续测试[/green]")
            else:
                console.print("[yellow]您选择跳过[/yellow]")
        else:
            console.print("[yellow]未选择，默认跳过[/yellow]")
    except Exception:
        pass
    
    # 显示最终信息
    console.print("\n[bold cyan]=== 测试总结 ===[/bold cyan]")
    summary_table = Table(title="输入信息总结")
    summary_table.add_column("项目", style="cyan")
    summary_table.add_column("值", style="green")
    summary_table.add_row("姓名", name)
    summary_table.add_row("年龄", str(age))
    summary_table.add_row("测试状态", "[green]✓ 完成[/green]")
    
    console.print(summary_table)
    console.print("\n[bold green]Rich 彩色打印测试完成！[/bold green]")


def testAnsi():
    """使用原生 ANSI 转义码进行彩色打印测试（非 rich）。

    目的：验证 GUI 日志输出对 ANSI 颜色的渲染转换能力。
    """
    import sys
    import time

    CSI = "\x1b["  # 控制序列引导符

    def color(fg=None, bg=None, bold=False, underline=False, italic=False):
        codes = []
        if bold:
            codes.append("1")
        if italic:
            codes.append("3")
        if underline:
            codes.append("4")
        if fg is not None:
            codes.append(str(fg))
        if bg is not None:
            codes.append(str(bg))
        if not codes:
            return ""
        return f"{CSI}{';'.join(codes)}m"

    RESET = f"{CSI}0m"

    # 基本前景色
    print(color(31) + "红色 (31) 前景" + RESET)
    print(color(32) + "绿色 (32) 前景" + RESET)
    print(color(33) + "黄色 (33) 前景" + RESET)
    print(color(34) + "蓝色 (34) 前景" + RESET)
    print(color(35) + "紫色 (35) 前景" + RESET)
    print(color(36) + "青色 (36) 前景" + RESET)
    print(color(37) + "白色 (37) 前景" + RESET)

    # 亮色前景
    print(color(91) + "亮红 (91) 前景" + RESET)
    print(color(92) + "亮绿 (92) 前景" + RESET)
    print(color(93) + "亮黄 (93) 前景" + RESET)
    print(color(94) + "亮蓝 (94) 前景" + RESET)
    print(color(95) + "亮紫 (95) 前景" + RESET)
    print(color(96) + "亮青 (96) 前景" + RESET)
    print(color(97) + "亮白 (97) 前景" + RESET)

    # 背景色搭配
    print(color(30, 43) + "黑字黄底 (30;43)" + RESET)
    print(color(37, 41) + "白字红底 (37;41)" + RESET)
    print(color(34, 47) + "蓝字白底 (34;47)" + RESET)

    # 文本样式
    print(color(32, bold=True) + "粗体绿色" + RESET)
    print(color(33, underline=True) + "下划线黄色" + RESET)
    print(color(36, italic=True) + "斜体青色（有些终端可能不支持）" + RESET)

    # 多段组合
    sys.stdout.write(color(31, bold=True) + "[开始] " + RESET)
    sys.stdout.write(color(32) + "处理中... " + RESET)
    sys.stdout.write(color(34, underline=True) + "等待 I/O" + RESET + "\n")
    sys.stdout.flush()

    # 模拟进度
    for i in range(5):
        bar = "#" * (i + 1) + "-" * (5 - i - 1)
        sys.stdout.write("\r" + color(96) + f"进度: [{bar}] {((i+1)/5)*100:>3.0f}%" + RESET)
        sys.stdout.flush()
        time.sleep(0.2)
    print()  # 换行

    # stderr 颜色（用于测试错误流捕获）
    sys.stderr.write(color(31, bold=True) + "这是错误输出示例（stderr，红色粗体）" + RESET + "\n")
    sys.stderr.flush()

    # 提示用户输入（走内置 input → GUI 的输入路由）
    name = input("ANSI 测试：请输入昵称: ")
    print(color(92) + f"你好, {name or 'Guest'}! ANSI 打印测试完成。" + RESET)
