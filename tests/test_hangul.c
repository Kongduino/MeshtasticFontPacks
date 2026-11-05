// Tests of the 나랏글 input (c/hangul.c): key sequences and the text they give. Keys as on the phone's keypad: 1 ㄱ,
// 2 ㄴ, 3 ㅏㅓ, 4 ㄹ, 5 ㅁ, 6 ㅗㅜ, 7 ㅅ, 8 ㅇ, 9 ㅣ, * 획추가, 0 ㅡ, # 쌍자음; a space finishes the syllable and types a
// space, < is backspace (inside the syllable being composed, or the last character typed)
#include "../c/hangul.h"

#include <stdio.h>
#include <string.h>

static int failures, count;

static size_t put_utf8(char *p, uint32_t cp)
{
    if (cp < 0x80) {
        p[0] = (char)cp;
        return 1;
    }
    if (cp < 0x800) {
        p[0] = (char)(0xC0 | (cp >> 6));
        p[1] = (char)(0x80 | (cp & 0x3F));
        return 2;
    }
    p[0] = (char)(0xE0 | (cp >> 12));
    p[1] = (char)(0x80 | ((cp >> 6) & 0x3F));
    p[2] = (char)(0x80 | (cp & 0x3F));
    return 3;
}

static void type(const char *keys, char *text)
{
    static const char keypad[] = "123456789*0#";
    uint32_t cps[256];
    int n = 0;
    hg_state s;
    hg_init(&s);
    for (const char *k = keys; *k; k++) {
        if (*k == ' ') {
            n += hg_flush(&s, cps + n);
            cps[n++] = ' ';
        } else if (*k == '<') {
            if (!hg_backspace(&s) && n > 0)
                n--;
        } else {
            const char *at = strchr(keypad, *k);
            n += hg_press(&s, (hg_key)(at - keypad), cps + n);
        }
    }
    n += hg_flush(&s, cps + n);
    size_t len = 0;
    for (int i = 0; i < n; i++)
        len += put_utf8(text + len, cps[i]);
    text[len] = 0;
}

static void expect(const char *keys, const char *want)
{
    char got[1024];
    type(keys, got);
    count++;
    if (strcmp(got, want) != 0) {
        printf("FAIL \"%s\": got \"%s\", expected \"%s\"\n", keys, got, want);
        failures++;
    }
}

int main(void)
{
    // What the phone does (Samsung 나랏글)
    expect("2***", "ㄴ");
    expect("8**", "ㅇ");
    expect("1##", "ㄱ");
    expect("863", "와");
    expect("8633", "와");
    expect("86633", "워");
    expect("13 3", "가 ㅏ");

    // Letters on their own
    expect("12", "ㄱㄴ");
    expect("31", "ㅏㄱ");
    expect("1*", "ㅋ");
    expect("2*", "ㄷ");
    expect("2**", "ㅌ");
    expect("5*", "ㅂ");
    expect("5**", "ㅍ");
    expect("5***", "ㅁ");
    expect("7*", "ㅈ");
    expect("7**", "ㅊ");
    expect("7#", "ㅆ");
    expect("7*#", "ㅉ");
    expect("2*#", "ㄸ");
    expect("5*#", "ㅃ");

    // Vowels
    expect("83", "아");
    expect("833", "어");
    expect("8333", "아");
    expect("83*", "야");
    expect("833*", "여");
    expect("86", "오");
    expect("866", "우");
    expect("86*", "요");
    expect("866*", "유");
    expect("80", "으");
    expect("89", "이");
    expect("839", "애");
    expect("8339", "에");
    expect("83*9", "얘");
    expect("833*9", "예");
    expect("869", "외");
    expect("8669", "위");
    expect("809", "의");
    expect("8639", "왜");
    expect("86639", "웨");
    expect("8663", "워");

    // Words
    expect("8*32104", "한글");
    expect("8*32104 1#665", "한글 꿈");
    expect("832 7*83", "안 ㅈ아");
    expect("8327*83", "앉아");
    expect("8335*7833", "없어");
    expect("89412*3", "읽다");
    expect("163927**328*83", "괜찮아");
    expect("2*3 41", "다 ㄹㄱ");
    expect("2*341", "닭");
    expect("5663", "뭐");
    expect("80973", "의사");
    expect("7#38", "쌍");
    expect("837#3", "아싸");
    expect("2***3", "나");
    expect("13202*3", "가느다");
    expect("8*3*1#", "햒");
    expect("8*3*1##", "햑");
    expect("17*9", "ㄱ지");

    // A final that isn't one: shown after the syllable, then the next syllable's
    expect("132*#", "가ㄸ");
    expect("132*#3", "가따");
    expect("132*##", "갇");
    expect("132*#1", "가ㄸㄱ");
    expect("1327", "간ㅅ");
    expect("1327*", "갅");
    expect("1327**", "간ㅊ");
    expect("1327**3", "간차");
    expect("13271", "간ㅅㄱ");

    // Backspace
    expect("163<", "고");
    expect("1639<", "과");
    expect("131<", "가");
    expect("1327*<", "간");
    expect("13<", "ㄱ");
    expect("13<<", "");
    expect("13 <", "가");
    expect("13 <<", "");
    expect("8*32104<", "한그");
    expect("8*32104<<", "한ㄱ");
    expect("8*32104<<<", "한");
    expect("8*32104<<<<", "");

    printf("%d tests, %d failures\n", count, failures);
    return failures ? 1 : 0;
}
