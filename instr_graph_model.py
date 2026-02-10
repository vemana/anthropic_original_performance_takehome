from dataclasses import dataclass, field, replace
from typing import Any, Protocol
from scratch import ScratchSpace 
from lib import InsertionOrderedSet as ios
from collections import defaultdict, Counter
from display import Display, DataInfo
from lib import MinHeap, TestMinHeap
import threading
import time

EX_VALU="valu"
EX_ALU="alu"
EX_LOAD="load"
EX_STORE="store"
EX_FLOW="flow"

# The order is important. valu > alu because we should try to assign bulk work first
EX_UNITS = [EX_VALU, EX_ALU, EX_LOAD, EX_STORE, EX_FLOW]
VLEN = 8

SLOT_LIMITS = {
    "alu": 12,
    "valu": 6,
    "load": 2,
    "store": 2,
    "flow": 1,
    "debug": 64,
}

# The instruction understood by this machine
SerializedInstruction = tuple[str, tuple] # Example: ("valu", ("vbroadcast", destaddr, srcaddr))

# Models an inclusive range
@dataclass() # Force key naming
class Range:
    lo: int
    hi: int

    def is_empty(self):
        return self.hi < self.lo

    def intersect(self, that: 'Range') -> 'Range':
        return Range(max(self.lo, that.lo), min(self.hi, that.hi))

    def values(self):
        lo = self.lo
        hi = self.hi
        if hi >= lo:
            return [x for x in range(lo, hi+1)]
        return []

SPECIAL_MEM_REGISTER_NAME = '__mem__'

class LogicalOp:
    pass

@dataclass(kw_only=True, eq=True, frozen=True, order=True)
class ArrayOp(LogicalOp):
    name: str # The variable whose block this Array encompasses
    offset: int # offset within the array
    is_vector: bool # Whether vectored read
    is_read: bool


    @classmethod
    def of(cls, *, ss, name, offset, is_vector, is_read):
        vm = ss.var_meta_of(name)
        assert offset < vm.size()
        if is_vector:
            assert offset + VLEN <= vm.size()

        return cls(name = name, offset = offset, is_vector = is_vector, is_read = is_read)


    def addr_of(self, ss: ScratchSpace):
        return ss.var_meta_of(self.name).addr_of(0) + self.offset


    def range(self, ss: ScratchSpace, slot:int):
        if self.is_mem():
            return Range(-1, -1)

        base = self.addr_of(ss)
        return Range(base, base + (VLEN if self.is_vector else 1) - 1)


    def is_mem(self):
        return False


    def compact_str(self):
        if self.is_vector:
            return f"{self.name:>13}[{self.offset:>2} - {self.offset+VLEN-1:>2}]"
        else:
            return f"{self.name:>18}[{self.offset:>2}]"


# A Logical Register that is converted to address when emitting SerializedInstruction
# It is annotated with whether the usage is a read/write and scalar/vector
# for performing optimizations
@dataclass(kw_only=True, eq=True, frozen=True, order=True) # Force key naming
class LogicalRegister(LogicalOp):
    name: str
    offset: int
    # True iff this read is a vectored read. Implies offset = 0.
    # Scalar read is either a single word read at `offset` of a vectored
    # variable `name` or a read of a scalar variable
    # This says nothing about whether the variable `name` is itself a vector
    is_vector: bool
    is_read: bool


    def __post_init__(self):
        assert self.offset >= 0
        assert self.offset < VLEN
        if self.is_vector:
            assert self.offset == 0


    def range(self, ss: ScratchSpace, slot:int):
        if self.is_mem():
            return Range(-1, -1)

        vm = ss.var_meta_of(self.name)
        if self.is_vector:
            assert vm.is_vector
            return Range(vm.addr_of(slot), vm.addr_of(slot) + VLEN - 1)
        else:
            addr = vm.addr_of(slot) + self.offset
            return Range(addr, addr)


    def is_mem(self):
        return self.name == SPECIAL_MEM_REGISTER_NAME


    def scalar_at_offset(self, offset:int):
        return replace(self, offset = offset, is_vector = False)


    def addr_of(self, ss, slot):
        assert not self.is_mem()
        return ss.var_meta_of(self.name).addr_of(slot) + self.offset
    

    def is_vector_constant(self, ss):
        assert not self.is_mem()
        varmeta = ss.var_meta_of(self.name)
        return varmeta.is_constant and self.is_vector


    def is_scalar_constant(self, ss):
        assert not self.is_mem()
        varmeta = ss.var_meta_of(self.name)
        # Note: use self.is_vector (the actual use type) not varmeta.is_vector (the declared type)
        return varmeta.is_constant and (not self.is_vector)


    def constant_value(self, ss):
        assert not self.is_mem()
        assert self.is_vector_constant(ss) or self.is_scalar_constant(ss)
        varmeta = ss.var_meta_of(self.name)
        return varmeta.constant_value


    def overlaps(self, that, ss: ScratchSpace, slot: int):
        return not self.range(ss, slot).intersect(that.range(ss, slot)).is_empty()


    def compact_str(self):
        if self.is_vector:
            return f"{self.name:>19}[ ]"
        elif self.offset > 0:
            return f"{self.name:>19}[{self.offset}]"
        else:
            return f"{self.name:>22}"

LR = LogicalRegister


# An instruction that is specified in terms of logical registers that can be replaced 
# at optimization time based on thread_idx
@dataclass(eq=True, frozen=True, order=True)
class LogicalInstruction:
    engine: str
    inst: tuple # Same as SerializedInstruction except that registers are Logical

    def compact_str(self):
        ret = f"{self.engine:>10}"
        ret += " ".join([y.compact_str() if isinstance(y, LR) or isinstance(y, ArrayOp) else f"{str(y):>22}" for y in self.inst])
        return ret


LI = LogicalInstruction


class Work(Protocol):
    def have_more(self) -> bool: ...
    def take(self) -> list[SerializedInstruction]: ...

INFINITE_SET = frozenset(range(-1, 100))


@dataclass(kw_only=True, eq=True, unsafe_hash=True)
class InstrMeta:
    instid: int # Instruction id in the program order
    lin: LogicalInstruction
    tid: int # Thread id; = 0 if global
    instid_in_thread: int # The instruction id within this thread
    after: ios  # ids of instructions that this unlocks
    tidrange: frozenset[int] = field(default_factory = lambda: INFINITE_SET)


    def __post_init__(self):
        tid = self.tid
        tidrange = self.tidrange
        assert tid == -2 or (tid in tidrange), f"{tid} was neither -2 nor in {tidrange}"


    def __priority_tuple(self):
        is_global = 1 if self.tid < 0 else 0
        is_greedy = (1 if self.tid < 16 else 0) * (1 - is_global)
        is_batch = (1 - is_greedy) * (1 - is_global)
        return (0
                , self.__block()
                , self.tid
                , self.instid
                , self.lin
                , self.tid
                , self.instid_in_thread
                , self.after
                )


    # Remember that after split, there can be VLEN with the same instid but different register offsets
    def __lt__(self, that):
        return self.__priority_tuple() < that.__priority_tuple()

    
    def __block(self):

        if self.tid < 0:
            return (-1, 0)

        if not hasattr(self, 'checkpoints'):
            self.checkpoints = [284, 10000]

        for idx, c in enumerate(self.checkpoints):
            if self.instid_in_thread < c:
                return idx, 0
#                 return (c - self.instid_in_thread, self.tid)
#                 return (idx, c - self.instid_in_thread)

        assert False


    def registers(self, ss:ScratchSpace):
        ret = []
        lin = self.lin
        for param in lin.inst:
            if not isinstance(param, LogicalRegister) and not isinstance(param, ArrayOp):
                continue
            ret.append(param)

        # Reads and Writes to memory are treated as happening to a special register
        # since we don't know the actual memory address the read or write is happening
        # at optimization time.
        if lin.inst[0] in ["load", "load_offset", "vload", "vstore", "store"]:
            lr = LogicalRegister(name = SPECIAL_MEM_REGISTER_NAME
                                  , offset = 0
                                  , is_vector = False
                                  , is_read = lin.engine == EX_LOAD)
            ret.append(lr)

        return ret


    def is_vector_imm_add(self, ss):
        lin = self.lin
        if lin.engine != EX_VALU:
            return False
        if lin.inst[0] != '+':
            return False
        regs = self.registers(ss)
        if len(regs) != 3:
            return False
        for reg in regs:
            if not reg.is_vector:
                return False
        if not regs[2].is_vector_constant(ss):
            return False
        return True


    def is_scalar_imm_add(self, ss):
        lin = self.lin
        if lin.engine != EX_ALU:
            return False
        if lin.inst[0] != '+':
            return False
        regs = self.registers(ss)
        if len(regs) != 3:
            return False
        for reg in regs:
            if reg.is_vector:
                return False
        if not regs[2].is_scalar_constant(ss):
            return False
        return True


    def compact_str(self):
        return f"{self.instid:>10} {self.tid:>5} {self.instid_in_thread:>5} {self.lin.compact_str():150}          {self.after}"

SET_MINUS_ONE = frozenset([-1])

class InstrGraph:
    def __init__(self, ss: ScratchSpace, num_threads:int):
        self.num_threads = num_threads
        self.ss = ss
        self.imetas: list[InstrMeta] = []
        self.num_global = 0
        self.globalimetas: list[InstrMeta] = []


    def add(self, linst: LogicalInstruction, is_global, *, tidrange: set[int]):
        if is_global:
            assert tidrange is None or tidrange == {-1}, f"For global instructions, tidrange should be -1, but was {tidrange}"
            self.globalimetas.append(InstrMeta(instid=-1, lin=linst, tid=-1, instid_in_thread = -1, after=ios(), tidrange = SET_MINUS_ONE))
        else:
            self.imetas.append(InstrMeta(instid=-1
                                         , lin=linst
                                         , tid=-2
                                         , instid_in_thread=-1
                                         , after=ios()
                                         , tidrange = INFINITE_SET if tidrange is None else tidrange))

    
    def add_pause(self, pinst: LogicalInstruction, is_global):
        pass
        # Needs real sync between threads, which we don't suppor


    def get_tidmetas(self, conc_threads, emit_constants = False):
        nthreads = self.num_threads
        cthreads = conc_threads
        if not self.ss.has_variable('tidxlen'):
            return [], []

#         raise ValueError(f"Doing tidx {cthreads} {nthreads}")
        if cthreads < nthreads or nthreads <= VLEN:
            ret = [
                InstrMeta(instid = -1
                          , lin = LI(EX_LOAD, ("const", LR(name="tidxlen", offset=0, is_vector=False, is_read=False), i * VLEN))
                          , tid = i
                          , instid_in_thread = -1
                          , after = ios()) 
                for i in range(0, nthreads)
                ]
            return ret, []

        assert cthreads == nthreads, f"conc_threads must be <= num_threads; {cthreads} vs {nthreads}"


        def tid_array_op(offset, *, is_vector, is_read):
            return ArrayOp.of(ss = self.ss
                           , name = "tidxlen"
                           , offset = offset
                           , is_vector = is_vector
                           , is_read = is_read)
          
        ret = []

        if emit_constants:
            ret.append(InstrMeta(instid = -1
                                 , lin = LI(EX_LOAD
                                            , ("const"
                                               , LR(name=self.ss.constant_name(VLEN * VLEN, is_vector=True)
                                                    , offset = 0
                                                    , is_vector=True
                                                    , is_read=False)
                                               , VLEN*VLEN))
                                 , tid = -1
                                 , instid_in_thread = -1
                                 , after = ios()))
            ret.append(InstrMeta(instid = -1
                                 , lin = LI(EX_VALU
                                            , ("vbroadcast"
                                               , LR(name=self.ss.constant_name(VLEN * VLEN, is_vector=True)
                                                    , offset = 0
                                                    , is_vector=True
                                                    , is_read=False)
                                               , LR(name=self.ss.constant_name(VLEN * VLEN, is_vector = True)
                                                    , offset = 0
                                                    , is_vector = False
                                                    , is_read = True)))
                                 , tid = -1
                                 , instid_in_thread = -1
                                 , after = ios()))

        npos = nthreads % VLEN
        if npos == 0:
            npos = VLEN
        lpos=0
        ret.extend([InstrMeta(instid = -1
                          , lin = LI(EX_LOAD, ("const" , tid_array_op(i, is_vector = False, is_read = False) , i * VLEN if i < npos else -64 + i * VLEN))
                          , tid = -1
                          , instid_in_thread = -1
                          , after = ios()) 
               for i in range(0, VLEN)])

        while npos < nthreads:
            ret.append(InstrMeta(instid = -1
                          , lin = LI(EX_VALU, ("+"
                                               , tid_array_op(npos, is_vector=True, is_read=False)
                                               , tid_array_op(lpos, is_vector=True, is_read=True)
                                               , LR(name=self.ss.constant_name(VLEN * VLEN, is_vector=True), offset = 0, is_vector=True, is_read=True)))
                          , tid = -1
                          , instid_in_thread = -1
                          , after = ios()))
            npos += VLEN
            lpos += VLEN

        return [], ret


    def get_work(self, *, conc_threads:int, optimize=False) -> Work:
        ss = self.ss
        ssize = ss.size()
        imetas = []
        tidmetas, moreglobal = self.get_tidmetas(conc_threads, emit_constants = True)
        # These can be swapped if emit_constants = True
        imetas.extend(self.globalimetas)
        imetas.extend(moreglobal)

        assert len(tidmetas) % self.num_threads == 0, f"{len(tidmetas)}, {self.num_threads}"

        for i in range(0, self.num_threads):
            threadinsts = [tidmetas[i + self.num_threads * x] for x in range(0, len(tidmetas) // self.num_threads)] \
                          + [replace(x, tid=i) for x in self.imetas if i in x.tidrange]
            for idx, x in enumerate(threadinsts):
                x.instid_in_thread = idx
            imetas.extend(threadinsts)
        
        # If not optimizing, assign serial work
        if not optimize:
            for idx, imeta in enumerate(imetas):
                imeta.instid = idx
                # Strict-order instructions within a thread
                imeta.after = ios.initial(idx+1) if idx + 1 < len(imetas) \
                        and imeta.tid >= 0 and imeta.tid == imetas[idx+1].tid else ios()
        else:
            for idx, imeta in enumerate(imetas):
                imeta.instid = idx
                imeta.after = ios()


        def handle_conflict(prev, cur, loop_count):
            if loop_count == 1:
                prev, cur = cur, prev

            imetas[prev].after.add(len(imetas) - 1 - cur if loop_count == 1 else cur)

      
        for loop_count in range(0, 2):
            last_write = [-1] * (ssize + 1)
            for idx, imeta in enumerate(imetas):
                slot = work_slot_of(imeta.tid, conc_threads)
                for register in imeta.registers(ss):
                    if register.is_mem():
                        # This is not safe in general, but works for our problem
                        # We assume no pointer aliasing at all and a few such assumptions
                        continue

                    for loc in register.range(ss, slot).values():
                        # This makes serious assumptions about how memory is accessed. It is NOT general purpose
                        if last_write[loc] >= 0:
                            handle_conflict(last_write[loc], idx, loop_count)

                for register in imeta.registers(ss):
                    if not register.is_read:
                        for loc in register.range(ss, slot).values():
                            last_write[loc] = idx

            imetas.reverse()


        return GreedyWorkPacker(imetas, self.num_threads, conc_threads, ss)


def work_slot_of(tid, conc_threads):
    return tid % conc_threads


def data_map(imeta:InstrMeta):
    text = imeta.compact_str()
    engine = imeta.lin.engine
    instr = imeta.lin.inst[0]
    if engine == EX_ALU:
        return DataInfo(hover=text, color="magenta", label="A")
    if engine == EX_VALU:
        return DataInfo(hover=text, color="green", label="V")
    if engine == EX_LOAD:
        return DataInfo(hover=text, color="blue", label="L")
    if engine == EX_STORE:
        return DataInfo(hover=text, color="purple", label="S")
    if engine == EX_FLOW:
        if instr == "vselect":
            return DataInfo(hover=text, color="red", label="F")
        else:
            return DataInfo(hover=text, color="orange", label="I")

    raise Exception("haha")

# Packs work by taking any schedulable instructions in the following manner:
# If VALU slots are available, schedule it
# If ALU slots are available, split any VALU work to schedule here
# Otherwise, just pack as many as you can
class GreedyWorkPacker:
    def __init__(self, imetas: list[InstrMeta], num_threads:int, conc_threads: int, ss: ScratchSpace):
        self.imetas = imetas
        self.ss = ss
        self.num_threads = num_threads
        self.conc_threads = conc_threads

        self.incount: list[int] = [0] * len(self.imetas)
        self.frontier: list[InstrMeta] = []  # All issuable instructions
        self.free: MinHeap[InstrMeta] = MinHeap()      # All issuable instructions with tids < self.next_batch_tid
        self.next_batch_tid = self.conc_threads # Enable the first batch of conc_threads AND global thread

        self.cycle_number = 0
        self.__initialize()


    def __initialize(self):
        imetas = self.imetas
        for imeta in imetas:
            for idx in imeta.after:
                self.incount[idx] = self.incount[idx] + 1

        for idx in range(0, len(imetas)):
            if self.incount[idx] == 0:
                (self.free if imetas[idx].tid < self.next_batch_tid else self.frontier).append(imetas[idx])

        self.__initialize_display()
    

    def __initialize_display(self):
        imetas = self.imetas
        conc_threads = self.conc_threads
        self.display = Display(
            N          = conc_threads + 1, 
            S          = len(imetas),
        )


    def __fall_down_to_free(self):
        # This can be a HashSet and avoid copy
        for imeta in self.frontier[:]:
            if imeta.tid < self.next_batch_tid:
                self.free.append(imeta)
                self.frontier.remove(imeta)


    def __retire(self, imeta):
        imetas = self.imetas
        self.free.remove(imeta)
        for idx in imeta.after:
            self.incount[idx] = self.incount[idx] - 1
            if self.incount[idx] == 0:
                (self.free if imetas[idx].tid < self.next_batch_tid else self.frontier).append(imetas[idx])


    def __to_serialized(self, linst: LogicalInstruction, slot:int) -> SerializedInstruction:
        engine, inst = linst.engine, linst.inst
#         print(f"Serializing {inst} in engine {engine}")
        ilist = list(inst)
        for idx in range(0, len(ilist)):
            cur = ilist[idx]
            match cur:
                case LogicalRegister(name=name, offset=offset) as reg:
                    ilist[idx] = reg.addr_of(self.ss, slot)
                case ArrayOp() as aop:
                    ilist[idx] = aop.addr_of(self.ss)
        return (engine, tuple(ilist))


    def __obtain_for_engine(self, engine, slots) -> list[SerializedInstruction]:
        to_retire = []
        ret = []
        rem_slots = slots
        for imeta in self.free:
            if rem_slots > 0 and imeta.lin.engine == engine:
                rem_slots = rem_slots - 1
                ret.append(self.__to_serialized(imeta.lin, work_slot_of(imeta.tid, self.conc_threads)))
                to_retire.append(imeta)

        return (ret, to_retire)


    def __split_one_free_valu_to_alu(self, imeta):
        regs = imeta.registers(self.ss)
        assert len(regs) == 3, f"Length of valu instruction expected to be 3. Was {len(regs)} from {imeta}"
        for i in range(0, 3):
            assert regs[i].offset == 0

        nmetas = [InstrMeta(
                    instid = imeta.instid
                    , lin = LI(EX_ALU , (imeta.lin.inst[0]
                                   , regs[0].scalar_at_offset(i)
                                   , regs[1].scalar_at_offset(i)
                                   , regs[2].scalar_at_offset(i)))
                    , tid = imeta.tid
                    , instid_in_thread = imeta.instid_in_thread
                    , after = imeta.after) for i in range(0, VLEN)]

        for idx in imeta.after:
            self.incount[idx] += (VLEN - 1)
        self.free.remove(imeta)
        self.free.extend(nmetas)


    def __split_one_free_multiply_add(self, imeta):
        regs = imeta.registers(self.ss)
        assert imeta.lin.inst[0] == "multiply_add"
        assert len(regs) == 4
        for i in range(0, 4):
            assert regs[i].offset == 0

        dest,a,b,c = regs[0], regs[1], regs[2], regs[3]
        # dest = a*b + c

        if dest.overlaps(c, self.ss, work_slot_of(imeta.tid, self.conc_threads)):
            return False

        clen = len(self.imetas)

        # dest = a * b
        first =  [InstrMeta(
                    instid = imeta.instid
                    , lin = LI(EX_ALU , ('*'
                                   , dest.scalar_at_offset(i)
                                   , a.scalar_at_offset(i)
                                   , b.scalar_at_offset(i)))
                    , tid = imeta.tid
                    , instid_in_thread = imeta.instid_in_thread
                    , after = MinHeap([clen + i])) for i in range(0, VLEN)]

        # dest = dest + c
        second =  [InstrMeta(
                    instid = clen + i
                    , lin = LI(EX_ALU , ('+'
                                   , dest.scalar_at_offset(i)
                                   , dest.scalar_at_offset(i)
                                   , c.scalar_at_offset(i)))
                    , tid = imeta.tid
                    , instid_in_thread = imeta.instid_in_thread
                    , after = imeta.after) for i in range(0, VLEN)]

        assert len(second) == VLEN

        self.imetas.extend(second)
        self.incount.extend([0] * VLEN)
        for idx in range(clen, len(self.imetas)):
            self.incount[idx] = 1

        for idx in imeta.after:
            self.incount[idx] += (VLEN - 1)
        self.free.remove(imeta)
        self.free.extend(first)
        return False


    def __split_one_free_broadcast(self, imeta):
        regs = imeta.registers(self.ss)
        assert imeta.lin.inst[0] == "vbroadcast"
        assert len(regs) == 2

        dest,src = regs[0], regs[1]

        if dest.overlaps(src, self.ss, work_slot_of(imeta.tid, self.conc_threads)):
            return False

        nmetas =  [InstrMeta(
                    instid = imeta.instid
                    , lin = LI(EX_ALU , ('|'
                                   , dest.scalar_at_offset(i)
                                   , src
                                   , src))
                    , tid = imeta.tid
                    , instid_in_thread = imeta.instid_in_thread
                    , after = imeta.after) for i in range(0, VLEN)]

        for idx in imeta.after:
            self.incount[idx] += (VLEN - 1)
        self.free.remove(imeta)
        self.free.extend(nmetas)
        return True


    def __split_valu_into_alu(self, alu_slots, already_taken_imetas):
        to_split = (alu_slots + VLEN - 1) // VLEN

        so_far = 0
        mul_adds = []
        broadcasts = []
        for imeta in self.free:
            if so_far >= to_split:
                break

            if not (imeta.lin.engine == EX_VALU):
                continue

            if imeta in already_taken_imetas:
                continue

            # Split non multiply-adds preferentially
            opcode = imeta.lin.inst[0]
            if opcode == "multiply_add":
                mul_adds.append(imeta)
                continue
            elif opcode == "vbroadcast":
                broadcasts.append(imeta)
                continue
            elif len(imeta.lin.inst[0]) > 5:
                # Only support +, -, ... arithmetic operators for splitting
                # Can't split vbroadcast
                continue
            else:
                self.__split_one_free_valu_to_alu(imeta)
                so_far += 1

        for imeta in broadcasts:
            if so_far >= to_split:
                break
            if self.__split_one_free_broadcast(imeta):
                so_far += 1

        for imeta in mul_adds:
            if so_far >= to_split:
                break
            if self.__split_one_free_multiply_add(imeta):
                so_far += 1


    def __split_one_vector_imm_add(self, imeta):
        regs = imeta.registers(self.ss)
        assert len(regs) == 3, f"Length of valu instruction expected to be 3. Was {len(regs)} from {imeta}"
        for i in range(0, 3):
            assert regs[i].is_vector
            # TODO
            if isinstance(regs[i], ArrayOp):
                return
        assert regs[2].is_vector_constant(self.ss), f"Expected imeta to be <vector register+ constant>.\nimeta = {imeta}"
        

        nmetas = [InstrMeta(
                    instid = imeta.instid
                    , lin = LI(EX_FLOW 
                               , ("add_imm"
                                   , regs[0].scalar_at_offset(i)
                                   , regs[1].scalar_at_offset(i)
                                   , regs[2].constant_value(self.ss)))
                    , tid = imeta.tid
                    , instid_in_thread = imeta.instid_in_thread
                    , after = imeta.after) for i in range(0, VLEN)]

#         print("Converting vector imm add", f"imeta = {imeta}", f"nmetas = {len(nmetas)}")
#         print(*["Converted" + nmeta.compact_str() for nmeta in nmetas], sep='\n')

        for idx in imeta.after:
            self.incount[idx] += (VLEN - 1)
        self.free.remove(imeta)
        self.free.extend(nmetas)


    def __convert_one_scalar_imm_add(self, imeta):
        regs = imeta.registers(self.ss)
        assert len(regs) == 3, f"Length of valu instruction expected to be 3. Was {len(regs)} from {imeta}"
        for i in range(0, 3):
            assert not regs[i].is_vector
        assert regs[2].is_scalar_constant(self.ss), f"Expected imeta to be <scalar register + constant>.\nimeta = {imeta}"


        nmeta = InstrMeta(
                    instid = imeta.instid
                    , lin = LI(EX_FLOW 
                               , ("add_imm"
                                   , regs[0]
                                   , regs[1]
                                   , regs[2].constant_value(self.ss)))
                    , tid = imeta.tid
                    , instid_in_thread = imeta.instid_in_thread
                    , after = imeta.after)

#         print("Converting scalar imm add", f"imeta = {imeta}", f"nmeta = {nmeta}", sep='\n')
        # Note: since nmeta.after == imeta.after and there's only one nmeta, self.incount is unchanged
        self.free.remove(imeta)
        self.free.append(nmeta)



    def __split_add_into_imm(self, flow_slots, already_taken_imetas):
        to_split = (flow_slots + VLEN - 1) // VLEN

        so_far = 0
        for imeta in self.free:
            if so_far >= to_split:
                break

            if imeta in already_taken_imetas:
                continue

            if imeta.is_vector_imm_add(self.ss):
                self.__split_one_vector_imm_add(imeta)
                so_far += 1
                continue

            if imeta.is_scalar_imm_add(self.ss):
                self.__convert_one_scalar_imm_add(imeta)
                so_far += 1
                continue


    def __update_status(self, retired, to_print):
        graphic_update = defaultdict(list)
        summary = defaultdict(int)
        summary[EX_LOAD] = 0
        for dmeta in retired:
            graphic_update[-1 if dmeta.tid == -1 else work_slot_of(dmeta.tid, self.conc_threads)].append(dmeta)
            summary[dmeta.lin.engine] += 1
        self.display.update(graphic_update
                            , summary = str({k:v for k, v in sorted(summary.items())}) + "\n" + ("FINE" if summary.get('valu', 0) == 6 else "UNSATURATED")
                            , datainfos = {k : data_map(k) for k in retired})
        if not to_print:
            return

        def of_engine(engine, R):
            return len([x for x in R if x.lin.engine == engine])

        print(f"------------------------ CYCLE NUMBER {self.cycle_number} -----------------")
        print(*[x.compact_str() for x in retired], sep='\n')
        print()
        print(f"Retired {len(retired)}, Free {len(self.free)}")
        print()
        for engine in EX_UNITS:
            print(f"{engine:>10}: {of_engine(engine, retired):>10} {of_engine(engine, self.free):>10}")
        print()
        print("-" * 200)


    def print(self):
        print('-'*200)
        print(f'ALL INSTRUCTIONS BELOW, {len([x for x in self.imetas if x.tid < 1])}')
        print(*[x.compact_str() for x in self.imetas if x.tid < 1], sep='\n')
        print("\n")
        print(*[x.compact_str() for x in self.imetas if x.tid == self.num_threads - 1], sep='\n')


    def have_more(self):
        if len(self.free) > 0:
            return True

        if len(self.frontier) > 0:
            self.next_batch_tid = self.next_batch_tid + self.conc_threads
            self.__fall_down_to_free()
            return len(self.free) > 0

        self.display.render()
        return False


    def take(self) -> dict[str, list[SerializedInstruction]]:
        self.cycle_number += 1
        to_retire = []
        insts = {k:[] for k in EX_UNITS}
        for engine in EX_UNITS:
            full_slots = SLOT_LIMITS[engine]
            cur, done = self.__obtain_for_engine(engine, full_slots)
            rem_slots = full_slots - len(cur)

            if engine == EX_ALU and rem_slots > 0:
                self.__split_valu_into_alu(rem_slots, to_retire)
                cur, done = self.__obtain_for_engine(engine, SLOT_LIMITS[engine])

            if engine == EX_FLOW and rem_slots > 0:
                self.__split_add_into_imm(rem_slots, to_retire)
                cur, done = self.__obtain_for_engine(engine, SLOT_LIMITS[engine])

            insts[engine].extend([x[1] for x in cur])
            to_retire.extend(done)

        for dmeta in to_retire:
            self.__retire(dmeta)

        self.__update_status(to_retire, to_print=False)

        return insts
        

