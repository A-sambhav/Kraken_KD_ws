#pragma once

// Replace with the MAC address of the other ESP32.
#define PEER_MAC {0x24, 0x6F, 0x28, 0x00, 0x00, 0x01}
#define ESPNOW_CHANNEL 1

// Air-side host UART. Pi TX -> ESP32 RX (GPIO16), Pi RX <- ESP32 TX (GPIO17).
#define AIR_UART_RX_PIN 16
#define AIR_UART_TX_PIN 17
#define AIR_UART_BAUD 460800
#define UART_BAUD 460800

// Optional pairing fallback sends to broadcast when the configured peer is absent.
#define ENABLE_BROADCAST_PAIRING 0
#define USE_LR_MODE 0

#define UART_FRAME_MAX 130
#define TX_QUEUE_DEPTH 8
