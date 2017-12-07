import dis
import os
import unittest

import pycfg


function_registry = []


def register(f):
    function_registry.append(f)


@register
def _1(x):
    for i in range(x):
        print(i)

    return i


@register
def _2(x):
    for i in range(x):
        print(i)

        if i > 3:
            break

    return 5


@register
def _3(x):
    for i in range(x):
        print(i)

        try:
            print(i**2)

            if i > 3:
                break

        finally:
            print("done")


@register
def _4():
    try:
        return 1
    finally:
        return 2


@register
def _5():
    try:
        return 1/0
    except ZeroDivisionError:
        return -1
    finally:
        print(5)


@register
def _6(a, i):
    try:
        return a[i].x
    except IndexError:
        return -1
    except AttributeError:
        return -2


@register
def _7(a, i):
    try:
        return a[i].x
    except IndexError:
        return -1
    except AttributeError:
        return -2
    finally:
        return -3


@register
def _8(x):
    with open(x, 'w') as f:
        try:
            f.readlines()
        except Exception:
            return 1


@register
def _9(x):
    """
    Test for both a POP_BLOCK and a POP_EXCEPT depending on the branch
    """

    try:
        x
    except:     # noqa
        print(x)

    print(x**2)


@register
def _10(x):
    for i in range(x):
        break
    else:
        print(x)


@register
def _11(x):
    while x:
        break
    else:
        print(x)


@register
def _12(x):
    try:
        x
    except Exception:
        raise


@register
def _13(x):
    try:
        x
    except Exception as e:
        raise


@register
def _14(x):
    while True:
        if x:
            break


@register
def _15(x):
    while True:
        if x:
            break
        else:
            if x+1:
                break
        if x+2:
            break


@register
def _16(x):
    while True:
        if x:
            break
        else:
            break
        if not x:
            break


class TestCFG(unittest.TestCase):
    def test_all_successors_exist(self):
        for func in function_registry:
            try:
                cfg = pycfg.CFG(func.__code__)
            except Exception:
                print(dis.Bytecode(func.__code__).dis())
                raise

            if os.environ.get('SAVE_CFG'):
                with open('function' + func.__name__ + '_' + str(hash(func)) + '.dot', 'w') as f:
                    f.write(cfg.to_dot())

                with open('function' + func.__name__ + '_' + str(hash(func)) + '.bc', 'w') as f:
                    f.write(dis.Bytecode(func.__code__).dis())

            for bb in cfg:
                for bb_succ in bb.successors:
                    assert bb_succ in cfg, func.__code__

    def test_filter(self):
        def f(x):
            for i in range(x):
                print(i)
                if i > 3:
                    break
            return 1

        cfg = pycfg.CFG(f.__code__)

        pred_10 = list(cfg.filter(predecessors_of=10))    # FOR_ITER
        pred_34 = list(cfg.filter(predecessors_of=34))    # POP_BLOCK

        assert len(pred_10) == 2
        assert len(pred_34) == 1
        assert pred_10[0].offset == 8
        assert pred_10[1].offset == 28
        assert pred_34[0].offset == 10

    def test_edge_number(self):
        def f(x):
            for i in range(x):
                print(i)
                if i > 3:
                    break
            return 1

        cfg = pycfg.CFG(f.__code__)

        assert cfg.edge_number((8, 10)) == 0
        assert cfg.edge_number((28, 10)) == 1
        assert cfg.edge_number((10, 34)) == 0
