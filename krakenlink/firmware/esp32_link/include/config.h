#pragma once

#define NET_ID 0x4B4C4E31UL
#define ESPNOW_CHANNEL 1

// Optional fixed peer: define FORCE_PEER_MAC as six comma-separated bytes.
// Example: -DFORCE_PEER_MAC=0x01,0x02,0x03,0x04,0x05,0x06

// Air-side host UART. Pi TX -> ESP32 RX (GPIO16), Pi RX <- ESP32 TX (GPIO17).
#define AIR_UART_RX_PIN 16
#define AIR_UART_TX_PIN 17
#define AIR_UART_BAUD 460800
#define UART_BAUD 460800

#define USE_LR_MODE 0
#define UART_FRAME_MAX 130
#define TX_QUEUE_DEPTH 8
#define RX_QUEUE_DEPTH 16
