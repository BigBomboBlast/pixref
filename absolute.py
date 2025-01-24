class glob:
    def __init__(self):
        self.mem = []

    def push(self, value):
        self.mem.append(value)

    def pop(self, enforce=None):
        value = self.mem[len(self.mem)-1]
        del self.mem[len(self.mem)-1]

        if enforce != None:
            if type(value) != enforce:
                print(f"Type Problem: {type(value)} != {enforce}")
                exit(1)

        return value

    def trace(self, current):
        print(f"\n --- Current scope: {current} --- \n")
        print("Stack trace: { ")
        for item in self.mem:
            print("\t", item)
        print("}")

        cont = input("Continue? y/n: ")
        if cont != 'y':
            print("Exiting.")
            exit()

# just some colors in case i want to do super pretty printing
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
MAGENTA = "\033[35m"
CYAN = "\033[36m"

"""
# absolute coding example
i = 0
def start():
    global i
    if i >= 10:
        return end
    print(f"{i}: Hello World!")
    i += 1
    return start

def end():
    pass

current = start
while current:
    current = current()

# equivalent
i=0
start:
    if i >= 10 goto end
    print Hello World!
    goto start
end:
"""
