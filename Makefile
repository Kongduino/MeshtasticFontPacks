CFLAGS = -std=c99 -Wall -Wextra -Werror -O1 -g
SANITIZE = -fsanitize=undefined -fno-sanitize-recover=undefined  # AddressSanitizer hangs at startup on this macOS
PY = .venv/bin/python
FONT = fonts/fusion12/fusion-pixel-12px-proportional-zh_hans.ttf
FONT_VERSION = 2026.10.25
FONT_URL = https://github.com/TakWolf/fusion-pixel-font/releases/download/$(FONT_VERSION)/fusion-pixel-font-12px-proportional-ttf-v$(FONT_VERSION).zip

all: out/fpview out/cjk12.mfp

out/fpview: c/fpview.c c/fontpack.c c/fontpack.h
	mkdir -p out
	$(CC) $(CFLAGS) $(SANITIZE) -o $@ c/fpview.c c/fontpack.c

# Test pack: simplified Chinese (GB2312), kana, common Hangul, CJK punctuation, Latin-1
out/cjk12.mfp: tools/mkfontpack.py $(FONT)
	$(PY) tools/mkfontpack.py --font $(FONT) --size 12 \
		--set latin1,cjk-punct,kana,hangul-ksx1001,hanzi-gb2312 \
		--name cjk12 --license OFL-1.1 --source "Fusion Pixel Font 12px (TakWolf)" --out $@

# The test font (OFL-1.1) is downloaded, not kept in the repository
$(FONT):
	mkdir -p fonts out
	curl -sL -o out/font.zip $(FONT_URL)
	unzip -o -q out/font.zip -d fonts/fusion12
	rm out/font.zip

test: all
	./tests/run.sh

clean:
	rm -rf out/*

.PHONY: all test clean
