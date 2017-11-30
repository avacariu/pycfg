import os
import pathlib
import sys
import unittest

from . import utils


class TestCFG(unittest.TestCase):
    def test_path_is_possible(self):

        path = pathlib.Path(os.environ['CFG_TEST_PATH'])

        if path.is_dir():
            filenames = path.iterdir()
        else:
            filenames = [path]

        for i, test_case_filename in enumerate(filenames):

            try:
                test_case = utils.load_test_case(test_case_filename)
            except (utils.NoPathException, EOFError):
                print("Skipped test %d" % i, file=sys.stderr)
                continue
            else:
                print("Completed test %d" % i, file=sys.stderr)

            try:
                res = utils.try_path(test_case['path'], test_case['cfg'])
            except utils.MissingSuccessorException:
                print(test_case['bytecode'].dis(), file=sys.stderr)
                raise
            else:
                self.assertTrue(res)
