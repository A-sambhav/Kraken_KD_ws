#pragma once
#include <stddef.h>
#include <stdint.h>

namespace klf {
constexpr size_t MAX_PAYLOAD = 120;
constexpr size_t MAX_FRAME = 128;
uint16_t crc16(const uint8_t *data, size_t len);
size_t cobsEncode(const uint8_t *input, size_t len, uint8_t *output, size_t capacity);
size_t cobsDecode(const uint8_t *input, size_t len, uint8_t *output, size_t capacity);
bool validateFrame(const uint8_t *frame, size_t len);
size_t makeFrame(uint8_t type, uint16_t seq, const uint8_t *payload, size_t payloadLen,
                 uint8_t *out, size_t capacity);
}
