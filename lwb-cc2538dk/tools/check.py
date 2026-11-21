#!/usr/bin/env python3
"""Run actual host-side C codec/stats/scheduler tests and Python log tests."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--contiki", required=True, type=Path)
    args = ap.parse_args()
    project = Path(__file__).resolve().parents[1]
    core = args.contiki.expanduser().resolve() / "core"
    if not (core / "lib/list.c").exists():
        ap.error("--contiki must contain core/lib/list.c")
    subprocess.run(["python3", "-m", "unittest", "discover", "-s", str(project / "tests"), "-p", "test_*.py", "-v"], check=True)
    with tempfile.TemporaryDirectory(prefix="lwb-native-") as tmp:
        executable = Path(tmp) / "native-tests"
        cmd = ["cc", "-std=c99", "-Wall", "-Wextra", "-Werror", "-g",
               "-fsanitize=address,undefined", "-fno-omit-frame-pointer",
               "-DLWB_CONF_SCHED_N_CONS_MISSED_MAX=2",
               "-I" + str(project / "tests/stubs"), "-I" + str(project / "net/lwb"),
               "-I" + str(project / "apps/lwb-cc2538dk-env"), "-I" + str(core),
               str(project / "tests/test_native.c"), str(project / "net/lwb/lwb-sched-compressor.c"),
               str(project / "net/lwb/lwb-scheduler-static.c"), str(core / "lib/list.c"),
               str(core / "lib/memb.c"), "-o", str(executable)]
        subprocess.run(cmd, check=True)
        env = os.environ.copy()
        # These embedded modules use static pools, not malloc. LeakSanitizer
        # cannot enumerate threads in some traced CI/container environments.
        env["ASAN_OPTIONS"] = env.get("ASAN_OPTIONS", "") + ":detect_leaks=0"
        subprocess.run([str(executable)], check=True, env=env)


if __name__ == "__main__":
    main()
