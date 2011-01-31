import django.contrib.admin
import djangomail.models

class MailTaskAdmin(django.contrib.admin.ModelAdmin):
    list_display = ('name', 'group', 'subject', 'often')
django.contrib.admin.site.register(djangomail.models.MailTask, MailTaskAdmin)
django.contrib.admin.site.register(djangomail.models.MailTaskGroup)
django.contrib.admin.site.register(djangomail.models.EmailTemplate)
