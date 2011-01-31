# -*- coding: utf-8 -*-
from django.db import models
from djangomail.html2text import html2text
from django.utils.translation import ugettext_lazy as _
import django.template
import settings

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
        from djangomail import Mailer

        if hasattr(recipients, 'all'):
            recipients=recipients.all()

        if not hasattr(recipients, '__iter__'):
            recipients = [recipients]

        attachments = []
        if 'attachments' in kw:
            attachments = kw['attachments']

#        logging.getLogger('ticket').warning('Send email to %s' % repr(recipients))

        done = {}
        for recipient in recipients:  
            if hasattr(recipient,'email'):
                recipient_mail = recipient.email
            else:
                recipient_mail = recipient

            if recipient_mail is None:
                continue

            if recipient_mail in done:
                continue

            done[recipient_mail] = recipient

            kw['recipient']=recipient

            #d = ModelDict(kw)
            context = django.template.Context(kw)

            subject_template = django.template.Template(self.subject)
            subject = subject_template.render(context)

            body_template = django.template.Template(self.body)
            html = self.body

            html = body_template.render(context)

            # Make sure we have a str and not a unicode, or html2text will mess up
            if type(html) is str:
                pass
            else:
                html=html.encode('utf-8')

            plain = html2text(html)

            # Make sure we have a unicode and not a str
            plain = plain.decode('utf-8')

            try:                    
                Mailer.send_email(subject, recipient_mail, plain, html, attachments)
            except:
                import traceback as tb
                msg = tb.format_exc()
#                    logging.getLogger('ticket').error('Failed to send email to %s. Error: %s' % 
#                                                      (recipient.email, msg))


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
