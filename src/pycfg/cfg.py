import dis
from collections import namedtuple

from . import ops


class InvalidInstruction(Exception):
    pass


class NotOnStackException(Exception):
    pass


class EmptyBlockStackException(Exception):
    pass


class CFG:
    def __init__(self, code):

        bytecode = dis.Bytecode(code)
        self.basic_blocks = {
            -1: BasicBlock(dis.Instruction('FUNCTION_EXIT', 0, 0, '', '', -1, 0, False))
        }

        self._blockstack = BlockStack()

        # maintains the list of reachable instructions
        reachable_instructions = {0}

        # the targets of unreachable jump instructions
        unreachable_jump_targets = set()

        def is_reachable(instr):
            if instr.offset in reachable_instructions:
                return True
            elif instr.is_jump_target:
                if instr.offset in unreachable_jump_targets:
                    return False
                return True

        def predecessors_of(current_bb):
            for bb in self.basic_blocks.values():
                if current_bb.offset in bb.successors:
                    yield bb

        def join_blockstack_views(current_bb):
            blocks = set()

            for bb in predecessors_of(current_bb):
                if not is_reachable(bb.instruction):
                    continue

                try:
                    view = bb.blockstack_view.pop_until(current_bb.offset)
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

        def join_path_metadata(current_bb):
            metadata = {}
            for bb in predecessors_of(current_bb):
                if bb.path_metadata.get('has return', False):
                    metadata['has return'] = True
                if bb.path_metadata.get('has except', False):
                    metadata['has except'] = True

                broken_loops = bb.path_metadata.get('broken loops', [])
                metadata.setdefault('broken loops', []).extend(broken_loops)

            return metadata

        for instr in bytecode:

            if not is_reachable(instr):
                if instr.opname in ops.jumps:
                    unreachable_jump_targets.add(instr.argval)

                continue

            bb = BasicBlock(instr)
            self.basic_blocks[bb.offset] = bb

            # TODO: maintain path metdata (stuff like whether there's a
            # RETURN_VALUE along the path) that gets inherited like the
            # blockstack view

            successors, new_metadata, blockstack_view = compute_jump_targets(
                instr,
                join_path_metadata(bb),
                join_blockstack_views(bb),
            )

            reachable_instructions.update(set(successors))

            bb.successors = successors
            bb.blockstack_view = blockstack_view
            bb.path_metadata = new_metadata

    def to_dot(self):
        dot = "digraph cfg { node [shape=record]; "

        def repr_offset(offset):
            if offset >= 0:
                return offset
            return 'x'

        for bb in self.basic_blocks.values():
            bb_offset_repr = repr_offset(bb.offset)

            dot += f'BB{bb_offset_repr} [label="{{{{{bb.offset}|{bb.instruction.opname}}}}}"]; '

        for bb in self.basic_blocks.values():
            bb_offset_repr = repr_offset(bb.offset)

            for bb_succ in bb.successors:
                bb_succ = repr_offset(bb_succ)
                dot += f'BB{bb_offset_repr} -> BB{bb_succ}; '

        dot += "}"

        return dot

    def __iter__(self):
        return iter(self.basic_blocks.values())

    def __getitem__(self, key):
        return self.basic_blocks[key]

    def __contains__(self, key):
        return key in self.basic_blocks


class BlockStackView:
    __slots__ = ('blockstack', 'last_block')

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
        if self.last_block is None:
            raise EmptyBlockStackException("Cannot pop from empty block stack.")

        return BlockStackView(self.blockstack, self.last_block.parent)

    def pop_until(self, offset):
        block = self.last_block
        while block is not None and block.next_offset <= offset:
            block = block.parent

        # if block is None:
            # raise NotOnStackException()

        return BlockStackView(self.blockstack, block)

    def push(self, creator, next_offset):
        new_block = Block(creator, next_offset, self.last_block)
        self.blockstack.add(new_block)

        return BlockStackView(self.blockstack, new_block)

    def _first_X(self, X):
        block = self.last_block

        while block is not None and block.creator != X:
            block = block.parent

        return block

    @property
    def first_loop(self):
        return self._first_X('SETUP_LOOP')

    @property
    def first_finally(self):
        return self._first_X('SETUP_FINALLY')

    def __str__(self):
        return "Last block: {}".format(str(self.last_block))

    __repr__ = __str__


class BasicBlock:
    __slots__ = ('instruction', 'offset', 'blockstack_view', 'successors',
                 'path_metadata')

    def __init__(self, instruction, blockstack_view=None, successors=None,
                 path_metadata=None):
        self.instruction = instruction
        self.offset = instruction.offset
        self.blockstack_view = blockstack_view
        self.successors = successors or []

        self.path_metadata = path_metadata or {}

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

    def __len__(self):
        return len(self.blocks)

    def __str__(self):
        return str(self.blocks)


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


def compute_jump_targets(instr, path_metadata, blockstack_view):
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
        new_view = blockstack_view

    elif opname in {'WITH_CLEANUP_START', 'WITH_CLEANUP_FINISH'}:
        targets = [next_offset]

    elif opname == 'POP_EXCEPT':

        # inner_block = blockstack_view[0]
        # if inner_block.creator == 'SETUP_EXCEPT':
            # # both these instruction create blocks which end with END_FINALLY,
            # # and we'll let that one pop the block
            # new_view = blockstack_view.pop()
        # else:
            # raise Exception("Can't pop except when there's no except on stack")

        targets = [next_offset]

    elif opname == 'BREAK_LOOP':
        inner_block = blockstack_view[0]

        broken_loops = path_metadata.setdefault('broken loops', [])
        broken_loops.append(blockstack_view.first_loop)

        if inner_block.creator == 'SETUP_LOOP':
            new_view = blockstack_view
            targets = [inner_block.next_offset]   # past the POP_BLOCK at the end
        else:
            targets = exceptional_jump_targets(offset, blockstack_view)

    elif opname == 'POP_BLOCK':
        new_view = blockstack_view
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
            if block.creator in {'SETUP_FINALLY', 'SETUP_WITH'}:
                if instr.offset < block.next_offset:
                    targets = [block.next_offset]
                    break

        targets = targets or [-1]
        new_view = blockstack_view

        path_metadata['has return'] = True

    elif opname in {'SETUP_FINALLY', 'SETUP_EXCEPT', 'SETUP_LOOP',
                    'SETUP_WITH'}:
        targets = [next_offset]

        block_end = instr.argval
        new_view = blockstack_view.push(opname, block_end)

    elif opname == 'END_FINALLY':
        # this should propagate exceptions since an exception that is propagated
        # is indistinguishable from an which is raised from within the finally
        # block
        targets = [next_offset] + exceptional_jump_targets(offset, blockstack_view)

        finally_block_on_stack = any(filter(lambda b: b.creator in {'SETUP_FINALLY', 'SETUP_WITH'},
                                            new_view))

        if path_metadata.get('has return') and not finally_block_on_stack:
            targets.append(-1)

        first_loop = blockstack_view.first_loop

        if first_loop in path_metadata.get('broken loops', []):
            targets.append(first_loop.next_offset)

        new_view = blockstack_view

    elif opname == 'RAISE_VARARGS':
        targets = [next_offset] + exceptional_jump_targets(offset, blockstack_view)
        path_metadata['has except'] = True

        new_view = blockstack_view

    else:
        raise ValueError("Unhandled instruction: %s" % str(instr))

    return targets, path_metadata, new_view
