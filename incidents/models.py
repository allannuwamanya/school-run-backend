from django.db import models
from django.utils.translation import gettext_lazy as _
from accounts.models import BaseModel, CustomUser
from children.models import Child
from trips.models import Trip


class Incident(BaseModel):
    """
    A safety or operational incident logged by a parent, driver, or the system.
    """
    PANIC_ALERT = 'panic_alert'
    LATE_PICKUP = 'late_pickup'
    SICK_CHILD = 'sick_child'
    ROUTE_DEVIATION = 'route_deviation'
    NO_SHOW = 'no_show'
    OTHER = 'other'
    INCIDENT_TYPE_CHOICES = [
        (PANIC_ALERT, _('Panic Alert')),
        (LATE_PICKUP, _('Late Pickup')),
        (SICK_CHILD, _('Sick Child')),
        (ROUTE_DEVIATION, _('Route Deviation')),
        (NO_SHOW, _('No Show')),
        (OTHER, _('Other')),
    ]

    CRITICAL = 'critical'
    MEDIUM = 'medium'
    LOW = 'low'
    SEVERITY_CHOICES = [
        (CRITICAL, _('Critical')),
        (MEDIUM, _('Medium')),
        (LOW, _('Low')),
    ]

    OPEN = 'open'
    IN_PROGRESS = 'in_progress'
    RESOLVED = 'resolved'
    STATUS_CHOICES = [
        (OPEN, _('Open')),
        (IN_PROGRESS, _('In Progress')),
        (RESOLVED, _('Resolved')),
    ]

    incident_id = models.CharField(max_length=20, unique=True, help_text='e.g. INC-001')
    incident_type = models.CharField(max_length=30, choices=INCIDENT_TYPE_CHOICES)
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=OPEN)

    triggered_by = models.ForeignKey(
        CustomUser, on_delete=models.SET_NULL, null=True,
        related_name='triggered_incidents'
    )
    trip = models.ForeignKey(
        Trip, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='incidents'
    )
    child = models.ForeignKey(
        Child, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='incidents'
    )

    # Location at time of incident
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    police_involved = models.BooleanField(default=False)
    response_time = models.DurationField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_notes = models.TextField(null=True, blank=True)

    def __str__(self):
        return f"{self.incident_id} — {self.get_incident_type_display()} ({self.severity})"

    @classmethod
    def next_incident_id(cls):
        """INC-001, INC-002, ... — shared so every creation path (admin
        emergency dispatch, no-show auto-escalation, self-reports) numbers
        incidents the same way instead of duplicating the parsing logic."""
        last = cls.objects.order_by('-incident_id').values_list('incident_id', flat=True).first()
        next_num = int(last.split('-')[-1]) + 1 if last and last.split('-')[-1].isdigit() else 1
        return f"INC-{next_num:03d}"

    class Meta:
        verbose_name = 'Incident'
        verbose_name_plural = 'Incidents'
        ordering = ['-created_at']


class IncidentTimeline(models.Model):
    """
    A chronological event entry in an incident's history.
    """
    incident = models.ForeignKey(
        Incident, on_delete=models.CASCADE, related_name='timeline'
    )
    actor = models.ForeignKey(
        CustomUser, on_delete=models.SET_NULL, null=True, blank=True
    )
    event_text = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.incident.incident_id} @ {self.timestamp}: {self.event_text[:50]}"

    class Meta:
        ordering = ['timestamp']
        verbose_name = 'Incident Timeline Event'
        verbose_name_plural = 'Incident Timeline Events'


class MessageThread(BaseModel):
    """
    A conversation thread between parents, drivers, and/or support.
    Can optionally be linked to a trip or incident.
    """
    participants = models.ManyToManyField(
        CustomUser, related_name='message_threads', blank=True
    )
    trip = models.ForeignKey(
        Trip, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='message_threads'
    )
    incident = models.ForeignKey(
        Incident, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='message_threads'
    )

    def __str__(self):
        return f"Thread #{self.id}"

    @property
    def unread_count(self):
        return self.messages.filter(is_read=False).count()

    class Meta:
        verbose_name = 'Message Thread'
        verbose_name_plural = 'Message Threads'


class Message(models.Model):
    """
    An individual message within a thread.
    """
    thread = models.ForeignKey(
        MessageThread, on_delete=models.CASCADE, related_name='messages'
    )
    sender = models.ForeignKey(
        CustomUser, on_delete=models.SET_NULL, null=True, related_name='sent_messages'
    )
    body = models.TextField()
    is_read = models.BooleanField(default=False)
    sent_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Msg from {self.sender} in Thread #{self.thread_id}"

    class Meta:
        ordering = ['sent_at']
        verbose_name = 'Message'
        verbose_name_plural = 'Messages'
