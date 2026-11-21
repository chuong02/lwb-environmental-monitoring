"""Additive monitoring endpoints. No writes, model changes or global DRF settings."""
from datetime import timedelta
from ipaddress import ip_address

from django.conf import settings
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import BasePermission
from rest_framework.response import Response

from telemetry.models import Node, SensorReading
from .core import STATUSES, bounded_int, node_status, policy, reading_data


class MobileAccess(BasePermission):
    """Local test server: loopback only. Normal deployment: staff only.

    Do not trust X-Forwarded-For, do not expose the local settings via a reverse
    proxy/tunnel. Per-gateway roles and mobile authentication are not implemented.
    """
    message = 'Mobile API requires staff authentication or the loopback-only local settings.'

    def has_permission(self, request, view):
        if getattr(settings, 'LWB_MOBILE_LOCAL_ONLY', False):
            try:
                return ip_address(request.META.get('REMOTE_ADDR', '')).is_loopback
            except ValueError:
                return False
        return bool(request.user and request.user.is_authenticated and request.user.is_staff)


def config():
    return policy(
        int(getattr(settings, 'LWB_MOBILE_LIVE_SECONDS', 15)),
        int(getattr(settings, 'LWB_MOBILE_OFFLINE_SECONDS', 30)),
        int(getattr(settings, 'LWB_MOBILE_FUTURE_SECONDS', 10)),
    )


def status_queries(now, cfg):
    live = now - timedelta(seconds=cfg['live_seconds'])
    offline = now - timedelta(seconds=cfg['offline_seconds'])
    future = now + timedelta(seconds=cfg['future_seconds'])
    return {
        'never': Q(last_seen__isnull=True),
        'clock_error': Q(last_seen__gt=future),
        'live': Q(last_seen__gte=live, last_seen__lte=future),
        'stale': Q(last_seen__gte=offline, last_seen__lt=live),
        'offline': Q(last_seen__lt=offline),
    }


def node_data(node, now, cfg):
    return {
        'gateway_id': node.gateway.gateway_id, 'node_id': node.node_id,
        'last_seen': node.last_seen.isoformat() if node.last_seen else None,
        'created_at': node.created_at.isoformat(),
        'status': node_status(node.last_seen, now, cfg['live_seconds'],
                              cfg['offline_seconds'], cfg['future_seconds']),
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
    qs = Node.objects.all()
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
    return get_object_or_404(Node.objects.select_related('gateway'),
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
