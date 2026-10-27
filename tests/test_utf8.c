// Tests of fp_utf8_next: valid sequences, and every kind of invalid one gives U+FFFD and moves one byte
#include "../c/fontpack.h"

#include <stdio.h>
#include <string.h>

static int failures;

static void expect(const char *name, const char *s, size_t len, const uint32_t *cps, int n)
{
    const char *p = s, *end = s + len;
    for (int i = 0; i < n; i++) {
        uint32_t cp = fp_utf8_next(&p, end);
        if (cp != cps[i]) {
            printf("FAIL %s: code point %d is U+%04X, expected U+%04X\n", name, i, cp, cps[i]);
            failures++;
            return;
        }
    }
    if (p != end) {
        printf("FAIL %s: %d bytes left\n", name, (int)(end - p));
        failures++;
    }
}

#define T(name, str, ...)                                                                                        \
    do {                                                                                                         \
        static const uint32_t cps[] = {__VA_ARGS__};                                                             \
        expect(name, str, sizeof(str) - 1, cps, (int)(sizeof(cps) / sizeof(cps[0])));                           \
    } while (0)

int main(void)
{
    T("ascii", "Hi", 'H', 'i');
    T("2 bytes", "\xC3\xA7", 0xE7);
    T("3 bytes", "\xE4\xBD\xA0", 0x4F60);
    T("4 bytes", "\xF0\x9F\x98\x80", 0x1F600);
    T("lone continuation", "\x80" "A", 0xFFFD, 'A');
    T("truncated", "\xE4\xBD", 0xFFFD, 0xFFFD);
    T("bad continuation", "\xE4" "A" "\xA0", 0xFFFD, 'A', 0xFFFD);
    T("overlong", "\xC0\xAF", 0xFFFD, 0xFFFD);
    T("overlong 3", "\xE0\x80\xAF", 0xFFFD, 0xFFFD, 0xFFFD);
    T("surrogate", "\xED\xA0\x80", 0xFFFD, 0xFFFD, 0xFFFD);
    T("above U+10FFFF", "\xF4\x90\x80\x80", 0xFFFD, 0xFFFD, 0xFFFD, 0xFFFD);
    T("F8", "\xF8" "A", 0xFFFD, 'A');
    T("max", "\xF4\x8F\xBF\xBF", 0x10FFFF);

    // Never reads past end
    const char buf[] = "\xF0\x9F\x98\x80";
    const char *p = buf;
    uint32_t cp = fp_utf8_next(&p, buf + 2);
    if (cp != 0xFFFD || p != buf + 1) {
        printf("FAIL end: U+%04X, moved %d\n", cp, (int)(p - buf));
        failures++;
    }

    printf("UTF-8 tests: %s\n", failures ? "FAILED" : "OK");
    return failures ? 1 : 0;
}
