This is a simple language for writing programs against the VLIW machine of this problem.
The grammar is specified in the `prompt.txt` which Gemini turns into a useful parser, `parser.py`

Variables are declared with types
- `register f1, f2` denotes two single word variables f1 and f2
- `register[] f1, f2` denotes two variables each of VLEN length (in words).
- `thread register f1` denotes a threadlocal variable named f1

Statements
- Assignment (see below)
- "end global"

Semantics
- Programs start by executing a single therad until "end global" is ecnountered. Thereafter, threads are spawned and each thread continues independently to completion
- Each thread is an independent stream of work.
- Threads can use an implicit variable `tidx`, set to a unique value between [0, numThreads) for each thread
- Variables are typed `register` or `register[]` and their scope (threadlocal or global) is identified with the presence or absence of the keyword `thread` in front of the type.
- Variable types cannot be changed
- Variable types get promoted as required (see Assignment statement)

Assignment Statement
- There's only one type of statement: `variable = computation`
- This can be combined with type declaration like `register variable = computation`
- The basic structure is `variable = computation` where variable can be typed `register` or `register[]`
- The LHS determines the type that RHS variables get promoted to (if required)
- Computation is basic and strictly limited to operations between primtives (i.e. variables and constants)
- LHS determines the type being written: memory, register whether word/word[]. The RHS gets promoted as required. '@' indicates memory.
