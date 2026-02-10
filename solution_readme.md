# Performance

1174 cycles.

```text
[17:30:19] [lsv@vemana]$ git diff origin/main tests/

[/data/devel/vemana/anthropic/anthropic_original_performance_takehome]
[17:30:21] [lsv@vemana]$ python3 tests/submission_tests.py > /tmp/log.txt && tail -n 20 /tmp/log.txt
.........
----------------------------------------------------------------------
Ran 9 tests in 1.292s

OK
Kernel for H = 10, batch_size = 256, rounds = 16
Using 32 concurrent threads and found 1174 instructions.
CYCLES:  1174
Testing forest_height=10, rounds=16, batch_size=256
CYCLES:  1174
Testing forest_height=10, rounds=16, batch_size=256
CYCLES:  1174
Testing forest_height=10, rounds=16, batch_size=256
CYCLES:  1174
Testing forest_height=10, rounds=16, batch_size=256
CYCLES:  1174
Testing forest_height=10, rounds=16, batch_size=256
CYCLES:  1174
Testing forest_height=10, rounds=16, batch_size=256
CYCLES:  1174
Testing forest_height=10, rounds=16, batch_size=256
CYCLES:  1174
Testing forest_height=10, rounds=16, batch_size=256
CYCLES:  1174
Speedup over baseline:  125.8381601362862
```

Stats

```text
----------------------------------------------------------------------------------------------------
                                    Instruction Count per engine                                    
----------------------------------------------------------------------------------------------------
alu --> 12389
flow --> 1008
load --> 2178
store --> 32
valu --> 6906
----------------------------------------------------------------------------------------------------
                                       Count per instruction                                        
----------------------------------------------------------------------------------------------------
% --> 1022
* --> 1984
+ --> 2481
- --> 1906
>> --> 2543
^ --> 6509
add_imm --> 96
const --> 30
load --> 2114
multiply_add --> 2184
vbroadcast --> 663
vload --> 34
vselect --> 912
vstore --> 32
| --> 3
----------------------------------------------------------------------------------------------------
                                   Histogram of engine slot usage                                   
----------------------------------------------------------------------------------------------------
('alu', 0) --> 93
('alu', 1) --> 3
('alu', 2) --> 4
('alu', 3) --> 1
('alu', 4) --> 19
('alu', 7) --> 2
('alu', 8) --> 83
('alu', 9) --> 1
('alu', 10) --> 2
('alu', 12) --> 966
('flow', 0) --> 166
('flow', 1) --> 1008
('load', 0) --> 85
('load', 2) --> 1089
('store', 0) --> 1142
('store', 1) --> 32
('valu', 0) --> 6
('valu', 1) --> 3
('valu', 2) --> 9
('valu', 3) --> 5
('valu', 4) --> 12
('valu', 5) --> 12
('valu', 6) --> 1127
Arithcount = 67637
alu_intensity = 1127.2833333333333
alu_flow_intensity = 1108.8032786885246

----------------------------------------------------------------------------------------------------
                                        SCRATCH SPACE LAYOUT                                        
----------------------------------------------------------------------------------------------------
        ADDRESS       VARIABLE                LENGTH        SLOTS
----------------------------------------------------------------------------------------------------
           1504       _KV_-5                       8            1
           1512       _KV_-6                       8            1
           1520       _KV_1                        8            1
           1488       _KV_16                       8            1
           1448       _KV_16896                    8            1
           1528       _KV_17                       8            1
           1424       _KV_19                       8            1
           1496       _KV_2                        8            1
           1408       _KV_2127912214               8            1
           1456       _KV_2899272192               8            1
           1480       _KV_3042594569               8            1
           1432       _KV_33                       8            1
           1416       _KV_3345072700               8            1
           1440       _KV_3925396509               8            1
           1400       _KV_4097                     8            1
           1472       _KV_4251993797               8            1
              0       _KV_64                       8            1
           1464       _KV_9                        8            1
              9       _K_4                         1            1
             11       _K_6                         1            1
             55       _K_7                         1            1
           1368       a                            1           32
            344       idx                          8           32
             10       inp_values_ptr               1            1
            856       p1                           8           32
           1112       p2                           8           32
            600       t                            8           32
             20       t0                           1            1
             21       t1                           1            1
             22       t2                           1            1
             23       t3                           8            1
             31       t4                           8            1
             39       t5                           8            1
             47       t6                           8            1
             56       tidxlen                      1           32
              8       tree_values_ptr              1            1
             12       treevals                     8            1
             88       v                            8           32
----------------------------------------------------------------------------------------------------
Concurrent threads  = 32
Per thread space    = 42
Globals space       = 192
Used space          = 1536
Free space          = 0
----------------------------------------------------------------------------------------------------
```


# Correctness

Tests robustness with a newly-created exhaustive test suite in `perf_takehome.py` named `test_exhaustive_kernel_cycles`.


# Approach

Tools
- Understand Little's law on throughput [my 10-minute-mental-model](https://openparens.pages.dev/blog/2025/10mmm-littles-law/)
- Create a simple througput oriented programming language with global and per-thread context. Call this `XYZ` language. Similar to CUDA.
- Write a compiler for this language targeting the machine of this problem
- Write an optimizer alongside the compiler
- Create a visualizer for the compiled code
- Print stats convenient for throughput analysis
- The brain 


Approach
- Start with the approximation `Cycles ~ Pipeline depth + inverse throughput`
- Calculate the VALU, ALU, LOAD and FLOW engine budget
- Don't have budget for `load` for 16 rounds --> First three levels should not use load
- Simplify the hash calcuation using `multiply_add`
- Once the bottleneck is `load`, try to always saturate `LOAD` engine
- Look at the visualizer to improve saturation


Interesting Files
- `xyz_program.txt` contains the program (in `XYZ` language). Generated by `kernel_builder.py`
- [visual_instructions.html](https://htmlpreview.github.io/?https://raw.githubusercontent.com/vemana/anthropic_original_performance_takehome/refs/heads/main/visual_instructions.html) contains a visualization of instruction packing
- `prompt_parser.txt` contains the hand-written Grammar (a PEG style grammar) and the base prompt for generating the parser
- `kernel_builder.py` contains the workflow going from input to machine code
- `program_to_graph.py` converts a parsed program AST into a dependency graph
- `instr_graph_model.py` is the optimizer. It performs dependency analysis, reorder instructions and splits large-word ops into single-word ops
- `display.py` is the visualizer API


Assumptions
- Avoid overfitting the specific problem shape and target robustness (e.g. correctness checks via `test_exhaustive_kernel_cycles`)
- Assumption wrt problem shape
  - Input is a complete binary tree
  - `batch_size` is a multiple of VLEN (can be fixed; but lazy)
  - Affect the program generation in `XYZ` language but not that language itself. 
- Hacks specific to problem shape (`10, 256, 16`)
  - There's one hack in the optimizer that targets the test shape. This can be inferred at the cost of extra passes. I didn't want to implement it.
  - The optimizer's dependency analysis ignores pointer aliasing in establishing safety


Help used
- Display is generated by [Gemini session](https://gemini.google.com/share/076340d6d2e2) which starts with a base prompt and follows up with additional modifications
- Parser is generated from hand-written Grammar by [Gemini session](https://gemini.google.com/share/0bd587ebade2). Base prompt + follow ups + inline modifications


Interesting details

- The `XYZ` language has CUDA like semantics and runs with a number of concurrent threads
- The program calculates the max number of concurrent threads based on scratch space supply (fixed by this problem) and demand (implied by the program)
- Dependency analysis on scratch space is accurate and enables instruction reordering and splitting a VALU instruction into ALU instructions
  - Ignores pointer aliasing because it is tough and it is not needed for our toy program
- PEG style grammar for `XYZ` language, in order to add features quickly. Specifically ordered choice is the user-friendly feature of PEG
- Generally functional style code. Python's lack of first-class union types is a bummer
- The visualization tool was very handy and Gemini did a terrific job of one-shotting it
- The parser was harder for Gemini because of the myriad of detail but it eventually did a good job after repeatedly fixing the prompt to tell it one more thing

