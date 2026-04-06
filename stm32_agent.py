#!/usr/bin/env python3
"""Gary CLI 入口"""

import argparse

from core.agent import run


def main() -> None:
    """Parse CLI arguments and hand control to the core runtime."""

    parser = argparse.ArgumentParser(prog="gary")
    parser.add_argument("command", nargs="?", default="")
    parser.add_argument("command_args", nargs=argparse.REMAINDER)
    parser.add_argument("--connect", action="store_true")
    parser.add_argument("--chip", default="")
    parser.add_argument("--doctor", action="store_true")
    parser.add_argument("--config", action="store_true")
    parser.add_argument("--do", dest="task", default="")
    parser.add_argument("--telegram", default="")
    parser.add_argument("--thinking", action="store_true")
    run(parser.parse_args())


if __name__ == "__main__":
    main()
