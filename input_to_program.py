from parser import Program, program as parser

def input_to_program(height:int, batch_size:int, rounds:int) -> str: 
    return parser.parse(input_to_program_text(height, batch_size, rounds)).value

global_preamble="""
register tree_values_ptr = @4
register inp_idx_ptr = @5
register inp_values_ptr = @6
register vlen = 8
register[] treevals = @tree_values_ptr

#register[] t0 = treevals[0]
#register[] t1 = treevals[1]
#register[] t2 = treevals[2]
#register[] t3 = treevals[3]
#register[] t4 = treevals[4]

register[] t5 = treevals[5]
register[] t6 = treevals[6]

end global
"""

thread_preamble="""
# tidx is an implicit register filled by compiler
thread register tidx

# Work registers
thread register[] v, idx, t, p1, p2

thread register valoffset
valoffset = tidx * vlen
valoffset = valoffset + inp_values_ptr
v = @valoffset

#thread register idxoffset
#idxoffset = tidx * vlen
#idxoffset = idxoffset + inp_idx_ptr
"""

level0_header = """
t = treevals[0]
"""

level0_footer = """
p1 = v % 2
idx = p1 ? 9 : 8
"""

level1_header = """
#t = p1 ? t2 : t1

p2 = treevals[2]
t = treevals[1]
t = p1 ? p2 : t
"""

level2_header = """
#p1 = idx < 11 ? t3 : t4
#p2 = 12 < idx ? t6 : t5
#t = idx < 12 ? p1 : p2

t = treevals[3]
p2 = treevals[4]
p1 = idx < 11 ? t : p2
p2 = 12 < idx ? t6 : t5
t = idx < 12 ? p1 : p2
"""

level3_header = """
t = @idx[]
"""

level_footer="""
p1 = v % 2
p1 = p1 ? -5 : -6
idx = idx * 2 + p1
"""

computation="""
v = v ^ t

p1 = v + 0x7ED55D16
p2 = v << 12
v = p1 + p2

p1 = v ^ 0xC761C23C
p2 = v >> 19
v = p1 ^ p2

p1 = v + 0x165667B1
p2 = v << 5
v = p1 + p2

p1 = v + 0xD3A2646C
p2 = v << 9
v = p1 ^ p2

p1 = v + 0xFD7046C5
p2 = v << 3
v = p1 + p2

p1 = v ^ 0xB55A4F09
p2 = v >> 16
v = p1 ^ p2
"""

footer="""
@valoffset = v
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
        if level == 0:
          ret += level0_header
          ret += computation
          if level != height:
            ret += level0_footer
        elif level == 1:
          ret += level1_header
          ret += computation
          if level != height:
            ret += level_footer
        elif level == 2:
          ret += level2_header
          ret += computation
          if level != height:
            ret += level_footer
        else:
          ret += level3_header
          ret += computation
          if level != height:
            ret += level_footer

    ret += footer
#     with open('/tmp/p3.txt', "w", encoding="utf-8") as file:
#         file.write(ret) 
    return ret
