#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#if (defined(__x86_64__) || defined(__i386__)) &&                             \
    (defined(__GNUC__) || defined(__clang__))
#define CRC64NVME_X86_SIMD 1
#include <immintrin.h>

#define TARGET_PCLMUL __attribute__((target("pclmul,sse4.1")))
#define TARGET_VPCLMUL __attribute__((target("avx2,vpclmulqdq,pclmul,sse4.1")))
#else
#define CRC64NVME_X86_SIMD 0
#endif

#define CRC64_POLY UINT64_C(0x9A6C9329AC4BC9B5)
#define CRC64_MASK UINT64_MAX

#define K_127 UINT64_C(0x21e9761e252621ac)
#define K_191 UINT64_C(0xeadc41fd2ba3d420)
#define K_255 UINT64_C(0xe1e0bb9d45d7a44c)
#define K_319 UINT64_C(0xb0bc2e589204f500)
#define K_383 UINT64_C(0xa3ffdc1fe8e82a8b)
#define K_447 UINT64_C(0xbdd7ac0ee1a4a0f0)
#define K_511 UINT64_C(0x62242240ace5045a)
#define K_575 UINT64_C(0x0c32cdb31e18a84a)
#define K_639 UINT64_C(0x03363823e6e791e5)
#define K_703 UINT64_C(0x7b0ab10dd0f809fe)
#define K_767 UINT64_C(0x34f5a24e22d66e90)
#define K_831 UINT64_C(0x3c255f5ebc414423)
#define K_895 UINT64_C(0x946588403d4adcbc)
#define K_959 UINT64_C(0xd083dd594d96319d)
#define K_1023 UINT64_C(0x5f852fb61e8d92dc)
#define K_1087 UINT64_C(0xa1ca681e733f9c40)

#define BARRETT_POLY UINT64_C(0x34d926535897936b)
#define BARRETT_MU UINT64_C(0x27ecfa329aef9f77)

#define GIL_RELEASE_THRESHOLD (16 * 1024)

typedef uint64_t (*crc64_update_fn)(uint64_t state, const unsigned char *data,
                                    size_t length);

#if CRC64NVME_X86_SIMD
TARGET_PCLMUL
static inline __m128i
fold_16(__m128i value, __m128i coefficient)
{
    const __m128i low = _mm_clmulepi64_si128(value, coefficient, 0x00);
    const __m128i high = _mm_clmulepi64_si128(value, coefficient, 0x11);

    return _mm_xor_si128(low, high);
}
#endif

static uint64_t table[8][256];

static void
init_crc64nvme_table(void)
{
    for (size_t value = 0; value < 256; value++) {
        uint64_t crc = value;

        for (unsigned int bit = 0; bit < 8; bit++) {
            crc = (crc >> 1) ^ ((crc & 1) ? CRC64_POLY : 0);
        }

        table[0][value] = crc;
    }

    for (size_t slice = 1; slice < 8; slice++) {
        for (size_t value = 0; value < 256; value++) {
            const uint64_t crc = table[slice - 1][value];
            table[slice][value] = table[0][crc & 0xFF] ^ (crc >> 8);
        }
    }
}

static inline uint64_t
load_le64(const unsigned char *data)
{
    uint64_t value;
    memcpy(&value, data, sizeof(value));

#if defined(__BYTE_ORDER__) && __BYTE_ORDER__ == __ORDER_BIG_ENDIAN__
    value = __builtin_bswap64(value);
#endif

    return value;
}

static uint64_t
crc64_update_table(uint64_t crc, const unsigned char *cursor, size_t remaining)
{
    while (remaining >= 8) {
        const uint64_t value = crc ^ load_le64(cursor);

        // slicing-by-8
        /* clang-format off */
        crc = table[7][(value >> 0) & 0xff] ^
              table[6][(value >> 8) & 0xff] ^
              table[5][(value >> 16) & 0xff] ^
              table[4][(value >> 24) & 0xff] ^
              table[3][(value >> 32) & 0xff] ^
              table[2][(value >> 40) & 0xff] ^
              table[1][(value >> 48) & 0xff] ^
              table[0][value >> 56];
        /* clang-format on */

        cursor += 8;
        remaining -= 8;
    }

    while (remaining > 0) {
        crc = table[0][(crc ^ *cursor++) & 0xFF] ^ (crc >> 8);
        remaining--;
    }

    return crc;
}

static crc64_update_fn crc64_update_impl = crc64_update_table;
static const char *crc64_backend = "table";

#if CRC64NVME_X86_SIMD
TARGET_PCLMUL
static uint64_t
fold_tail(__m128i x[8])
{
    static const uint64_t coefficients[7][2] = {
        {K_895, K_959}, {K_767, K_831}, {K_639, K_703}, {K_511, K_575},
        {K_383, K_447}, {K_255, K_319}, {K_127, K_191},
    };
    __m128i result = x[7];

    for (size_t i = 0; i < 7; i++) {
        const __m128i coefficient = _mm_set_epi64x(
            (long long)coefficients[i][0], (long long)coefficients[i][1]);

        result = _mm_xor_si128(result, fold_16(x[i], coefficient));
    }

    const __m128i k127 = _mm_set_epi64x(0, K_127);
    result = _mm_xor_si128(_mm_srli_si128(result, 8),
                           _mm_clmulepi64_si128(result, k127, 0x00));

    const __m128i poly_mu = _mm_set_epi64x(BARRETT_POLY, BARRETT_MU);
    const __m128i quotient = _mm_clmulepi64_si128(result, poly_mu, 0x00);
    const __m128i reduced = _mm_xor_si128(
        result,
        _mm_xor_si128(_mm_slli_si128(quotient, 8),
                      _mm_clmulepi64_si128(quotient, poly_mu, 0x10)));

    return _mm_extract_epi64(reduced, 1);
}

TARGET_PCLMUL
static uint64_t
crc64_update_pclmul(uint64_t state, const unsigned char *data, size_t length)
{
    if (length < 128) {
        return crc64_update_table(state, data, length);
    }

    __m128i x[8];
    const __m128i coefficient = _mm_set_epi64x(K_1023, K_1087);

    for (size_t i = 0; i < 8; i++) {
        x[i] = _mm_loadu_si128((const __m128i *)(data + i * 16));
    }

    x[0] = _mm_xor_si128(x[0], _mm_cvtsi64_si128((long long)state));

    data += 128;
    length -= 128;

    while (length >= 128) {
        for (size_t i = 0; i < 8; i++) {
            const __m128i block =
                _mm_loadu_si128((const __m128i *)(data + i * 16));

            x[i] = _mm_xor_si128(block, fold_16(x[i], coefficient));
        }

        data += 128;
        length -= 128;
    }

    state = fold_tail(x);
    return crc64_update_table(state, data, length);
}

TARGET_VPCLMUL
static inline __m256i
fold_32(__m256i value, __m256i coefficient)
{
    const __m256i low = _mm256_clmulepi64_epi128(value, coefficient, 0x00);
    const __m256i high = _mm256_clmulepi64_epi128(value, coefficient, 0x11);

    return _mm256_xor_si256(low, high);
}

TARGET_VPCLMUL
static uint64_t
crc64_update_vpclmul(uint64_t state, const unsigned char *data, size_t length)
{
    if (length < 256) {
        return crc64_update_pclmul(state, data, length);
    }

    const __m256i coefficient =
        _mm256_set_epi64x(K_1023, K_1087, K_1023, K_1087);

    __m256i x[4];

    for (size_t i = 0; i < 4; i++) {
        x[i] = _mm256_loadu_si256((const __m256i *)(data + i * 32));
    }

    x[0] =
        _mm256_xor_si256(x[0], _mm256_set_epi64x(0, 0, 0, (long long)state));

    for (size_t i = 0; i < 4; i++) {
        const __m256i block =
            _mm256_loadu_si256((const __m256i *)(data + 128 + i * 32));
        x[i] = _mm256_xor_si256(fold_32(x[i], coefficient), block);
    }

    data += 256;
    length -= 256;

    while (length >= 256) {
        for (size_t half = 0; half < 2; half++) {
            for (size_t i = 0; i < 4; i++) {
                const __m256i block = _mm256_loadu_si256(
                    (const __m256i *)(data + half * 128 + i * 32));
                x[i] = _mm256_xor_si256(fold_32(x[i], coefficient), block);
            }
        }

        data += 256;
        length -= 256;
    }

    __m128i lanes[8];

    for (size_t i = 0; i < 4; i++) {
        lanes[i * 2] = _mm256_castsi256_si128(x[i]);
        lanes[i * 2 + 1] = _mm256_extracti128_si256(x[i], 1);
    }

    _mm256_zeroupper();

    state = fold_tail(lanes);
    return crc64_update_pclmul(state, data, length);
}
#endif

static PyObject *
crc64nvme(PyObject *Py_UNUSED(module), PyObject *args, PyObject *kwargs)
{
    Py_buffer view;
    uint64_t previous = 0;
    PyObject *previous_object = NULL;

    static char *keywords[] = {
        "data",
        "previous",
        NULL,
    };

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "y*|O:crc64nvme", keywords,
                                     &view, &previous_object))
    {
        return NULL;
    }

    if (previous_object != NULL) {
        if (!PyIndex_Check(previous_object)) {
            PyBuffer_Release(&view);
            PyErr_SetString(PyExc_TypeError,
                            "crc64nvme() argument 'previous' must "
                            "be an integer");
            return NULL;
        }

        previous = (uint64_t)PyLong_AsUnsignedLongLong(previous_object);
        if (PyErr_Occurred()) {
            if (PyErr_ExceptionMatches(PyExc_OverflowError)) {
                PyErr_Clear();
                PyBuffer_Release(&view);
                PyErr_SetString(PyExc_OverflowError,
                                "crc64nvme() argument "
                                "'previous' must fit in "
                                "an unsigned 64-bit integer");
            }
            else {
                PyBuffer_Release(&view);
            }
            return NULL;
        }
    }

    uint64_t crc = previous ^ CRC64_MASK;

    // if data very small, do not release GIL
    if (view.len > GIL_RELEASE_THRESHOLD) {
        Py_BEGIN_ALLOW_THREADS;
        crc = crc64_update_impl(crc, view.buf, (size_t)view.len);
        Py_END_ALLOW_THREADS;
    }
    else {
        crc = crc64_update_impl(crc, view.buf, (size_t)view.len);
    }

    PyBuffer_Release(&view);
    return PyLong_FromUnsignedLongLong(crc ^ CRC64_MASK);
}

static int
init_crc64_dispatch(void)
{
    const char *requested = getenv("CRC64NVME_BACKEND");
    const int automatic = requested == NULL || requested[0] == '\0' ||
        strcmp(requested, "auto") == 0;

    crc64_update_impl = crc64_update_table;
    crc64_backend = "table";

#if CRC64NVME_X86_SIMD
    __builtin_cpu_init();
    const int has_pclmul =
        __builtin_cpu_supports("pclmul") && __builtin_cpu_supports("sse4.1");
    const int has_vpclmul = has_pclmul && __builtin_cpu_supports("avx2") &&
        __builtin_cpu_supports("vpclmulqdq");

    if (automatic) {
        if (has_vpclmul) {
            crc64_update_impl = crc64_update_vpclmul;
            crc64_backend = "vpclmul";
        }
        else if (has_pclmul) {
            crc64_update_impl = crc64_update_pclmul;
            crc64_backend = "pclmul";
        }
        return 0;
    }

    if (strcmp(requested, "table") == 0) {
        return 0;
    }

    if (strcmp(requested, "pclmul") == 0) {
        if (has_pclmul) {
            crc64_update_impl = crc64_update_pclmul;
            crc64_backend = "pclmul";
            return 0;
        }
    }
    else if (strcmp(requested, "vpclmul") == 0) {
        if (has_vpclmul) {
            crc64_update_impl = crc64_update_vpclmul;
            crc64_backend = "vpclmul";
            return 0;
        }
    }
    else {
        PyErr_Format(PyExc_ImportError,
                     "invalid CRC64NVME_BACKEND value '%s'; expected auto, "
                     "table, pclmul, or vpclmul",
                     requested);
        return -1;
    }
#else
    if (automatic || strcmp(requested, "table") == 0) {
        return 0;
    }

    if (strcmp(requested, "pclmul") != 0 && strcmp(requested, "vpclmul") != 0)
    {
        PyErr_Format(PyExc_ImportError,
                     "invalid CRC64NVME_BACKEND value '%s'; expected auto, "
                     "table, pclmul, or vpclmul",
                     requested);
        return -1;
    }
#endif

    PyErr_Format(PyExc_ImportError,
                 "CRC64NVME_BACKEND '%s' is not supported by this CPU",
                 requested);
    return -1;
}

static PyMethodDef methods[] = {
    {
        .ml_name = "crc64nvme",
        .ml_meth = _PyCFunction_CAST(crc64nvme),
        .ml_flags = METH_VARARGS | METH_KEYWORDS,
        .ml_doc = PyDoc_STR("crc64nvme($module, /, data, previous=0)\n"
                            "--\n\n"
                            "Calculate a CRC64/NVMe checksum."),
    },
    {
        .ml_name = NULL,
        .ml_meth = NULL,
        .ml_flags = 0,
        .ml_doc = NULL,
    },
};

static struct PyModuleDef module = {
    .m_base = PyModuleDef_HEAD_INIT,
    .m_name = "_crc64nvme",
    .m_size = -1,
    .m_methods = methods,
};

PyMODINIT_FUNC PyInit__crc64nvme(void);

PyMODINIT_FUNC
PyInit__crc64nvme(void)
{
    init_crc64nvme_table();
    if (init_crc64_dispatch() < 0) {
        return NULL;
    }

    PyObject *module_object = PyModule_Create(&module);
    if (module_object == NULL) {
        return NULL;
    }

    if (PyModule_AddStringConstant(module_object, "_backend", crc64_backend) <
        0)
    {
        Py_DECREF(module_object);
        return NULL;
    }

    return module_object;
}

#undef CRC64NVME_X86_SIMD
#undef CRC64_MASK
#undef CRC64_POLY
#undef TARGET_PCLMUL
#undef TARGET_VPCLMUL
#undef PY_SSIZE_T_CLEAN
