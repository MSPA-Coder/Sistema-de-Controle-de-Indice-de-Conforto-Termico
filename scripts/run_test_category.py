"""Executa apenas os testes unittest de uma categoria registrada."""

from __future__ import annotations

import argparse
import sys
import unittest

from tests.categories import categories_for_test_id


def _flatten(suite: unittest.TestSuite):
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            yield from _flatten(test)
        else:
            yield test


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("category")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    suite = unittest.defaultTestLoader.discover("tests")
    selected = [
        test for test in _flatten(suite) if args.category in categories_for_test_id(test.id())
    ]
    if not selected:
        parser.error(f"nenhum teste classificado como {args.category!r}")
    result = unittest.TextTestRunner(verbosity=2 if args.verbose else 1).run(
        unittest.TestSuite(selected)
    )
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
