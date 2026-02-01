from dataclasses import dataclass, field
from problem import SCRATCH_SIZE, VLEN

class InsufficientRegisterCountException(Exception):
    def __init__(self, message="Not enough registers to run the given number of threads simultaneously"):
        self.message = message
        super().__init__(self.message) # Call the base class constructor
    
    def __str__(self):
        return f'InsufficientRegisterCountException: {self.message}' 

@dataclass
class VariableMeta:
    name: str
    addr: int
    is_vector:bool
    length : int
    slots: int
    is_constant: bool = False
    constant_value: int = -123 # Applies only when is_constant

    def addr_of(self, slot_num: int) -> int:
        if self.slots == 1:
            return self.addr

        assert 0 <= slot_num and slot_num < self.slots, f"{slot_num} outside of [0, {self.slots}) for variable {self.name}."
        return self.addr + slot_num * self.length


    def size(self):
        return self.slots * self.length 
        

    def is_constant(self):
        return self.is_constant

class ScratchSpace:
    def __init__(self):
        self.scratch = {}
        self.var_meta = {} # name -> VariableMeta
        self.scratch_ptr = 0
        self.const_map = {} # (val, is_vector) to VariableMeta
        self.scratch_debug = {}

    def alloc_scratch(self, name, length, slots:int):
        addr = self.scratch_ptr
        assert name not in self.scratch, f"Duplicate scratch allocation request for {name}"

        self.scratch[name] = addr
        varmeta = VariableMeta(name, addr, length > 1, length, slots)
        varmeta.is_constant = False
        varmeta.constant_value = -123
        self.var_meta[name] = varmeta
        self.scratch_debug[addr] = (name, slots * length)
        self.scratch_ptr += length * slots

        if self.scratch_ptr > SCRATCH_SIZE:
            raise InsufficientRegisterCountException("Out of scratch space")

        return addr, varmeta

    def alloc_word(self, name, slots:int):
        return self.alloc_scratch(name, 1, slots)

    def alloc_wide_word(self, name, slots:int):
        return self.alloc_scratch(name, VLEN, slots)

    # All constants get allocated a unique name and you can use that as required
    def alloc_const(self, val, is_vector):
        key = (val, is_vector)
        if key not in self.const_map:
            cname = ("_KV_" if is_vector else "_K_") + str(val)
            length = VLEN if is_vector else 1
            addr, varmeta = self.alloc_scratch(cname, length, 1)
            varmeta.is_constant = True
            varmeta.constant_value = val
            assert varmeta == self.var_meta[cname]
            self.const_map[key] = varmeta
            return (addr, cname, True)

        v = self.const_map[key]
        return (v.addr, v.name, False)


    def var_meta_of(self, name):
        return self.var_meta[name]


    def constant_name(self, name, *, is_vector):
        key = (name, is_vector)
        assert key in self.const_map
        vm = self.const_map[key]
        return vm.name


    def has_variable(self, name):
        ret = name in self.var_meta
        return name in self.var_meta


    def size(self):
      return self.scratch_ptr


    def per_thread_space(self):
        var_meta = self.var_meta
        return sum([vm.length for vm in var_meta.values() if vm.slots > 1])


    def globals_space(self):
        var_meta = self.var_meta
        return sum([vm.length for vm in var_meta.values() if vm.slots == 1])


    def free_space(self):
        return SCRATCH_SIZE - self.size()


    def print(self):
        line = '-' * 200    
        print(line)
        print("Scratch space bariables")
        print(line)

        for _, var_meta in self.var_meta.items():
            print(f"{var_meta.addr:15}   {var_meta.name:15} {var_meta.length:10} {var_meta.slots: 8}")
        print(line)

        var_meta = self.var_meta
        conc_threads = max([vm.slots for vm in var_meta.values()])
        per_thread_space = self.per_thread_space()
        global_space = self.globals_space()
        free_space = self.free_space()
        print("----------------Scratch Space Stats For Nerds-------------")
        print(f"Concurrent threads  = {conc_threads}")
        print(f"Per thread space    = {per_thread_space}")
        print(f"Globals space       = {global_space}")
        print(f"Used space          = {self.scratch_ptr}")
        print(f"Free space          = {free_space}")
        print('-' * 100)

