def pretty_print_insts(insts):
    pass

def pretty_print(mem, message=''):
  mem = [i for i in range(0, 100)] + mem
  width:int = 20
  size:int = len(mem)
  block:int = 100 // width
  assert block * width == 100, f"Make them multiply to 100"

  if message != '':
    print(f"{message}")

  for y in range(0, (size + width - 1) // width):
    if y % block == 0:
      print('-' * 400)
    idx = "" if y < block else str(y//block - 1)

    print(f"  {idx:3}    |", end='')
    for j in range(0, width):
      val = '  ' * (y % block)
      val = val + (str(mem[y*width + j]) if y*width + j < size else '')
      rem_len = 18 - len(val)
      val = val + (' ' * rem_len) + '|'
      print(val, end='')
    print()

  print('-' * 400)

HASH_STAGES = [
    ("+", 0x7ED55D16, "+", "<<", 12),
    ("^", 0xC761C23C, "^", ">>", 19),
    ("+", 0x165667B1, "+", "<<", 5),
    ("+", 0xD3A2646C, "^", "<<", 9),
    ("+", 0xFD7046C5, "+", "<<", 3),
    ("^", 0xB55A4F09, "^", ">>", 16),
]


def myhash(a: int) -> int:
    """A simple 32-bit hash function"""
    fns = {
        "+": lambda x, y: x + y,
        "^": lambda x, y: x ^ y,
        "<<": lambda x, y: x << y,
        ">>": lambda x, y: x >> y,
    }

    def r(x):
        return x % (2**32)

    for op1, val1, op2, op3, val3 in HASH_STAGES:
        a = r(fns[op2](r(fns[op1](a, val1)), r(fns[op3](a, val3))))

    return a

if __name__ == "__main__":
    v = 626638978 
    v = 924787169 
    t0 =112449971
    tp = 2**32

    v = (v ^ t0) % tp
    expected = myhash(v)
    print(expected)

    p1 = (v + 0x7ED55D16) % tp
    p2 = (v << 12) % tp
    v = (p1 + p2) % tp

    p1 = (v ^ 0xC761C23C) % tp
    p2 = (v >> 19)%tp
    v = (p1 ^ p2) % tp

    p1 = (v + 0x165667B1) % tp
    p2 = (v << 5) % tp
    v = (p1 + p2) % tp

    p1 = (v + 0xD3A2646C) % tp
    p2 = (v << 9) % tp
    v = (p1 ^ p2) % tp

    p1 = (v + 0xFD7046C5) % tp
    p2 = (v << 3) % tp
    v = (p1 + p2) % tp

    p1 = (v ^ 0xB55A4F09) % tp
    p2 = (v >> 16) % tp
    v = (p1 ^ p2) % tp

    print(v)

    print("DONE XXXXXXXXXXXXXXXXXX",)
  
