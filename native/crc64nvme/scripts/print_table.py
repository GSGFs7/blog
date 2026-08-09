poly = 0x9A6C9329AC4BC9B5
table = []

if __name__ == "__main__":
    for value in range(256):
        crc = value
        for _ in range(8):
            crc = (crc >> 1) ^ (poly if crc & 1 else 0)
        table.append(crc)

    print("static const uint64_t table[256] = {")
    for offset in range(0, 256, 4):
        values = table[offset : offset + 4]
        print("  " + ", ".join(f"UINT64_C(0x{value:016X})" for value in values) + ",")
    print("};")
