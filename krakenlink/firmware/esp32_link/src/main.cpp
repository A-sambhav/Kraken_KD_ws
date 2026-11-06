#include <esp_arduino_version.h>
#include <Arduino.h>
#include <WiFi.h>
#include <esp_now.h>
#include <esp_wifi.h>
#include "config.h"
#include "klf.h"

#if defined(ROLE_AIR) == defined(ROLE_GROUND)
#error "Define exactly one of ROLE_AIR or ROLE_GROUND"
#endif

static constexpr uint8_t ROLE_ID =
#ifdef ROLE_AIR
  0;
#else
  1;
#endif
static const uint8_t peerMac[6] = PEER_MAC;
// Stream covers both HardwareSerial (UART) and HWCDC (ESP32-S3 native USB).
static Stream &host =
#ifdef ROLE_AIR
  Serial2;
#else
  Serial;
#endif

struct Packet { uint16_t len; uint8_t bytes[klf::MAX_FRAME]; };
static QueueHandle_t toRadio, toHost;
static volatile uint32_t txOk = 0, txFail = 0, rxOk = 0, rxBad = 0, uartBad = 0;
static volatile int8_t lastRssi = 0;
static uint16_t statusSeq = 0;
static uint8_t uartEncoded[UART_FRAME_MAX], uartRaw[klf::MAX_FRAME];
static size_t uartUsed = 0;

static void dropOldestSend(QueueHandle_t q, const Packet &p) {
  if (xQueueSend(q, &p, 0) != pdTRUE) {
    Packet discarded;
    xQueueReceive(q, &discarded, 0);
    xQueueSend(q, &p, 0);
  }
}

static void onSent(const uint8_t *, esp_now_send_status_t status) {
  if (status == ESP_NOW_SEND_SUCCESS) ++txOk; else ++txFail;
}

#if ESP_ARDUINO_VERSION_MAJOR >= 3
static void onRecv(const esp_now_recv_info_t *info, const uint8_t *data, int len) {
#else
// Arduino core 2.x: callback gets the sender MAC only; RSSI is not available here (reported as 0).
static void onRecv(const uint8_t *, const uint8_t *data, int len) {
#endif
  if (!data || len < 8 || len > static_cast<int>(klf::MAX_FRAME) || !klf::validateFrame(data, len)) {
    ++rxBad; return;
  }
  if (data[2] == 0x7F) return;
  Packet p; p.len = static_cast<uint16_t>(len);
  memcpy(p.bytes, data, len);
#if ESP_ARDUINO_VERSION_MAJOR >= 3
  if (info && info->rx_ctrl) lastRssi = info->rx_ctrl->rssi;
#endif
  dropOldestSend(toHost, p);
  ++rxOk;
}

static void emitStatus() {
  uint8_t payload[22];
  uint32_t values[5] = {txOk, txFail, rxOk, rxBad, uartBad};
  for (int k = 0; k < 5; ++k) for (int b = 0; b < 4; ++b) payload[k * 4 + b] = values[k] >> (8 * b);
  payload[20] = static_cast<uint8_t>(lastRssi);
  payload[21] = ROLE_ID;
  Packet p; p.len = klf::makeFrame(0x7F, statusSeq++, payload, sizeof(payload), p.bytes, sizeof(p.bytes));
  if (p.len) dropOldestSend(toHost, p);
}

static void handleHostFrame(const uint8_t *encoded, size_t len) {
  size_t rawLen = klf::cobsDecode(encoded, len, uartRaw, sizeof(uartRaw));
  if (!rawLen || !klf::validateFrame(uartRaw, rawLen)) { ++uartBad; return; }
  if (uartRaw[2] == 0x7F) return;
  Packet p; p.len = rawLen; memcpy(p.bytes, uartRaw, rawLen);
  dropOldestSend(toRadio, p);
}

void setup() {
#ifdef ROLE_AIR
  Serial.begin(115200);
  Serial2.begin(AIR_UART_BAUD, SERIAL_8N1, AIR_UART_RX_PIN, AIR_UART_TX_PIN);
#else
  Serial.begin(UART_BAUD);
#endif
  toRadio = xQueueCreate(TX_QUEUE_DEPTH, sizeof(Packet));
  toHost = xQueueCreate(TX_QUEUE_DEPTH, sizeof(Packet));
  WiFi.mode(WIFI_STA);
  WiFi.disconnect();
  esp_wifi_set_channel(ESPNOW_CHANNEL, WIFI_SECOND_CHAN_NONE);
#if USE_LR_MODE
  esp_wifi_set_protocol(WIFI_IF_STA, WIFI_PROTOCOL_LR);
#endif
  if (esp_now_init() != ESP_OK) return;
  esp_now_register_send_cb(onSent);
  esp_now_register_recv_cb(onRecv);
  esp_now_peer_info_t peer = {};
  memcpy(peer.peer_addr, peerMac, 6); peer.channel = ESPNOW_CHANNEL; peer.encrypt = false;
  esp_now_add_peer(&peer);
#if ENABLE_BROADCAST_PAIRING
  const uint8_t broadcast[6] = {0xFF,0xFF,0xFF,0xFF,0xFF,0xFF};
  memcpy(peer.peer_addr, broadcast, 6); esp_now_add_peer(&peer);
#endif
}

void loop() {
  while (host.available()) {
    uint8_t byte = host.read();
    if (byte == 0) {
      if (uartUsed) handleHostFrame(uartEncoded, uartUsed);
      uartUsed = 0;
    } else if (uartUsed < sizeof(uartEncoded)) uartEncoded[uartUsed++] = byte;
    else { uartUsed = 0; ++uartBad; }
  }

  Packet p;
  if (xQueueReceive(toRadio, &p, 0) == pdTRUE) {
#if ENABLE_BROADCAST_PAIRING
    esp_now_send(peerMac, p.bytes, p.len);
#else
    esp_now_send(peerMac, p.bytes, p.len);
#endif
  }
  if (xQueueReceive(toHost, &p, 0) == pdTRUE) {
    uint8_t encoded[UART_FRAME_MAX];
    size_t n = klf::cobsEncode(p.bytes, p.len, encoded, sizeof(encoded) - 1);
    if (n) { host.write(encoded, n); host.write(static_cast<uint8_t>(0)); }
  }
  static uint32_t lastStatus = 0;
  if (millis() - lastStatus >= 1000) { lastStatus = millis(); emitStatus(); }
  delay(1);
}
