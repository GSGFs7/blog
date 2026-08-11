#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <stdint.h>
#include <string.h>

#define CRC64_POLY UINT64_C(0x9A6C9329AC4BC9B5)
#define CRC64_MASK UINT64_MAX

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
    const unsigned char *cursor = view.buf;
    Py_ssize_t remaining = view.len;

    // if data very small, do not release GIL
    if (remaining > 8 * 1024) {
        Py_BEGIN_ALLOW_THREADS;
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

        Py_END_ALLOW_THREADS;
    }
    else {
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
    }

    PyBuffer_Release(&view);
    return PyLong_FromUnsignedLongLong(crc ^ CRC64_MASK);
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
    return PyModule_Create(&module);
}

#undef CRC64_MASK
#undef CRC64_POLY
#undef PY_SSIZE_T_CLEAN
