poly = 0x9A6C9329AC4BC9B5
base_table = []
tables = []

if __name__ == "__main__":
    for value in range(256):
        crc = value
        for _ in range(8):
            crc = (crc >> 1) ^ (poly if crc & 1 else 0)
        base_table.append(crc)

    tables.append(base_table)
    for _ in range(1, 8):
        previous_table = tables[-1]
        tables.append(
            [base_table[value & 0xFF] ^ (value >> 8) for value in previous_table]
        )

    print("static const uint64_t table[8][256] = {")
    for table in tables:
        print("{")
        for offset in range(0, 256, 4):
            values = table[offset : offset + 4]
            print(
                "  " + ", ".join(f"UINT64_C(0x{value:016X})" for value in values) + ","
            )
        print("},")
    print("};")
