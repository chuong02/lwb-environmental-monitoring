#ifndef ENV_PERF_STATS_H_
#define ENV_PERF_STATS_H_
#include <stdint.h>
typedef struct {
  uint16_t unique, duplicate, out_of_order, highest_seq, delay_count;
  uint32_t delay_min_ticks, delay_max_ticks;
  uint64_t delay_sum_ticks;
} up_stats_t;
/* Return 0=invalid, 1=unique, 2=duplicate. */
static inline uint8_t up_stats_rx(up_stats_t *s, uint8_t *seen,
  uint16_t seq, uint16_t expected, uint8_t delay_valid, uint32_t delay)
{
  uint16_t i;
  uint8_t mask;
  if(seq == 0 || seq > expected) return 0;
  i = seq - 1; mask = (uint8_t)(1u << (i & 7));
  if(seen[i >> 3] & mask) { s->duplicate++; return 2; }
  seen[i >> 3] |= mask; s->unique++;
  if(seq < s->highest_seq) s->out_of_order++;
  if(seq > s->highest_seq) s->highest_seq = seq;
  if(delay_valid) {
    if(!s->delay_count || delay < s->delay_min_ticks) s->delay_min_ticks = delay;
    if(delay > s->delay_max_ticks) s->delay_max_ticks = delay;
    s->delay_count++; s->delay_sum_ticks += delay;
  }
  return 1;
}
static inline uint8_t up_delay(uint32_t tx, uint32_t rx,
  uint8_t tx_valid, uint8_t rx_valid, uint32_t max_ticks, uint32_t *out)
{
  uint32_t d = rx - tx; /* Modulo 2^32; numeric zero is legitimate. */
  if(!tx_valid || !rx_valid || d > max_ticks) { *out = 0; return 0; }
  *out = d; return 1;
}
/* Percentage *100; -1 means unavailable. */
static inline int32_t up_ratio(uint16_t received, uint16_t denominator)
{
  if(!denominator) return -1;
  return ((uint32_t)received * 10000UL) / denominator;
}

/* ---- Continuous mode (PACKETS=0) helpers; unused when PACKETS>0 ----------
 * The wire seq stays 16 bit (28-byte format is frozen). The n-th DATA packet
 * (n = 1, 2, ...) carries seq = ((n - 1) mod 65535) + 1, so seq cycles through
 * 1..65535 and 0 stays invalid. The HOST rebuilds ordering with serial-number
 * arithmetic on that circle (half range = 32767 packets). */
#define UP_SEQ_MOD 65535UL
static inline uint16_t up_seq_wire(uint32_t n)
{
  return (uint16_t)(((n - 1UL) % UP_SEQ_MOD) + 1UL);
}
/* Signed distance a - b on the 1..65535 circle, in -32767..32767. */
static inline int32_t up_seq_diff(uint16_t a, uint16_t b)
{
  int32_t d = (int32_t)a - (int32_t)b;
  if(d > 32767) d -= (int32_t)UP_SEQ_MOD;
  else if(d < -32767) d += (int32_t)UP_SEQ_MOD;
  return d;
}
/* Per-source receive statistics with 32-bit counters and a 32-packet
 * sliding window for duplicate detection (no per-seq bitmap needed). */
typedef struct {
  uint32_t unique, duplicate, out_of_order, delay_count;
  uint32_t highest;  /* extended 1-based seq of the newest packet; 0 = none yet */
  uint32_t window;   /* bit i set: packet (highest - i) was received */
  uint32_t delay_min_ticks, delay_max_ticks;
  uint64_t delay_sum_ticks;
} up_cstats_t;
/* Return 0=invalid, 1=unique, 2=duplicate. Older than 32 packets behind the
 * newest cannot be checked for duplicates and is counted as unique+reordered. */
static inline uint8_t up_cstats_rx(up_cstats_t *s, uint16_t seq,
  uint8_t delay_valid, uint32_t delay)
{
  int32_t d;
  uint32_t age;
  if(seq == 0) return 0;
  if(s->highest == 0) {
    s->highest = seq; s->window = 1;
  } else {
    d = up_seq_diff(seq, up_seq_wire(s->highest));
    if(d == 0) { s->duplicate++; return 2; }
    if(d > 0) {
      s->window = d >= 32 ? 0 : (s->window << d);
      s->window |= 1;
      s->highest += (uint32_t)d;
    } else {
      age = (uint32_t)(-d);
      if(age < 32) {
        if(s->window & (1UL << age)) { s->duplicate++; return 2; }
        s->window |= (1UL << age);
      }
      s->out_of_order++;
    }
  }
  s->unique++;
  if(delay_valid) {
    if(!s->delay_count || delay < s->delay_min_ticks) s->delay_min_ticks = delay;
    if(delay > s->delay_max_ticks) s->delay_max_ticks = delay;
    s->delay_count++; s->delay_sum_ticks += delay;
  }
  return 1;
}
/* Extend a cumulative 16-bit wire counter: previous 32-bit value + modular delta. */
static inline uint32_t up_ext16(uint32_t previous, uint16_t current)
{
  return previous + (uint16_t)(current - (uint16_t)previous);
}
/* Same as up_ratio() with 32-bit operands. */
static inline int32_t up_ratio32(uint32_t numerator, uint32_t denominator)
{
  if(!denominator) return -1;
  return (int32_t)(((uint64_t)numerator * 10000ULL) / denominator);
}
#endif
