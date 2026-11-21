/*
 * Software radio-on accounting for Glossy floods (compiled only with GLOSSY_RADIO_STATS=1).
 *
 * The radio is switched on in glossy_start() and off in glossy_stop() (see
 * docs/RADIO_STATS_NOTES.md). This header only holds the arithmetic so that it can be
 * unit-tested on a host; it touches no hardware and adds nothing to the relay/TX-trigger
 * path of the Glossy ISRs. Timestamps are RTIMER_NOW() values: the 32-bit counter may wrap,
 * so every interval is computed with unsigned 32-bit subtraction (valid for floods < 2^32
 * ticks, ~36 h at 32768 Hz) and summed into 64-bit accumulators.
 */
#ifndef GLOSSY_RADIO_STATS_H_
#define GLOSSY_RADIO_STATS_H_

#include <stdint.h>

/* Accumulated since boot. Readers must use glossy_rs_read() (writers run in ISRs). */
typedef struct {
  uint64_t radio_on_ticks;  /* sum over floods of (radio off - radio on), rtimer ticks */
  uint64_t tx_on_us;        /* ESTIMATED TX airtime: tx_cnt * (6 + len) * 32 us per flood */
  uint32_t floods;          /* completed on/off pairs */
  uint32_t tx_count;        /* completed transmissions */
} glossy_radio_stats_t;

typedef struct {
  volatile uint32_t seq;    /* odd while the accumulators are being updated (seqlock) */
  uint32_t t_on;            /* RTIMER_NOW() at the last radio-on */
  volatile uint8_t on;      /* 1 between radio on and radio off */
  glossy_radio_stats_t acc;
} glossy_rs_t;

#define GLOSSY_RS_BARRIER() __asm__ volatile("" ::: "memory")
/* IEEE 802.15.4 O-QPSK: 32 us per byte; SHR = 4 preamble + 1 SFD bytes, PHR = 1 length byte. */
#define GLOSSY_RS_PHY_OVERHEAD_BYTES 6
#define GLOSSY_RS_US_PER_BYTE 32

/* Radio switched on. A second start while already on keeps the first timestamp. */
static inline void glossy_rs_on(glossy_rs_t *rs, uint32_t now)
{
  if(!rs->on) {
    rs->t_on = now;
    GLOSSY_RS_BARRIER();
    rs->on = 1;
  }
}

/* Radio switched off. tx_cnt / tx_rx_len: completed transmissions of this flood and the
 * length byte (PSDU incl. FCS) of the frame. Ignored if the radio was not counted as on
 * (the atomic exchange also makes a stop that preempts another stop count once). */
static inline void glossy_rs_off(glossy_rs_t *rs, uint32_t now, uint8_t tx_cnt, uint8_t tx_rx_len)
{
  if(!__atomic_exchange_n(&rs->on, (uint8_t)0, __ATOMIC_ACQ_REL)) return;
  rs->seq++;
  GLOSSY_RS_BARRIER();
  rs->acc.radio_on_ticks += (uint32_t)(now - rs->t_on);
  rs->acc.floods++;
  rs->acc.tx_count += tx_cnt;
  rs->acc.tx_on_us += (uint64_t)tx_cnt * (uint32_t)(GLOSSY_RS_PHY_OVERHEAD_BYTES + tx_rx_len) *
                      GLOSSY_RS_US_PER_BYTE;
  GLOSSY_RS_BARRIER();
  rs->seq++;
}

/* Consistent snapshot from process context (retries if an ISR updates meanwhile). */
static inline void glossy_rs_read(glossy_rs_t *rs, glossy_radio_stats_t *out)
{
  uint32_t s;
  do {
    s = rs->seq;
    GLOSSY_RS_BARRIER();
    *out = rs->acc;
    GLOSSY_RS_BARRIER();
  } while((s & 1u) || s != rs->seq);
}

#endif /* GLOSSY_RADIO_STATS_H_ */
