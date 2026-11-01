// Desktop test tool for the stroke dictionary reader (strokedict.c), with the reader's own code, as the firmware will
// use it.
//
//   sdview -i dict.msd                   header, metadata, CRC
//   sdview dict.msd hspn [pzpn 1234 ...]  the candidates for each input (strokes as h s p n z or 1 to 5)
//   sdview -p 2 dict.msd hspn            the same, page 2 (pages of 10, as a device would show them)
//   sdview -a dict.msd hspn              every candidate the reader can page through (up to 64)
#include "strokedict.h"

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

static const char *result_name(sd_result r)
{
    switch (r) {
    case SD_OK:
        return "OK";
    case SD_ERR_READ:
        return "read error";
    case SD_ERR_MAGIC:
        return "not a stroke dictionary";
    case SD_ERR_VERSION:
        return "unknown format version";
    case SD_ERR_FORMAT:
        return "malformed (out of bounds)";
    case SD_ERR_CRC:
        return "CRC mismatch";
    }
    return "?";
}

static void put_utf8(uint32_t cp)
{
    char b[4];
    int n;
    if (cp < 0x80) {
        b[0] = (char)cp;
        n = 1;
    } else if (cp < 0x800) {
        b[0] = (char)(0xC0 | (cp >> 6));
        b[1] = (char)(0x80 | (cp & 0x3F));
        n = 2;
    } else if (cp < 0x10000) {
        b[0] = (char)(0xE0 | (cp >> 12));
        b[1] = (char)(0x80 | ((cp >> 6) & 0x3F));
        b[2] = (char)(0x80 | (cp & 0x3F));
        n = 3;
    } else {
        b[0] = (char)(0xF0 | (cp >> 18));
        b[1] = (char)(0x80 | ((cp >> 12) & 0x3F));
        b[2] = (char)(0x80 | ((cp >> 6) & 0x3F));
        b[3] = (char)(0x80 | (cp & 0x3F));
        n = 4;
    }
    fwrite(b, 1, (size_t)n, stdout);
}

static int usage(void)
{
    fprintf(stderr, "usage: sdview -i dict.msd\n"
                    "       sdview [-p page | -a] dict.msd strokes...   (strokes: h s p n z, or 1 to 5)\n");
    return 2;
}

int main(int argc, char **argv)
{
    bool info = false, all = false;
    int page = 1, i = 1;
    for (; i < argc && argv[i][0] == '-'; i++) {
        if (strcmp(argv[i], "-i") == 0)
            info = true;
        else if (strcmp(argv[i], "-a") == 0)
            all = true;
        else if (strcmp(argv[i], "-p") == 0 && i + 1 < argc)
            page = atoi(argv[++i]);
        else
            return usage();
    }
    if (i >= argc || page < 1 || (!info && i + 1 >= argc))
        return usage();

    file_ctx ctx = {fopen(argv[i], "rb")};
    if (!ctx.f) {
        perror(argv[i]);
        return 1;
    }
    fseek(ctx.f, 0, SEEK_END);
    uint32_t size = (uint32_t)ftell(ctx.f);
    sd_dict dict;
    sd_result r = sd_open(&dict, file_read, &ctx, size);
    if (r != SD_OK) {
        fprintf(stderr, "%s: %s\n", argv[i], result_name(r));
        return 1;
    }

    if (info) {
        printf("%s: %u bytes, %u entries, strokes up to %u, top table 1 to %u strokes x %u candidates\n", argv[i],
               dict.file_size, dict.entry_count, dict.max_strokes, dict.top_depth, dict.top_k);
        char *meta = malloc(dict.meta_size + 1);
        if (meta && file_read(&ctx, dict.meta_offset, meta, dict.meta_size)) {
            meta[dict.meta_size] = 0;
            printf("%s\n", meta);
        }
        free(meta);
        r = sd_verify(&dict);
        printf("CRC: %s\n", result_name(r));
        return r == SD_OK ? 0 : 1;
    }

    int skip = all ? 0 : (page - 1) * 10, max = all ? SD_MAX_CANDIDATES : 10;
    if (skip + max > SD_MAX_CANDIDATES) {
        fprintf(stderr, "page %d is past the %d candidates a lookup pages through\n", page, SD_MAX_CANDIDATES);
        return 1;
    }
    int status = 0;
    for (int a = i + 1; a < argc; a++) {
        uint8_t strokes[SD_MAX_STROKES];
        int n = 0;
        bool ok = strlen(argv[a]) <= SD_MAX_STROKES;
        for (const char *c = argv[a]; ok && *c; c++)
            ok = (strokes[n++] = sd_stroke_value(*c)) != 0;
        if (!ok || n == 0) {
            fprintf(stderr, "%s: strokes are h s p n z, or 1 to 5 (at most %d)\n", argv[a], SD_MAX_STROKES);
            status = 1;
            continue;
        }
        uint32_t out[SD_MAX_CANDIDATES], total;
        int got = sd_lookup(&dict, strokes, n, skip, out, max, &total);
        printf("%s: %u\t", argv[a], total);
        for (int k = 0; k < got; k++)
            put_utf8(out[k]);
        printf("\n");
    }
    fclose(ctx.f);
    return status;
}
