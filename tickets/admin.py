from django.contrib import admin
from .models import Company, Profile, Ticket, TicketMessage, TicketHistory, Notification

admin.site.register(Company)
admin.site.register(Profile)
admin.site.register(Ticket)
admin.site.register(TicketMessage)
admin.site.register(TicketHistory)
admin.site.register(Notification)

