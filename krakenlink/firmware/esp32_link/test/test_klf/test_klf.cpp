#include <unity.h>
#include <string.h>
#include "klf.h"
#include "vectors.h"

void test_crc_vector() {
  const uint8_t text[] = "123456789";
  TEST_ASSERT_EQUAL_HEX16(0x29B1, klf::crc16(text, 9));
}

void test_cobs_round_trip_with_zeroes() {
  uint8_t input[] = {0, 1, 0, 2, 3, 0, 0, 255};
  uint8_t encoded[32], decoded[32];
  size_t n = klf::cobsEncode(input, sizeof(input), encoded, sizeof(encoded));
  TEST_ASSERT_GREATER_THAN(0, n);
  TEST_ASSERT_EQUAL(0, memchr(encoded, 0, n) != nullptr);
  size_t m = klf::cobsDecode(encoded, n, decoded, sizeof(decoded));
  TEST_ASSERT_EQUAL(sizeof(input), m);
  TEST_ASSERT_EQUAL_MEMORY(input, decoded, m);
}

void test_python_golden_frames_validate() {
  TEST_ASSERT_TRUE(klf::validateFrame(vector_frame_0, sizeof(vector_frame_0)));
  TEST_ASSERT_TRUE(klf::validateFrame(vector_frame_1, sizeof(vector_frame_1)));
  TEST_ASSERT_TRUE(klf::validateFrame(vector_frame_2, sizeof(vector_frame_2)));
  uint8_t bad[sizeof(vector_frame_0)];
  memcpy(bad, vector_frame_0, sizeof(bad)); bad[0] ^= 1;
  TEST_ASSERT_FALSE(klf::validateFrame(bad, sizeof(bad)));
  memcpy(bad, vector_frame_0, sizeof(bad)); bad[1] = 0x20;
  TEST_ASSERT_FALSE(klf::validateFrame(bad, sizeof(bad)));
  memcpy(bad, vector_frame_0, sizeof(bad)); bad[3] = 121;
  TEST_ASSERT_FALSE(klf::validateFrame(bad, sizeof(bad)));
  TEST_ASSERT_FALSE(klf::validateFrame(vector_frame_0, sizeof(vector_frame_0) - 1));
  memcpy(bad, vector_frame_0, sizeof(bad)); bad[sizeof(bad)-1] ^= 1;
  TEST_ASSERT_FALSE(klf::validateFrame(bad, sizeof(bad)));
}

int main(int, char **) {
  UNITY_BEGIN();
  RUN_TEST(test_crc_vector);
  RUN_TEST(test_cobs_round_trip_with_zeroes);
  RUN_TEST(test_python_golden_frames_validate);
  return UNITY_END();
}
