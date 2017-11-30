import dis
import marshal

import pycfg

code_boundary = b"\n\n\n---162b4a78-0bc7-4966-a4e7-59aa1f784c39\n\n\n"


class MissingSuccessorException(Exception):
    pass


class MissingBasicBlockException(Exception):
    pass


class NoPathException(Exception):
    pass


def load_test_case(filename):
    with open(filename, 'rb') as f:
        marshalled_code, path = f.read().split(code_boundary)

    code = marshal.loads(marshalled_code)

    bc = dis.Bytecode(code)
    cfg = None

    try:
        cfg = pycfg.CFG(code)
    except Exception:
        print("DISASSEMBLY:", bc.dis(), sep='\n')
        raise

    offsets_in_path = []

    if not path:
        raise NoPathException("Test case contains no path: %s" % filename)

    for offset_and_opcode in path.decode().strip().split('\n'):
        offset, opcode = offset_and_opcode.split()

        offsets_in_path.append(int(offset) - 2)

    return {
        'bytecode': bc,
        'cfg': cfg,
        'path': offsets_in_path,
    }


def try_path(path, cfg):
    """
    Given a path, try to follow it through the CFG, returning True if it's
    possible, and raising an exception if not.
    """

    for instruction, successor in zip(path, path[1:]):
        try:
            bb = cfg[instruction]
        except KeyError:
            raise MissingBasicBlockException("Missing instruction at offset %d"
                                             % instruction)

        if successor not in bb.successors:
            succ_bb = cfg[successor]

            if instruction == successor:
                # TODO: figure out why this happens
                continue

            error_msg = "There should be an edge [%d -> %d]\n" % (instruction, successor)
            error_msg += "Instr %d :: %s\n" % (instruction, str(bb))
            error_msg += "Succ  %d :: %s\n" % (successor, str(succ_bb))
            error_msg += "Successors of %d: %s\n" % (instruction, str(bb.successors))
            error_msg += "Blockstack of %d: %s\n\n" % (instruction, str(bb.blockstack_view))

            raise MissingSuccessorException(error_msg)

    return True
