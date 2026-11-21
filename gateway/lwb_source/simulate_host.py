#!/usr/bin/env python3
"""TEST ONLY: imitate the HOST UART output of the unified firmware.

Writes lines in the exact firmware format (with *HH checksum) so the gateway,
MQTT and dashboard can be tested without kits. Optionally corrupts a fraction
of lines to check that the gateway rejects them.

Data produced here is synthetic. Never use it as a measurement result.

  python3 simulate_host.py --pty            # creates a fake serial port, prints its path
  python3 simulate_host.py --stdout         # print lines only
"""
import argparse
import os
import random
import sys
import time

RUN = 9001


def cs(line):
    x = 0
    for ch in line:
        x ^= ord(ch)
    return f"{line}*{x:02X}\r\n"


def corrupt(line):
    i = random.randrange(1, len(line) - 3)
    return line[:i] + line[i + 1:]  # drop one character, like the real UART fault


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--pty", action="store_true")
    g.add_argument("--stdout", action="store_true")
    ap.add_argument("--sources", default="2:3:4:5")
    ap.add_argument("--round", type=float, default=5.0, help="seconds per LWB round")
    ap.add_argument("--loss", type=float, default=0.03, help="simulated radio loss per packet")
    ap.add_argument("--corrupt", type=float, default=0.05, help="fraction of UART lines corrupted")
    ap.add_argument("--packets", type=int, default=100)
    args = ap.parse_args()

    if args.pty:
        import pty
        master, slave = pty.openpty()
        print("Fake serial port:", os.ttyname(slave), flush=True)
        out = lambda s: os.write(master, s.encode())
    else:
        out = lambda s: (sys.stdout.write(s), sys.stdout.flush())

    def emit(line):
        if random.random() < args.corrupt:
            out(corrupt(cs(line)))
        else:
            out(cs(line))

    sources = [int(s) for s in args.sources.split(":")]
    emit(f"PERF_CONFIG,protocol,env_perf_v1,node,1,role,HOST,run,{RUN},expected,{args.packets},ipi_s,5,"
         f"source_ids,{args.sources},payload_bytes,28,timer_hz,32768,channel,26,tx_drive_dbm,7,n_sync,3,"
         f"n_data_tx,3,application_ack,0,application_retry,0,rtc_integrated,0,delay_endpoint,slot_end,scheduler,static_5s")
    seq = {s: 0 for s in sources}
    got = {s: 0 for s in sources}
    delays = {s: [] for s in sources}
    rnd = 0
    while True:
        rnd += 1
        t = 21.0 + random.random()
        emit(f"LOCAL,run,{RUN},node,1,seq,{rnd * 5},sensor_mask,7,hdc_temp_x10,{int(t * 10 + 80)},"
             f"hdc_hum_x10,{random.randint(600, 700)},light_raw,{random.randint(100, 140)},"
             f"bmp_temp_x10,{int(t * 10 + 85)},pressure_pa,{random.randint(100700, 100800)}")
        for i, s in enumerate(sources):
            if seq[s] >= args.packets:
                continue
            seq[s] += 1
            if random.random() < args.loss:
                continue
            got[s] += 1
            hop = 1 if s in (2, 3) else 2
            d = int(80 + 35 * i + random.random() * 20)
            delays[s].append(d)
            emit(f"SENSOR_DATA,run,{RUN},from,{s},node,{s},seq,{seq[s]},unique,1,sensor_mask,7,"
                 f"tx_net_ticks,{rnd * 163840},rx_slot_end_ticks,{rnd * 163840 + d * 33},"
                 f"delay_ticks,{d * 33},delay_ms,{d},delay_valid,1,timer_hz,32768,relay_cnt,{hop - 1},"
                 f"hop_est,{hop},hop_est_valid,1,hdc_temp_x10,{280 + s * 3 + random.randint(-2, 2)},"
                 f"hdc_hum_x10,{650 + s * 10},light_raw,{50 * s},bmp_temp_x10,{282 + s * 3},"
                 f"pressure_pa,{100750 + s}")
        if rnd % 6 == 0:
            for s in sources:
                final = int(seq[s] >= args.packets)
                dl = delays[s] or [0]
                y = int(10000 * got[s] / seq[s]) if final and seq[s] else -1
                emit(f"PERF_SUMMARY,run,{RUN},source,{s},expected,{args.packets},received,{got[s]},duplicate,0,"
                     f"out_of_order,0,report_received,{final},final,{final},generated,{seq[s] if final else -1},"
                     f"queued,{seq[s] if final else -1},tx_started,{seq[s] if final else -1},queue_failed,{0 if final else -1},"
                     f"deadline_missed,{0 if final else -1},tx_start_failed,{0 if final else -1},drain_timeout,0,"
                     f"application_yield_x100,{y},enqueue_delivery_x100,{y},flood_delivery_x100,{y},"
                     f"delay_count,{len(delays[s])},delay_min_us,{min(dl) * 1000},"
                     f"delay_avg_us,{int(sum(dl) / len(dl) * 1000)},delay_max_us,{max(dl) * 1000},"
                     f"relay_samples,{got[s]},relay_min,{0 if s in (2, 3) else 1},relay_max,{0 if s in (2, 3) else 1}")
        time.sleep(args.round)


if __name__ == "__main__":
    main()
