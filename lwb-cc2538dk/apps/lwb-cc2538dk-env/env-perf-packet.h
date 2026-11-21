#ifndef ENV_PERF_PACKET_H_
#define ENV_PERF_PACKET_H_
#include <stdint.h>
#define UP_MAGIC 0xe7
#define UP_VERSION 1
#define UP_DATA 1
#define UP_REPORT 2
#define UP_TIME_VALID 0x80
#define UP_SENSOR_MASK 0x07
#define UP_REPORT_DRAIN_TIMEOUT 0x01
/* New 28-byte wire protocol, little endian on CC2538. The old 18-byte
 * env_packet_t remains local to the sensor/OLED. No RTC/battery is invented. */
typedef struct __attribute__((packed)) {
  uint8_t magic, version, type, flags;
  uint32_t run;
  uint16_t source, seq;
  uint32_t tx_network_ticks; /* Before enqueue; NOT radio TX. */
  union {
    struct __attribute__((packed)) {
      int16_t hdc_temp_x10;
      uint16_t hdc_hum_x10, light_raw;
      int16_t bmp_temp_x10;
      int32_t pressure_pa;
    } sensor;
    struct __attribute__((packed)) {
      uint16_t generated, queued, tx_started, queue_failed;
      uint16_t deadline_missed, tx_start_failed;
    } report;
  } body;
} up_packet_t;
typedef char up_size_28[(sizeof(up_packet_t) == 28) ? 1 : -1];
#endif
