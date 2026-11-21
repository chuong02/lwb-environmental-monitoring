from django.db import models


class Gateway(models.Model):
    gateway_id = models.CharField(
        max_length=100,
        unique=True
    )

    last_seen = models.DateTimeField(
        null=True,
        blank=True
    )

    # Latest retained status from the Raspberry Pi publisher
    # (UART ok/bad counters, outbox backlog, online flag).
    status = models.JSONField(default=dict, blank=True)

    status_ts = models.DateTimeField(
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return self.gateway_id


class Node(models.Model):
    gateway = models.ForeignKey(
        Gateway,
        on_delete=models.CASCADE,
        related_name="nodes"
    )

    node_id = models.PositiveIntegerField()

    # host / source / relay, learned from PERF_CONFIG or record type.
    role = models.CharField(max_length=16, blank=True, default="")

    last_seen = models.DateTimeField(
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["gateway", "node_id"],
                name="uniq_gateway_node"
            )
        ]

    def __str__(self):
        return f"{self.gateway.gateway_id}/node-{self.node_id}"


class SensorReading(models.Model):
    gateway = models.ForeignKey(
        Gateway,
        on_delete=models.CASCADE,
        related_name="readings"
    )

    node = models.ForeignKey(
        Node,
        on_delete=models.CASCADE,
        related_name="readings"
    )

    event_id = models.BigIntegerField()

    seq = models.BigIntegerField(
        null=True,
        blank=True
    )

    recv_ts_utc = models.DateTimeField()

    host_time = models.BigIntegerField(
        null=True,
        blank=True
    )

    hdc_temp_x10 = models.IntegerField(
        null=True,
        blank=True
    )

    hdc_hum_x10 = models.IntegerField(
        null=True,
        blank=True
    )

    light_raw = models.IntegerField(
        null=True,
        blank=True
    )

    bmp_temp_x10 = models.IntegerField(
        null=True,
        blank=True
    )

    pressure_pa = models.IntegerField(
        null=True,
        blank=True
    )

    # LWB metadata carried by SENSOR_DATA (firmware env_perf_v1).
    run = models.BigIntegerField(null=True, blank=True)
    delay_ms = models.IntegerField(null=True, blank=True)
    hop_est = models.IntegerField(null=True, blank=True)

    raw_payload = models.JSONField(
        default=dict
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        ordering = ["-recv_ts_utc"]

        constraints = [
            # event_id restarts if the gateway SQLite file is recreated,
            # so recv_ts_utc is part of the key.
            models.UniqueConstraint(
                fields=["gateway", "event_id", "recv_ts_utc"],
                name="uniq_gateway_event_ts"
            )
        ]

    @property
    def hdc_temp_c(self):
        if self.hdc_temp_x10 is None:
            return None
        return self.hdc_temp_x10 / 10.0

    @property
    def humidity_percent(self):
        if self.hdc_hum_x10 is None:
            return None
        return self.hdc_hum_x10 / 10.0

    @property
    def bmp_temp_c(self):
        if self.bmp_temp_x10 is None or self.bmp_temp_x10 == -32768:
            return None
        return self.bmp_temp_x10 / 10.0


class PerfEvent(models.Model):
    """LWB performance records (PERF_CONFIG, PERF_SUMMARY, PERF_REPORT ...).

    Kept independently of SensorReading retention so test results survive the
    15-minute cleanup of sensor readings.
    """
    gateway = models.ForeignKey(Gateway, on_delete=models.CASCADE, related_name="perf_events")
    node = models.ForeignKey(Node, on_delete=models.CASCADE, related_name="perf_events")
    event_id = models.BigIntegerField()
    record_type = models.CharField(max_length=40)
    run = models.BigIntegerField(null=True, blank=True)
    recv_ts_utc = models.DateTimeField()
    data = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-recv_ts_utc"]
        indexes = [models.Index(fields=["record_type", "run", "node"])]
        constraints = [
            models.UniqueConstraint(
                fields=["gateway", "event_id", "recv_ts_utc"],
                name="uniq_perf_event_ts"
            )
        ]

    def __str__(self):
        return f"{self.record_type} run={self.run} {self.node}"
