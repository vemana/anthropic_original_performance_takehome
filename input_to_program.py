from parser import Program, program as parser

def input_to_program(height:int, batch_size:int, rounds:int) -> str: 
    text = input_to_program_text(height, batch_size, rounds)
    parsed = parser.parse(text)
    if parsed.next_index != len(text):
      print(f"Remaining text: {text[parsed.next_index:]}")
      raise Exception("Failed to parse the whole program")
    return parsed.value

global_preamble="""
register tree_values_ptr = @4
register inp_values_ptr = @6
register vlen = 8
register[] treevals = @tree_values_ptr
register t0 = treevals[0]
register t1 = treevals[1]
register t2 = treevals[2]
register[] t3 = treevals[3]
register[] t4 = treevals[4]
register[] t5 = treevals[5]
register[] t6 = treevals[6]

# treevals holds level 3 values
tree_values_ptr = tree_values_ptr + 7
treevals = @tree_values_ptr
tree_values_ptr = tree_values_ptr - 7


end global
"""


thread_preamble="""
# Compiler fills in implicit registers tidx and tidxlen
# Declare if you want to use them
thread register tidxlen

# Work registers
thread register[] v, idx, t, p1, p2
thread register a

a = tidxlen + inp_values_ptr
v = @a

"""

level0_header = """
p1 = t0
v = v ^ p1
"""

level0_footer = """
idx = v % 2
"""

level1_header = """
p1 = t1
p2 = t2
t = idx ? p2 : p1
v = v ^ t
"""

level1_footer="""
p1 = v % 2
"""

level2_header = """
p2 = p1 ? t6 : t5
t = p1 ? t4 : t3
t = idx ? p2 : t
idx = idx - -5
idx = idx * 2 + p1
v = v ^ t
"""

level3_header = """
t = @idx[]
v = v ^ t
"""

level_footer="""
p1 = v % 2
p2 = p1 ? -5 : -6
# p2 = p1 - 6
idx = idx * 2 + p2
"""

level3_flow_based_header = """
idx = idx - 14
# idx in [0, 7]

t = 0

p1 = treevals[0]
p2 = 0
p2 = idx == p2
# t = p1 * p2 + t
t = p2 ? p1 : t

p1 = treevals[1]
p2 = 1
p2 = idx == p2
# t = p1 * p2 + t
t = p2 ? p1 : t

p1 = treevals[2]
p2 = 2
p2 = idx == p2
# t = p1 * p2 + t
t = p2 ? p1 : t

p1 = treevals[3]
p2 = 3
p2 = idx == p2
# t = p1 * p2 + t
t = p2 ? p1 : t

p1 = treevals[4]
p2 = 4
p2 = idx == p2
# t = p1 * p2 + t
t = p2 ? p1 : t

p1 = treevals[5]
p2 = 5
p2 = idx == p2
# t = p1 * p2 + t
t = p2 ? p1 : t

p1 = treevals[6]
p2 = 6
p2 = idx == p2
# t = p1 * p2 + t
t = p2 ? p1 : t

p1 = treevals[7]
p2 = 7
p2 = idx == p2
# t = p1 * p2 + t
t = p2 ? p1 : t

v = v ^ t
"""

level3_flow_based_footer = """
p1 = v % 2
idx = idx + 11
idx = idx * 2 + p1
"""

computation="""

v = v * 4097 + 0x7ED55D16

p1 = v ^ 0xC761C23C
p2 = v >> 19
v = p1 ^ p2


v = v * 33 + 0x165667B1 

p1 = v + 0xD3A2646C
p2 = v << 9
v = p1 ^ p2

v = v * 9 + 0xFD7046C5 

p1 = v ^ 0xB55A4F09
p2 = v >> 16
v = p1 ^ p2
"""

footer="""
a = tidxlen + inp_values_ptr
@a = v
"""

def input_to_program_text(height, batch_size, rounds) -> str:
#     with open('./p.txt') as f:
#         return f.read()
    # global, thread_preamble 
    # level0_header computation level0_footer
    # level1_header computation level_footer
    # level2_header computation level_footer
    # level3_header computation level_footer
    # level3_header computation level_footer
    # ...
    # last level: level3_header computation [no level_footer for last round since indices wrap around]
    # level0_header computation level0_footer
    # ....
    # footer

    ret = ""
    ret += global_preamble
    ret += thread_preamble
    for r in range(0, rounds):
        ret += f"\n######### Round {r} #########"
        level = r % (height+1)
        custom = True and level == 3 and r == rounds - 2

        if custom:
          ret += level3_flow_based_header
        elif level == 0:
          ret += level0_header
        elif level == 1:
          ret += level1_header
        elif level == 2:
          ret += level2_header
        else:
          ret += level3_header
        
        ret += computation

        if level == height or r == rounds - 1:
          pass
        elif custom:
          ret += level3_flow_based_footer
        else:
          ret += (level0_footer if level == 0 else (level1_footer if level == 1 else level_footer))

    ret += footer
    with open('/tmp/program.txt', "w", encoding="utf-8") as file:
        file.write(ret) 
    return ret

old_level0_header = """
t = treevals[0]
v = v ^ t
"""

old_level0_footer = """
p1 = v % 2
idx = p1 ? 9 : 8

#idx = p1 + 8 # SLOWER
"""

old_level1_header = """
p2 = treevals[2]
t = treevals[1]
t = p1 ? p2 : t
v = v ^ t
"""

old_level_footer="""
p1 = v % 2
p1 = p1 ? -5 : -6
#p1 = p1 - 6
idx = idx * 2 + p1
"""

old_level2_header = """
t = treevals[3]
p2 = treevals[4]
p1 = idx < 11 ? t : p2
p2 = 12 < idx ? t6 : t5
t = idx < 12 ? p1 : p2
v = v ^ t
"""
