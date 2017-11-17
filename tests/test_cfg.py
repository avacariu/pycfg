import dis
import unittest

import pycfg


function_registry = []


def register(f):
    function_registry.append(f)


@register
def _(x):
    for i in range(x):
        print(i)

    return i

@register   # noqa
def _(x):
    for i in range(x):
        print(i)

        if i > 3:
            break

    return 5

@register   # noqa
def _(x):
    for i in range(x):
        print(i)

        try:
            print(i**2)

            if i > 3:
                break

        finally:
            print("done")


@register   # noqa
def _():
    try:
        return 1
    finally:
        return 2


@register   # noqa
def _():
    try:
        return 1/0
    except ZeroDivisionError:
        return -1
    finally:
        print(5)


@register   # noqa
def _(a, i):
    try:
        return a[i].x
    except IndexError:
        return -1
    except AttributeError:
        return -2


@register   # noqa
def _(a, i):
    try:
        return a[i].x
    except IndexError:
        return -1
    except AttributeError:
        return -2
    finally:
        return -3


@register   # noqa
def _(x):
    with open(x, 'w') as f:
        try:
            f.readlines()
        except Exception:
            return 1


class TestCFG(unittest.TestCase):
    def test_all_successors_exist(self):
        for func in function_registry:
            try:
                cfg = pycfg.CFG(func.__code__)
            except Exception:
                print(dis.Bytecode(func.__code__).dis())
                raise

            for bb in cfg:
                for bb_succ in bb.successors:
                    assert bb_succ in cfg, func.__code__
