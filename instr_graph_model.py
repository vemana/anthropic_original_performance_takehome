from dataclasses import dataclass, field, replace
from typing import Any, Protocol
from scratch import ScratchSpace 

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
        return hi < lo

    def intersect(self, that: 'Range') -> 'Range':
        return Range(max(self.lo, that.lo), min(self.hi, that.hi))

    def values(self):
        lo = self.lo
        hi = self.hi
        if hi >= lo:
            return [x for x in range(lo, hi+1)]
        return []

SPECIAL_MEM_REGISTER_NAME = '__mem__'

# A Logical Register that is converted to address when emitting SerializedInstruction
# It is annotated with whether the usage is a read/write and scalar/vector
# for performing optimizations
@dataclass(kw_only=True) # Force key naming
class LogicalRegister:
    name: str
    offset: str
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

LR = LogicalRegister


# An instruction that is specified in terms of logical registers that can be replaced 
# at optimization time based on thread_idx
@dataclass
class LogicalInstruction:
    engine: str
    inst: tuple # Same as SerializedInstruction except that registers are Logical

LI = LogicalInstruction


class Work(Protocol):
    def have_more(self) -> bool: ...
    def take(self) -> list[SerializedInstruction]: ...


@dataclass
class InstrMeta:
    instid: int # Instruction id in the program order
    lin: LogicalInstruction
    tid: int # Thread id; = 0 if global
    after: set[int] = field(default_factory=set) # ids of instructions that this unlocks

    def registers(self, ss:ScratchSpace):
        ret = []
        lin = self.lin
        for param in lin.inst:
            if not isinstance(param, LogicalRegister):
                continue
            ret.append(param)

        # Reads and Writes to memory are treated as happening to a special register
        # since we don't know the actual memory address the read or write is happening
        # at optimization time.
        if lin.engine in [EX_LOAD, EX_STORE]:
            lr = LogicalRegister(name = SPECIAL_MEM_REGISTER_NAME
                                  , offset = 0
                                  , is_vector = False
                                  , is_read = lin.engine == EX_LOAD)
            ret.append(lr)

        return ret



class InstrGraph:
    def __init__(self, ss: ScratchSpace, num_threads:int):
        self.num_threads = num_threads
        self.ss = ss
        self.imetas: list[InstrMeta] = []
        self.tidmetas: list[InstrMeta] = [
            InstrMeta(-1, LI(EX_LOAD, ("const", LR(name="tidx", offset=0, is_vector=False, is_read=False), i)), i, []) 
            for i in range(0, self.num_threads)
            ]
        self.num_global = 0
        self.globalimetas: list[InstrMeta] = []


    def add(self, linst: LogicalInstruction, is_global):
        if is_global:
            self.globalimetas.append(InstrMeta(-1, linst, -1, []))
        else:
            self.imetas.append(InstrMeta(-1, linst, -2, []))

    
    def add_pause(self, pinst: LogicalInstruction, is_global):
        if is_global:
            self.globalimetas.append(InstrMeta(-1, pinst, -1, []))
        else:
            self.imetas.append(InstrMeta(-1, pinst, VLEN - 1, []))


    def get_work(self, *, conc_threads:int, optimize=False) -> Work:
        ss = self.ss
        ssize = ss.size()
        last_read = [-1] * (ssize + 1) # For memory register, addr = -1
        last_write = [-1] * (ssize + 1)
        imetas = []
        imetas.extend(self.globalimetas)
        assert len(self.tidmetas) == self.num_threads
        for i in range(0, self.num_threads):
            imetas.extend([self.tidmetas[i]] + [replace(x, tid=i) for x in self.imetas])
        
        # If not optimizing, assign serial work
        if not optimize:
            for idx, imeta in enumerate(imetas):
                imeta.instid = idx
                imeta.after = {idx+1} if idx + 1 < len(imetas) else set()
            return GreedyWorkPacker(imetas, conc_threads, ss)

        def handle_conflict(prev, cur):
            imetas[prev].after.add(cur)

        for idx, imeta in enumerate(imetas):
            imeta.instid = idx
            imeta.after = set()
            slot = imeta.tid % conc_threads
            for register in imeta.registers(ss):
                is_read = register.is_read
                for loc in register.range(ss, slot).values():
                    if last_write[loc] >= 0:
                        lw = last_write[loc]
                        # Assume that threads don't communicate using memory writes or else this
                        # optimization would be incorrect
                        if (not register.is_mem()) or imetas[lw].tid == imeta.tid or imetas[lw].tid < 0:
                            handle_conflict(lw, idx)

                    if (not is_read) and last_read[loc] >= 0:
                        lr = last_read[loc]
                        if (not register.is_mem()) or imetas[lw].tid == imeta.tid:
                            handle_conflict(lr, idx)

            for register in imeta.registers(ss):
                for loc in register.range(ss, slot).values():
                    (last_read if register.is_read else last_write)[loc] = idx

        return GreedyWorkPacker(imetas, conc_threads, ss)


# Packs work by taking any schedulable instructions in the following manner:
# If VALU slots are available, schedule it
# If ALU slots are available, split any VALU work to schedule here
# Otherwise, just pack as many as you can
class GreedyWorkPacker:
    def __init__(self, imetas: list[InstrMeta], conc_threads: int, ss: ScratchSpace):
        self.imetas = imetas
        self.ss = ss
        self.conc_threads = conc_threads

        self.incount: list[int] = [0] * len(self.imetas)
        self.frontier: list[InstrMeta] = []  # All issuable instructions
        self.free: list[InstrMeta] = []      # All issuable instructions with tids in  [self.next_batch_tid - conc_threads, self.next_batch_tid)
        self.next_batch_tid = 0

        self.__initialize()

    def __initialize(self):
        imetas = self.imetas
        for imeta in imetas:
            for idx in imeta.after:
                self.incount[idx] = self.incount[idx] + 1

        for idx in range(0, len(imetas)):
            if self.incount[idx] == 0:
                # It's intentional that in the beginning we don't put anything in free tier
                # This way, the cycle will unlock Global + First batch of threads
                self.frontier.append(imetas[idx])


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
            match ilist[idx]:
                case LogicalRegister(name=name, offset=offset):
                    ilist[idx] = self.ss.var_meta_of(name).addr_of(slot) + offset
        return (engine, tuple(ilist))


    def __obtain_for_engine(self, engine, slots) -> list[SerializedInstruction]:
        # Find and/or split until slots available
        to_retire = []
        ret = []
        rem_slots = slots
        for imeta in self.free:
            if rem_slots > 0 and imeta.lin.engine == engine:
                rem_slots = rem_slots - 1
                ret.append(self.__to_serialized(imeta.lin, imeta.tid % self.conc_threads))
                to_retire.append(imeta)

        return (ret, to_retire)


    def __split_valu_into_alu(self, alu_slots):
        pass


    def print(self):
        print("\n\n".join(str(x) for x in self.imetas))
        print(len(self.imetas))


    def have_more(self):
        if len(self.free) > 0:
            return True

        if len(self.frontier) > 0:
            self.next_batch_tid = self.next_batch_tid + self.conc_threads
            self.__fall_down_to_free()
            return len(self.free) > 0

        return False


    def take(self) -> dict[str, list[SerializedInstruction]]:
        to_retire = []
        insts = {k:[] for k in EX_UNITS}
        for engine in EX_UNITS:
            slots = SLOT_LIMITS[engine]
            cur, done = self.__obtain_for_engine(engine, slots)
            slots -= len(cur)
            if engine == EX_ALU and slots > 0:
                self.__split_valu_into_alu(slots)
                cur, done = self.__obtain_for_engine(engine, slots)

            insts[engine].extend([x[1] for x in cur])
            to_retire.extend(done)

        for donemeta in to_retire:
            self.__retire(donemeta)

        return insts
        

