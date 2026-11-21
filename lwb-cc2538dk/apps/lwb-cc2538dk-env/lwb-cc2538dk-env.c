/* Unified environmental telemetry and finite, fixed-offered-load LWB test.
 * Application ACK/retry is intentionally absent. Glossy retransmissions remain.
 * See README_VI.md for measurement definitions and hardware validation limits.
 * OLED fix: initialize I2C before OLED on HOST and SOURCE. A HOST with
 * HOST_LOCAL_SENSOR=1 displays its own sensors; otherwise it displays received
 * sensor data during a guarded background period.
 * Optional build flags (all default to the behaviour above; see docs/PHASE_ALIGN_NOTES.md):
 *   GEN_MODE=1    SOURCE enqueues GEN_LEAD_MS before the next LWB round starts. Just before
 *                 the enqueue it reads the sensors (I2C only) when SENSOR_BUDGET_MS of idle
 *                 time remain, else it reuses the old sample (sensor_stale). The OLED is
 *                 refreshed right after a round.
 *   FRESH_ONLY=1  no packet while unsynced / without stream ack; stale queued packet is
 *                 replaced by the new one (counted as "superseded").
 *   PACKETS=0     continuous mode: unbounded DATA, cumulative REPORT every REPORT_EVERY.
 *   RADIO_STATS=1 software radio duty cycle: Glossy radio-on time per flood, PERF_RADIO line
 *                 every RADIO_STATS_PERIOD rounds (docs/RADIO_STATS_NOTES.md).
 */
#include "contiki.h"
#include "sys/etimer.h"
#include "sys/rtimer.h"
#include "sys/node-id.h"
#include "lpm.h"
#include "lwb.h"
#include "glossy.h"
#include "deployment.h"
#include "env-packet.h"
#include "env-sensors.h"
#include "env-oled.h"
#include "i2c_sw.h"
#include "env-perf-packet.h"
#include "env-perf-stats.h"
#include "unified-conf.h"
#include <stdint.h>
#include <stdio.h>
#include <string.h>

PROCESS(lwb_cc2538dk_env_process, "Unified LWB sensor performance");
AUTOSTART_PROCESSES(&lwb_cc2538dk_env_process);

#define STREAM_ID 2
#define BG_BUDGET_MS 700
#define TX_RING_SIZE 16
#define STATE_JOIN 0
#define STATE_SEND 1
#define STATE_DRAIN 2
#define STATE_CLOSED 3
#define STATE_ABORT 4

static uint8_t role, state, fresh_rounds, sensor_mask, sensor_enabled;
static uint8_t expected_source[UP_MAX_NODE_ID + 1];
static struct etimer maintenance_et;
#if UP_GEN_MODE
static struct etimer gen_et;
#else
static struct etimer send_et;
#endif
static env_packet_t latest;
#if LWB_ENV_OLED_CONF
/* Separate display data from local sensor samples and the wire payload. */
static env_packet_t host_oled_data;
static uint8_t host_oled_pending;
#endif
#if !UP_GEN_MODE
static uint32_t next_release;
#endif
static uint32_t drain_started_s, last_slot_s;
static uint32_t last_sample_s, last_summary_s, next_report_s;
static uint16_t generated, queued, queue_failed, deadline_missed;
static uint16_t invalid_sensor, unsynced_generated, discarded;
static volatile uint16_t tx_started, tx_start_failed, tx_log_dropped;
static uint8_t report_flags, reports_left, report_attempts, measurement_closed;
static up_packet_t final_report;
#if UP_FRESH_ONLY
/* superseded: stale queue entries replaced by a fresh packet; gate_skipped: releases
 * suppressed because the node was unsynced or had no stream ack (no seq consumed). */
static uint16_t superseded, gate_skipped;
#endif
#if UP_CONTINUOUS
static uint32_t gen_total;         /* DATA packets released so far (1-based) */
static uint8_t report_due;         /* next release carries a periodic REPORT */
static volatile uint8_t report_queued; /* a periodic REPORT sits in the TX queue */
static uint8_t tx_have_last;
static uint16_t tx_last_seq;
#endif
#if UP_GEN_MODE
static uint8_t gen_armed;          /* gen_et is pending */
static uint8_t gen_deferred;       /* release postponed to the end of the running round */
static uint16_t gen_wait_rounds;   /* round ends to skip first (IPI > round period) */
static volatile uint8_t round_end_flag;
static uint32_t sensor_stale;      /* releases that reused an old sample (no time for I2C) */
static uint32_t sample_rt;         /* RTIMER_NOW() when the last sensor read started */
#if LWB_ENV_OLED_CONF
static uint8_t oled_due;           /* refresh the SOURCE OLED in the idle time after this round */
#endif
#endif

#if UP_RADIO_STATS
static uint16_t radio_rounds;             /* rounds since the previous PERF_RADIO */
static volatile uint8_t radio_due;        /* print PERF_RADIO from the app process */
static uint32_t radio_tlast;              /* RTIMER_NOW() at the previous PERF_RADIO / app start */
static uint64_t radio_cum_ticks;          /* rtimer ticks elapsed since app start (64 bit) */
static glossy_radio_stats_t radio_last;   /* Glossy accumulators at the previous PERF_RADIO */
#endif

/* Single producer (rtimer) / single consumer (process) log queue. */
typedef struct { uint16_t seq; uint32_t ticks; uint8_t valid, started; } tx_event_t;
static tx_event_t tx_ring[TX_RING_SIZE];
static volatile uint8_t tx_write, tx_read;
#if !UP_CONTINUOUS
static uint8_t tx_seen[UP_BITMAP_BYTES];
#endif

#if UP_CONTINUOUS
/* Cumulative REPORT counters extended from their 16-bit wire values. */
typedef struct {
  uint32_t generated, queued, tx_started, queue_failed;
  uint32_t deadline_missed, tx_start_failed;
} up_cum_t;
#endif

typedef struct {
#if UP_CONTINUOUS
  up_cstats_t cs;
  up_cum_t cum, base;              /* base = counters of the first REPORT seen */
  uint32_t snap_unique, base_unique, reports;
#else
  up_stats_t stats;
  uint8_t seen[UP_BITMAP_BYTES];
#endif
  uint8_t report_received, report_flags;
  uint16_t generated, queued, tx_started, queue_failed;
  uint16_t deadline_missed, tx_start_failed;
  uint16_t relay_samples;
  uint32_t relay_sum;
  uint8_t relay_min, relay_max;
} host_stats_t;
static host_stats_t host[UP_MAX_NODE_ID + 1];

static uint32_t ticks_to_us(uint32_t ticks)
{
  return (uint32_t)(((uint64_t)ticks * 1000000ULL + RTIMER_SECOND / 2) / RTIMER_SECOND);
}

static const char *role_name(void)
{
  return role == ROLE_HOST ? "HOST" : role == ROLE_SOURCE ? "SOURCE" : "RELAY";
}

static uint8_t parse_sources(void)
{
  const char *s = UP_SOURCE_IDS;
  uint32_t id;
  uint8_t n = 0;
  while(*s) {
    id = 0;
    if(*s < '0' || *s > '9') return 0;
    while(*s >= '0' && *s <= '9') {
      id = id * 10 + (uint8_t)(*s++ - '0');
      if(id > UP_MAX_NODE_ID) return 0;
    }
    if(id == 0 || id == UP_HOST_ID || expected_source[id]) return 0;
    expected_source[id] = 1; n++;
    if(!*s) break;
    if(*s++ != ':' || !*s) return 0;
  }
  return n != 0;
}

static void clear_sensor(void)
{
  memset(&latest, 0, sizeof(latest));
  latest.node_id = node_id;
  latest.hdc_temp_x10 = latest.bmp_temp_x10 = ENV_INVALID_TEMP_X10;
  latest.hdc_hum_x10 = latest.light_raw = ENV_INVALID_U16;
  latest.pressure_pa = ENV_INVALID_PRESSURE_PA;
}

/* I2C reads only (HDC1080/Si7021, TSL2561, BMP180); no OLED. */
static void sensor_read(void)
{
  int16_t t, bt;
  uint16_t rh, light;
  int32_t pressure;
#if UP_GEN_MODE
  sample_rt = (uint32_t)RTIMER_NOW(); /* start of the read: the age includes the I2C time */
#endif
  clear_sensor(); sensor_mask = 0;
#if ENV_USE_TEMP_RH_CONF
  if(env_read_temp_rh(&t, &rh) == 0) {
    latest.hdc_temp_x10 = t; latest.hdc_hum_x10 = rh; sensor_mask |= 1;
  }
#endif
#if ENV_USE_LIGHT_CONF
  light = env_read_light_raw();
  if(light != ENV_INVALID_U16) { latest.light_raw = light; sensor_mask |= 2; }
#endif
#if ENV_USE_BMP180_CONF
  if(env_read_bmp180(&bt, &pressure) == 0) {
    latest.bmp_temp_x10 = bt; latest.pressure_pa = pressure; sensor_mask |= 4;
  }
#endif
  (void)t; (void)bt; (void)rh; (void)light; (void)pressure;
}

#if LWB_ENV_OLED_CONF
/* Called only when local sensing is enabled, on SOURCE or HOST. */
static void sensor_oled(void)
{
  env_oled_show_env(&latest);
}
#endif

/* Read + display, as before. Used by the legacy SOURCE, the HOST local sensor and at boot. */
static void sample_sensor(void)
{
  sensor_read();
#if LWB_ENV_OLED_CONF
  sensor_oled();
#endif
  last_sample_s = clock_seconds();
}

static void packet_init(up_packet_t *p, uint8_t type, uint16_t seq)
{
  memset(p, 0, sizeof(*p));
  p->magic = UP_MAGIC; p->version = UP_VERSION; p->type = type;
  p->run = UP_RUN_ID; p->source = node_id; p->seq = seq;
}

/* This callback runs after a flood ends in rtimer context. No I/O or loops. */
static void observe_tx(const uint8_t *data, uint8_t len, uint32_t ticks,
                       uint8_t time_valid, uint8_t started)
{
  up_packet_t p;
#if !UP_CONTINUOUS
  uint16_t i;
#endif
  uint8_t next;
  if(measurement_closed || len != sizeof(p)) return;
  memcpy(&p, data, sizeof(p));
#if UP_CONTINUOUS
  /* Wire seq wraps (1..65535): only suppress an immediate repeat of the last seq.
   * A periodic REPORT only clears report_queued; it is not logged or counted here. */
  if(p.magic != UP_MAGIC || p.version != UP_VERSION ||
     p.run != UP_RUN_ID || p.source != node_id) return;
  if(p.type == UP_REPORT) { report_queued = 0; return; }
  if(p.type != UP_DATA || !p.seq) return;
  if(tx_have_last && p.seq == tx_last_seq) return;
  tx_have_last = 1; tx_last_seq = p.seq;
#else
  if(p.magic != UP_MAGIC || p.version != UP_VERSION || p.type != UP_DATA ||
     p.run != UP_RUN_ID || p.source != node_id || !p.seq || p.seq > UP_PACKETS) return;
  i = p.seq - 1;
  if(tx_seen[i >> 3] & (1u << (i & 7))) return;
  tx_seen[i >> 3] |= (uint8_t)(1u << (i & 7));
#endif
  if(started) tx_started++; else tx_start_failed++;
  next = (uint8_t)((tx_write + 1) % TX_RING_SIZE);
  if(next == tx_read) { tx_log_dropped++; return; }
  tx_ring[tx_write].seq = p.seq;
  tx_ring[tx_write].ticks = ticks;
  tx_ring[tx_write].valid = time_valid;
  tx_ring[tx_write].started = started;
  __asm__ volatile("" ::: "memory");
  tx_write = next;
  process_poll(&lwb_cc2538dk_env_process);
}

static void print_tx_events(void)
{
  tx_event_t e;
  while(tx_read != tx_write) {
    e = tx_ring[tx_read];
    __asm__ volatile("" ::: "memory");
    tx_read = (uint8_t)((tx_read + 1) % TX_RING_SIZE);
    printf("PERF_TX,run,%lu,source,%u,seq,%u,tx_start_ticks,%lu,time_valid,%u,started,%u\r\n",
      (unsigned long)UP_RUN_ID, node_id, e.seq, (unsigned long)e.ticks, e.valid, e.started);
  }
}

#if UP_CONTINUOUS
/* Continuous mode: counters are cumulative and 32 bit. The REPORT-derived values
 * (generated, queued, ...) are measured from the FIRST REPORT this HOST saw, so a
 * HOST that (re)booted late still gets a consistent yield. The yield uses the
 * received count captured when the LATEST REPORT arrived, not the live count. */
static void print_host_summary(uint16_t id)
{
  host_stats_t *h = &host[id];
  up_cstats_t *s = &h->cs;
  uint32_t avg = s->delay_count ? (uint32_t)(s->delay_sum_ticks / s->delay_count) : 0;
  uint32_t gen_w = h->cum.generated - h->base.generated;
  uint32_t que_w = h->cum.queued - h->base.queued;
  uint32_t txs_w = h->cum.tx_started - h->base.tx_started;
  uint32_t rx_w = h->snap_unique - h->base_unique;
  uint8_t have = h->report_received;
  printf("PERF_SUMMARY,run,%lu,source,%u,expected,%u,received,%lu,duplicate,%lu,out_of_order,%lu,report_received,%u,final,0,generated,%ld,queued,%ld,tx_started,%ld,queue_failed,%ld,deadline_missed,%ld,tx_start_failed,%ld,drain_timeout,0,application_yield_x100,%ld,enqueue_delivery_x100,%ld,flood_delivery_x100,%ld,delay_count,%lu,delay_min_us,%lu,delay_avg_us,%lu,delay_max_us,%lu,relay_samples,%u,relay_min,%u,relay_max,%u,mode,continuous,reports,%lu\r\n",
    (unsigned long)UP_RUN_ID, id, UP_PACKETS, (unsigned long)s->unique,
    (unsigned long)s->duplicate, (unsigned long)s->out_of_order, have,
    have ? (long)gen_w : -1L, have ? (long)que_w : -1L, have ? (long)txs_w : -1L,
    have ? (long)(h->cum.queue_failed - h->base.queue_failed) : -1L,
    have ? (long)(h->cum.deadline_missed - h->base.deadline_missed) : -1L,
    have ? (long)(h->cum.tx_start_failed - h->base.tx_start_failed) : -1L,
    have ? (long)up_ratio32(rx_w, gen_w) : -1L,
    have ? (long)up_ratio32(rx_w, que_w) : -1L,
    have ? (long)up_ratio32(rx_w, txs_w) : -1L,
    (unsigned long)s->delay_count, (unsigned long)ticks_to_us(s->delay_min_ticks),
    (unsigned long)ticks_to_us(avg), (unsigned long)ticks_to_us(s->delay_max_ticks),
    h->relay_samples, h->relay_min, h->relay_max, (unsigned long)h->reports);
}
#else
static void print_host_summary(uint16_t id)
{
  host_stats_t *h = &host[id];
  up_stats_t *s = &h->stats;
  uint32_t avg = s->delay_count ? (uint32_t)(s->delay_sum_ticks / s->delay_count) : 0;
  printf("PERF_SUMMARY,run,%lu,source,%u,expected,%u,received,%u,duplicate,%u,out_of_order,%u,report_received,%u,final,%u,generated,%ld,queued,%ld,tx_started,%ld,queue_failed,%ld,deadline_missed,%ld,tx_start_failed,%ld,drain_timeout,%u,application_yield_x100,%ld,enqueue_delivery_x100,%ld,flood_delivery_x100,%ld,delay_count,%u,delay_min_us,%lu,delay_avg_us,%lu,delay_max_us,%lu,relay_samples,%u,relay_min,%u,relay_max,%u\r\n",
    (unsigned long)UP_RUN_ID, id, UP_PACKETS, s->unique, s->duplicate, s->out_of_order,
    h->report_received, h->report_received,
    h->report_received ? (long)h->generated : -1L,
    h->report_received ? (long)h->queued : -1L,
    h->report_received ? (long)h->tx_started : -1L,
    h->report_received ? (long)h->queue_failed : -1L,
    h->report_received ? (long)h->deadline_missed : -1L,
    h->report_received ? (long)h->tx_start_failed : -1L,
    !!(h->report_flags & UP_REPORT_DRAIN_TIMEOUT),
    h->report_received ? (long)up_ratio(s->unique, h->generated) : -1L,
    h->report_received ? (long)up_ratio(s->unique, h->queued) : -1L,
    h->report_received ? (long)up_ratio(s->unique, h->tx_started) : -1L,
    s->delay_count, (unsigned long)ticks_to_us(s->delay_min_ticks),
    (unsigned long)ticks_to_us(avg), (unsigned long)ticks_to_us(s->delay_max_ticks),
    h->relay_samples, h->relay_min, h->relay_max);
}
#endif

#if UP_CONTINUOUS
/* Periodic cumulative REPORT in continuous mode. Only the identity
 * q + qf + dm == g (mod 2^16) can be checked: the wire counters wrap. */
static void host_report_cont(host_stats_t *h, uint16_t from, const up_packet_t *p)
{
  const uint16_t g = p->body.report.generated, q = p->body.report.queued;
  const uint16_t t = p->body.report.tx_started, qf = p->body.report.queue_failed;
  const uint16_t dm = p->body.report.deadline_missed, tf = p->body.report.tx_start_failed;
  if(!p->seq || (uint16_t)(q + qf + dm) != g) {
    printf("PERF_ERR,reason,bad_report,source,%u\r\n", from); return;
  }
  if(!h->report_received) {
    h->base.generated = h->cum.generated = g; h->base.queued = h->cum.queued = q;
    h->base.tx_started = h->cum.tx_started = t;
    h->base.queue_failed = h->cum.queue_failed = qf;
    h->base.deadline_missed = h->cum.deadline_missed = dm;
    h->base.tx_start_failed = h->cum.tx_start_failed = tf;
    h->base_unique = h->cs.unique;
  } else {
    h->cum.generated = up_ext16(h->cum.generated, g);
    h->cum.queued = up_ext16(h->cum.queued, q);
    h->cum.tx_started = up_ext16(h->cum.tx_started, t);
    h->cum.queue_failed = up_ext16(h->cum.queue_failed, qf);
    h->cum.deadline_missed = up_ext16(h->cum.deadline_missed, dm);
    h->cum.tx_start_failed = up_ext16(h->cum.tx_start_failed, tf);
  }
  h->snap_unique = h->cs.unique;
  h->report_received = 1; h->report_flags = p->flags; h->reports++;
  printf("PERF_REPORT,run,%lu,source,%u,generated,%u,queued,%u,tx_started,%u,queue_failed,%u,deadline_missed,%u,tx_start_failed,%u,drain_timeout,%u\r\n",
    (unsigned long)p->run, from, g, q, t, qf, dm, tf,
    !!(p->flags & UP_REPORT_DRAIN_TIMEOUT));
  print_host_summary(from);
}
#endif

static void on_data(uint8_t *data, uint8_t len, uint16_t from)
{
  up_packet_t p;
  lwb_rx_metadata_t meta;
  host_stats_t *h;
  uint32_t delay_ticks;
  uint8_t delay_valid, unique, relay_valid;
  if(role != ROLE_HOST) return;
  if(len != sizeof(p)) {
    printf("PERF_ERR,reason,bad_length,from,%u,length,%u\r\n", from, len); return;
  }
  memcpy(&p, data, sizeof(p));
  if(p.magic != UP_MAGIC || p.version != UP_VERSION || p.run != UP_RUN_ID ||
     from != p.source || from > UP_MAX_NODE_ID || !expected_source[from]) {
    printf("PERF_ERR,reason,bad_identity,from,%u,run,%lu\r\n", from, (unsigned long)p.run); return;
  }
  h = &host[from];
  if(p.type == UP_REPORT) {
#if UP_CONTINUOUS
    host_report_cont(h, from, &p); return;
#else
    if(p.body.report.generated != UP_PACKETS || p.seq != UP_PACKETS ||
       p.body.report.queued > p.body.report.generated ||
       p.body.report.tx_started > p.body.report.queued ||
       p.body.report.queued + p.body.report.queue_failed + p.body.report.deadline_missed != p.body.report.generated ||
       p.body.report.tx_started + p.body.report.tx_start_failed > p.body.report.queued ||
       p.body.report.tx_started < h->stats.unique) {
      printf("PERF_ERR,reason,bad_report,source,%u\r\n", from); return;
    }
    h->report_received = 1; h->report_flags = p.flags;
    h->generated = p.body.report.generated; h->queued = p.body.report.queued;
    h->tx_started = p.body.report.tx_started; h->queue_failed = p.body.report.queue_failed;
    h->deadline_missed = p.body.report.deadline_missed;
    h->tx_start_failed = p.body.report.tx_start_failed;
    printf("PERF_REPORT,run,%lu,source,%u,generated,%u,queued,%u,tx_started,%u,queue_failed,%u,deadline_missed,%u,tx_start_failed,%u,drain_timeout,%u\r\n",
      (unsigned long)p.run, from, h->generated, h->queued, h->tx_started,
      h->queue_failed, h->deadline_missed, h->tx_start_failed,
      !!(p.flags & UP_REPORT_DRAIN_TIMEOUT));
    print_host_summary(from); return;
#endif
  }
#if UP_CONTINUOUS
  if(p.type != UP_DATA || !p.seq) return;
#else
  if(p.type != UP_DATA || !p.seq || p.seq > UP_PACKETS) return;
#endif
  memset(&meta, 0, sizeof(meta)); meta.relay_cnt = 0xff;
  (void)lwb_get_last_rx_metadata(&meta);
  delay_valid = up_delay(p.tx_network_ticks, meta.rx_slot_end_ticks,
     !!(p.flags & UP_TIME_VALID), meta.time_valid, UP_MAX_DELAY_TICKS, &delay_ticks);
#if UP_CONTINUOUS
  unique = up_cstats_rx(&h->cs, p.seq, delay_valid, delay_ticks);
#else
  unique = up_stats_rx(&h->stats, h->seen, p.seq, UP_PACKETS, delay_valid, delay_ticks);
#endif
  relay_valid = (meta.n_rx > 0 && meta.relay_cnt != 0xff);
  if(unique == 1 && relay_valid) {
    if(!h->relay_samples || meta.relay_cnt < h->relay_min) h->relay_min = meta.relay_cnt;
    if(meta.relay_cnt > h->relay_max) h->relay_max = meta.relay_cnt;
    /* Saturate: a wrap to 0 would reset relay_min (identical for PACKETS <= 2000). */
    if(h->relay_samples != 0xffff) h->relay_samples++;
    h->relay_sum += meta.relay_cnt;
  }
  printf("SENSOR_DATA,run,%lu,from,%u,node,%u,seq,%u,unique,%u,sensor_mask,%u,tx_net_ticks,%lu,rx_slot_end_ticks,%lu,delay_ticks,%lu,delay_ms,%lu,delay_valid,%u,timer_hz,%lu,relay_cnt,%u,hop_est,%u,hop_est_valid,%u,hdc_temp_x10,%d,hdc_hum_x10,%u,light_raw,%u,bmp_temp_x10,%d,pressure_pa,%ld\r\n",
    (unsigned long)p.run, from, p.source, p.seq, unique == 1,
    p.flags & UP_SENSOR_MASK, (unsigned long)p.tx_network_ticks,
    (unsigned long)meta.rx_slot_end_ticks, (unsigned long)delay_ticks,
    (unsigned long)((ticks_to_us(delay_ticks) + 500) / 1000), delay_valid,
    (unsigned long)RTIMER_SECOND, meta.relay_cnt,
    relay_valid ? (unsigned)meta.relay_cnt + 1u : 0u, relay_valid,
    p.body.sensor.hdc_temp_x10, p.body.sensor.hdc_hum_x10,
    p.body.sensor.light_raw, p.body.sensor.bmp_temp_x10, (long)p.body.sensor.pressure_pa);

#if LWB_ENV_OLED_CONF
  /* HOST without local sensing displays remote samples. No OLED/I2C I/O here.
   * With local sensing enabled, remote data still reaches UART and statistics
   * but must not overwrite the local OLED page.
   */
  if(unique == 1 && !sensor_enabled) {
    host_oled_data.node_id = p.source;
    host_oled_data.seq = p.seq;
    host_oled_data.hdc_temp_x10 = (p.flags & 1) ?
      p.body.sensor.hdc_temp_x10 : ENV_INVALID_TEMP_X10;
    host_oled_data.hdc_hum_x10 = (p.flags & 1) ?
      p.body.sensor.hdc_hum_x10 : ENV_INVALID_U16;
    host_oled_data.light_raw = (p.flags & 2) ?
      p.body.sensor.light_raw : ENV_INVALID_U16;
    host_oled_data.bmp_temp_x10 = (p.flags & 4) ?
      p.body.sensor.bmp_temp_x10 : ENV_INVALID_TEMP_X10;
    host_oled_data.pressure_pa = (p.flags & 4) ?
      p.body.sensor.pressure_pa : ENV_INVALID_PRESSURE_PA;
    host_oled_pending = 1;
  }
#endif
}

static void on_sched_end(void)
{
#if UP_RADIO_STATS
  /* Every role: count rounds only. The line is printed by the app process, never from here. */
  if(++radio_rounds >= UP_RADIO_STATS_PERIOD) {
    radio_rounds = 0; radio_due = 1;
    process_poll(&lwb_cc2538dk_env_process);
  }
#endif
  if(role != ROLE_SOURCE) return;
  if(lwb_time_is_fresh()) { if(fresh_rounds < 255) fresh_rounds++; }
  else fresh_rounds = 0;
  if(lwb_get_n_my_slots()) last_slot_s = clock_seconds();
#if UP_GEN_MODE
  /* Runs inside lwb_main_process right after a round: only raise a flag. The app
   * process arms the release timer and reads the sensors (no I2C in this context). */
  round_end_flag = 1;
  process_poll(&lwb_cc2538dk_env_process);
#endif
}
static lwb_callbacks_t callbacks = { on_data, on_sched_end };

#if UP_CONTINUOUS || UP_FRESH_ONLY
/* Wire seq of the newest DATA packet released so far. */
static uint16_t newest_seq(void)
{
#if UP_CONTINUOUS
  return up_seq_wire(gen_total);
#else
  return generated;
#endif
}
#endif

#if UP_FRESH_ONLY
/* A release is allowed only when synced and the stream request was acknowledged.
 * Otherwise nothing is created and no seq is consumed. */
static uint8_t fresh_gate(void)
{
  if(lwb_time_is_fresh() && lwb_get_joining_state() == LWB_JOINING_STATE_JOINED) return 1;
  gate_skipped++;
  printf("PERF_GATE,run,%lu,source,%u,reason,%s,gate_skipped,%u\r\n",
    (unsigned long)UP_RUN_ID, node_id,
    lwb_time_is_fresh() ? "no_stream_ack" : "not_synced", gate_skipped);
  return 0;
}

/* Replace a stale queued packet by the one about to be created. Dropping needs a safe
 * idle window (lwb_drop_tx_queue() checks it); outside one the stale entry stays. */
static void fresh_drop_stale(void)
{
  uint8_t n, rep = 0;
  if(!lwb_get_tx_queue_len()) return;
  n = lwb_drop_tx_queue();
  if(!n) return;
#if UP_CONTINUOUS
  /* A stale periodic REPORT is not a DATA packet: keep it out of "superseded". */
  if(report_queued) { report_queued = 0; rep = 1; n--; }
#endif
  superseded += n;
  printf("PERF_SUPERSEDE,run,%lu,source,%u,last_seq,%u,dropped,%u,report_dropped,%u,superseded,%u\r\n",
    (unsigned long)UP_RUN_ID, node_id, newest_seq(), n, rep, superseded);
}
#endif

#if UP_GEN_MODE
/* PERF_GEN extra fields: age of the sensor sample at enqueue (sample read -> enqueue) and
 * the running count of releases that had to reuse an old sample. */
#define GEN_AGE_FMT ",sample_age_ms,%lu,sensor_stale,%lu"
#define GEN_AGE_ARGS , (unsigned long)(ticks_to_us((uint32_t)RTIMER_NOW() - sample_rt) / 1000UL), \
  (unsigned long)sensor_stale
#else
#define GEN_AGE_FMT ""
#define GEN_AGE_ARGS
#endif

/* Build one DATA packet from the sensor buffer (no I2C here) and enqueue it. */
static void source_emit_data(void)
{
  up_packet_t p;
#if UP_CONTINUOUS
  gen_total++; generated++;
  packet_init(&p, UP_DATA, up_seq_wire(gen_total));
#else
  generated++;
  packet_init(&p, UP_DATA, generated);
#endif
  p.body.sensor.hdc_temp_x10 = latest.hdc_temp_x10;
  p.body.sensor.hdc_hum_x10 = latest.hdc_hum_x10;
  p.body.sensor.light_raw = latest.light_raw;
  p.body.sensor.bmp_temp_x10 = latest.bmp_temp_x10;
  p.body.sensor.pressure_pa = latest.pressure_pa;
  p.flags = sensor_mask;
  if(!sensor_mask) invalid_sensor++;
  if(lwb_time_is_fresh()) p.flags |= UP_TIME_VALID; else unsynced_generated++;
  p.tx_network_ticks = lwb_get_network_time_ticks();
  if(lwb_queue_packet((uint8_t *)&p, sizeof(p), UP_HOST_ID) == LWB_STATUS_SUCCESS) queued++;
  else queue_failed++;
  printf("PERF_GEN,run,%lu,source,%u,seq,%u,generated,%u,queued,%u,queue_failed,%u,tx_net_ticks,%lu,time_valid,%u,sensor_mask,%u" GEN_AGE_FMT "\r\n",
    (unsigned long)UP_RUN_ID, node_id, p.seq, generated, queued, queue_failed,
    (unsigned long)p.tx_network_ticks, !!(p.flags & UP_TIME_VALID), sensor_mask GEN_AGE_ARGS);
#if UP_CONTINUOUS
  if(gen_total % UP_REPORT_EVERY == 0) report_due = 1;
#endif
}

#if UP_CONTINUOUS
/* Periodic cumulative REPORT. It takes the release slot of one DATA packet (the
 * stream has exactly one slot per round), consumes no DATA seq and is not counted
 * in generated/queued. seq = wire seq of the newest DATA packet. */
static void source_emit_report(void)
{
  up_packet_t r;
  uint8_t ok;
  packet_init(&r, UP_REPORT, up_seq_wire(gen_total));
  r.flags = report_flags;
  r.body.report.generated = generated;
  r.body.report.queued = queued;
  r.body.report.tx_started = tx_started;
  r.body.report.queue_failed = queue_failed;
  r.body.report.deadline_missed = deadline_missed;
  r.body.report.tx_start_failed = tx_start_failed;
  ok = lwb_queue_packet((uint8_t *)&r, sizeof(r), UP_HOST_ID) == LWB_STATUS_SUCCESS;
  if(ok) report_queued = 1;
  report_due = 0;
  printf("PERF_REPORT_TX,run,%lu,source,%u,seq,%u,generated,%u,queued,%u,tx_started,%u,queue_failed,%u,deadline_missed,%u,tx_start_failed,%u,enqueued,%u\r\n",
    (unsigned long)UP_RUN_ID, node_id, r.seq, generated, queued, tx_started,
    queue_failed, deadline_missed, tx_start_failed, ok);
}
#endif

#if UP_GEN_MODE
/* ---- GEN_MODE=1: release one packet GEN_LEAD_MS before the next round starts ----
 * on_sched_end -> round_end_flag -> gen_round_end() arms gen_et for
 * (next round start - lead). gen_fire() creates the packet from the sensor buffer. */
#define GEN_LEAD_TICKS (((uint32_t)UP_GEN_LEAD_MS * (uint32_t)RTIMER_SECOND) / 1000UL)
#define GEN_GUARD_MS 30 /* same guard lwb_drop_tx_queue() applies internally */

/* Fill the sensor buffer just before a DATA packet is built: read the sensors (I2C only, no
 * OLED) if GEN_GUARD_MS + SENSOR_BUDGET_MS of idle time remain, else keep the old sample and
 * count sensor_stale. Returns 0 if the round started during the read: the release then moves
 * to the end of that round (gen_deferred) and nothing has been enqueued. */
static uint8_t gen_sense(void)
{
  if(lwb_background_allowed(GEN_GUARD_MS + UP_SENSOR_BUDGET_MS)) {
    sensor_read();
    if(!lwb_background_allowed(GEN_GUARD_MS)) { gen_deferred = 1; return 0; }
  } else if(!lwb_background_allowed(GEN_GUARD_MS)) {
    gen_deferred = 1; return 0;
  } else {
    sensor_stale++;
  }
  return 1;
}

/* Release now. The caller has verified the safe window (queue ops are not ISR-safe). */
static void gen_emit(void)
{
#if UP_FRESH_ONLY
  if(!fresh_gate()) return;
  fresh_drop_stale();
#endif
#if UP_CONTINUOUS
  if(report_due) { source_emit_report(); return; }
#endif
  if(!gen_sense()) return;
  source_emit_data();
#if !UP_CONTINUOUS
  if(generated == UP_PACKETS) { state = STATE_DRAIN; drain_started_s = clock_seconds(); }
#endif
}

/* If a round is running (late timer) or about to start, the enqueue moves to the end
 * of that round: still exactly one packet, and it goes out in the following round. */
static void gen_fire(void)
{
  if(state != STATE_SEND) return;
  if(!lwb_background_allowed(GEN_GUARD_MS)) { gen_deferred = 1; return; }
  gen_emit();
}

/* Plan the release for the next round: timer at (round start - lead); release at
 * once if the round start is unknown (just joined) or already inside the lead. */
static void gen_plan(void)
{
  uint32_t next, remain, clk;
  if(state != STATE_SEND || gen_armed) return;
  gen_wait_rounds = UP_GEN_ROUNDS - 1;
  if(!lwb_get_next_round_ticks(&next)) { gen_fire(); return; }
  remain = next - (uint32_t)RTIMER_NOW();
  if(remain >= 0x80000000UL || remain <= GEN_LEAD_TICKS) { gen_fire(); return; }
  /* RTIMER ticks -> clock ticks, rounded up so the timer never fires early. */
  clk = (uint32_t)((((uint64_t)(remain - GEN_LEAD_TICKS)) * CLOCK_SECOND +
                    RTIMER_SECOND - 1) / RTIMER_SECOND);
  if(clk == 0) clk = 1;
  etimer_set(&gen_et, clk);
  gen_armed = 1;
}

static void gen_round_end(void)
{
#if UP_GEN_ROUNDS > 1
  /* IPI is a multiple of the round period: re-lock on a round where this node had a slot. */
  if(lwb_get_n_my_slots()) gen_wait_rounds = UP_GEN_ROUNDS - 1;
#endif
  if(state == STATE_SEND) {
    if(gen_deferred) {
      /* The timer fired late, inside a round: release once now (the round is over). */
      gen_deferred = 0; gen_wait_rounds = UP_GEN_ROUNDS - 1;
      gen_fire();
    } else if(gen_wait_rounds) gen_wait_rounds--;
    else gen_plan();
  }
#if LWB_ENV_OLED_CONF
  if(sensor_enabled) oled_due = 1;
#endif
}

static void gen_service(process_event_t ev, process_data_t data)
{
  if(ev == PROCESS_EVENT_TIMER && data == &gen_et && gen_armed) { gen_armed = 0; gen_fire(); }
  if(round_end_flag) { round_end_flag = 0; gen_round_end(); }
#if LWB_ENV_OLED_CONF
  /* The OLED (slow) is refreshed in the idle time right after a round, never close to the
   * next one. It shows the sample of the last release; the I2C read is done in gen_sense(). */
  if(oled_due && lwb_background_allowed(BG_BUDGET_MS)) { oled_due = 0; sensor_oled(); }
#endif
}
#else
/* Legacy release: etimer with period IPI, no relation to the LWB round phase. */
static void source_generate(void)
{
  uint32_t now = clock_time();
  uint32_t period = (uint32_t)UP_IPI * CLOCK_SECOND;
  uint32_t missed = 0;
  if((int32_t)(now - next_release) < 0) return;
  missed = (uint32_t)(now - next_release) / period;
#if UP_FRESH_ONLY
  if(!fresh_gate()) {
    next_release += (missed + 1) * period;
    now = clock_time();
    etimer_set(&send_et, (int32_t)(next_release - now) > 0 ? next_release - now : 1);
    return;
  }
  fresh_drop_stale();
#endif
#if !UP_CONTINUOUS
  if(missed >= (uint32_t)(UP_PACKETS - generated)) missed = UP_PACKETS - generated - 1;
#endif
  if(missed) {
#if UP_CONTINUOUS
    printf("PERF_RELEASE_SKIP,run,%lu,source,%u,first_seq,%u,count,%lu\r\n",
      (unsigned long)UP_RUN_ID, node_id, up_seq_wire(gen_total + 1), (unsigned long)missed);
    gen_total += missed;
#else
    printf("PERF_RELEASE_SKIP,run,%lu,source,%u,first_seq,%u,count,%lu\r\n",
      (unsigned long)UP_RUN_ID, node_id, generated + 1, (unsigned long)missed);
#endif
    generated += missed; deadline_missed += missed;
  }
#if UP_CONTINUOUS
  if(report_due) source_emit_report(); else source_emit_data();
#else
  source_emit_data();
#endif
  next_release += (missed + 1) * period;
#if !UP_CONTINUOUS
  if(generated == UP_PACKETS) { state = STATE_DRAIN; drain_started_s = clock_seconds(); }
  else
#endif
  {
    now = clock_time();
    etimer_set(&send_et, (int32_t)(next_release - now) > 0 ? next_release - now : 1);
  }
}
#endif

#if UP_FRESH_ONLY
#define SUMMARY_FRESH_FMT ",superseded,%u,gate_skipped,%u"
#define SUMMARY_FRESH_ARGS , superseded, gate_skipped
#else
#define SUMMARY_FRESH_FMT ""
#define SUMMARY_FRESH_ARGS
#endif
#if UP_GEN_MODE
#define SUMMARY_GEN_FMT ",sensor_stale,%lu"
#define SUMMARY_GEN_ARGS , (unsigned long)sensor_stale
#else
#define SUMMARY_GEN_FMT ""
#define SUMMARY_GEN_ARGS
#endif

static void source_close(uint8_t timed_out)
{
  /* Called only during a guarded idle period, with no DATA flood in flight. */
  if(timed_out) { discarded = lwb_drop_tx_queue(); report_flags |= UP_REPORT_DRAIN_TIMEOUT; }
  measurement_closed = 1;
  print_tx_events();
  packet_init(&final_report, UP_REPORT, generated);
  final_report.flags = report_flags;
  final_report.body.report.generated = generated;
  final_report.body.report.queued = queued;
  final_report.body.report.tx_started = tx_started;
  final_report.body.report.queue_failed = queue_failed;
  final_report.body.report.deadline_missed = deadline_missed;
  final_report.body.report.tx_start_failed = tx_start_failed;
  /* FRESH_ONLY adds ",superseded,N,gate_skipped,M": superseded entries were queued but
   * neither sent nor discarded at the timeout, so queued = tx_started + tx_start_failed
   * + discarded + superseded. */
  printf("PERF_SOURCE_SUMMARY,run,%lu,source,%u,expected,%u,generated,%u,queued,%u,tx_started,%u,queue_failed,%u,deadline_missed,%u,tx_start_failed,%u,discarded,%u,invalid_sensor,%u,unsynced_generated,%u,tx_log_dropped,%u,drain_timeout,%u" SUMMARY_FRESH_FMT SUMMARY_GEN_FMT "\r\n",
    (unsigned long)UP_RUN_ID, node_id, UP_PACKETS, generated, queued, tx_started,
    queue_failed, deadline_missed, tx_start_failed, discarded, invalid_sensor,
    unsynced_generated, tx_log_dropped, !!(report_flags & UP_REPORT_DRAIN_TIMEOUT)
    SUMMARY_FRESH_ARGS SUMMARY_GEN_ARGS);
  state = STATE_CLOSED; reports_left = UP_REPORT_REPEAT;
  next_report_s = clock_seconds();
}

#if UP_RADIO_STATS
/* ---- RADIO_STATS: radio duty cycle from the Glossy radio on/off timestamps ----
 * Each PERF_RADIO line carries the interval since the previous line (no prefix) and the totals
 * since boot (cum_ prefix). duty = radio-on time / elapsed time, both in rtimer ticks, so the
 * 32-bit RTIMER wrap cancels out. tx_on_ms is an ESTIMATE (completed transmissions x frame
 * airtime), not a measurement. 64-bit totals are printed through u64_dec(): the minimal
 * newlib printf is not relied upon for %llu. */
#define RADIO_PRINT_BUDGET_MS 100 /* the UART line (~330 chars) must not run into the next round */

static uint64_t rt_to_ms(uint64_t t) { return (t * 1000ULL + RTIMER_SECOND / 2) / RTIMER_SECOND; }

static uint32_t duty_x10000(uint64_t on, uint64_t elapsed)
{
  return elapsed ? (uint32_t)((on * 10000ULL + elapsed / 2) / elapsed) : 0;
}

static uint32_t avg_on_us(uint64_t on, uint32_t floods)
{
  uint64_t d = (uint64_t)RTIMER_SECOND * floods;
  return floods ? (uint32_t)((on * 1000000ULL + d / 2) / d) : 0;
}

/* Decimal text of v written backwards into buf[21]; returns the start of the text. */
static const char *u64_dec(char *buf, uint64_t v)
{
  char *p = buf + 20;
  *p = 0;
  do { *--p = (char)('0' + (uint8_t)(v % 10)); v /= 10; } while(v);
  return p;
}

static void radio_stats_print(void)
{
  glossy_radio_stats_t cur;
  uint32_t now = (uint32_t)RTIMER_NOW();
  uint64_t dt = (uint32_t)(now - radio_tlast);
  uint64_t on_p, tx_p;
  uint32_t fl_p;
  char b_el[21], b_on[21], b_tx[21];
  glossy_get_radio_stats(&cur);
  radio_tlast = now;
  radio_cum_ticks += dt;
  on_p = cur.radio_on_ticks - radio_last.radio_on_ticks;
  tx_p = cur.tx_on_us - radio_last.tx_on_us;
  fl_p = cur.floods - radio_last.floods;
  radio_last = cur;
  printf("PERF_RADIO,run,%lu,node,%u,role,%s,elapsed_ms,%lu,radio_on_ms,%lu,duty_x10000,%lu,floods,%lu,avg_on_per_flood_us,%lu,tx_on_ms,%lu,cum_elapsed_ms,%s,cum_radio_on_ms,%s,cum_duty_x10000,%lu,cum_floods,%lu,cum_avg_on_per_flood_us,%lu,cum_tx_on_ms,%s\r\n",
    (unsigned long)UP_RUN_ID, node_id, role_name(),
    (unsigned long)rt_to_ms(dt), (unsigned long)rt_to_ms(on_p),
    (unsigned long)duty_x10000(on_p, dt), (unsigned long)fl_p,
    (unsigned long)avg_on_us(on_p, fl_p), (unsigned long)((tx_p + 500) / 1000),
    u64_dec(b_el, rt_to_ms(radio_cum_ticks)), u64_dec(b_on, rt_to_ms(cur.radio_on_ticks)),
    (unsigned long)duty_x10000(cur.radio_on_ticks, radio_cum_ticks),
    (unsigned long)cur.floods, (unsigned long)avg_on_us(cur.radio_on_ticks, cur.floods),
    u64_dec(b_tx, (cur.tx_on_us + 500) / 1000));
}
#define CONFIG_RADIO_FMT ",radio_stats,%u,radio_stats_period,%u"
#define CONFIG_RADIO_ARGS , UP_RADIO_STATS, UP_RADIO_STATS_PERIOD
#else
#define CONFIG_RADIO_FMT ""
#define CONFIG_RADIO_ARGS
#endif

/* PERF_CONFIG records the new flags only when one of them differs from the defaults,
 * so a default build prints exactly the previous line. */
#if UP_GEN_MODE || UP_FRESH_ONLY || UP_CONTINUOUS
#define CONFIG_EXT_FMT ",gen_mode,%u,gen_lead_ms,%u,fresh_only,%u,report_every,%u"
#define CONFIG_EXT_ARGS , UP_GEN_MODE, UP_GEN_LEAD_MS, UP_FRESH_ONLY, UP_REPORT_EVERY
#else
#define CONFIG_EXT_FMT ""
#define CONFIG_EXT_ARGS
#endif

PROCESS_THREAD(lwb_cc2538dk_env_process, ev, data)
{
  static uint32_t now_s, waited, rejoin_threshold;
  static uint16_t id;
  PROCESS_BEGIN();
  deployment_load_ieee_addr();
  deployment_set_node_id_ieee_addr();
  role = UP_ROLE == ROLE_AUTO ? (node_id == UP_HOST_ID ? ROLE_HOST : ROLE_SOURCE) : UP_ROLE;
  if(!node_id || node_id > UP_MAX_NODE_ID || !parse_sources() ||
     (role == ROLE_HOST && node_id != UP_HOST_ID) ||
     (role != ROLE_HOST && node_id == UP_HOST_ID) ||
     (role == ROLE_SOURCE && !expected_source[node_id]) ||
     (role == ROLE_RELAY && expected_source[node_id])) {
    printf("PERF_ERR,reason,invalid_build_configuration,node,%u\r\n", node_id);
    PROCESS_EXIT();
  }
  lpm_set_max_pm(LPM_PM0);
  sensor_enabled = role == ROLE_SOURCE || (role == ROLE_HOST && LWB_ENV_HOST_LOCAL_SENSOR_CONF);
  clear_sensor();
  /* env_sensors_init() initializes the shared I2C bus on sensor nodes. */
  if(sensor_enabled) {
    env_sensors_init();
  }
#if LWB_ENV_OLED_CONF
  if(role == ROLE_HOST || role == ROLE_SOURCE) {
    /* HOST without local sensors still needs I2C before OLED initialization. */
    if(!sensor_enabled) i2c_sw_init();
    env_oled_init(); env_oled_show_status(node_id, role == ROLE_HOST);
  }
#endif
  if(sensor_enabled) {
    sample_sensor();
  }
  printf("PERF_CONFIG,protocol,env_perf_v1,node,%u,role,%s,run,%lu,expected,%u,ipi_s,%u,source_ids,%s,payload_bytes,%u,timer_hz,%lu,channel,%u,tx_drive_dbm,%d,n_sync,%u,n_data_tx,%u,application_ack,0,application_retry,0,rtc_integrated,0,delay_endpoint,slot_end,scheduler,static_5s" CONFIG_EXT_FMT CONFIG_RADIO_FMT "\r\n",
    node_id, role_name(), (unsigned long)UP_RUN_ID, UP_PACKETS, UP_IPI,
    UP_SOURCE_IDS, (unsigned)sizeof(up_packet_t), (unsigned long)RTIMER_SECOND,
    CC2538_RF_CONF_CHANNEL, CC2592_CONF_TX_POWER_DBM, N_SYNC, N_RR CONFIG_EXT_ARGS CONFIG_RADIO_ARGS);
  lwb_init(role == ROLE_HOST ? LWB_MODE_HOST : LWB_MODE_SOURCE, &callbacks);
  glossy_set_enc(GLOSSY_ENC_OFF);
  if(role == ROLE_SOURCE) {
    lwb_set_tx_observer(observe_tx);
    lwb_request_stream_mod(STREAM_ID, UP_IPI);
  }
  last_slot_s = clock_seconds();
#if UP_RADIO_STATS
  radio_tlast = (uint32_t)RTIMER_NOW();
#endif
  etimer_set(&maintenance_et, CLOCK_SECOND);
  while(1) {
    PROCESS_WAIT_EVENT();
    if(role == ROLE_SOURCE) print_tx_events();
#if UP_RADIO_STATS
    if(radio_due && lwb_background_allowed(RADIO_PRINT_BUDGET_MS)) { radio_due = 0; radio_stats_print(); }
#endif
#if UP_GEN_MODE
    if(role == ROLE_SOURCE) gen_service(ev, data);
#else
    if(role == ROLE_SOURCE && state == STATE_SEND &&
       ev == PROCESS_EVENT_TIMER && data == &send_et) source_generate();
#endif
    if(ev != PROCESS_EVENT_TIMER || data != &maintenance_et) continue;
    etimer_reset(&maintenance_et); now_s = clock_seconds();
    /* GEN_MODE=1: a SOURCE reads its sensors just before each release (gen_sense) and
     * refreshes its OLED after a round (gen_service); the HOST local sensor keeps the
     * periodic read. */
    if(sensor_enabled &&
#if UP_GEN_MODE
       role == ROLE_HOST &&
#endif
       now_s - last_sample_s >= UP_SAMPLE_PERIOD &&
       lwb_background_allowed(BG_BUDGET_MS)) {
      sample_sensor();
      if(role == ROLE_HOST) {
        printf("LOCAL,run,%lu,node,%u,seq,%lu,sensor_mask,%u,hdc_temp_x10,%d,hdc_hum_x10,%u,light_raw,%u,bmp_temp_x10,%d,pressure_pa,%ld\r\n",
          (unsigned long)UP_RUN_ID, node_id, (unsigned long)now_s, sensor_mask,
          latest.hdc_temp_x10, latest.hdc_hum_x10, latest.light_raw,
          latest.bmp_temp_x10, (long)latest.pressure_pa);
      }
    }
#if LWB_ENV_OLED_CONF
    /* Coalesce received samples and refresh only with enough idle time. */
    if(role == ROLE_HOST && !sensor_enabled && host_oled_pending &&
       lwb_background_allowed(BG_BUDGET_MS)) {
      env_oled_show_env(&host_oled_data);
      host_oled_pending = 0;
    }
#endif
    if(role == ROLE_HOST && now_s - last_summary_s >= UP_SUMMARY_PERIOD) {
      last_summary_s = now_s;
      for(id = 1; id <= UP_MAX_NODE_ID; id++) if(expected_source[id]) print_host_summary(id);
    }
    if(role != ROLE_SOURCE) continue;
    if(state == STATE_JOIN) {
      if(now_s >= UP_START_DELAY && fresh_rounds >= 2 &&
         lwb_get_joining_state() == LWB_JOINING_STATE_JOINED && lwb_get_n_my_slots()) {
        printf("PERF_START,run,%lu,source,%u,uptime_s,%lu\r\n",
          (unsigned long)UP_RUN_ID, node_id, (unsigned long)now_s);
#if UP_GEN_MODE
        state = STATE_SEND; gen_plan();
#else
        state = STATE_SEND; next_release = clock_time(); source_generate();
#endif
      } else if(now_s >= UP_JOIN_TIMEOUT) {
        state = STATE_ABORT;
        printf("PERF_ABORT,run,%lu,source,%u,reason,join_timeout,generated,0\r\n",
          (unsigned long)UP_RUN_ID, node_id);
      }
    }
    rejoin_threshold = UP_IPI * 3UL; if(rejoin_threshold < 30) rejoin_threshold = 30;
    if((state == STATE_JOIN || state == STATE_SEND || state == STATE_DRAIN) &&
       now_s - last_slot_s >= rejoin_threshold &&
       lwb_get_joining_state() == LWB_JOINING_STATE_JOINED &&
       lwb_time_is_fresh() && lwb_get_n_my_slots() == 0) {
      last_slot_s = now_s; lwb_request_stream_mod(STREAM_ID, UP_IPI);
      printf("REJOIN_REQUEST,run,%lu,source,%u,reason,no_allocated_slots\r\n",
        (unsigned long)UP_RUN_ID, node_id);
    }
    if(state == STATE_DRAIN && lwb_background_allowed(30)) {
      waited = now_s - drain_started_s;
      if(waited >= UP_REPORT_WAIT && lwb_get_tx_queue_len() == 0) source_close(0);
      else if(waited >= UP_DRAIN_TIMEOUT) source_close(1);
    }
    if(state == STATE_CLOSED && reports_left && now_s >= next_report_s &&
       lwb_background_allowed(30)) {
      report_attempts++; next_report_s = now_s + UP_IPI;
      if(lwb_queue_packet((uint8_t *)&final_report, sizeof(final_report), UP_HOST_ID) == LWB_STATUS_SUCCESS) reports_left--;
      if(!reports_left || report_attempts >= UP_REPORT_REPEAT * 4 + 4) {
        reports_left = 0;
        printf("PERF_REPORT_END,run,%lu,source,%u,attempts,%u\r\n",
          (unsigned long)UP_RUN_ID, node_id, report_attempts);
      }
    }
  }
  PROCESS_END();
}
