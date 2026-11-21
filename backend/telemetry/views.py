from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status

from .models import Node, SensorReading
from .serializers import NodeSerializer, SensorReadingSerializer


@api_view(["GET"])
def node_list(request):
    nodes = Node.objects.select_related("gateway").order_by(
        "-last_seen",
        "gateway__gateway_id",
        "node_id"
    )

    serializer = NodeSerializer(
        nodes,
        many=True
    )

    return Response(serializer.data)


@api_view(["GET"])
def latest_reading(request, node_id):
    gateway_id = request.query_params.get("gateway")
    qs = SensorReading.objects.filter(node__node_id=node_id)
    if gateway_id:
        qs = qs.filter(gateway__gateway_id=gateway_id)

    reading = (
        qs.select_related("node", "gateway")
        .order_by("-recv_ts_utc")
        .first()
    )

    if reading is None:
        return Response(
            {"detail": "No data"},
            status=status.HTTP_404_NOT_FOUND
        )

    return Response(
        SensorReadingSerializer(reading).data
    )


@api_view(["GET"])
def history(request, node_id):
    try:
        limit = int(
            request.query_params.get(
                "limit",
                100
            )
        )
    except ValueError:
        return Response(
            {
                "detail":
                "limit must be an integer"
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    if limit < 1:
        return Response(
            {
                "detail":
                "limit must be greater than 0"
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    # Tránh request lấy quá nhiều dữ liệu
    limit = min(limit, 1000)

    gateway_id = request.query_params.get("gateway")
    qs = SensorReading.objects.filter(node__node_id=node_id)
    if gateway_id:
        qs = qs.filter(gateway__gateway_id=gateway_id)

    readings = (
        qs.select_related("node", "gateway")
        .order_by("-recv_ts_utc")[:limit]
    )

    serializer = SensorReadingSerializer(
        readings,
        many=True
    )

    return Response(serializer.data)


# ---------------------------------------------------------------------------
# Dashboard endpoints (one request per refresh)
# ---------------------------------------------------------------------------
from datetime import timedelta

from django.conf import settings
from django.db.models import Avg, Count, Max, Min
from django.utils import timezone

from .models import Gateway, PerfEvent
from .status import is_online, role_of, with_effective_seen


def _age_s(ts, now):
    return None if ts is None else round((now - ts).total_seconds(), 1)


@api_view(["GET"])
def overview(request):
    """All known nodes with online flag and their latest reading.

    ?online=1 returns only nodes heard within LWB_ONLINE_SECONDS. "Heard" is the effective
    last_seen of telemetry.status (shared with the Mobile API): a HOST sends almost nothing
    itself but relays its whole gateway, so it counts as heard whenever its gateway is.
    """
    now = timezone.now()
    online_s = settings.LWB_ONLINE_SECONDS
    only_online = request.query_params.get("online") in ("1", "true")

    # HOST relays every gateway packet: see telemetry/status.py.
    qs = with_effective_seen(Node.objects.select_related("gateway")).order_by("gateway__gateway_id", "node_id")
    nodes = []
    for node in qs:
        role = role_of(node)
        seen = node.eff_seen
        age = _age_s(seen, now)
        online = is_online(node, now, online_s)
        if only_online and not online:
            continue
        latest = node.readings.order_by("-recv_ts_utc").first()
        window = node.readings.filter(recv_ts_utc__gte=now - timedelta(minutes=5))
        stats = window.aggregate(n=Count("id"), delay_avg=Avg("delay_ms"),
                                 delay_max=Max("delay_ms"), hop_avg=Avg("hop_est"),
                                 hop_max=Max("hop_est"))
        nodes.append({
            "gateway_id": node.gateway.gateway_id,
            "node_id": node.node_id,
            "role": role,
            "last_seen": seen,
            "age_s": age,
            "online": online,
            "latest": SensorReadingSerializer(latest).data if latest else None,
            "last_5min": {
                "packets": stats["n"],
                "delay_avg_ms": round(stats["delay_avg"], 1) if stats["delay_avg"] is not None else None,
                "delay_max_ms": stats["delay_max"],
                "hop_avg": round(stats["hop_avg"], 2) if stats["hop_avg"] is not None else None,
                "hop_max": stats["hop_max"],
            },
        })

    gateways = [{
        "gateway_id": g.gateway_id,
        "last_seen": g.last_seen,
        "age_s": _age_s(g.last_seen, now),
        "status": g.status,
        "status_age_s": _age_s(g.status_ts, now),
    } for g in Gateway.objects.order_by("gateway_id")]

    return Response({
        "now": now,
        "online_seconds": online_s,
        "retention_minutes": settings.LWB_READING_RETENTION_MINUTES,
        "gateways": gateways,
        "nodes": nodes,
    })


def _num(d, key):
    v = d.get(key)
    return v if isinstance(v, (int, float)) and v >= 0 else None


@api_view(["GET"])
def perf(request):
    """LWB test results per source for one run (default: latest run).

    Values come from the HOST's periodic PERF_SUMMARY line, so they are the
    firmware's own counters (see lwb-cc2538dk/README_VI.md section 4).
    """
    runs = list(PerfEvent.objects.exclude(run=None).values_list("run", flat=True)
                .order_by("-recv_ts_utc").distinct()[:200])
    seen, run_list = set(), []
    for r in runs:
        if r not in seen:
            seen.add(r)
            run_list.append(r)
    run = request.query_params.get("run")
    run = int(run) if run and run.isdigit() else (run_list[0] if run_list else None)
    if run is None:
        return Response({"run": None, "runs": [], "config": [], "sources": []})

    events = PerfEvent.objects.filter(run=run).select_related("node")
    config = [{"node_id": e.node.node_id, **e.data}
              for e in events.filter(record_type="PERF_CONFIG").order_by("node__node_id", "-recv_ts_utc")]
    dedup, cfg = set(), []
    for c in config:
        if c["node_id"] not in dedup:
            dedup.add(c["node_id"])
            cfg.append(c)

    latest = {}
    for e in events.filter(record_type="PERF_SUMMARY").order_by("-recv_ts_utc"):
        src = e.data.get("source", e.node.node_id)
        if src not in latest:
            latest[src] = e
    sources = []
    for src, e in sorted(latest.items()):
        d = e.data
        expected = _num(d, "expected")
        received = _num(d, "received")
        x100 = lambda k: (d.get(k) / 100.0) if isinstance(d.get(k), (int, float)) and d.get(k) >= 0 else None
        sources.append({
            "source": src,
            "recv_ts_utc": e.recv_ts_utc,
            "final": d.get("final") == 1,
            "expected": expected,
            "received": received,
            "duplicate": _num(d, "duplicate"),
            "generated": _num(d, "generated"),
            "progress_pct": round(100.0 * received / expected, 1) if expected and received is not None else None,
            "application_yield_pct": x100("application_yield_x100"),
            "flood_delivery_pct": x100("flood_delivery_x100"),
            "delay_min_ms": round(d["delay_min_us"] / 1000, 1) if _num(d, "delay_min_us") is not None and d.get("delay_count") else None,
            "delay_avg_ms": round(d["delay_avg_us"] / 1000, 1) if _num(d, "delay_avg_us") is not None and d.get("delay_count") else None,
            "delay_max_ms": round(d["delay_max_us"] / 1000, 1) if _num(d, "delay_max_us") is not None and d.get("delay_count") else None,
            "relay_min": d.get("relay_min") if d.get("relay_samples") else None,
            "relay_max": d.get("relay_max") if d.get("relay_samples") else None,
        })
    aborts = list(events.filter(record_type="PERF_ABORT").values_list("node__node_id", flat=True))
    return Response({"run": run, "runs": run_list, "config": cfg, "sources": sources,
                     "join_failed_nodes": sorted(set(aborts))})
