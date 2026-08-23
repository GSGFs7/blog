#define _POSIX_C_SOURCE 200809L // POSIX time api

#include <cmark-gfm.h>
#include <cmark-gfm_version.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

static char *
read_source(const char *path, size_t *length)
{
    FILE *file = fopen(path, "rb");
    if (file == NULL || fseek(file, 0, SEEK_END) != 0) {
        return NULL;
    }

    const long size = ftell(file);
    if (size < 0 || fseek(file, 0, SEEK_SET) != 0) {
        fclose(file);
        return NULL;
    }

    char *source = malloc((size_t)size + 1);
    if (source == NULL || fread(source, 1, (size_t)size, file) != (size_t)size)
    {
        free(source);
        fclose(file);
        return NULL;
    }

    fclose(file);
    source[size] = '\0';
    *length = (size_t)size;
    return source;
}

static double
now_ms(void)
{
    struct timespec value;
    clock_gettime(CLOCK_MONOTONIC, &value);
    return value.tv_sec * 1000.0 + value.tv_nsec / 1000000.0;
}

int
main(const int argc, char **argv)
{
    if (argc != 5) {
        fprintf(stderr, "usage: %s SPEC WARMUPS ITERATIONS REPEATS\n",
                argv[0]);
        return 2;
    }

    size_t source_length = 0;
    char *source = read_source(argv[1], &source_length);
    if (source == NULL) {
        fprintf(stderr, "failed to read %s\n", argv[1]);
        return 1;
    }

    const int warmups = atoi(argv[2]);
    const int iterations = atoi(argv[3]);
    const int repeats = atoi(argv[4]);
    volatile size_t checksum = 0;
    size_t output_bytes = 0;
    for (int index = 0; index < warmups; index++) {
        char *output =
            cmark_markdown_to_html(source, source_length, CMARK_OPT_DEFAULT);
        output_bytes = strlen(output);
        free(output);
    }

    printf("{\"engine\":\"cmark-gfm default\",\"version\":\"%s\",",
           CMARK_GFM_VERSION_STRING);
    printf("\"samples_ms\":[");
    for (int repeat = 0; repeat < repeats; repeat++) {
        const double started_at = now_ms();
        for (int iteration = 0; iteration < iterations; iteration++) {
            char *output = cmark_markdown_to_html(source, source_length,
                                                  CMARK_OPT_DEFAULT);
            output_bytes = strlen(output);
            checksum += output_bytes;
            free(output);
        }
        const double sample_ms = (now_ms() - started_at) / iterations;
        printf("%s%.9f", repeat == 0 ? "" : ",", sample_ms);
    }
    printf("],\"output_bytes\":%zu,\"checksum\":%zu}\n", output_bytes,
           (size_t)checksum);

    free(source);
    return 0;
}
