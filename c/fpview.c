// Desktop test tool for the font pack reader (fontpack.c), with the reader's own code, as the firmware will use it.
//
//   fpview -i pack.mfp                 header, metadata, CRC
//   fpview -c pack.mfp                 look up and read every glyph the ranges declare
//   -n                                 don't copy the metrics table to RAM (the reader then reads it from the file)
//   fpview [-w 128] [-o out.pbm] pack.mfp "text"   lay the text out on a screen that wide, as text art (and a PBM)
//   fpview ... pack.mfp -f file.txt    the same with the text of a file
//
// Missing glyphs are drawn as a box (tofu). Lines wrap per character for CJK, per word otherwise.
#include "fontpack.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct {
    FILE *f;
} file_ctx;

static bool file_read(void *ctx, uint32_t off, void *buf, uint32_t len)
{
    FILE *f = ((file_ctx *)ctx)->f;
    return fseek(f, (long)off, SEEK_SET) == 0 && fread(buf, 1, len, f) == len;
}

static const char *result_name(fp_result r)
{
    switch (r) {
    case FP_OK:
        return "OK";
    case FP_ERR_READ:
        return "read error";
    case FP_ERR_MAGIC:
        return "not a font pack";
    case FP_ERR_VERSION:
        return "unknown format version";
    case FP_ERR_FORMAT:
        return "malformed (out of bounds)";
    case FP_ERR_CRC:
        return "CRC mismatch";
    }
    return "?";
}

// A code point that may start a new line by itself (CJK, kana, Hangul, fullwidth forms)
static bool breakable(uint32_t cp)
{
    return cp >= 0x2E80;
}

typedef struct {
    uint32_t cp;
    bool found;
    fp_glyph g;
    int advance;
} item;

#define MAX_LINES 64
static uint8_t *screen; // 1 byte per pixel
static int screen_w, screen_h;

static void plot(int x, int y)
{
    if (x >= 0 && x < screen_w && y >= 0 && y < screen_h)
        screen[y * screen_w + x] = 1;
}

static void draw_item(const fp_pack *pack, const item *it, int x, int top)
{
    if (!it->found) {
        // Tofu: a box inside the advance, from the cap line to the baseline
        int w = it->advance - 2, y0 = top + pack->line_height / 4, y1 = top + pack->baseline - 1;
        for (int i = 0; i < w; i++)
            plot(x + 1 + i, y0), plot(x + 1 + i, y1);
        for (int y = y0; y <= y1; y++)
            plot(x + 1, y), plot(x + w, y);
        return;
    }
    uint8_t bits[1024];
    if (!fp_read_bitmap(pack, &it->g, bits, sizeof(bits)))
        return;
    for (int y = 0; y < it->g.height; y++)
        for (int x2 = 0; x2 < it->g.width; x2++)
            if (fp_pixel(bits, it->g.width, x2, y))
                plot(x + it->g.x_offset + x2, top + it->g.y_offset + y);
}

static int layout(const fp_pack *pack, const char *text, int width)
{
    size_t len = strlen(text);
    item *items = calloc(len + 1, sizeof(item));
    int n = 0;
    const char *s = text, *end = text + len;
    while (s < end) {
        item *it = &items[n++];
        it->cp = fp_utf8_next(&s, end);
        it->found = fp_find(pack, it->cp, &it->g);
        it->advance = it->found ? it->g.advance : pack->line_height * 2 / 3;
        if (it->cp == '\n')
            it->found = false, it->advance = 0;
    }

    screen_w = width;
    screen_h = MAX_LINES * pack->line_height;
    screen = calloc((size_t)screen_w * screen_h, 1);
    int line = 0, x = 0;
    for (int i = 0; i < n && line < MAX_LINES;) {
        if (items[i].cp == '\n') {
            line++, x = 0, i++;
            continue;
        }
        if (items[i].cp == ' ' && x == 0) { // no space at the start of a line
            i++;
            continue;
        }
        // The next unit: one breakable character, a space, or a word
        int j = i + 1, w = items[i].advance;
        if (!breakable(items[i].cp) && items[i].cp != ' ')
            while (j < n && items[j].cp != ' ' && items[j].cp != '\n' && !breakable(items[j].cp))
                w += items[j++].advance;
        if (x > 0 && x + w > width) { // doesn't fit: next line
            line++, x = 0;
            continue;
        }
        for (; i < j; i++) {
            if (x > 0 && x + items[i].advance > width) // a word wider than the screen: cut it
                line++, x = 0;
            if (line >= MAX_LINES)
                break;
            draw_item(pack, &items[i], x, line * pack->line_height);
            x += items[i].advance;
        }
    }
    free(items);
    return x > 0 ? line + 1 : line;
}

static int info(const fp_pack *pack, FILE *f)
{
    printf("size %u bytes, %u glyphs, %u ranges in %u planes, %u metrics\n", pack->file_size, pack->glyph_count,
           pack->range_count, pack->plane_count, pack->metrics_count);
    printf("line height %u, baseline %u, max advance %u\n", pack->line_height, pack->baseline, pack->max_advance);
    printf("tables: ranges %u, metrics %u, glyphs %u, checkpoints %u; bitmaps %u; metadata %u\n",
           pack->plane_count * 8 + pack->range_count * 3, fp_metrics_size(pack), pack->glyph_count * pack->metric_index_size,
           ((pack->range_count + 63) / 64 + (pack->glyph_count + 63) / 64) * 4, pack->bitmaps_size, pack->meta_size);
    printf("CRC %08X: %s\n", pack->crc32, result_name(fp_verify(pack)));
    if (pack->meta_size) {
        char *meta = calloc(pack->meta_size + 1, 1);
        file_ctx ctx = {f};
        if (file_read(&ctx, pack->meta_offset, meta, pack->meta_size))
            printf("%s\n", meta);
        free(meta);
    }
    return 0;
}

// Every code point the ranges declare, read from the tables directly (not through the reader)
static int check(const fp_pack *pack, FILE *f)
{
    file_ctx ctx = {f};
    uint32_t ok = 0, bad = 0;
    uint8_t planes[17 * 8];
    if (!file_read(&ctx, pack->planes_offset, planes, pack->plane_count * 8))
        return 1;
    for (uint32_t p = 0; p < pack->plane_count; p++) {
        uint32_t plane = planes[p * 8];
        uint32_t first = planes[p * 8 + 4] | planes[p * 8 + 5] << 8 | planes[p * 8 + 6] << 16 | (uint32_t)planes[p * 8 + 7] << 24;
        uint32_t end = pack->range_count;
        if (p + 1 < pack->plane_count)
            end = planes[p * 8 + 12] | planes[p * 8 + 13] << 8 | planes[p * 8 + 14] << 16 | (uint32_t)planes[p * 8 + 15] << 24;
        for (uint32_t r = first; r < end && r < pack->range_count; r++) {
            uint8_t b[3];
            if (!file_read(&ctx, pack->ranges_offset + r * 3, b, 3))
                return 1;
            uint32_t start = plane << 16 | (uint32_t)(b[0] | b[1] << 8);
            for (uint32_t cp = start; cp <= start + b[2] && cp <= 0x10FFFF; cp++) {
                fp_glyph g;
                uint8_t bits[1024];
                if (fp_find(pack, cp, &g) && fp_read_bitmap(pack, &g, bits, sizeof(bits)))
                    ok++;
                else
                    bad++;
            }
        }
    }
    printf("%u glyphs read, %u failed\n", ok, bad);
    return bad || ok != pack->glyph_count ? 1 : 0;
}

int main(int argc, char **argv)
{
    int width = 128;
    const char *out = NULL, *path = NULL, *text = NULL, *text_file = NULL;
    char mode = 'v';
    bool metrics_in_ram = true;
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "-w") && i + 1 < argc)
            width = atoi(argv[++i]);
        else if (!strcmp(argv[i], "-o") && i + 1 < argc)
            out = argv[++i];
        else if (!strcmp(argv[i], "-f") && i + 1 < argc)
            text_file = argv[++i];
        else if (!strcmp(argv[i], "-i"))
            mode = 'i';
        else if (!strcmp(argv[i], "-c"))
            mode = 'c';
        else if (!strcmp(argv[i], "-n"))
            metrics_in_ram = false;
        else if (!path)
            path = argv[i];
        else
            text = argv[i];
    }
    if (!path || (mode == 'v' && !text && !text_file) || width < 8 || width > 2000) {
        fprintf(stderr, "usage: fpview [-i | -c] [-n] [-w width] [-o out.pbm] pack.mfp [\"text\" | -f file]\n");
        return 2;
    }

    FILE *f = fopen(path, "rb");
    if (!f) {
        perror(path);
        return 1;
    }
    fseek(f, 0, SEEK_END);
    long size = ftell(f);
    file_ctx ctx = {f};
    fp_pack pack;
    fp_result r = fp_open(&pack, file_read, &ctx, size > 0xFFFFFFFFL ? 0xFFFFFFFFu : (uint32_t)size);
    if (r != FP_OK) {
        fprintf(stderr, "%s: %s\n", path, result_name(r));
        return 1;
    }
    static uint8_t metrics[65535 * 5];
    if (metrics_in_ram && !fp_load_metrics(&pack, metrics, sizeof(metrics))) {
        fprintf(stderr, "%s: can't read the metrics table\n", path);
        return 1;
    }
    if (mode == 'i')
        return info(&pack, f);
    if (mode == 'c')
        return check(&pack, f);

    char *buf = NULL;
    if (text_file) {
        FILE *t = fopen(text_file, "rb");
        if (!t) {
            perror(text_file);
            return 1;
        }
        buf = calloc(65537, 1);
        fread(buf, 1, 65536, t);
        fclose(t);
        text = buf;
    }
    int lines = layout(&pack, text, width);
    int h = lines * pack.line_height;

    printf("+");
    for (int x = 0; x < width; x++)
        putchar('-');
    printf("+\n");
    for (int y = 0; y < h; y++) {
        putchar('|');
        for (int x = 0; x < width; x++)
            putchar(screen[y * width + x] ? '#' : ' ');
        printf("|\n");
    }
    printf("+");
    for (int x = 0; x < width; x++)
        putchar('-');
    printf("+\n%d lines of %u px\n", lines, pack.line_height);

    if (out) {
        FILE *o = fopen(out, "wb");
        if (o) {
            fprintf(o, "P4\n%d %d\n", width, h);
            for (int y = 0; y < h; y++)
                for (int x = 0; x < width; x += 8) {
                    uint8_t b = 0;
                    for (int k = 0; k < 8 && x + k < width; k++)
                        if (screen[y * width + x + k])
                            b |= 0x80 >> k;
                    fputc(b, o);
                }
            fclose(o);
        }
    }
    free(buf);
    free(screen);
    fclose(f);
    return 0;
}
