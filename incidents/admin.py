from django.contrib import admin
from .models import Incident, IncidentTimeline, MessageThread, Message


class IncidentTimelineInline(admin.TabularInline):
    model = IncidentTimeline
    extra = 0
    readonly_fields = ('timestamp',)
    fields = ('actor', 'event_text', 'timestamp')


class MessageInline(admin.TabularInline):
    model = Message
    extra = 0
    readonly_fields = ('sent_at',)
    fields = ('sender', 'body', 'is_read', 'sent_at')


@admin.register(Incident)
class IncidentAdmin(admin.ModelAdmin):
    list_display = (
        'incident_id', 'incident_type', 'severity', 'status',
        'triggered_by', 'police_involved', 'created_at', 'resolved_at'
    )
    list_filter = ('incident_type', 'severity', 'status', 'police_involved')
    search_fields = ('incident_id', 'triggered_by__full_name')
    readonly_fields = ('created_at', 'resolved_at')
    inlines = [IncidentTimelineInline]


@admin.register(MessageThread)
class MessageThreadAdmin(admin.ModelAdmin):
    list_display = ('id', 'trip', 'incident', 'unread_count', 'created_at')
    inlines = [MessageInline]
