import dis
from collections import namedtuple

from . import ops


class InvalidInstruction(Exception):
    pass


class NotOnStackException(Exception):
    pass


class CFG:
    def __init__(self, code):
        bytecode = dis.Bytecode(code)
        self.basic_blocks = {}
        self._blockstack = BlockStack()

        def predecessors_of(current_bb):
            for bb in self.basic_blocks.values():
                if current_bb.offset in bb.successors:
                    yield bb

        def join_blockstack_views(current_bb):
            blocks = set()

            for bb in predecessors_of(current_bb):
                try:
                    view = bb.blockstack_view.pop_until(current_bb)
                except NotOnStackException:
                    view = bb.blockstack_view

                blocks.add(view.last_block)

            assert len(blocks) <= 1, \
                (blocks, current_bb, list(predecessors_of(current_bb)))

            if blocks:
                last_block = blocks.pop()
            else:
                last_block = None

            return BlockStackView(self._blockstack, last_block)

        for instr in bytecode:
            bb = BasicBlock(instr)
            self.basic_blocks[bb.offset] = bb

            successors, blockstack_view = compute_jump_targets(
                instr,
                join_blockstack_views(bb)
            )

            bb.successors = successors
            bb.blockstack_view = blockstack_view

    def __iter__(self):
        return iter(self.basic_blocks.values())

    def __getitem__(self, key):
        return self.basic_blocks[key]

    def __contains__(self, key):
        return key in self.basic_blocks


class BlockStackView:
    def __init__(self, blockstack, last_block=None):
        self.blockstack = blockstack
        self.last_block = last_block

    def __getitem__(self, index):
        if not index >= 0:
            raise ValueError("Index in blockstack must be >= 0. Top of stack is 0.")

        for i, block in enumerate(self):
            if i == index:
                return block

        raise IndexError

    def __iter__(self):
        block = self.last_block

        while block is not None:
            yield block
            block = block.parent

    def pop(self):
        return BlockStackView(self.blockstack, self.last_block.parent)

    def pop_until(self, bb):
        """
        Jumping to an exception handler or to a finally block means we have to
        pop all blocks on the stack that are above that handler.
        """

        block = self.last_block
        while block is not None and block.next_offset != bb.offset:
            block = block.parent

        if block is None:
            raise NotOnStackException()

        return BlockStackView(self.blockstack, block)

    def push(self, creator, next_offset):
        new_block = Block(creator, next_offset, self.last_block)
        self.blockstack.add(new_block)

        return BlockStackView(self.blockstack, new_block)

    def __str__(self):
        return "Last block: {}".format(str(self.last_block))

    __repr__ = __str__


class BasicBlock:
    def __init__(self, instruction, blockstack_view=None, successors=None):
        self.instruction = instruction
        self.offset = instruction.offset
        self.blockstack_view = blockstack_view
        self.successors = successors or []

    def __str__(self):
        return "{i.opname}:{i.offset} [{i.arg} ({i.argval})]".format(i=self.instruction)

    __repr__ = __str__


class Block(namedtuple('Block', 'creator next_offset parent')):
    pass


class BlockStack:
    def __init__(self):
        self.blocks = []

    def add(self, block):
        self.blocks.append(block)


def exceptional_jump_targets(offset, blockstack_view):
    try:
        inner_block = blockstack_view[0]
    except IndexError:
        return []
    else:
        # There are all instructions which tell us where to jump in case
        # of an exception. The EXCEPT/FINALLY ops give the offsets of
        # the respective handlers, and the WITH gives the cleanup
        # instruction offstes.
        exception_handling_ops = {
            'SETUP_EXCEPT',
            'SETUP_FINALLY',
            'SETUP_WITH',
        }
        if inner_block.creator in exception_handling_ops:
            handler_offset = inner_block.next_offset

            if offset < handler_offset:
                # we're not in the handler itself, so we have to jump to
                # jump to it
                return [handler_offset]
            else:
                # we're in a handler, so we either jump to the finally
                # block (if it exists and we're in an except block), or
                # we jump to the handler one level up. Both cases mean
                # looking at the next block on the blockstack.
                return exceptional_jump_targets(offset, blockstack_view.pop())

        elif inner_block.creator == 'SETUP_LOOP':
            # we jump to the first handler we find, which just means we
            # have to look at the next level up
            return exceptional_jump_targets(offset, blockstack_view.pop())


def compute_jump_targets(instr, blockstack_view):
    opname = instr.opname
    offset = instr.offset
    next_offset = instr.offset + 2

    new_view = blockstack_view

    if opname in ops.boring_opnames:
        targets = exceptional_jump_targets(offset, blockstack_view)
        targets.append(next_offset)

    elif opname in {'JUMP_FORWARD', 'JUMP_ABSOLUTE'}:
        targets = [instr.argval]

    elif opname in {'POP_JUMP_IF_TRUE', 'POP_JUMP_IF_FALSE',
                    'JUMP_IF_TRUE_OR_POP', 'JUMP_IF_FALSE_OR_POP',
                    'FOR_ITER'}:
        targets = [next_offset, instr.argval]

    elif opname in {'WITH_CLEANUP_START', 'WITH_CLEANUP_FINISH'}:
        targets = [next_offset]

    elif opname == 'POP_EXCEPT':
        targets = [next_offset]
        new_view = blockstack_view.pop()

    elif opname == 'BREAK_LOOP':
        inner_block = blockstack_view[0]

        if inner_block.creator == 'SETUP_LOOP':
            # NOTE: the offset the break will jump to should be right after
            # a POP_BLOCK, so we'll just pop the block here
            new_view = blockstack_view.pop()
            targets = [inner_block.next_offset]
        else:
            # we're inside some other block within this for loop (maybe a
            # with / try block), so we need to jump to those handlers before
            # exiting the loop
            # TODO: will there always be a POP_BLOCK instruction that will
            # remove the loop block, or does the BREAK_LOOP instruction do
            # that?
            targets = exceptional_jump_targets(offset, blockstack_view)

    elif opname == 'POP_BLOCK':
        inner_block = blockstack_view[0]

        if inner_block.creator not in {'SETUP_WITH', 'SETUP_FINALLY'}:
            # both these instruction create blocks which end with END_FINALLY,
            # and we'll let that one pop the block
            new_view = blockstack_view.pop()

        targets = [next_offset]

    elif opname == 'CONTINUE_LOOP':
        inner_block = blockstack_view[0]

        if inner_block.creator == 'SETUP_LOOP':
            targets = [instr.argval]
        else:
            # we're inside some other block within this for loop (maybe a
            # with / try block), so we need to jump to those handlers first
            targets = exceptional_jump_targets(offset, blockstack_view)

    elif opname == 'RETURN_VALUE':
        # we first try to jump to the innermost finally block, or else we
        # exit the function
        targets = []

        for block in blockstack_view:
            if block.creator == 'SETUP_FINALLY':
                targets = [block.next_offset]
                break

        new_view = blockstack_view

    elif opname in {'SETUP_FINALLY', 'SETUP_EXCEPT', 'SETUP_LOOP',
                    'SETUP_WITH'}:
        targets = [next_offset]
        new_view = blockstack_view.push(opname, instr.argval)

    elif opname == 'END_FINALLY':
        # TODO check how we got here. If we got here because of a BREAK_LOOP,
        # we'll want to jump to the end of the loop, not just the next offset
        targets = [next_offset] + exceptional_jump_targets(offset, blockstack_view)
        new_view = blockstack_view.pop()

    else:
        raise ValueError("Unhandled instruction: %r" % instr)

    return targets, new_view
