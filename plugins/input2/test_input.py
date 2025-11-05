def test_input1():
    while True:
        input1 = input("请输入1: ")
        if input1 == "exit":
            break
        print(input1)

def test_input2():
    while True:
        import sys
        print("请输入2: ", end="")
        input2 = sys.stdin.readline()
        if input2 == "exit":
            break
        print(input2)