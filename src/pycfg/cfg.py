import dis
import functools
from collections import namedtuple

from . import ops


class InvalidInstruction(Exception):
    pass


def _is_boring(instr):
    return instr.opname in ops.boring_opnames


class CFG:
    def __init__(self, code):
        bytecode = dis.Bytecode(code)
        self.basic_blocks = {}

        ctx = Context(bytecode)

        for instr in bytecode:
            bb = BasicBlock([instr])
            self.basic_blocks[instr.offset] = bb

            if _is_boring(instr):
                # TODO: depend on the type of block we're in, we might also need
                # to add the finally/except/WITH_CLEANUP_FINISH instructions as
                # successors
                bb.successors.append(instr.offset + 2)

            elif instr.opname == 'BREAK_LOOP':
                jump_target = ctx.break_loop()

                bb.successors.append(jump_target)

            # Unconditional jumps
            elif instr.opname in {'JUMP_FORWARD', 'JUMP_ABSOLUTE'}:
                bb.successors.append(instr.argval)

            # Conditional jumps
            elif instr.opname in {'POP_JUMP_IF_TRUE', 'POP_JUMP_IF_FALSE',
                                  'JUMP_IF_TRUE_OR_POP', 'JUMP_IF_FALSE_OR_POP',
                                  'FOR_ITER'}:
                bb.successors.append(instr.offset + 2)
                bb.successors.append(instr.argval)

            elif instr.opname == 'POP_BLOCK':
                ctx.pop_block()
                bb.successors.append(instr.offset + 2)

            elif instr.opname == 'CONTINUE_LOOP':
                bb.successors.append(instr.argval)

            elif instr.opname == 'RETURN_VALUE':
                # TODO: a return within a finally will always execute instead of
                # the return anywhere else, so it's not always accurate to say
                # that a return is always a leaf in the CFG
                bb.successors = None

            elif instr.opname == 'SETUP_FINALLY':
                ctx.setup_finally(instr)
                bb.successors.append(instr.offset + 2)

            elif instr.opname == 'SETUP_EXCEPT':
                ctx.setup_except(instr)
                bb.successors.append(instr.offset + 2)

            elif instr.opname == 'SETUP_LOOP':
                ctx.setup_loop(instr)
                bb.successors.append(instr.offset + 2)

            elif instr.opname == 'SETUP_WITH':
                ctx.setup_with(instr)
                bb.successors.append(instr.offset + 2)

            elif instr.opname == 'WITH_CLEANUP_START':
                bb.successors.append(instr.offset + 2)

            elif instr.opname == 'WITH_CLEANUP_FINISH':
                bb.successors.append(instr.offset + 2)

            else:
                raise ValueError("Unhandled instruction: %r" % instr)

    def __iter__(self):
        return iter(self.basic_blocks.values())

    def __getitem__(self, key):
        return self.basic_blocks[key]

    def __contains__(self, key):
        return key in self.basic_blocks


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


class Block(namedtuple('Block', 'originator next_offset')):
    pass


def assert_blockstack(f):
    @functools.wraps(f)
    def wrapped(self, *args, **kwargs):
        if not self.blockstack:
            raise InvalidInstruction()

        return f(self, *args, **kwargs)

    return wrapped


def check_instr(opname):
    def decorator(f):
        @functools.wraps(f)
        def wrapped(self, instr, *args, **kwargs):
            if instr.opname != opname:
                raise ValueError(
                    "Wrong instruction type. Expected '%s'. Found '%s'" % (opname, instr.opname)
                )

            return f(self, instr, *args, **kwargs)
        return wrapped
    return decorator


class Context:
    def __init__(self, bytecode):
        self.bytecode = bytecode

        self.blockstack = []

    def _new_block(self, instr):
        block = Block(instr, instr.argval)
        self.blockstack.append(block)

    @assert_blockstack
    def break_loop(self):
        # NOTE: the offset the break will jump to should be right after a
        # POP_BLOCK, so we'll just pop the block here
        inner_block = self.blockstack.pop()
        return inner_block.next_offset

    @assert_blockstack
    def pop_block(self):
        inner_block = self.blockstack[-1]

        if inner_block.originator.opname == 'SETUP_WITH':
            # with blocks will have a END_FINALLY instruction after the cleanup
            # instructions, and we should let that one pop the block instead,
            # since exceptions within the `with` block may cause this POP_BLOCK
            # to not execute
            return

        self.block_stack.pop()

    @check_instr('SETUP_LOOP')
    def setup_loop(self, instr):
        self._new_block(instr)

    @check_instr('SETUP_FINALLY')
    def setup_finally(self, instr):
        self._new_block(instr)

    @check_instr('SETUP_EXCEPT')
    def setup_except(self, instr):
        self._new_block(instr)

    @check_instr('SETUP_WITH')
    def setup_with(self, instr):
        self._new_block(instr)
