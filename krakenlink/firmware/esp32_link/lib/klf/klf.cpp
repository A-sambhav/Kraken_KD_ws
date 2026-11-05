#include "klf.h"

namespace klf {
uint16_t crc16(const uint8_t *data, size_t len) {
  uint16_t crc = 0xFFFF;
  for (size_t i = 0; i < len; ++i) {
    crc ^= static_cast<uint16_t>(data[i]) << 8;
    for (uint8_t b = 0; b < 8; ++b)
      crc = (crc & 0x8000) ? static_cast<uint16_t>((crc << 1) ^ 0x1021) : static_cast<uint16_t>(crc << 1);
  }
  return crc;
}

size_t cobsEncode(const uint8_t *in, size_t len, uint8_t *out, size_t cap) {
  if (!out || cap == 0 || (!in && len)) return 0;
  size_t codePos = 0, write = 1;
  uint8_t code = 1;
  for (size_t i = 0; i < len; ++i) {
    if (in[i] == 0) {
      out[codePos] = code;
      if (write >= cap) return 0;
      codePos = write++; code = 1;
    } else {
      if (write >= cap) return 0;
      out[write++] = in[i];
      if (++code == 0xFF) {
        out[codePos] = code;
        if (write >= cap) return 0;
        codePos = write++; code = 1;
      }
    }
  }
  out[codePos] = code;
  return write;
}

size_t cobsDecode(const uint8_t *in, size_t len, uint8_t *out, size_t cap) {
  if (!in || !out || len == 0) return 0;
  size_t i = 0, n = 0;
  while (i < len) {
    uint8_t code = in[i++];
    if (code == 0 || static_cast<size_t>(code - 1) > len - i) return 0;
    size_t count = code - 1;
    if (count > cap - n) return 0;
    for (size_t j = 0; j < count; ++j) out[n++] = in[i++];
    if (code != 0xFF && i < len) {
      if (n >= cap) return 0;
      out[n++] = 0;
    }
  }
  return n;
}

bool validateFrame(const uint8_t *f, size_t len) {
  if (!f || len < 8 || f[0] != 0xA7 || (f[1] >> 4) != 1 || (f[1] & 0x0E)) return false;
  if (f[3] > MAX_PAYLOAD || len != static_cast<size_t>(f[3]) + 8) return false;
  uint16_t got = static_cast<uint16_t>(f[len - 2]) | (static_cast<uint16_t>(f[len - 1]) << 8);
  return crc16(f, len - 2) == got;
}

size_t makeFrame(uint8_t type, uint16_t seq, const uint8_t *payload, size_t plen,
                 uint8_t *out, size_t cap) {
  if (!out || plen > MAX_PAYLOAD || (!payload && plen) || cap < plen + 8) return 0;
  out[0] = 0xA7; out[1] = 0x10; out[2] = type; out[3] = static_cast<uint8_t>(plen);
  out[4] = seq & 0xFF; out[5] = seq >> 8;
  for (size_t i = 0; i < plen; ++i) out[6 + i] = payload[i];
  uint16_t crc = crc16(out, plen + 6);
  out[plen + 6] = crc & 0xFF; out[plen + 7] = crc >> 8;
  return plen + 8;
}
}
