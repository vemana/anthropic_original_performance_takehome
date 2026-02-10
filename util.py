def pretty_print_insts(insts):
    pass


def pretty_print_map(count, message=''):
    line = '-' * 100
    if message != '':
        print(line, f"{message:^100}", sep='\n')
    print(line, "\n".join([f"{key} --> {value}" for key, value in sorted(count.items())]), sep = '\n')


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

