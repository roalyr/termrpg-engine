"""Runs the whole test suite in parallel: the same tests as `unittest discover`, spread over the CPU cores.

    python3 -B tests/run.py            # every core
    python3 -B tests/run.py -j 4       # four workers
    python3 -B tests/run.py pack       # only test files whose name contains "pack"

Tests are handed out in small batches of one test class, so a big class (like the pack checker's) is shared
between workers. Each batch runs in a fresh test result; the failures are printed at the end, as unittest
prints them. `python3 -B -m unittest discover -s tests` stays the plain, one-process way to run them.
"""
import argparse
import io
import multiprocessing
import os
import sys
import time
import unittest
from pathlib import Path

TESTS = Path(__file__).resolve().parent
ROOT = TESTS.parent
BATCH = 6          # tests per batch: small enough to share big classes, large enough to keep setUpClass rare


def _ids(suite):
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            yield from _ids(test)
        else:
            yield test.id()


def batches(pattern: str):
    """Test ids grouped by class, cut into batches. Modules that fail to import come through as one id each."""
    suite = unittest.TestLoader().discover(str(TESTS), pattern=pattern, top_level_dir=str(TESTS))
    by_class = {}
    for test_id in _ids(suite):
        by_class.setdefault(test_id.rpartition(".")[0], []).append(test_id)
    work = [ids[i:i + BATCH] for ids in by_class.values() for i in range(0, len(ids), BATCH)]
    return sorted(work, key=len, reverse=True)


def _start():
    sys.dont_write_bytecode = True
    for path in (str(TESTS), str(ROOT)):
        if path not in sys.path:
            sys.path.insert(0, path)
    os.chdir(ROOT)


def _run(ids):
    out = io.StringIO()
    suite = unittest.TestLoader().loadTestsFromNames(ids)
    result = unittest.TextTestResult(unittest.runner._WritelnDecorator(out), descriptions=True, verbosity=0)
    suite.run(result)
    result.printErrors()
    problems = len(result.failures) + len(result.errors) + len(result.unexpectedSuccesses)
    return result.testsRun, problems, len(result.skipped), out.getvalue() if problems else ""


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run the tests in parallel.")
    parser.add_argument("only", nargs="?", default="", help="run only test files whose name contains this")
    parser.add_argument("-j", "--jobs", type=int, default=os.cpu_count() or 1, help="worker processes")
    args = parser.parse_args(argv)
    _start()
    work = batches(f"test_*{args.only}*.py" if args.only else "test_*.py")
    began = time.monotonic()
    ran = problems = skipped = 0
    reports = []
    with multiprocessing.get_context("spawn").Pool(max(1, args.jobs), initializer=_start) as pool:
        for count, bad, skip, report in pool.imap_unordered(_run, work):
            ran, problems, skipped = ran + count, problems + bad, skipped + skip
            sys.stderr.write("F" if bad else ".")
            sys.stderr.flush()
            if report:
                reports.append(report)
    sys.stderr.write("\n" + "".join(reports))
    sys.stderr.write("-" * 70 + f"\nRan {ran} tests in {time.monotonic() - began:.1f}s ({args.jobs} workers)\n\n")
    sys.stderr.write(("OK" if not problems else f"FAILED ({problems} failing)")
                     + (f" (skipped={skipped})" if skipped else "") + "\n")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
