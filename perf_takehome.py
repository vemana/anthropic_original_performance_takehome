"""
# Anthropic's Original Performance Engineering Take-home (Release version)

Copyright Anthropic PBC 2026. Permission is granted to modify and use, but not
to publish or redistribute your solutions so it's hard to find spoilers.

# Task

- Optimize the kernel (in KernelBuilder.build_kernel) as much as possible in the
  available time, as measured by test_kernel_cycles on a frozen separate copy
  of the simulator.

Validate your results using `python tests/submission_tests.py` without modifying
anything in the tests/ folder.

We recommend you look through problem.py next.
"""

from collections import defaultdict
from kernel_builder import KernelBuilder
import random
import unittest

from problem import (
    Engine,
    DebugInfo,
    SLOT_LIMITS,
    VLEN,
    N_CORES,
    SCRATCH_SIZE,
    Machine,
    Tree,
    Input,
    HASH_STAGES,
    reference_kernel,
    build_mem_image,
    reference_kernel2,
)

BASELINE = 147734
from util import pretty_print

def do_kernel_test(
    forest_height: int,
    rounds: int,
    batch_size: int,
    seed: int = 123,
    trace: bool = False,
    prints: bool = False,
):
    print(f"{forest_height=}, {rounds=}, {batch_size=}")
    random.seed(seed)
    forest = Tree.generate(forest_height)
    inp = Input.generate(forest, batch_size, rounds)
    mem = build_mem_image(forest, inp)

    kb = KernelBuilder()
    instrs = kb.build_kernel(forest.height, len(forest.values), len(inp.indices), rounds)
    # print(instrs)

    value_trace = {}
    machine = Machine(
        mem,
        instrs,
        kb.debug_info(),
        n_cores=N_CORES,
        value_trace=value_trace,
        trace=trace,
    )
    machine.prints = prints
    rnd = -2
    for i, ref_mem in enumerate(reference_kernel2(mem, value_trace)):
        rnd = 1 + rnd
        inp_values_p = ref_mem[6]
        inp_indices_p = ref_mem[5]
        try:
          machine.run()
        except Exception as ex:
          pretty_print(machine.mem)
          pretty_print(machine.cores[0].scratch)
          pretty_print(machine.mem[inp_values_p : inp_values_p + len(inp.values)])
          pretty_print(ref_mem[inp_values_p : inp_values_p + len(inp.values)])
          raise ex

        if prints:
            print(machine.mem[inp_values_p : inp_values_p + len(inp.values)])
            print(ref_mem[inp_values_p : inp_values_p + len(inp.values)])

        matching_values = machine.mem[inp_values_p : inp_values_p + len(inp.values)] == ref_mem[inp_values_p : inp_values_p + len(inp.values)]
        dmatchv = '' if matching_values else "DON'T"
        if not matching_values:
          print(f"XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX. INPUT VALUES {dmatchv} MATCH. First machine, then reference. Round = {rnd}")
          pretty_print(machine.mem[inp_values_p:inp_values_p + len(inp.values)])
          pretty_print(ref_mem[inp_values_p:inp_values_p + len(inp.values)])

          print(f"XXXXXXXXXXXXXXXXXXXXXXX REGISTER CONTENT XXXXXXXXXXXXXXXXXXXXXXXXXXX")
          pretty_print(machine.cores[0].scratch)

        gotindices = machine.mem[inp_indices_p : inp_indices_p + len(inp.values)]
        matching_indices = gotindices == ref_mem[inp_indices_p : inp_indices_p + len(inp.values)]
        dmatchi = '' if matching_indices else "DON'T"
        if not matching_values and matching_indices:
          print(f"XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX. INPUT INDICES {dmatchi} MATCH. First machine, then reference. Round = {rnd}")
          pretty_print(gotindices)
          pretty_print(ref_mem[inp_indices_p:inp_indices_p + len(inp.values)])

        
        assert (
            machine.mem[inp_values_p : inp_values_p + len(inp.values)]
            == ref_mem[inp_values_p : inp_values_p + len(inp.values)]
        ), f"Incorrect result on round {i}"
        inp_indices_p = ref_mem[5]
        if prints:
            print(machine.mem[inp_indices_p : inp_indices_p + len(inp.indices)])
            print(ref_mem[inp_indices_p : inp_indices_p + len(inp.indices)])
        # Updating these in memory isn't required, but you can enable this check for debugging
        # assert machine.mem[inp_indices_p:inp_indices_p+len(inp.indices)] == ref_mem[inp_indices_p:inp_indices_p+len(inp.indices)]

    print("CYCLES: ", machine.cycle)
    print("Speedup over baseline: ", BASELINE / machine.cycle)
    return machine.cycle


class Tests(unittest.TestCase):
    def test_ref_kernels(self):
        """
        Test the reference kernels against each other
        """
        random.seed(123)
        for i in range(10):
            f = Tree.generate(4)
            inp = Input.generate(f, 10, 6)
            mem = build_mem_image(f, inp)
            reference_kernel(f, inp)
            for _ in reference_kernel2(mem, {}):
                pass
            assert inp.indices == mem[mem[5] : mem[5] + len(inp.indices)]
            assert inp.values == mem[mem[6] : mem[6] + len(inp.values)]

    def test_kernel_trace(self):
        # Full-scale example for performance testing
        do_kernel_test(10, 16, 256, trace=True, prints=False)

    # Passing this test is not required for submission, see submission_tests.py for the actual correctness test
    # You can uncomment this if you think it might help you debug
    # def test_kernel_correctness(self):
    #     for batch in range(1, 3):
    #         for forest_height in range(3):
    #             do_kernel_test(
    #                 forest_height + 2, forest_height + 4, batch * 16 * VLEN * N_CORES
    #             )

    def test_kernel_cycles(self):
        do_kernel_test(10, 16, 256)
#         do_kernel_test(10, 1, 16)
#         do_kernel_test(2, 1, 16)


    def test_exhaustive_kernel_cycles(self):
        for height in range(1, 11, 2):
            for rounds in [1, 2, 3, height-1, height, height+1, 2*height-2, 2*height-1, 2*height, 2*height+1]:
                if rounds <= 0:
                    continue
                for bmult in [1, 2, 4, 8, 9, 32, 64]:
                    batch_size = VLEN * bmult
                    print('-'*200)
                    do_kernel_test(height, rounds, batch_size)


# To run all the tests:
#    python perf_takehome.py
# To run a specific test:
#    python perf_takehome.py Tests.test_kernel_cycles
# To view a hot-reloading trace of all the instructions:  **Recommended debug loop**
# NOTE: The trace hot-reloading only works in Chrome. In the worst case if things aren't working, drag trace.json onto https://ui.perfetto.dev/
#    python perf_takehome.py Tests.test_kernel_trace
# Then run `python watch_trace.py` in another tab, it'll open a browser tab, then click "Open Perfetto"
# You can then keep that open and re-run the test to see a new trace.

# To run the proper checks to see which thresholds you pass:
#    python tests/submission_tests.py

if __name__ == "__main__":
    unittest.main()
