import os
import pathlib
import sys
import unittest

from . import utils


def walker(path):
    for directory, _, filenames in os.walk(path):
        dirpath = pathlib.Path(directory)

        for filename in filenames:
            yield dirpath / filename


class TestCFG(unittest.TestCase):
    def test_path_is_possible(self):

        path = pathlib.Path(os.environ['CFG_TEST_PATH'])

        if path.is_dir():
            filenames = walker(path)
        else:
            filenames = [path]

        for i, test_case_filename in enumerate(filenames):

            try:
                test_case = utils.load_test_case(test_case_filename)
            except (utils.NoPathException, EOFError):
                print(f"Skipped test {i} [{test_case_filename}]", file=sys.stderr)
                continue
            except MemoryError:
                print(f"OOM on test {i} [{test_case_filename}]", file=sys.stderr)
                continue
            except ValueError:
                print(f"ValueError on test {i} [{test_case_filename}]", file=sys.stderr)
                continue
            else:
                print(f"Completed test {i}", file=sys.stderr)

            try:
                res = utils.try_path(test_case['path'], test_case['cfg'])
            except utils.MissingSuccessorException:
                print(test_case['bytecode'].dis(), file=sys.stderr)
                raise
            else:
                self.assertTrue(res)
