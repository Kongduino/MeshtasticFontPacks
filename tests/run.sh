#!/bin/sh
# Font pack tests: the reader's UTF-8 decoder, a full read of the test pack, then the corruption test
set -e
cd "$(dirname "$0")/.."
cc -std=c99 -Wall -Wextra -Werror -fsanitize=undefined -fno-sanitize-recover=undefined -o out/test_utf8 tests/test_utf8.c c/fontpack.c
out/test_utf8
out/fpview -c out/cjk12.mfp
.venv/bin/python tests/fuzz.py out/cjk12.mfp "${ROUNDS:-300}"
