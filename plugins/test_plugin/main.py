import sys
import os
from moudleA import ModuleA
import time

class TestPlugin:
    def __init__(self):
        pass
    
    def main(self, params=None):
        print("=== class TestPlugin main函数被调用 ===")
        moduleA = ModuleA()
        moduleA.funcA()
        print("sys.argv:", sys.argv)
        if params:
            print("接收到的参数:", params)
            for key, value in params.items():
                print(f"参数 {key}: {value}")
        else:
            print("未接收到参数")
        print("=== class TestPlugin main函数结束 ===")

    def process_data(self, params):
        """处理数据的函数，优先被调用"""
        print("=== class TestPlugin process_data函数被调用 ===")
        print("接收到的参数:", params)
        for key, value in params.items():
            print(f"参数 {key}: {value}")
        result = ["处理完成", "参数已接收"]
        print("=== class TestPlugin process_data函数结束 ===")
        return result

def main(params=None):
    print("=== main函数被调用 ===")
    print("sys.argv:", sys.argv)
    if params:
        print("接收到的参数:", params)
        for key, value in params.items():
            print(f"参数 {key}: {value}")
    else:
        print("未接收到参数")
    while True:
        print("等待输入...")
        text = sys.stdin.readline().strip()
        if input == "exit":
            break
        print("输入:", text)
        time.sleep(1)
    print("=== main函数结束 ===")

def process_data(params):
    """处理数据的函数，优先被调用"""
    print("=== process_data函数被调用 ===")
    print("接收到的参数:", params)
    for key, value in params.items():
        print(f"参数 {key}: {value}")
    result = ["处理完成", "参数已接收"]
    while True:
        print("等待输入...")
        text = input()
        if text == "exit":
            break
        print("输入:", text)
        time.sleep(1)
    print("=== process_data函数结束 ===")
    return result

if __name__ == "__main__":
    main()