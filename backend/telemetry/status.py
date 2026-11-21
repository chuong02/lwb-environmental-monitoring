"""One answer to "when was this node last heard?" and "is it online?".

Used by the web dashboard (/api/overview/) and by the Mobile API (/api/mobile/v1/), so both
report the same thing for the same node.

Why the HOST is special
-----------------------
The HOST (role "host", or node 1 while its role is still unknown) is the sink wired to the
gateway over UART. It sends hardly anything of its own (PERF_CONFIG once at start-up), yet every
SENSOR_DATA / PERF_* record of the whole network reaches the database *through* it. Its stored
``last_seen`` therefore freezes while the network is perfectly alive. So:

    normal node : effective_last_seen = its own last_seen
    HOST        : max(its own last_seen,
                      newest last_seen of any node on the same gateway,
                      newest PerfEvent of the same gateway)

``with_effective_seen`` computes this in SQL (annotation ``eff_seen``), so a list of nodes costs no
extra queries and can still be filtered, counted and paginated. ``effective_last_seen`` and
``is_online`` are the one-node conveniences built on the very same expression.
"""
from django.conf import settings
from django.db.models import Case, DateTimeField, F, OuterRef, Q, Subquery, When
from django.db.models.functions import Coalesce, Greatest
from django.utils import timezone

from .models import Node, PerfEvent

HOST_ROLE = 'host'
HOST_NODE_ID = 1  # a node whose role is not known yet is taken to be the HOST if it has this id
HOST_MIN_SECONDS = 45  # the HOST's own PERF_SUMMARY cadence is 30 s: never judge it by less
FUTURE_SECONDS = 10  # a last_seen further ahead than this is a clock error, not "online"

# SQL twin of is_host(); keep the two in step.
HOST_Q = Q(role__iexact=HOST_ROLE) | Q(role='', node_id=HOST_NODE_ID)


def is_host(node):
    role = (node.role or '').lower()
    return role == HOST_ROLE or (role == '' and node.node_id == HOST_NODE_ID)


def role_of(node):
    """The role to show: the stored one, else guessed from the node id."""
    if is_host(node):
        return HOST_ROLE
    return node.role or 'source'


def _newest(*times):
    """Newest non-NULL of several timestamp expressions; NULL only if every one is NULL.

    GREATEST/MAX return NULL when any argument is NULL on SQLite and MySQL but skip NULLs on
    PostgreSQL, so each argument is padded with Coalesce(...) to make all backends agree.
    """
    return Greatest(*(Coalesce(t, *times[:i], *times[i + 1:]) for i, t in enumerate(times)))


def with_effective_seen(qs):
    """Annotate a Node queryset with ``eff_seen`` = effective_last_seen (None if never heard)."""
    gateway_nodes = Subquery(Node.objects.filter(gateway=OuterRef('gateway'), last_seen__isnull=False)
                             .order_by('-last_seen').values('last_seen')[:1])
    gateway_perf = Subquery(PerfEvent.objects.filter(gateway=OuterRef('gateway'))
                            .order_by('-recv_ts_utc').values('recv_ts_utc')[:1])
    # The lookups sit inside the CASE branch, so only HOST rows pay for them (not every node).
    return qs.annotate(eff_seen=Case(
        When(HOST_Q, then=_newest(F('last_seen'), gateway_nodes, gateway_perf)),
        default=F('last_seen'),
        output_field=DateTimeField(),
    ))


def effective_last_seen(node):
    """effective_last_seen of one node: a datetime, or None if it has never been heard."""
    if hasattr(node, 'eff_seen'):  # the node came from a with_effective_seen() queryset
        return node.eff_seen
    return (with_effective_seen(Node.objects.filter(pk=node.pk))
            .values_list('eff_seen', flat=True).first())


def window_for(node, online_s=None):
    """Seconds since effective_last_seen within which the node counts as online."""
    if online_s is None:
        online_s = settings.LWB_ONLINE_SECONDS
    return max(online_s, HOST_MIN_SECONDS) if is_host(node) else online_s


def is_online(node, now=None, online_s=None, future_s=FUTURE_SECONDS):
    """online = effective_last_seen within LWB_ONLINE_SECONDS (a HOST gets HOST_MIN_SECONDS at least)."""
    seen = effective_last_seen(node)
    if seen is None:
        return False
    age = ((now or timezone.now()) - seen).total_seconds()
    return -future_s <= age <= window_for(node, online_s)
