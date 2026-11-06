#include <esp_arduino_version.h>
#include <Arduino.h>
#include <WiFi.h>
#include <Preferences.h>
#include <esp_now.h>
#include <esp_wifi.h>
#include "config.h"
#include "klf.h"
#include "pairing.h"

#if defined(ROLE_AIR) == defined(ROLE_GROUND)
#error "Define exactly one of ROLE_AIR or ROLE_GROUND"
#endif
static constexpr uint8_t ROLE_ID =
#ifdef ROLE_AIR
  0;
#else
  1;
#endif
static Stream &host =
#if defined(ROLE_AIR) && !defined(AIR_HOST_USB)
  Serial2;
#else
  Serial;
#endif

struct Packet { uint16_t len; uint8_t mac[6]; uint8_t bytes[klf::MAX_FRAME]; };
static QueueHandle_t toRadio, toHost, fromRadio;
static uint32_t txOk=0, txFail=0, rxOk=0, rxBad=0, uartBad=0, txNoPeer=0;
static int8_t lastRssi=0;
static uint16_t statusSeq=0;
static uint8_t uartEncoded[UART_FRAME_MAX], uartRaw[klf::MAX_FRAME];
static size_t uartUsed=0;
static klf::Pairing pairing;
static Preferences preferences;
static bool nvsReady=false;
#ifdef FORCE_PEER_MAC
static const uint8_t forcePeerMac[6]={FORCE_PEER_MAC};
#endif

static void dropOldestSend(QueueHandle_t q, const Packet &p) {
  if (xQueueSend(q,&p,0)!=pdTRUE) { Packet discarded; xQueueReceive(q,&discarded,0); xQueueSend(q,&p,0); }
}
static void onSent(const uint8_t *, esp_now_send_status_t s) { if(s==ESP_NOW_SEND_SUCCESS) ++txOk; else ++txFail; }
#if ESP_ARDUINO_VERSION_MAJOR >= 3
static void onRecv(const esp_now_recv_info_t *info, const uint8_t *data, int len) {
  const uint8_t *mac=info ? info->src_addr : nullptr;
#else
static void onRecv(const uint8_t *mac, const uint8_t *data, int len) {
#endif
  if (!mac || !data || len<=0 || len>static_cast<int>(klf::MAX_FRAME)) { ++rxBad; return; }
  Packet p; p.len=static_cast<uint16_t>(len); memcpy(p.mac,mac,6); memcpy(p.bytes,data,len);
  if (xQueueSend(fromRadio,&p,0)!=pdTRUE) ++rxBad;
#if ESP_ARDUINO_VERSION_MAJOR >= 3
  if(info && info->rx_ctrl) lastRssi=info->rx_ctrl->rssi;
#endif
}

static bool addPeer(const uint8_t *mac) {
  if (esp_now_is_peer_exist(mac)) return true;
  esp_now_peer_info_t peer={}; memcpy(peer.peer_addr,mac,6); peer.channel=ESPNOW_CHANNEL; peer.encrypt=false;
  return esp_now_add_peer(&peer)==ESP_OK;
}
static const uint8_t broadcastMac[6]={0xff,0xff,0xff,0xff,0xff,0xff};
static void savePeer() { if(nvsReady && pairing.has_peer) preferences.putBytes("peer",pairing.peer,6); }
static void emitStatus() {
  uint8_t payload[31]={0}; uint32_t values[5]={txOk,txFail,rxOk,rxBad,uartBad};
  for(int k=0;k<5;k++) for(int b=0;b<4;b++) payload[k*4+b]=values[k]>>(8*b);
  payload[20]=static_cast<uint8_t>(lastRssi); payload[21]=ROLE_ID; payload[22]=pairing.state==klf::PAIRED;
  if(pairing.has_peer) memcpy(payload+23,pairing.peer,6);
  uint16_t nopeer=txNoPeer; payload[29]=nopeer&0xff; payload[30]=nopeer>>8;
  Packet p={}; p.len=klf::makeFrame(0x7f,statusSeq++,payload,sizeof(payload),p.bytes,sizeof(p.bytes));
  if(p.len) dropOldestSend(toHost,p);
}
static void handleHostFrame(const uint8_t *encoded,size_t len) {
  size_t rawLen=klf::cobsDecode(encoded,len,uartRaw,sizeof(uartRaw));
  if(!rawLen || !klf::validateFrame(uartRaw,rawLen)) { ++uartBad; return; }
  if(uartRaw[2]==0x7f) return;
  Packet p={}; p.len=rawLen; memcpy(p.bytes,uartRaw,rawLen); dropOldestSend(toRadio,p);
}
static void processRadioPacket(const Packet &p,uint32_t now) {
  uint8_t role; uint32_t net; bool paired;
  if(klf::decodeBeacon(p.bytes,p.len,role,net,paired)) {
#ifdef FORCE_PEER_MAC
    if(memcmp(p.mac,forcePeerMac,6)!=0) return;
#endif
    uint8_t oldPeer[6]; bool hadPeer=pairing.has_peer; if(hadPeer) memcpy(oldPeer,pairing.peer,6);
    bool adopted=klf::pairingBeacon(pairing,p.mac,p.bytes,p.len,now);
#ifdef FORCE_PEER_MAC
    (void)adopted;
#else
    if(adopted) { if(hadPeer && memcmp(oldPeer,p.mac,6)!=0) esp_now_del_peer(oldPeer); addPeer(p.mac); savePeer(); }
#endif
    return;
  }
  if(!klf::validateFrame(p.bytes,p.len)) { ++rxBad; return; }
  if(!klf::pairingFrame(pairing,p.mac,now)) return;
  if(p.bytes[2]==0x7f) return;
  dropOldestSend(toHost,p); ++rxOk;
}
static void updateLed(uint32_t now) {
#ifdef STATUS_LED_RGB_PIN
  static uint32_t lastBlink=0, lastTxFail=0, redUntil=0; static bool on=false;
  uint8_t r=0,g=0,b=0;
  if(pairing.state==klf::PAIRED) g=18;
  else { if(static_cast<uint32_t>(now-lastBlink)>=250) { lastBlink=now; on=!on; } if(on) b=18; }
  if(txFail!=lastTxFail) { lastTxFail=txFail; redUntil=now+120; }
  if(static_cast<int32_t>(redUntil-now)>0) r=18;
  neopixelWrite(STATUS_LED_RGB_PIN,r,g,b);
#else
  (void)now;
#endif
}
void setup() {
#if defined(ROLE_AIR) && !defined(AIR_HOST_USB)
  Serial.begin(115200); Serial2.begin(AIR_UART_BAUD,SERIAL_8N1,AIR_UART_RX_PIN,AIR_UART_TX_PIN);
#else
  Serial.begin(UART_BAUD);
#endif
  toRadio=xQueueCreate(TX_QUEUE_DEPTH,sizeof(Packet)); toHost=xQueueCreate(TX_QUEUE_DEPTH,sizeof(Packet)); fromRadio=xQueueCreate(RX_QUEUE_DEPTH,sizeof(Packet));
  uint8_t saved[6]; const uint8_t *savedPtr=nullptr;
#ifdef FORCE_PEER_MAC
  savedPtr=forcePeerMac;
#else
  preferences.begin("klink",false); nvsReady=true;
  if(preferences.getBytesLength("peer")==6 && preferences.getBytes("peer",saved,6)==6) savedPtr=saved;
#endif
  klf::pairingInit(pairing,ROLE_ID,NET_ID,savedPtr,millis());
  WiFi.mode(WIFI_STA); WiFi.disconnect(); esp_wifi_set_channel(ESPNOW_CHANNEL,WIFI_SECOND_CHAN_NONE);
#if USE_LR_MODE
  esp_wifi_set_protocol(WIFI_IF_STA,WIFI_PROTOCOL_LR);
#endif
  if(esp_now_init()!=ESP_OK) return;
  esp_now_register_send_cb(onSent); esp_now_register_recv_cb(onRecv); addPeer(broadcastMac);
  if(pairing.has_peer) addPeer(pairing.peer);
}
void loop() {
  while(host.available()) { uint8_t byte=host.read(); if(byte==0) { if(uartUsed) handleHostFrame(uartEncoded,uartUsed); uartUsed=0; }
    else if(uartUsed<sizeof(uartEncoded)) uartEncoded[uartUsed++]=byte; else { uartUsed=0; ++uartBad; } }
  uint32_t now=millis(); Packet incoming;
  while(xQueueReceive(fromRadio,&incoming,0)==pdTRUE) processRadioPacket(incoming,now);
  klf::pairingTick(pairing,now);
  if(klf::pairingDueBeacon(pairing,now)) { uint8_t beacon[klf::BEACON_SIZE]; klf::encodeBeacon(ROLE_ID,NET_ID,pairing.state==klf::PAIRED,beacon); esp_now_send(broadcastMac,beacon,sizeof(beacon)); }
  Packet p;
  if(xQueueReceive(toRadio,&p,0)==pdTRUE) {
    if(!pairing.has_peer) ++txNoPeer;
    else { addPeer(pairing.peer); if(esp_now_send(pairing.peer,p.bytes,p.len)!=ESP_OK) ++txFail; }
  }
  if(xQueueReceive(toHost,&p,0)==pdTRUE) { uint8_t encoded[UART_FRAME_MAX]; size_t n=klf::cobsEncode(p.bytes,p.len,encoded,sizeof(encoded)-1); if(n) { host.write(encoded,n); host.write(static_cast<uint8_t>(0)); } }
  static uint32_t lastStatus=0; if(now-lastStatus>=1000) { lastStatus=now; emitStatus(); }
  updateLed(now); delay(1);
}
