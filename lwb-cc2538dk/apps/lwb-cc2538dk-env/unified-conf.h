#ifndef UNIFIED_CONF_H_
#define UNIFIED_CONF_H_
#define ROLE_AUTO 0
#define ROLE_HOST 1
#define ROLE_SOURCE 2
#define ROLE_RELAY 3
#if UP_ROLE < 0 || UP_ROLE > 3
#error "ROLE must be 0, 1, 2 or 3"
#endif
/* PACKETS=0 selects continuous mode (no fixed count, periodic REPORT). */
#if UP_PACKETS < 0 || UP_PACKETS > 2000
#error "PACKETS must be 0 (continuous) or between 1 and 2000"
#endif
#define UP_CONTINUOUS (UP_PACKETS == 0)

/* Phase-aligned generation and queue hygiene. All default to the legacy
 * behaviour (etimer IPI, no gating). FRESH_ONLY follows GEN_MODE unless the
 * build passes FRESH_ONLY explicitly. */
#ifndef UP_GEN_MODE
#define UP_GEN_MODE 0
#endif
#ifndef UP_GEN_LEAD_MS
#define UP_GEN_LEAD_MS 250
#endif
/* GEN_MODE=1: sensors are read (I2C, no OLED) right before the enqueue when at least
 * GEN_GUARD_MS + SENSOR_BUDGET_MS remain before the next round; else the old sample is
 * reused and counted in sensor_stale. The lead must leave room for this read. */
#ifndef UP_SENSOR_BUDGET_MS
#define UP_SENSOR_BUDGET_MS 150
#endif
#ifndef UP_FRESH_ONLY
#define UP_FRESH_ONLY UP_GEN_MODE
#endif
#ifndef UP_REPORT_EVERY
#define UP_REPORT_EVERY 60
#endif
/* Software radio duty-cycle accounting (Glossy radio on/off timestamps). 0 = off: no code,
 * no UART line. PERIOD = LWB rounds between two PERF_RADIO lines (12 rounds = 60 s). */
#ifndef UP_RADIO_STATS
#define UP_RADIO_STATS 0
#endif
#ifndef UP_RADIO_STATS_PERIOD
#define UP_RADIO_STATS_PERIOD 12
#endif
#if UP_GEN_MODE < 0 || UP_GEN_MODE > 1
#error "GEN_MODE must be 0 (etimer IPI) or 1 (phase aligned)"
#endif
#if UP_FRESH_ONLY < 0 || UP_FRESH_ONLY > 1
#error "FRESH_ONLY must be 0 or 1"
#endif
/* Lead must exceed the 30 ms safe-window guard plus etimer granularity, and
 * stay well inside the ~4.7 s idle part of a 5 s round. For a fresh sensor read at
 * release time it should also exceed 30 + SENSOR_BUDGET_MS + etimer slack (default 250). */
#if UP_GEN_LEAD_MS < 50 || UP_GEN_LEAD_MS > 3000
#error "GEN_LEAD_MS must be between 50 and 3000"
#endif
#if UP_SENSOR_BUDGET_MS < 20 || UP_SENSOR_BUDGET_MS > 1000
#error "SENSOR_BUDGET_MS must be between 20 and 1000"
#endif
#if UP_REPORT_EVERY < 5 || UP_REPORT_EVERY > 10000
#error "REPORT_EVERY must be between 5 and 10000"
#endif
#if UP_RADIO_STATS < 0 || UP_RADIO_STATS > 1
#error "RADIO_STATS must be 0 or 1"
#endif
#if UP_RADIO_STATS_PERIOD < 1 || UP_RADIO_STATS_PERIOD > 10000
#error "RADIO_STATS_PERIOD must be between 1 and 10000 rounds"
#endif
#if UP_RADIO_STATS && !GLOSSY_RADIO_STATS
#error "RADIO_STATS=1 needs the Glossy accounting: build with GLOSSY_RADIO_STATS_CONF=1 (the Makefile does)"
#endif
#if UP_GEN_MODE && !LWB_ROUND_TIMING_CONF
#error "GEN_MODE=1 needs lwb_get_next_round_ticks(): build with LWB_ROUND_TIMING_CONF=1 (the Makefile does)"
#endif
/* Static scheduler period (LWB_SCHED_PERIOD_STEADY in lwb-scheduler-static.c). */
#define UP_ROUND_PERIOD_S 5
#define UP_GEN_ROUNDS (UP_IPI / UP_ROUND_PERIOD_S)
/* Uploaded port has a static 5-second scheduler. */
#if UP_IPI < 5 || (UP_IPI % 5) != 0
#error "This static scheduler profile requires IPI >=5 and a multiple of 5"
#endif
#if UP_SAMPLE_PERIOD < 1 || UP_MAX_NODE_ID < 2 || UP_MAX_NODE_ID > 32
#error "Invalid sample period or MAX_NODE_ID"
#endif
#if UP_START_DELAY < 1 || UP_JOIN_TIMEOUT <= UP_START_DELAY
#error "JOIN_TIMEOUT must be greater than START_DELAY >=1"
#endif
#if UP_DRAIN_TIMEOUT < UP_REPORT_WAIT || UP_REPORT_WAIT < 1
#error "DRAIN_TIMEOUT must be >= REPORT_WAIT >=1"
#endif
#if UP_REPORT_REPEAT < 0 || UP_REPORT_REPEAT > 10 || UP_SUMMARY_PERIOD < 1
#error "REPORT_REPEAT must be 0..10 and SUMMARY_PERIOD >=1"
#endif
#if UP_MAX_DELAY_S < 1 || UP_MAX_DELAY_S > 3600 || UP_IPI > 3600
#error "MAX_DELAY_S must be 1..3600 and IPI <=3600"
#endif
#if UP_RUN_ID < 1 || UP_RUN_ID > 4294967295ULL
#error "RUN_ID must be 1..4294967295"
#endif
#if CC2538_RF_CONF_CHANNEL < 11 || CC2538_RF_CONF_CHANNEL > 26
#error "CHANNEL must be between 11 and 26"
#endif
#if N_SYNC < 1 || N_SYNC > 8 || N_RR < 1 || N_RR > 8
#error "This Glossy port supports N_SYNC/N_DATA_TX between 1 and 8"
#endif
#if LWB_MAX_DATA_BUF_ELEMENTS < 1 || LWB_MAX_DATA_BUF_ELEMENTS > 64
#error "DATA_BUFFERS must be 1..64; verify link map RAM usage"
#endif
#if CC2592_CONF_TX_POWER_DBM != 7 && CC2592_CONF_TX_POWER_DBM != 5 && \
    CC2592_CONF_TX_POWER_DBM != 3 && CC2592_CONF_TX_POWER_DBM != 1 && \
    CC2592_CONF_TX_POWER_DBM != 0 && CC2592_CONF_TX_POWER_DBM != -1 && \
    CC2592_CONF_TX_POWER_DBM != -3 && CC2592_CONF_TX_POWER_DBM != -5 && \
    CC2592_CONF_TX_POWER_DBM != -7 && CC2592_CONF_TX_POWER_DBM != -9 && \
    CC2592_CONF_TX_POWER_DBM != -11 && CC2592_CONF_TX_POWER_DBM != -13 && \
    CC2592_CONF_TX_POWER_DBM != -15 && CC2592_CONF_TX_POWER_DBM != -24
#error "TX_POWER_DBM must be an exact drive level from the CC2538 table"
#endif
/* Continuous mode keeps no per-seq bitmap; 1 keeps array sizes legal. */
#define UP_BITMAP_BYTES (UP_PACKETS > 0 ? ((UP_PACKETS + 7) / 8) : 1)
#define UP_MAX_DELAY_TICKS ((uint32_t)UP_MAX_DELAY_S * (uint32_t)RTIMER_SECOND)
#endif
