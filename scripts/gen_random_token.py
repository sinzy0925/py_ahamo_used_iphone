#!/usr/bin/env python3
"""WEBHOOK_TOKEN 用などに、英数字のみのランダム文字列を生成する。"""

from __future__ import annotations

import argparse
import secrets
import string

ALPHANUM = string.ascii_letters + string.digits


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-n",
        "--length",
        type=int,
        default=64,
        metavar="N",
        help="文字数（既定: 64）",
    )
    args = parser.parse_args()
    if args.length < 1:
        raise SystemExit("length は 1 以上にしてください")

    print("".join(secrets.choice(ALPHANUM) for _ in range(args.length)))


if __name__ == "__main__":
    main()
