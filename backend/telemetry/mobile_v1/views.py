"""Additive monitoring endpoints. No writes, model changes or global DRF settings."""
from datetime import timedelta
from ipaddress import ip_address, ip_network

from django.conf import settings
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import BasePermission
from rest_framework.response import Response

from telemetry.models import Node, SensorReading
from telemetry.status import HOST_MIN_SECONDS, HOST_Q, effective_last_seen, is_host, with_effective_seen
from .core import STATUSES, bounded_int, node_status, policy, reading_data


class MobileAccess(BasePermission):
    """Local mode: loopback or a configured network (Tailscale). Normal deployment: staff only.

    In local mode (LWB_MOBILE_LOCAL_ONLY) REMOTE_ADDR must be loopback or inside one of
    LWB_MOBILE_ALLOWED_NETS (CIDR list, default 100.64.0.0/10 = Tailscale). Do not trust
    X-Forwarded-For, do not expose the local settings via a reverse proxy/tunnel.
    Per-gateway roles and mobile authentication are not implemented.
    """
    message = ('Mobile API requires staff authentication or, in local settings, '
               'a loopback/LWB_MOBILE_ALLOWED_NETS client address.')

    def has_permission(self, request, view):
        if getattr(settings, 'LWB_MOBILE_LOCAL_ONLY', False):
            try:
                addr = ip_address(request.META.get('REMOTE_ADDR', ''))
            except ValueError:
                return False
            if addr.version == 6 and addr.ipv4_mapped is not None:
                addr = addr.ipv4_mapped  # dual-stack socket reporting ::ffff:a.b.c.d
            if addr.is_loopback:
                return True
            for net in getattr(settings, 'LWB_MOBILE_ALLOWED_NETS', ()):
                try:
                    if addr in ip_network(net, strict=False):
                        return True
                except ValueError:
                    continue  # ignore a malformed entry rather than open access
            return False
        return bool(request.user and request.user.is_authenticated and request.user.is_staff)


def config():
    return policy(
        int(getattr(settings, 'LWB_MOBILE_LIVE_SECONDS', 15)),
        int(getattr(settings, 'LWB_MOBILE_OFFLINE_SECONDS', 30)),
        int(getattr(settings, 'LWB_MOBILE_FUTURE_SECONDS', 10)),
    )


def host_window(cfg):
    return max(cfg['offline_seconds'], HOST_MIN_SECONDS)


def status_queries(now, cfg):
    live = now - timedelta(seconds=cfg['live_seconds'])
    offline = now - timedelta(seconds=cfg['offline_seconds'])
    host = now - timedelta(seconds=host_window(cfg))
    future = now + timedelta(seconds=cfg['future_seconds'])
    return {
        'never': Q(eff_seen__isnull=True),
        'clock_error': Q(eff_seen__gt=future),
        'live': (~HOST_Q & Q(eff_seen__gte=live, eff_seen__lte=future))
                | (HOST_Q & Q(eff_seen__gte=host, eff_seen__lte=future)),
        'stale': ~HOST_Q & Q(eff_seen__gte=offline, eff_seen__lt=live),
        'offline': (~HOST_Q & Q(eff_seen__lt=offline)) | (HOST_Q & Q(eff_seen__lt=host)),
    }


def node_data(node, now, cfg):
    seen = effective_last_seen(node)  # host-aware, shared with /api/overview/
    live_s, offline_s = cfg['live_seconds'], cfg['offline_seconds']
    if is_host(node):  # no stale band: one window covers the 30 s perf cadence
        live_s = offline_s = host_window(cfg)
    return {
        'gateway_id': node.gateway.gateway_id, 'node_id': node.node_id,
        'role': node.role or '',
        'last_seen': seen.isoformat() if seen else None,
        'created_at': node.created_at.isoformat(),
        'status': node_status(seen, now, live_s, offline_s, cfg['future_seconds']),
    }


def response(data):
    result = Response(data)
    # A stale cached list must not claim nodes are still live.
    result['Cache-Control'] = 'no-store'
    return result


def parse_int(request, key, default, maximum):
    try:
        return bounded_int(request.query_params.get(key), default, maximum, key)
    except ValueError as exc:
        raise ValidationError({key: str(exc)}) from exc


def base_nodes(request):
    qs = with_effective_seen(Node.objects.all())
    gateway = request.query_params.get('gateway', '').strip()
    q = request.query_params.get('q', '').strip()
    if len(gateway) > 100 or len(q) > 100:
        raise ValidationError('gateway and q must have at most 100 characters.')
    if gateway:
        qs = qs.filter(gateway__gateway_id=gateway)
    if q:
        term = Q(gateway__gateway_id__icontains=q)
        if q.isdecimal() and len(q) <= 10:
            term |= Q(node_id=int(q))
        qs = qs.filter(term)
    return qs


def summary_data(qs, now, cfg):
    filters = status_queries(now, cfg)
    return qs.aggregate(total=Count('pk'), **{
        key: Count('pk', filter=predicate) for key, predicate in filters.items()
    })


@api_view(['GET'])
@permission_classes([MobileAccess])
def health(request):
    # Executes a small DB query so a 200 response also checks DB connectivity.
    Node.objects.exists()
    return response({'service': 'lwb-mobile', 'api_version': 1,
                     'server_time': timezone.now().isoformat(), 'policy': config(),
                     'mode': 'local_read_only' if getattr(settings, 'LWB_MOBILE_LOCAL_ONLY', False)
                             else 'staff_read_only'})


@api_view(['GET'])
@permission_classes([MobileAccess])
def node_list(request):
    now, cfg = timezone.now(), config()
    qs = base_nodes(request)
    summary = summary_data(qs, now, cfg)  # One aggregate query, no per-node queries.
    status = request.query_params.get('status', '').strip()
    if status and status not in STATUSES:
        raise ValidationError({'status': 'Use live, stale, offline, never or clock_error.'})
    if status:
        qs = qs.filter(status_queries(now, cfg)[status])
    count = summary[status] if status else summary['total']
    size = parse_int(request, 'page_size', 25, 100)
    requested = parse_int(request, 'page', 1, 1000000)
    pages = max(1, (count + size - 1) // size)
    page = min(requested, pages)  # Recover gracefully when the last page shrinks.
    start = (page - 1) * size
    # Stable ordering: don't move a row just because last_seen changed.
    rows = qs.select_related('gateway').order_by('gateway__gateway_id', 'node_id', 'pk')[start:start + size]
    return response({'server_time': now.isoformat(), 'policy': cfg, 'summary': summary,
                     'count': count, 'page': page, 'page_size': size, 'pages': pages,
                     'has_next': page < pages, 'has_previous': page > 1,
                     'results': [node_data(n, now, cfg) for n in rows]})


@api_view(['GET'])
@permission_classes([MobileAccess])
def summary(request):
    now, cfg = timezone.now(), config()
    return response({'server_time': now.isoformat(), 'policy': cfg,
                     'summary': summary_data(base_nodes(request), now, cfg)})


def selected_node(request, node_id):
    gateway = request.query_params.get('gateway', '').strip()
    if not gateway or len(gateway) > 100:
        raise ValidationError({'gateway': 'A gateway ID is required (maximum 100 characters).'})
    return get_object_or_404(with_effective_seen(Node.objects.select_related('gateway')),
                             gateway__gateway_id=gateway, node_id=node_id)


@api_view(['GET'])
@permission_classes([MobileAccess])
def latest(request, node_id):
    now, cfg = timezone.now(), config()
    node = selected_node(request, node_id)
    row = (SensorReading.objects.filter(node=node, gateway=node.gateway)
           .select_related('node', 'gateway').order_by('-recv_ts_utc', '-pk').first())
    return response({'server_time': now.isoformat(), 'policy': cfg,
                     'node': node_data(node, now, cfg),
                     'reading': reading_data(row) if row else None})


@api_view(['GET'])
@permission_classes([MobileAccess])
def history(request, node_id):
    node = selected_node(request, node_id)
    limit = parse_int(request, 'limit', 100, 1000)
    rows = list(SensorReading.objects.filter(node=node, gateway=node.gateway)
                .select_related('node', 'gateway').order_by('-recv_ts_utc', '-pk')[:limit])
    rows.reverse()  # Chronological order for charts, oldest -> newest.
    return response({'server_time': timezone.now().isoformat(), 'count': len(rows),
                     'limit': limit, 'results': [reading_data(r) for r in rows]})
