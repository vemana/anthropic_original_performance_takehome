from problem import SCRATCH_SIZE, VLEN

from parser import (
        program as parser,
        AssignmentStmt,
        BinOpExpr,
        CondExpr,
        DerefConstant,
        DerefIndividualWords,
        DerefVariable,
        EndGlobalStmt,
        GlobalProgram,
        GlobalStmt,
        IntConstantExpr,
        StoreMemory,
        LoadVariable,
        MultAddExpr,
        NumberString,
        NumberStringHex,
        Program,
        PauseStmt,
        SelectExpr,
        ThreadLocalProgram,
        ThreadLocalStmt,
        ThreadLocalVariableStmt,
        ValueExpr,
        Variable,
        VariableDefinition,
        VariableDeclaration,
        VariableDeclarationStmt,
        )

from scratch import ScratchSpace
from instr_graph_model import InstrGraph
from instr_graph_model import (
        EX_UNITS, EX_VALU, EX_ALU, EX_LOAD, EX_STORE, EX_FLOW, 
        Work, SerializedInstruction, LogicalRegister as LR,
        LogicalInstruction as LI,
        )

def estimate_max_conc_threads(program: Program, num_threads: int) -> Program:
    try:
        # Try with 2 concurrent threads
        ss = __program_to_irp(program, num_threads, 2).ss
    except InsufficientRegisterCountException as ex:
        # 1 concurrent thread is the best we can do
        return __program_to_work(program, num_threads, 1)
    
    max_conc_threads = 2 + ss.free_space() // ss.per_thread_space()
    return max_conc_threads


def program_to_work(program: Program, num_threads: int, conc_threads: int):
    irp = __program_to_irp(program, num_threads, conc_threads)
    return (irp.work(), irp.ss)
    

def __program_to_irp(program: Program, num_threads: int, conc_threads: int) -> Program:
    is_global = False
    irp = IRPipeline(num_threads, conc_threads)

    def variable_decl_stmt_handler(vds: VariableDeclarationStmt):
        match vds:
            case VariableDeclaration() as vd:
                irp.handle_variable_declaration(vd, is_global)
            case VariableDefinition() as va:
                irp.handle_variable_definition(va, is_global)

    for stmts in [program.global_prog.stmts, program.thread_prog.stmts]:
        is_global = not is_global
        for stmt in stmts:
            match stmt:
                case VariableDeclarationStmt() as vds:
                    variable_decl_stmt_handler(vds)
                case ThreadLocalVariableStmt(decl = vds):
                    variable_decl_stmt_handler(vds)
                case AssignmentStmt() as ast:
                    match ast:
                        case LoadVariable() as lv:
                            irp.handle_load_variable(lv, is_global)
                        case StoreMemory() as sm:
                            irp.handle_store_memory(sm, is_global)
                case PauseStmt() as  pst:
                    irp.handle_pause_stmt(pst, is_global)
    
    return irp


def to_int(intconst: IntConstantExpr):
    match intconst:
        case NumberString(value = s):
            v = int(s)
        case NumberStringHex(value = s):
            v = int(s, 16)
    return v



class IRPipeline:
    # num_threads = total number of threads
    # conc_threads = concurrent number of threads (due to scratch memory size limitations)
    def __init__(self, num_threads: int, conc_threads: int):
        self.num_threads = num_threads
        self.conc_threads = conc_threads
        self.ss = ScratchSpace()
        self.graph = InstrGraph(self.ss, num_threads)


    def __add(self, is_global:bool, linstr):
        # linstr can be in (engine, (inst...)) format
        # or a real LogicalInstruction instance
        if isinstance(linstr, tuple):
            linstr = LI(linstr[0], linstr[1])
        self.graph.add(linstr, is_global)


    def __register_variable(self, name, var_type, num_slots: int):
        is_vector = var_type == "register[]"
        return self.ss.alloc_wide_word(name, num_slots) if is_vector else self.ss.alloc_word(name, num_slots)


    def __handle_const(self, v, is_vector):
        addr, cname, first_time = self.ss.alloc_const(v, is_vector)
        instrs = []
        readSingle  = LR(name = cname, offset = 0, is_vector = False, is_read = True)
        writeSingle = LR(name= cname, offset = 0, is_vector = False, is_read = False)
        writeVec    = LR(name= cname, offset = 0, is_vector = True, is_read = False)

        if first_time:                            
            setup_instr_1 = (EX_LOAD, ("const", writeSingle, v))
            self.__add(True, setup_instr_1)
            if is_vector:
                setup_instr_2 = (EX_VALU, ("vbroadcast", writeVec, readSingle))
                self.__add(True, setup_instr_2)

        # Constant registers are readonly after setting up
        return LR(name=cname, offset=0, is_vector = is_vector, is_read = True)
    

    def __check_is_vector(self, lname:str, expect_vector:bool):
        var_meta = self.ss.var_meta_of(lname)
        assert var_meta.is_vector == expect_vector, f"The variable {lname} had is_vector declared {var_meta.is_vector} but required {expect_vector}"


    def __addr_of(self, original, expect_vector, scalar_within_vector=None, *, is_read):
        match original:
            case str() as s:
                self.__check_is_vector(s, expect_vector)
                return LR(name = s, offset = 0, is_vector = expect_vector, is_read = is_read)

            case Variable(name = name, index = offset) as v:
                self.__check_is_vector(name, expect_vector)
                offset = to_int(offset) if offset else 0
                return LR(name = name, offset = offset, is_vector = True if scalar_within_vector == True else expect_vector, is_read = is_read)

            case IntConstantExpr() as intconst:
                return self.__handle_const(to_int(intconst), expect_vector) 

            case _:
                raise NotImplementedError(f"Unsupported __addr_of({original})")


    def __read_variable(self, name, is_vector):
        self.__check_is_vector(name, is_vector)
        return LR(name=name, offset=0, is_vector = is_vector, is_read = True)

    def __write_variable(self, name, is_vector):
        self.__check_is_vector(name, is_vector)
        return LR(name=name, offset=0, is_vector = is_vector, is_read = False)

    def __read_scalar_within_vector(self, name, offset):
        self.__check_is_vector(name, True)
        return LR(name=name, offset=offset, is_vector=False, is_read = True)

    def __write_scalar_within_vector(self, name, offset):
        self.__check_is_vector(name, True)
        return LR(name=name, offset=offset, is_vector=False, is_read = False)
  
    def __handle_variable_assignment(self, lname:str, rvalue: ValueExpr, is_global: bool):
        is_vector = self.ss.var_meta_of(lname).is_vector
        read_variable = self.__read_variable
        write_variable = self.__write_variable
        read_scalar_within_vector = self.__read_scalar_within_vector
        write_scalar_within_vector = self.__write_scalar_within_vector

        instrs = []
        match rvalue:

            case DerefIndividualWords(name=rname):
                # lname[i] = *rname[i] for i in range(0, VLEN)
                assert is_vector and self.ss.var_meta_of(rname).is_vector, f"Both left and right should be vectors in DerefIndividualWords: {lname} = {rvalue}"
                instrs = [(EX_LOAD, ("load"
                                     , write_scalar_within_vector(lname, i)
                                     , read_scalar_within_vector(rname, i))) for i in range(0, VLEN)]

            case DerefVariable(name=rname):
                # lname = *rname
                instrs = [(EX_LOAD, ("vload" if is_vector else "load"
                                     , write_variable(lname, is_vector)
                                     , read_variable(rname, False)))]

            case DerefConstant(expr = intconst):
                # lname = *constant
                # Don't need a constant vector in this case.
                instrs = [(EX_LOAD, ("vload" if is_vector else "load"
                                     , write_variable(lname, is_vector)
                                     , self.__addr_of(intconst, False, is_read=True)))]

            case BinOpExpr(left=r1varOrConstant, op=op, right = r2varOrConstant):
                # lname = a op b
                r1 = self.__addr_of(r1varOrConstant, is_vector, is_read = True)
                r2 = self.__addr_of(r2varOrConstant, is_vector, is_read = True)
                instrs = [(EX_VALU if is_vector else EX_ALU, (op, write_variable(lname, is_vector), r1, r2))]

            case MultAddExpr(factor1 = r1name, factor2 = r2, add = r3):
                assert is_vector, f"multiply_add is only supported on vectors. Here, {lname} = {rvalue}"
                instrs = [(EX_VALU, ("multiply_add"
                                     , write_variable(lname, True)
                                     , read_variable(r1name, True)
                                     , self.__addr_of(r2, True, is_read = True)
                                     , self.__addr_of(r3, True, is_read = True)))]

            case SelectExpr(cond=cond, if_true=if_true, if_false=if_false):
                # lname = a ? b : c
                # lanme = a op x ? b : c
                assert is_vector, f"condexpr is only supported on vectors. Here, {lname} = {rvalue}"
                caddr = -1
                instrs = []

                match cond:
                    case str() as name:
                        caddr = read_variable(name, True)

                    case CondExpr(left = lvarOrConst, op = op, right = rvarOrConst):
                        l1addr = self.__addr_of(lvarOrConst, True, is_read=True)
                        r1addr = self.__addr_of(rvarOrConst, True, is_read=True)

                        error_message = f"""
                        A conditional expression like [x = a < b ? x : y] is forbidden since x is used as intermediate for a < b
                        Here, {lname} occurs on both LHS and in one of the `if` clauses
                        """
                        assert l1addr.name != lname, error_message
                        assert r1addr.name != lname, error_message
                        caddr = write_variable(lname, True)
                        instrs.append((EX_VALU, (op, caddr, l1addr, r1addr)))

                instrs.append((EX_FLOW, ("vselect"
                                         , write_variable(lname, True)
                                         , caddr
                                         , self.__addr_of(if_true, True, is_read=True)
                                         , self.__addr_of(if_false, True, is_read=True))))

            case IntConstantExpr() as intconst:
                # lname = constant
                if not is_vector:
                    instrs = [(EX_LOAD, ("const", write_variable(lname, False), to_int(intconst)))]
                else:
                    instrs = [(EX_VALU, ("vbroadcast"
                                         , write_variable(lname, True)
                                         , self.__addr_of(intconst, False)))]

            case Variable() as v:
                # lname = v[constant]
                rname = v.name
                ridx = to_int(v.index) if v.index else 0
                assert is_vector, f"Assignments like `x = y[4]` only support where x is a register[]. Here it was {lname} = {rvalue}"
                assert 0 <= ridx and ridx < VLEN, f"y[t] is invalid if t is outside [0, 8). Here, t is {ridx}, from expr {rvalue}."
                instrs = [(EX_VALU, ("vbroadcast"
                                     , write_variable(lname, True)
                                     # This is tricky because we are reading a scalar from within a vector
                                     # So, is_vector (as in whether rname is declared vector) has to be checked
                                     # But, the actual LogicalRegister should mark it as a scalar read
                                     , read_scalar_within_vector(rname, ridx)))]

            case _:
                raise NotImplementedError(f"Unsupported assignment: {lname} = {rvalue}")

        for instr in instrs:
            self.__add(is_global, instr)


    def handle_store_memory(self, sm: StoreMemory, is_global: bool):
        lname = sm.name
        match sm.value:
            case Variable(name=rname):
                # For stores, RHS determines is_vector
                is_vector = self.ss.var_meta_of(rname).is_vector
                opcode = "vstore" if is_vector else "store"
                instr = (EX_STORE, (opcode
                                    , self.__read_variable(lname, False)
                                    , self.__write_variable(rname, is_vector)))
                self.__add(is_global, instr)
            case _:
                raise NotImplementedError(f"Not supported yet: {lm}")


    def handle_load_variable(self, lv: LoadVariable, is_global: bool):
        self.__handle_variable_assignment(lv.name, lv.value, is_global)


    def handle_variable_definition(self, vd: VariableDefinition, is_global: bool):
        self.__register_variable(vd.name, vd.var_type, 1 if is_global else self.conc_threads)
        self.__handle_variable_assignment(vd.name, vd.value, is_global)


    def handle_variable_declaration(self, vd: VariableDeclaration, is_global: bool):
        all_names = [vd.name] + vd.other_names
        for name in all_names:
            self.__register_variable(name, vd.var_type, 1 if is_global else self.conc_threads)

    
    def handle_pause_stmt(self, ps: PauseStmt, is_global: bool):
        self.graph.add_pause((EX_FLOW, ("pause", )), is_global)


    def work(self):
      return self.graph.get_work(conc_threads = self.conc_threads, optimize = True)

