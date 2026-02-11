from problem import VLEN
from parser import Program, program as parser
import textwrap

def input_to_program(height:int, batch_size:int, rounds:int) -> str: 
    assert batch_size % VLEN == 0
    text = input_to_program_text(height, batch_size, rounds)
    parsed = parser.parse(text)
    if parsed.next_index != len(text):
      print(f"Remaining text: {text[parsed.next_index:]}")
      raise Exception("Failed to parse the whole program")
    return parsed.value

global_preamble="""

register[] treevals = @7
register[] t0 = treevals[0]
register[] t1 = treevals[1]
register[] t2 = treevals[2]
register[] t3 = treevals[3]
register[] t4 = treevals[4]
register[] t5 = treevals[5]
register[] t6 = treevals[6]

treevals = @14
register[] b1 = treevals[1]
register[] b2 = treevals[2]
register[] b3 = treevals[3]
register[] b4 = treevals[4]

register inp_values_ptr = @6
end global
"""


thread_preamble="""
# Compiler fills in implicit registers tidx and tidxlen
# Declare if you want to use them
thread register tidxlen

# Work registers
thread register[] v, idx, t, p1, p2

tidxlen = tidxlen + inp_values_ptr
v = @tidxlen

"""

level0_header = """
v = v ^ t0
"""

level0_footer = """
idx = v % 2
"""

level1_header = """
t = idx ? t2 : t1
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

level2_footer="""
p1 = v % 2
p2 = p1 ? -5 : -6
# p2 = p1 + -6
idx = idx * 2 + p2
"""

level3_header = """
t = @idx[]
v = v ^ t
"""

level3_flow_based_header = """

t = treevals[0]

p1 = treevals[5]
p2 = idx - 19
t = p2 ? t : p1

p2 = p2 + 2
t = p2 ? t : b3

p2 = p2 + 2
t = p2 ? t : b1

p1 = treevals[7]
p2 = p2 + -6
t = p2 ? t : p1

p2 = p2 - -5
t = p2 ? t : b2

p2 = p2 - 2
t = p2 ? t : b4

p1 = treevals[6]
p2 = p2 - 2
t = p2 ? t : p1

v = v ^ t
"""

level_footer="""
p1 = v % 2
p2 = p1 ? -5 : -6
# p2 = p1 + -6
idx = idx * 2 + p2
"""

level3_flow_based_footer = """
p1 = v % 2
p2 = p1 ? -5 : -6
# p2 = p1 + -6
idx = idx * 2 + p2
"""

computation="""

# Stage 1
v = v * 4097 + 0x7ED55D16

# Stage 2
p1 = v ^ 0xC761C23C
p2 = v >> 19
v = p1 ^ p2

# Fuse stages 3 and 4
p1 = v * 33 + 3925396509
p2 = v * 16896 +2899272192 
v = p1 ^ p2

# Stage 5
v = v * 9 + 0xFD7046C5 

# Stage 6
p1 = v ^ 0xB55A4F09
p2 = v >> 16
v = p1 ^ p2
"""


footer="""
@tidxlen = v
"""

def make_template(size, special_nodes: set[int]):
    assert size > 0, f"Invalid size {size}. Should be > 0"
    for x in special_nodes:
        assert 0<=x and x < size, f"Invalid special node: {x}. Should be in [0, {size})"

    specials = []
    standards = []
    start = -1

    for i in range(0, size):
        special = i in special_nodes
        prev_special = (i-1) in special_nodes

        if i == 0 or prev_special != special:
            if start >= 0:
                (standards if special else specials).append((start, i))
            start = i

    (specials if size - 1 in special_nodes else standards).append((start, size))
    print(f"Specials = {specials}, standards = {standards}")

    if len(specials) == 0:
        return "\n$standard$\n"

    if len(standards) == 0:
        return "\n$special$\n"

    template = "\n\n"
    for idx, item in enumerate(specials):
        start, end = item
        template += "eliftid " if idx > 0 else "iftid "
        template += f"range({start}, {end})"
        template += "\n"
        template += "$special$"
        template += "\n"

    for idx, item in enumerate(standards):
        start, end = item
        template += "eliftid " if idx < len(standards) - 1 else "elsetid "
        template += f"range({start}, {end})" if idx < len(standards) - 1 else ""
        template += "\n"
        template += "$standard$"
        template += "\n"

    template += "endiftid\n\n"
    return template


def l3(size, special_nodes: set[int]):
    template = make_template(size, special_nodes)

    def indent(s):
        return textwrap.indent(s, '    ')

    header = template.replace('$special$', indent(level3_flow_based_header))\
            .replace('$standard$', indent(level3_header))

    footer = template.replace('$special$', indent(level3_flow_based_footer))\
            .replace('$standard$', indent(level_footer))

    return header, footer


def input_to_program_text(height, batch_size, rounds) -> str:
    ret = ""
    ret += global_preamble
    ret += thread_preamble

    use_custom = lambda: True and level == 3 #and r == rounds - 2
    nthreads = batch_size // VLEN

    for r in range(0, rounds):
        ret += f"\n######### Round {r} #########\n"
        level = r % (height+1)
        custom = use_custom()

        usecustom = True
        l3round1 = usecustom and level == 3 and r == 3
        l3round2 = usecustom and level == 3 and r > 3

        if level == 0:
            h, f = level0_header, level0_footer
        elif level == 1:
            h, f = level1_header, level1_footer
        elif level == 2:
            h, f = level2_header, level2_footer
        elif l3round1:
            h, f =  l3(nthreads, set(range(2, nthreads, 1)))
        elif l3round2:
            h, f =  l3(nthreads, set(range(0, nthreads, 1)))
        else:
            h, f = level3_header, level_footer
        
        ret += h
        ret += computation
        if level == height or r == rounds - 1:
            f = ""
        ret += f


    ret += footer

    with open('/tmp/program.txt', "w", encoding="utf-8") as file:
        file.write(ret) 
    return ret

