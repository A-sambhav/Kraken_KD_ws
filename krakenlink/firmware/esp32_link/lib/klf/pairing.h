#pragma once
#include <stddef.h>
#include <stdint.h>

namespace klf {
constexpr size_t BEACON_SIZE = 12;
constexpr uint32_t PEER_TIMEOUT_MS = 10000;
enum PairState : uint8_t { SEARCHING, PAIRED };
struct Pairing {
  uint8_t role;
  uint32_t net_id;
  uint8_t peer[6];
  bool has_peer;
  PairState state;
  uint32_t last_heard;
  uint32_t conflicts;
  uint32_t foreign;
  uint32_t tx_nopeer;
  uint32_t last_beacon;
};
void pairingInit(Pairing &p, uint8_t role, uint32_t net_id, const uint8_t *saved_peer, uint32_t now=0);
void encodeBeacon(uint8_t role, uint32_t net_id, bool paired, uint8_t out[BEACON_SIZE]);
bool decodeBeacon(const uint8_t *data, size_t len, uint8_t &role, uint32_t &net_id, bool &paired);
// Returns true when a peer was newly adopted and should be persisted.
bool pairingBeacon(Pairing &p, const uint8_t mac[6], const uint8_t *data, size_t len, uint32_t now);
bool pairingFrame(Pairing &p, const uint8_t mac[6], uint32_t now);
void pairingTick(Pairing &p, uint32_t now);
bool pairingDueBeacon(Pairing &p, uint32_t now);
bool pairingAccepts(const Pairing &p, const uint8_t mac[6]);
}
