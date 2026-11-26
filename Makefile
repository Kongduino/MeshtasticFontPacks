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

# 24 px packs for large screens (the T5 E-Paper's 960 x 540): Noto Sans CJK, an outline font, Hong Kong glyph forms for
# the hanzi and the Korean font for Hangul (make cjk24 hangul24)
NOTO_VERSION = 2.004
NOTO_URL = https://github.com/notofonts/noto-cjk/raw/Sans$(NOTO_VERSION)/Sans/OTF
NOTO_HK = fonts/noto-cjk-hk/NotoSansCJKhk-Regular.otf
NOTO_KR = fonts/noto-cjk-kr/NotoSansCJKkr-Regular.otf

cjk24: out/cjk24.mfp
hangul24: out/hangul24.mfp

out/cjk24.mfp: tools/mkfontpack.py $(NOTO_HK)
	$(PY) tools/mkfontpack.py --font $(NOTO_HK) --size 24 --set cjk-punct,cjk-all --name cjk24 --license OFL-1.1 \
		--source "Noto Sans CJK HK $(NOTO_VERSION) (github.com/notofonts/noto-cjk)" --out $@

out/hangul24.mfp: tools/mkfontpack.py $(NOTO_KR)
	$(PY) tools/mkfontpack.py --font $(NOTO_KR) --size 24 --set hangul --name hangul24 --license OFL-1.1 \
		--source "Noto Sans CJK KR $(NOTO_VERSION) (github.com/notofonts/noto-cjk)" --out $@

$(NOTO_HK):
	mkdir -p fonts/noto-cjk-hk
	curl -sfL -o $@ $(NOTO_URL)/TraditionalChineseHK/NotoSansCJKhk-Regular.otf

$(NOTO_KR):
	mkdir -p fonts/noto-cjk-kr
	curl -sfL -o $@ $(NOTO_URL)/Korean/NotoSansCJKkr-Regular.otf

# Japanese packs, with Japanese glyph forms (the zh packs above draw many kanji the Chinese way): JIS level 1 and 2 kanji,
# kana, half-width katakana (make ja12 k8x12 ja24)
#   ja12   Fusion Pixel 12 px, Japanese variant
#   k8x12  8 x 12 BDF bitmap font made for small screens, copied pixel for pixel; its kana sit well next to the OLED's
#          ArialMT_Plain_10 (128 x 64 OLEDs)
#   ja24   Noto Sans CJK JP 24 px, for large screens
JA_SETS = latin1,cjk-punct,kana,kanji-jis0208
K8X12_VERSION = 2021-05-05
K8X12 = fonts/k8x12/k8x12.bdf
NOTO_JP = fonts/noto-cjk-jp/NotoSansCJKjp-Regular.otf

ja12: out/ja12.mfp
k8x12: out/k8x12.mfp
ja24: out/ja24.mfp

out/ja12.mfp: tools/mkfontpack.py $(FONT)
	$(PY) tools/mkfontpack.py --font fonts/fusion12/fusion-pixel-12px-proportional-ja.ttf --size 12 --set $(JA_SETS) \
		--name ja12 --license OFL-1.1 --source "Fusion Pixel Font 12px ja (TakWolf)" --out $@

out/k8x12.mfp: tools/mkfontpack.py $(K8X12)
	$(PY) tools/mkfontpack.py --font $(K8X12) --size 12 --set $(JA_SETS) --name k8x12 \
		--license "free (k8x12.txt: use, copy and distribute, modified or not)" \
		--source "k8x12 $(K8X12_VERSION) (Num Kadoma, littlelimit.net)" --out $@

out/ja24.mfp: tools/mkfontpack.py $(NOTO_JP)
	$(PY) tools/mkfontpack.py --font $(NOTO_JP) --size 24 --set $(JA_SETS) --name ja24 --license OFL-1.1 \
		--source "Noto Sans CJK JP $(NOTO_VERSION) (github.com/notofonts/noto-cjk)" --out $@

$(K8X12):
	mkdir -p fonts/k8x12
	curl -sfL -o fonts/k8x12/k8x12_bdf.zip https://littlelimit.net/arc/k8x12/k8x12_bdf_$(K8X12_VERSION).zip
	unzip -o -q fonts/k8x12/k8x12_bdf.zip -d fonts/k8x12
	rm fonts/k8x12/k8x12_bdf.zip
	touch $@

$(NOTO_JP):
	mkdir -p fonts/noto-cjk-jp
	curl -sfL -o $@ $(NOTO_URL)/Japanese/NotoSansCJKjp-Regular.otf

# The test font (OFL-1.1) is downloaded, not kept in the repository
# Stroke input (STROKES.md): the reader's viewer, a dictionary, and the reader's test. The stroke table is the
# mainland one made from Wiktionary (CC BY-SA 4.0); TABLES adds others, e.g. Hong Kong and Taiwan orders:
#   make strokes        make strokes TABLES="out/strokes-cn.txt hk.txt"        make test-strokes
UNIHAN_VERSION = 18.0.0
UNIHAN = fonts/unihan/Unihan-$(UNIHAN_VERSION).zip
TABLES ?= out/strokes-cn.txt
PREFER ?= hk,tw,cn

out/sdview: c/sdview.c c/strokedict.c c/strokedict.h c/fontpack.c c/fontpack.h
	mkdir -p out
	$(CC) $(CFLAGS) $(SANITIZE) -o $@ c/sdview.c c/strokedict.c c/fontpack.c

strokes: out/strokes.msd

out/strokes.msd: tools/mkstrokedict.py $(UNIHAN) $(TABLES)
	$(PY) tools/mkstrokedict.py $(addprefix --table ,$(TABLES)) --prefer $(PREFER) --unihan $(UNIHAN) --out $@

# The Wiktionary pages are downloaded once into fonts/wiktionary
out/strokes-cn.txt: tools/wiktionary_strokes.py
	mkdir -p out
	$(PY) tools/wiktionary_strokes.py --cache fonts/wiktionary --out $@

test-strokes: out/sdview $(UNIHAN) out/strokes-cn.txt
	$(PY) tools/test_strokedict.py --table out/strokes-cn.txt --unihan $(UNIHAN) --sdview out/sdview

$(UNIHAN):
	mkdir -p fonts/unihan
	curl -sfL -o $@ https://www.unicode.org/Public/$(UNIHAN_VERSION)/ucd/Unihan.zip

$(FONT):
	mkdir -p fonts out
	curl -sL -o out/font.zip $(FONT_URL)
	unzip -o -q out/font.zip -d fonts/fusion12
	rm out/font.zip

test: all
	./tests/run.sh

clean:
	rm -rf out/*

.PHONY: all test clean cjk16 cjk12full cjk24 hangul24 ja12 k8x12 ja24 strokes test-strokes
