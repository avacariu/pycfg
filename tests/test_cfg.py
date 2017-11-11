import unittest

import pycfg


def _f(x):
    for i in range(x):
        print(i**2)

    return i


class TestCFG(unittest.TestCase):
    def test_all_successors_exist(self):
        cfg = pycfg.CFG(_f.__code__)

        for bb in cfg:
            for bb_succ in bb.successors:
                assert bb_succ in cfg
