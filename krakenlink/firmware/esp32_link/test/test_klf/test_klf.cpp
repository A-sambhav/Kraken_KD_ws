#include <unity.h>
#include <string.h>
#include "klf.h"
#include "pairing.h"
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

static const uint8_t macA[6]={1,2,3,4,5,6}, macB[6]={6,5,4,3,2,1};
void test_beacon_round_trip_and_bad_crc() {
  uint8_t b[klf::BEACON_SIZE], role=9; uint32_t net=0; bool paired=false;
  klf::encodeBeacon(0,0x4B4C4E31UL,true,b);
  TEST_ASSERT_EQUAL(12,sizeof(b));
  TEST_ASSERT_TRUE(klf::decodeBeacon(b,sizeof(b),role,net,paired));
  TEST_ASSERT_EQUAL_UINT8(0,role); TEST_ASSERT_EQUAL_HEX32(0x4B4C4E31UL,net); TEST_ASSERT_TRUE(paired);
  b[7]^=1; TEST_ASSERT_FALSE(klf::decodeBeacon(b,sizeof(b),role,net,paired));
}
void test_pairing_adopts_valid_opposite_beacon_and_filters() {
  klf::Pairing p; uint8_t b[12]; klf::pairingInit(p,1,0x4B4C4E31UL,nullptr);
  klf::encodeBeacon(0,0x4B4C4E31UL,false,b);
  TEST_ASSERT_TRUE(klf::pairingBeacon(p,macA,b,sizeof(b),100));
  TEST_ASSERT_EQUAL(klf::PAIRED,p.state); TEST_ASSERT_TRUE(klf::pairingAccepts(p,macA));
  klf::encodeBeacon(1,0x4B4C4E31UL,false,b); TEST_ASSERT_FALSE(klf::pairingBeacon(p,macB,b,sizeof(b),200));
  klf::encodeBeacon(0,0x12345678UL,false,b); TEST_ASSERT_FALSE(klf::pairingBeacon(p,macB,b,sizeof(b),200));
  klf::encodeBeacon(0,0x4B4C4E31UL,false,b);
  TEST_ASSERT_FALSE(klf::pairingBeacon(p,macB,b,sizeof(b),300)); TEST_ASSERT_EQUAL_UINT32(1,p.conflicts);
  TEST_ASSERT_FALSE(klf::pairingFrame(p,macB,400)); TEST_ASSERT_EQUAL_UINT32(1,p.foreign);
  TEST_ASSERT_TRUE(klf::pairingFrame(p,macA,500));
}
void test_pairing_timeout_allows_replacement_and_saved_peer() {
  klf::Pairing p; uint8_t b[12]; klf::pairingInit(p,1,0x4B4C4E31UL,macA);
  TEST_ASSERT_EQUAL(klf::SEARCHING,p.state); TEST_ASSERT_TRUE(klf::pairingFrame(p,macA,100));
  klf::pairingTick(p,10101); TEST_ASSERT_EQUAL(klf::SEARCHING,p.state);
  klf::encodeBeacon(0,0x4B4C4E31UL,false,b);
  TEST_ASSERT_TRUE(klf::pairingBeacon(p,macB,b,sizeof(b),10102));
  TEST_ASSERT_EQUAL_MEMORY(macB,p.peer,6); TEST_ASSERT_EQUAL(klf::PAIRED,p.state);
}

int main(int, char **) {
  UNITY_BEGIN();
  RUN_TEST(test_crc_vector);
  RUN_TEST(test_cobs_round_trip_with_zeroes);
  RUN_TEST(test_python_golden_frames_validate);
  RUN_TEST(test_beacon_round_trip_and_bad_crc);
  RUN_TEST(test_pairing_adopts_valid_opposite_beacon_and_filters);
  RUN_TEST(test_pairing_timeout_allows_replacement_and_saved_peer);
  return UNITY_END();
}
