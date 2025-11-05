def test_input1():
    while True:
        input1 = input("请输入1: ")
        if input1 == "exit":
            break
        print(input1)

def test_input2():
    while True:
        import sys
        print("*"*100)
        print("请输入2: ", end="")
        input2 = sys.stdin.readline()
        if input2 == "exit":
            break
        print(input2)

def test_rich_input():
    from rich.prompt import Prompt
    while True:
        input3 = Prompt.ask("请输入3: ")
        if input3 == "exit":
            break
        print(input3)
