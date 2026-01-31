from dataclasses import dataclass, field
from typing import Tuple, List, Any
from collections import defaultdict

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

from parser import Program
from scratch import ScratchSpace, InsufficientRegisterCountException
from instr_graph_model import (
        EX_UNITS, EX_VALU, EX_ALU, EX_LOAD, EX_STORE, EX_FLOW, 
        Work, SerializedInstruction,
        )
from program_to_graph import estimate_max_conc_threads, program_to_work
from input_to_program import input_to_program


class KernelBuilder:
    def __init__(self):
        # This state is only for the testers to access. This code itself is Functional and doesn't have state like this.
        self.instrs = []
        self.scratch_debug = {}

    def debug_info(self):
        return DebugInfo(scratch_map=self.scratch_debug)

    def build_kernel(self, forest_height: int, n_nodes: int, batch_size: int, rounds: int):
        assert n_nodes == (1<<(forest_height + 1)) - 1, "Expected a complete binary tree."

        num_threads: int = (batch_size + VLEN - 1) // VLEN
        assert num_threads * VLEN == batch_size, "batch_size should be a multiple of VLEN. You can always pad dummy nodes to make it so without much cost."

        program = input_to_program(forest_height, batch_size, rounds)
        conc_threads = estimate_max_conc_threads(program, num_threads)
        instrs, ss = optimize(program, num_threads, conc_threads)
        self.instrs = instrs

        print(f"Kernel for H = {forest_height}, batch_size = {batch_size}, rounds = {rounds}")
        print(f"Using {conc_threads} concurrent threads and found {len(instrs)} instructions.")
        return instrs


def optimize(program: Program, num_threads: int, conc_threads: int) -> List[SerializedInstruction]:
    work, ss = program_to_work(program, num_threads, conc_threads)
    insts = work_to_instrs(work)
    stats_for_nerds(insts, ss)
    return (insts, ss)


def work_to_instrs(work: Work) -> list[SerializedInstruction]:
#     work.print()
    insts = []
    while work.have_more():
        insts.append(work.take())
    return insts


def stats_for_nerds(instrs, ss):
    ss.print()
    stats = defaultdict(int)
    def add_stat(group):
        for engine, insts in group.items():
            stats[(engine, len(insts))] += 1
    for inst in instrs:
        add_stat(inst)
    print("\n".join([f"{key[0]}, {key[1]} --> {value}" for key, value in sorted(stats.items())]))


