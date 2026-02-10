# Performance

1253 cycles.

```text
[13:17:27] [lsv@vemana]$ git diff origin/main tests/


[13:17:29] [lsv@vemana]$ python3 tests/submission_tests.py > /tmp/log.txt && tail -n 20 /tmp/log.txt
.........
----------------------------------------------------------------------
Ran 9 tests in 1.226s

OK
Kernel for H = 10, batch_size = 256, rounds = 16
Using 32 concurrent threads and found 1253 instructions.
CYCLES:  1253
Testing forest_height=10, rounds=16, batch_size=256
CYCLES:  1253
Testing forest_height=10, rounds=16, batch_size=256
CYCLES:  1253
Testing forest_height=10, rounds=16, batch_size=256
CYCLES:  1253
Testing forest_height=10, rounds=16, batch_size=256
CYCLES:  1253
Testing forest_height=10, rounds=16, batch_size=256
CYCLES:  1253
Testing forest_height=10, rounds=16, batch_size=256
CYCLES:  1253
Testing forest_height=10, rounds=16, batch_size=256
CYCLES:  1253
Testing forest_height=10, rounds=16, batch_size=256
CYCLES:  1253
Speedup over baseline:  117.90422984836393
```


Stats

```text
----------------------------------------------------------------------------------------------------
                                    Instruction Count per engine                                    
----------------------------------------------------------------------------------------------------
alu --> 9467
flow --> 909
load --> 2399
store --> 32
valu --> 7361
----------------------------------------------------------------------------------------------------
                                       Count per instruction                                        
----------------------------------------------------------------------------------------------------
% --> 903
+ --> 1284
- --> 143
<< --> 1373
== --> 232
>> --> 2900
^ --> 7363
add_imm --> 130
const --> 35
load --> 2330
multiply_add --> 1920
vbroadcast --> 707
vload --> 34
vselect --> 779
vstore --> 32
| --> 3
----------------------------------------------------------------------------------------------------
                                   Histogram of engine slot usage                                   
----------------------------------------------------------------------------------------------------
('alu', 0) --> 314
('alu', 1) --> 2
('alu', 2) --> 5
('alu', 3) --> 2
('alu', 4) --> 123
('alu', 6) --> 1
('alu', 7) --> 1
('alu', 8) --> 177
('alu', 9) --> 1
('alu', 10) --> 1
('alu', 11) --> 3
('alu', 12) --> 623
('flow', 0) --> 344
('flow', 1) --> 909
('load', 0) --> 53
('load', 1) --> 1
('load', 2) --> 1199
('store', 0) --> 1221
('store', 1) --> 32
('valu', 0) --> 9
('valu', 1) --> 6
('valu', 2) --> 6
('valu', 3) --> 8
('valu', 4) --> 10
('valu', 5) --> 5
('valu', 6) --> 1209
Arithcount = 68355
alu_intensity = 1139.25
alu_flow_intensity = 1120.5737704918033

----------------------------------------------------------------------------------------------------
                                        SCRATCH SPACE LAYOUT                                        
----------------------------------------------------------------------------------------------------
        ADDRESS       VARIABLE                LENGTH        SLOTS
----------------------------------------------------------------------------------------------------
           1497       _KV_-5                       8            1
           1505       _KV_-6                       8            1
           1526       _KV_11                       8            1
           1513       _KV_14                       8            1
           1481       _KV_16                       8            1
           1425       _KV_19                       8            1
           1489       _KV_2                        8            1
           1409       _KV_2127912214               8            1
           1473       _KV_3042594569               8            1
           1433       _KV_33                       8            1
           1417       _KV_3345072700               8            1
           1449       _KV_3550635116               8            1
           1441       _KV_374761393                8            1
           1401       _KV_4097                     8            1
           1465       _KV_4251993797               8            1
              0       _KV_64                       8            1
           1457       _KV_9                        8            1
           1521       _K_0                         1            1
           1522       _K_1                         1            1
           1523       _K_2                         1            1
           1524       _K_3                         1            1
              9       _K_4                         1            1
           1525       _K_5                         1            1
             11       _K_6                         1            1
             56       _K_7                         1            1
           1369       a                            1           32
            345       idx                          8           32
             10       inp_values_ptr               1            1
            857       p1                           8           32
           1113       p2                           8           32
            601       t                            8           32
             21       t0                           1            1
             22       t1                           1            1
             23       t2                           1            1
             24       t3                           8            1
             32       t4                           8            1
             40       t5                           8            1
             48       t6                           8            1
             57       tidxlen                      1           32
              8       tree_values_ptr              1            1
             13       treevals                     8            1
             89       v                            8           32
             12       vlen                         1            1
----------------------------------------------------------------------------------------------------
Concurrent threads  = 32
Per thread space    = 42
Globals space       = 190
Used space          = 1534
Free space          = 2
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

