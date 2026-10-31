CFLAGS = -std=c99 -Wall -Wextra -Werror -O1 -g
SANITIZE = -fsanitize=undefined -fno-sanitize-recover=undefined  # AddressSanitizer hangs at startup on this macOS
PY = .venv/bin/python
FONT = fonts/fusion12/fusion-pixel-12px-proportional-zh_hans.ttf
FONT_VERSION = 2026.10.25
FONT_URL = https://github.com/TakWolf/fusion-pixel-font/releases/download/$(FONT_VERSION)/fusion-pixel-font-12px-proportional-ttf-v$(FONT_VERSION).zip

all: out/fpview out/cjk12.mfp out/astral2.mfp

out/fpview: c/fpview.c c/fontpack.c c/fontpack.h
	mkdir -p out
	$(CC) $(CFLAGS) $(SANITIZE) -o $@ c/fpview.c c/fontpack.c

# Test pack: simplified Chinese (GB2312), kana, common Hangul, CJK punctuation, Latin-1
out/cjk12.mfp: tools/mkfontpack.py $(FONT)
	$(PY) tools/mkfontpack.py --font $(FONT) --size 12 \
		--set latin1,cjk-punct,kana,hangul-ksx1001,hanzi-gb2312 \
		--name cjk12 --license OFL-1.1 --source "Fusion Pixel Font 12px (TakWolf)" --out $@

# Test pack for the code points above U+FFFF (4 planes) and 2-byte metrics indices
out/astral2.mfp: tools/mkfontpack.py $(FONT)
	$(PY) -c "from fontTools.ttLib import TTFont; print(''.join(chr(c) for c in TTFont('$(FONT)').getBestCmap() if c > 0xFFFF))" > out/astral.txt
	$(PY) tools/mkfontpack.py --font $(FONT) --size 12 --set ascii,kana --text out/astral.txt --metric-index-size 2 \
		--name astral2 --license OFL-1.1 --source "Fusion Pixel Font 12px (TakWolf)" --out $@

# 16 px pack for larger screens (e-ink): GNU Unifont, full CJK (make cjk16)
UNIFONT_VERSION = 18.0.01
UNIFONT = fonts/unifont/unifont-$(UNIFONT_VERSION).otf
CJK_SETS = latin1,cjk-punct,kana,hangul-ksx1001,hanzi-gb2312,hanzi-big5,kanji-jis0208,hkscs

cjk16: out/cjk16.mfp

out/cjk16.mfp: tools/mkfontpack.py $(UNIFONT)
	$(PY) tools/mkfontpack.py --font $(UNIFONT) --size 16 --set $(CJK_SETS) --name cjk16 \
		--license "OFL-1.1 OR GPL-2.0-or-later WITH Font-exception-2.0" --source "GNU Unifont $(UNIFONT_VERSION)" --out $@

$(UNIFONT):
	mkdir -p fonts/unifont
	curl -sfL -o $@ https://unifoundry.com/pub/unifont/unifont-$(UNIFONT_VERSION)/font-builds/unifont-$(UNIFONT_VERSION).otf

# 12 px full CJK pack for small screens (OLED): Fusion Pixel, Hong Kong glyph forms (make cjk12full)
cjk12full: out/cjk12full.mfp

out/cjk12full.mfp: tools/mkfontpack.py $(FONT)
	$(PY) tools/mkfontpack.py --font fonts/fusion12/fusion-pixel-12px-proportional-zh_hk.ttf --size 12 --set $(CJK_SETS) \
		--name cjk12full --license OFL-1.1 --source "Fusion Pixel Font 12px zh_hk (TakWolf)" --out $@

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

.PHONY: all test clean cjk16 cjk12full
