#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "env-perf-packet.h"
#include "env-perf-stats.h"
#include "lwb-sched-compressor.h"
#include "lwb-scheduler.h"
#include "lwb-macros.h"
#include "../net/glossy/glossy-radio-stats.h"

lwb_context_t lwb_context;

static void test_stats(void)
{
  up_stats_t s = {0};
  uint8_t seen[250] = {0};
  uint32_t d;
  uint16_t i;
  assert(sizeof(up_packet_t) == 28);
  assert(up_delay(0, 0, 1, 1, 100, &d) && d == 0);
  assert(up_delay(0xfffffff0UL, 0x10, 1, 1, 100, &d) && d == 32);
  assert(!up_delay(100, 99, 1, 1, 100, &d));
  assert(!up_delay(0, 1, 0, 1, 100, &d));
  assert(!up_delay(0, 101, 1, 1, 100, &d));
  assert(up_stats_rx(&s, seen, 2, 2000, 1, 0) == 1);
  assert(up_stats_rx(&s, seen, 1, 2000, 1, 20) == 1);
  assert(up_stats_rx(&s, seen, 2, 2000, 1, 999) == 2);
  assert(up_stats_rx(&s, seen, 0, 2000, 1, 50) == 0);
  assert(up_stats_rx(&s, seen, 2001, 2000, 1, 50) == 0);
  assert(s.unique == 2 && s.duplicate == 1 && s.out_of_order == 1);
  assert(s.delay_count == 2 && s.delay_min_ticks == 0 && s.delay_max_ticks == 20);
  assert(s.delay_sum_ticks == 20);
  for(i = 3; i <= 2000; i++) assert(up_stats_rx(&s, seen, i, 2000, 1, 3000000) == 1);
  assert(s.unique == 2000 && s.delay_sum_ticks > 0xffffffffULL);
  assert(up_ratio(9, 10) == 9000 && up_ratio(0, 0) == -1);
}

static void test_codec(void)
{
  lwb_schedule_t a, b;
  uint8_t buf[125], len, count, i;
  const uint8_t counts[] = {0, 1, 2, 17, LWB_SCHED_MAX_SLOTS};
  for(count = 0; count < sizeof(counts); count++) {
    memset(&a, 0, sizeof(a)); memset(&b, 0, sizeof(b));
    LWB_SET_N_DATA_SLOTS(a.sched_info.n_slots, counts[count]);
    LWB_SET_N_FREE_SLOTS(a.sched_info.n_slots, 1);
    for(i = 0; i < counts[count]; i++) a.slots[i] = i % 2 ? 65535 : i + 1;
    len = lwb_sched_compress(&a, buf, sizeof(buf));
    assert(len > 0);
    b.sched_info = a.sched_info;
    assert(lwb_sched_decompress(&b, buf, len) == 1);
    assert(!memcmp(a.slots, b.slots, counts[count] * sizeof(uint16_t)));
    assert(lwb_sched_decompress(&b, buf, 0) == 0);
    if(counts[count]) assert(lwb_sched_decompress(&b, buf, len - 1) == 0);
  }
  memset(&b, 0, sizeof(b)); b.sched_info.n_slots = 1;
  buf[0] = 0; assert(!lwb_sched_decompress(&b, buf, 2));
  buf[0] = 17; assert(!lwb_sched_decompress(&b, buf, 2));
  b.sched_info.n_slots = LWB_SCHED_MAX_SLOTS + 1;
  assert(!lwb_sched_decompress(&b, buf, 2));
}

static void add_test_stream(void)
{
  lwb_stream_req_t req = {0};
  memset(&lwb_context, 0, sizeof(lwb_context));
  lwb_sched_init();
  req.ipi = 5;
  LWB_SET_STREAM_ID(req.req_type, 2);
  LWB_SET_STREAM_TYPE(req.req_type, LWB_STREAM_TYPE_MOD);
  lwb_sched_process_stream_req(3, &req);
  /* ACK slot is removed to make the only DATA slot be slot zero. */
  lwb_context.n_stream_acks = 0;
  lwb_sched_compute_schedule(&lwb_context.current_sched);
  assert(N_CURRENT_DATA_SLOTS() == 1 && CURRENT_SCHEDULE().slots[0] == 3);
}

static void test_slot_zero_and_flags(void)
{
  unsigned i;
  add_test_stream();
  for(i = 0; i <= LWB_SCHED_N_CONS_MISSED_MAX; i++) {
    lwb_sched_update_data_slot_usage(0, 0);
    lwb_sched_compute_schedule(&lwb_context.current_sched);
  }
  assert(N_CURRENT_DATA_SLOTS() == 0);
  add_test_stream();
  for(i = 0; i < 20; i++) {
    lwb_sched_update_data_slot_usage(0, 0);
    lwb_sched_update_data_slot_usage(0, 1);
    lwb_sched_compute_schedule(&lwb_context.current_sched);
    assert(N_CURRENT_DATA_SLOTS() == 1);
  }
  lwb_context.poll_flags = 0;
  LWB_SET_POLL_FLAG(LWB_POLL_FLAGS_SCHED_END);
  assert(!LWB_IS_SET_POLL_FLAG(LWB_POLL_FLAGS_DATA));
  assert(LWB_IS_SET_POLL_FLAG(LWB_POLL_FLAGS_SCHED_END));
}

/* PACKETS=0 helpers: 16-bit wire seq cycling 1..65535, 32-packet duplicate window. */
static void test_continuous(void)
{
  up_cstats_t s;
  uint32_t n;
  assert(up_seq_wire(1) == 1 && up_seq_wire(65535) == 65535);
  assert(up_seq_wire(65536) == 1 && up_seq_wire(131071) == 1);
  for(n = 1; n < 200000; n++) assert(up_seq_wire(n) != 0);
  assert(up_seq_diff(1, 65535) == 1 && up_seq_diff(65535, 1) == -1);
  assert(up_seq_diff(32768, 1) == 32767 && up_seq_diff(32769, 1) == -32767);
  memset(&s, 0, sizeof(s));
  for(n = 1; n <= 140000; n++) assert(up_cstats_rx(&s, up_seq_wire(n), 1, 10) == 1);
  assert(s.unique == 140000 && s.highest == 140000 && s.delay_sum_ticks == 1400000ULL);
  assert(up_cstats_rx(&s, up_seq_wire(140000), 1, 10) == 2);
  assert(up_cstats_rx(&s, up_seq_wire(139990), 1, 10) == 2);
  assert(up_cstats_rx(&s, 0, 1, 10) == 0);
  assert(s.duplicate == 2 && s.out_of_order == 0 && s.unique == 140000);
  memset(&s, 0, sizeof(s));
  assert(up_cstats_rx(&s, up_seq_wire(65536), 0, 0) == 1);  /* wire seq 1 after the wrap */
  assert(up_cstats_rx(&s, 65535, 0, 0) == 1 && s.out_of_order == 1);
  assert(up_cstats_rx(&s, 65535, 0, 0) == 2);
  assert(up_ext16(65530, 5) == 65541 && up_ext16(60, 120) == 120);
  assert(up_ratio32(9, 10) == 9000 && up_ratio32(1, 0) == -1);
}

/* RADIO_STATS arithmetic (net/glossy/glossy-radio-stats.h): on/off pairs, RTIMER wrap, TX estimate. */
static void test_radio_stats(void)
{
  glossy_rs_t rs;
  glossy_radio_stats_t o;
  memset(&rs, 0, sizeof(rs));
  glossy_rs_off(&rs, 100, 3, 41);                  /* off without on: ignored */
  glossy_rs_read(&rs, &o);
  assert(o.floods == 0 && o.radio_on_ticks == 0 && !rs.on);
  glossy_rs_on(&rs, 1000);
  glossy_rs_on(&rs, 1500);                         /* second start keeps the first timestamp */
  glossy_rs_off(&rs, 1000 + 400, 3, 41);
  glossy_rs_off(&rs, 1000 + 999, 3, 41);           /* second stop of the same flood: ignored */
  glossy_rs_read(&rs, &o);
  assert(o.floods == 1 && o.radio_on_ticks == 400 && o.tx_count == 3);
  assert(o.tx_on_us == 3u * (6 + 41) * 32);        /* 4512 us */
  assert((rs.seq & 1u) == 0 && rs.seq == 2);
  /* RTIMER wrap: on at 2^32 - 100, off 250 ticks later (counter restarted at 150). */
  glossy_rs_on(&rs, 0xffffff9cu);
  glossy_rs_off(&rs, 150u, 0, 0);
  glossy_rs_read(&rs, &o);
  assert(o.floods == 2 && o.radio_on_ticks == 650 && o.tx_count == 3 && o.tx_on_us == 4512);
  /* Many floods with a wrap in between: 64-bit sum, no 32-bit overflow. */
  {
    uint32_t t = 0xfffff000u, i;
    uint64_t expect = o.radio_on_ticks;
    for(i = 0; i < 100000; i++) {
      glossy_rs_on(&rs, t); t += 1000;
      glossy_rs_off(&rs, t, 1, 20); t += 40000; expect += 1000;
    }
    glossy_rs_read(&rs, &o);
    assert(o.floods == 100002 && o.radio_on_ticks == expect && expect > 0xffffffffULL / 1000);
    assert(o.tx_count == 100003);
  }
  /* A long flood (e.g. bootstrap listening) across the wrap: 0x80000000 -> 0x10000 is 0x80010000 ticks. */
  {
    uint64_t before = o.radio_on_ticks;
    glossy_rs_on(&rs, 0x80000000u);
    glossy_rs_off(&rs, 0x10000u, 0, 0);
    glossy_rs_read(&rs, &o);
    assert(o.radio_on_ticks == before + 0x80010000ULL && o.floods == 100003);
  }
}

int main(void)
{
  test_stats(); test_codec(); test_slot_zero_and_flags(); test_continuous(); test_radio_stats();
  puts("PASS: packet size, delay/wrap, duplicate/ordering, codec/invalid input, slot zero, poll flags, continuous helpers, radio stats");
  return 0;
}
