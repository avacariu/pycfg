import dis


_conditional_jumps = {
    'FOR_ITER',
    'JUMP_IF_FALSE_OR_OP',
    'JUMP_IF_TRUE_OR_POP',
    'POP_JUMP_IF_FALSE',
    'POP_JUMP_IF_TRUE',
}

_unconditional_jumps = {
    'JUMP_FORWARD',
    'JUMP_ABSOLUTE',
    'CONTINUE_LOOP',
}

_new_block_instructions = {
    'SETUP_LOOP',
    'SETUP_EXCEPT',
    'SETUP_FINALLY',
    'SETUP_WITH',
}

_irregular_instructions = (_conditional_jumps |
                           _unconditional_jumps |
                           _new_block_instructions)


def _is_regular(instr):
    return instr.opname not in _irregular_instructions


class CFG:
    def __init__(self, code):
        bytecode = dis.Bytecode(code)

        basic_blocks = {}

        bb = BasicBlock()

        blockstack = []

        for instr in bytecode:
            if not bb or _is_regular(instr):
                bb.instructions.append(instr)

            elif instr.opname in _new_block_instructions:
                end_block_addr = instr.argval
                blockstack.append(end_block_addr)

            elif instr.opname == 'BREAK_LOOP':
                pass

            bb.instructions.append(instr)

            if instr.opname in _conditional_jumps:
                bb.successors.append(instr.offset + 2)

            bb.successors.append(instr.argval)

            basic_blocks[bb.instructions[0].offset] = bb

            bb = BasicBlock()

        if bb:
            basic_blocks[bb.instructions[0].offset] = bb

        self.basic_blocks = basic_blocks


class BasicBlock:
    def __init__(self, instructions=None, successors=None, predecessors=None):
        self.instructions = instructions or []
        self.successors = successors or []
        self.predecessors = predecessors or []

    @property
    def is_entry(self):
        if self.predecessors:
            return False
        return True

    def __bool__(self):
        return bool(self.instructions)

    def __iter__(self):
        return iter(self.instructions)

    def __str__(self):
        def repr_inst(i):
            return "{i.opname}\t{i.arg}\t({i.argval})".format(i=i)

        return "\n".join(map(repr_inst, self.instructions))
