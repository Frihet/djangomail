# -*- coding: utf-8 -*-
from django.db import models
from djangomail.html2text import html2text
from django.utils.translation import ugettext_lazy as _
import django.template
from django.conf import settings


class EmailTemplate(models.Model):
    """
    Email template. Used for sending emails after e.g. issue updates.
    """
    subject = models.CharField(_('subject'),max_length=1024)
    body = models.TextField(_('body'),max_length=8192)

    def __unicode__(self):
        return self.subject

    def send(self, recipients, **kw):
        """
        Format message and send it.
        """
        if hasattr(recipients, 'all'):
            recipients=recipients.all()

        if not hasattr(recipients, '__iter__'):
            recipients = [recipients]

    #   logging.getLogger('ticket').warning('Send email to %s' % repr(recipients))

        from djangomail import Mailer
        for recipient in recipients:
            Mailer.send_template_mail(self.subject, recipient, self.body, **kw)

    class Meta:
        verbose_name_plural = _('email templates')
        verbose_name = _('email template')

class MailTaskGroup(models.Model):
    name = models.CharField(max_length=100, verbose_name=_("Name"))
    enforced = models.BooleanField(verbose_name=_("Enforce sending (non user ignorable mails)"), default=False)

    def __unicode__(self):
        return self.name

class MailTask(EmailTemplate):
    name = models.CharField(max_length=100, verbose_name=_("Name"))
    often = models.IntegerField()
    group = models.ForeignKey(MailTaskGroup)

    class Meta:
        ordering = ['name']

    def __unicode__(self):
        return "%s: %s" % (self.group, self.name)
