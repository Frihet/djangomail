import django.contrib.admin
import appomatic_djangomail.models

class MailTaskAdmin(django.contrib.admin.ModelAdmin):
    list_display = ('name', 'group', 'subject', 'often')
django.contrib.admin.site.register(appomatic_djangomail.models.MailTask, MailTaskAdmin)
django.contrib.admin.site.register(appomatic_djangomail.models.MailTaskGroup)
django.contrib.admin.site.register(appomatic_djangomail.models.EmailTemplate)
