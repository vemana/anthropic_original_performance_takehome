# Performance

1110 cycles.

```text
[09:28:02] [lsv@vemana]$ git diff origin/main tests/

[09:28:12] [lsv@vemana]$ python3 tests/submission_tests.py > /tmp/log.txt && tail -n 20 /tmp/log.txt
.........
----------------------------------------------------------------------
Ran 9 tests in 1.239s

OK
Kernel for H = 10, batch_size = 256, rounds = 16
Using 32 concurrent threads and found 1110 instructions.
CYCLES:  1110
Testing forest_height=10, rounds=16, batch_size=256
CYCLES:  1110
Testing forest_height=10, rounds=16, batch_size=256
CYCLES:  1110
Testing forest_height=10, rounds=16, batch_size=256
CYCLES:  1110
Testing forest_height=10, rounds=16, batch_size=256
CYCLES:  1110
Testing forest_height=10, rounds=16, batch_size=256
CYCLES:  1110
Testing forest_height=10, rounds=16, batch_size=256
CYCLES:  1110
Testing forest_height=10, rounds=16, batch_size=256
CYCLES:  1110
Testing forest_height=10, rounds=16, batch_size=256
CYCLES:  1110
Speedup over baseline:  133.0936936936937

[09:28:16] [lsv@vemana]$ 
```

Stats

```text
----------------------------------------------------------------------------------------------------
                                         VALU SPLIT COUNTS                                          
----------------------------------------------------------------------------------------------------
                   %         60
                   +        106
                   -        156
                  >>        223
                   ^        508
        multiply_add        172
          vbroadcast         98
----------------------------------------------------------------------------------------------------
----------------------------------------------------------------------------------------------------
                                    Instruction Count per engine                                    
----------------------------------------------------------------------------------------------------
                 alu      11991
                flow       1035
                load       2127
               store         32
                valu       6427
----------------------------------------------------------------------------------------------------
----------------------------------------------------------------------------------------------------
                                       Count per instruction                                        
----------------------------------------------------------------------------------------------------
                   %        868
                   *       1376
                   +       2335
                   -       1404
                  >>       2585
                   ^       6628
             add_imm         25
               const         28
                load       2065
        multiply_add       2260
          vbroadcast        178
               vload         34
             vselect       1010
              vstore         32
                   |        784
----------------------------------------------------------------------------------------------------
----------------------------------------------------------------------------------------------------
                                   Histogram of engine slot usage                                   
----------------------------------------------------------------------------------------------------
          ('alu', 0)         99
          ('alu', 3)          1
          ('alu', 4)          7
          ('alu', 8)         19
         ('alu', 12)        984
         ('flow', 0)         75
         ('flow', 1)       1035
         ('load', 0)         46
         ('load', 1)          1
         ('load', 2)       1063
        ('store', 0)       1078
        ('store', 1)         32
         ('valu', 0)          5
         ('valu', 1)          6
         ('valu', 2)          6
         ('valu', 3)         26
         ('valu', 4)         22
         ('valu', 5)         27
         ('valu', 6)       1018
----------------------------------------------------------------------------------------------------
Arithcount = 63407
alu_intensity = 1056.7833333333333
alu_flow_intensity = 1039.4590163934427

----------------------------------------------------------------------------------------------------
                                        SCRATCH SPACE LAYOUT                                        
----------------------------------------------------------------------------------------------------
        ADDRESS       VARIABLE                LENGTH        SLOTS
----------------------------------------------------------------------------------------------------
           1516       _KV_-5                       8            1
           1524       _KV_-6                       8            1
           1500       _KV_16                       8            1
           1460       _KV_16896                    8            1
           1436       _KV_19                       8            1
           1508       _KV_2                        8            1
           1420       _KV_2127912214               8            1
           1468       _KV_2899272192               8            1
           1492       _KV_3042594569               8            1
           1444       _KV_33                       8            1
           1428       _KV_3345072700               8            1
           1452       _KV_3925396509               8            1
           1412       _KV_4097                     8            1
           1484       _KV_4251993797               8            1
           1476       _KV_9                        8            1
             65       _K_14                        1            1
             99       _K_6                         1            1
              8       _K_7                         1            1
             66       b1                           8            1
             74       b2                           8            1
             82       b3                           8            1
             90       b4                           8            1
            388       idx                          8           32
             98       inp_values_ptr               1            1
            900       p1                           8           32
           1156       p2                           8           32
            644       t                            8           32
              9       t0                           8            1
             17       t1                           8            1
             25       t2                           8            1
             33       t3                           8            1
             41       t4                           8            1
             49       t5                           8            1
             57       t6                           8            1
            100       tidxlen                      1           32
              0       treevals                     8            1
            132       v                            8           32
----------------------------------------------------------------------------------------------------
Concurrent threads  = 32
Per thread space    = 41
Globals space       = 220
Used space          = 1532
Free space          = 4
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


Unimplemented optimizations

- Borrow registers from completed threads to breakup long dependency chains in stragglers. Could be worth a substantial amount.
- Split `const dest <const>` to use `add_imm dest zero_register <const>` to parallelize constant loading. Worth at most 5 cycles.
