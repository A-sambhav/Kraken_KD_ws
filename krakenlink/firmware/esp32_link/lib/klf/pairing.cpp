#include "pairing.h"
#include "klf.h"
#include <string.h>

namespace klf {
static bool equalMac(const uint8_t *a, const uint8_t *b) { return memcmp(a, b, 6) == 0; }
void pairingInit(Pairing &p, uint8_t role, uint32_t net_id, const uint8_t *saved_peer, uint32_t now) {
  memset(&p, 0, sizeof(p)); p.role = role; p.net_id = net_id; p.state = SEARCHING;
  if (saved_peer) { memcpy(p.peer, saved_peer, 6); p.has_peer = true; p.last_heard=now; }
}
void encodeBeacon(uint8_t role, uint32_t net_id, bool paired, uint8_t out[BEACON_SIZE]) {
  out[0]='K'; out[1]='L'; out[2]='P'; out[3]=1; out[4]=role; out[5]=paired ? 1 : 0;
  for (uint8_t i=0;i<4;i++) out[6+i]=static_cast<uint8_t>(net_id >> (8*i));
  uint16_t crc=crc16(out,10); out[10]=crc & 0xff; out[11]=crc >> 8;
}
bool decodeBeacon(const uint8_t *d, size_t len, uint8_t &role, uint32_t &net_id, bool &paired) {
  if (!d || len != BEACON_SIZE || d[0]!='K' || d[1]!='L' || d[2]!='P' || d[3]!=1 || d[4]>1 || (d[5]&~1)) return false;
  uint16_t got=static_cast<uint16_t>(d[10]) | (static_cast<uint16_t>(d[11])<<8);
  if (crc16(d,10)!=got) return false;
  role=d[4]; paired=(d[5]&1)!=0; net_id=0;
  for (uint8_t i=0;i<4;i++) net_id |= static_cast<uint32_t>(d[6+i]) << (8*i);
  return true;
}
bool pairingBeacon(Pairing &p, const uint8_t mac[6], const uint8_t *d, size_t len, uint32_t now) {
  uint8_t role; uint32_t net; bool remote_paired;
  if (!decodeBeacon(d,len,role,net,remote_paired) || role==p.role || net!=p.net_id) return false;
  if (p.has_peer && equalMac(p.peer,mac)) { p.last_heard=now; p.state=PAIRED; return false; }
  if (p.has_peer && static_cast<uint32_t>(now-p.last_heard)<=PEER_TIMEOUT_MS) { ++p.conflicts; return false; }
  if (p.state==PAIRED && static_cast<uint32_t>(now-p.last_heard)<=PEER_TIMEOUT_MS) { ++p.conflicts; return false; }
  bool changed=!p.has_peer || !equalMac(p.peer,mac);
  memcpy(p.peer,mac,6); p.has_peer=true; p.last_heard=now; p.state=PAIRED;
  return changed;
}
bool pairingFrame(Pairing &p, const uint8_t mac[6], uint32_t now) {
  if (!p.has_peer || !equalMac(p.peer,mac)) { ++p.foreign; return false; }
  p.last_heard=now; p.state=PAIRED; return true;
}
void pairingTick(Pairing &p, uint32_t now) {
  if (p.state==PAIRED && static_cast<uint32_t>(now-p.last_heard)>PEER_TIMEOUT_MS) p.state=SEARCHING;
}
bool pairingDueBeacon(Pairing &p, uint32_t now) {
  uint32_t interval=p.state==PAIRED ? 2000 : 500;
  if (static_cast<uint32_t>(now-p.last_beacon)<interval) return false;
  p.last_beacon=now; return true;
}
bool pairingAccepts(const Pairing &p, const uint8_t mac[6]) { return p.has_peer && equalMac(p.peer,mac); }
}
