# -*- coding: utf-8 -*-
#
# Copyright (c) 2010 Freecode AS.
#
# Some parts are Copyright (c) 2001 Bizar Software Pty Ltd
# (http://www.bizarsoftware.com.au/) This module is free software, and
# you may redistribute it and/or modify under the same terms as
# Python, so long as this copyright message and disclaimer are
# retained in their original form.
#
# IN NO EVENT SHALL BIZAR SOFTWARE PTY LTD BE LIABLE TO ANY PARTY FOR
# DIRECT, INDIRECT, SPECIAL, INCIDENTAL, OR CONSEQUENTIAL DAMAGES ARISING
# OUT OF THE USE OF THIS CODE, EVEN IF THE AUTHOR HAS BEEN ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
#
# BIZAR SOFTWARE PTY LTD SPECIFICALLY DISCLAIMS ANY WARRANTIES, INCLUDING,
# BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
# FOR A PARTICULAR PURPOSE.  THE CODE PROVIDED HEREUNDER IS ON AN "AS IS"
# BASIS, AND THERE IS NO OBLIGATION WHATSOEVER TO PROVIDE MAINTENANCE,
# SUPPORT, UPDATES, ENHANCEMENTS, OR MODIFICATIONS.
#

"""
Email sending. 
"""
__docformat__ = 'restructuredtext'

import string, re, os, mimetools, cStringIO, smtplib, socket, binascii, quopri
import time, random, sys, logging
import traceback, rfc822
import cgi
import os 

from email.Header import decode_header
import djangomail.models
import scrubber

import email.mime.image
import email.mime.audio
import email.mime.text
import email.mime.message
import email.mime.base
from email import Encoders
import BeautifulSoup
import settings

from django.utils.translation import ugettext_lazy as _
import djangomail.html2text
import django.template


def unalias_charset(charset):
    if charset:
        return charset.lower().replace("windows-", 'cp')
        #return charset_table.get(charset.lower(), charset)
    return None

def email_valid(emailkey):
    """
    Email validation, checks for syntactically invalid email
    courtesy of Mark Nenadov.
    See
    http://aspn.activestate.com/ASPN/Cookbook/Python/Recipe/65215"""
    import re
    emailregex = "^.+\\@(\\[?)[a-zA-Z0-9\\-\\.]+\\.([a-zA-Z]{2,3}|[0-9]{1,3})(\\]?)$"
    if len(emailkey) > 7:
        if re.match(emailregex, emailkey) != None:
            return True
        return False
    else:
        return False

try:
    import pyme, pyme.core, pyme.gpgme
except ImportError:
    pyme = None

SENDMAILDEBUG = os.environ.get('SENDMAILDEBUG', '')


class MailUsageError(ValueError):
    pass

class MailUsageHelp(Exception):
    """ We need to send the help message to the user. """
    pass

class Unauthorized(Exception):
    """ Access denied """
    pass

class IgnoreMessage(Exception):
    """ A general class of message that we should ignore. """
    pass
class IgnoreBulk(IgnoreMessage):
        """ This is email from a mailing list or from a vacation program. """
        pass
class IgnoreLoop(IgnoreMessage):
        """ We've seen this message before... """
        pass

def scrub_html_email(text, cid_mapping={}):

    from BeautifulSoup import BeautifulSoup

    soup = BeautifulSoup(text)

    for tag in soup.findAll(True):
        attrs = dict(tag.attrs)
        if 'src' in attrs:
            src = attrs['src']
            if src[:4]=='cid:':
                tag['src'] = cid_mapping[src[4:]]

    mapped = soup.renderContents()

    scrubber = tuit.scrubber.Scrubber(autolink=False)

    # The scrubber removes complete html documents out of the box? Weird...
    scrubber.disallowed_tags_save_content.add('html')
    scrubber.disallowed_tags_save_content.add('body')
    scrubber.disallowed_tags_save_content.add('xml')
    scrubber.disallowed_tags_save_content.add('doctype')
    scrubber.allowed_attributes.add('color')
    scrubbed = scrubber.scrub(mapped)
    
    return scrubbed

def get_source_list(text):

    from BeautifulSoup import BeautifulSoup

    soup = BeautifulSoup(text)
    sources=[]

    for tag in soup.findAll(True):
        attrs = dict(tag.attrs)
        if 'src' in attrs:
            sources.append(attrs['src'])

    return sources

def remap_sources(text, remap):
#    print 'REMAP'
#    print text
#    print remap

    from BeautifulSoup import BeautifulSoup

    soup = BeautifulSoup(text)

    for tag in soup.findAll(True):
        attrs = dict(tag.attrs)
        if 'src' in attrs:
            src = attrs['src']
            if src in remap:
                tag['src'] = remap[src]

        if 'alt' in attrs:
            del(tag['alt'])

    res = soup.renderContents()
#    print res
    return res.replace('/>','>')

class Mailer:

    @classmethod
    def send_email(cls, subject, recipient, body_text, body_html, attachments=[]):
        try:
            # Create the message
            msg = email.mime.multipart.MIMEMultipart('related')
            msg['Subject'] = subject
            msg['From'] = "%s <%s>" % (settings.DJANGOMAIL_NAME, settings.DJANGOMAIL_EMAIL)
            msg['To'] = recipient


            remap = {}

            # Obtain a list of all links present in the document
            sources = set(get_source_list(body_html))

            # Try to make sure that inline images in the message are
            # preserved. To do this, we replace URLs that lead to an
            # attachment with cid:s for that attachment.
            #
            # For some reason, this code doesn't work with Evolution, but
            # after banging my head against whe wall for half a day, I
            # gave up. It is confirmed to work in Thunderbird, Gmail and
            # Outlook web mail.
            for att in attachments:
                # Do we have any links to this attachment? If so, make it
                # an inline attachment, give it a content id, etc.
                if getattr(att, 'url_internal', None) in sources:
                    import time
                    #Cids should be globally unique. concatenate
                    #attachment id, host name and current time. Should be
                    #unique.
                    cid = "%d:%f:%s" % (att.id, time.time(), settings.SITE_URL)
                    if 'Content-Disposition' not in att:
                        att.add_header('Content-Disposition', 'inline', filename=getattr(att, 'name', 'unnamed'))
                    att.add_header('Content-ID', '<%s>' % cid)
                    remap[att.url_internal] = 'cid:%s' % cid
                else:
                    if 'Content-Disposition' not in att:
                        att.add_header('Content-Disposition', 'attachment', filename=getattr(att, 'name', 'unnamed'))

            # Do the actual url to cid rewriting
            body_html = remap_sources(body_html, remap)

            submsg = email.mime.multipart.MIMEMultipart("alternative")
            if not type(body_html) is str:
                body_html=body_html.encode('utf-8')
            if not type(body_text) is str:
                body_text=body_text.encode('utf-8')
            part1 = email.mime.text.MIMEText(body_text, 'plain', _charset='UTF-8')
            part2 = email.mime.text.MIMEText(body_html, 'html', _charset='UTF-8')
            submsg.attach(part1)
            submsg.attach(part2)
            msg.attach(submsg)

            # We attach these _after_ attaching the actual text, seems
            # for some reason to display nicer in some crappy email
            # clients that way...
            for i in attachments:
                msg.attach(i)

            # Send it
            if settings.DJANGOMAIL_USE_SSL:
                s = smtplib.SMTP_SSL(settings.DJANGOMAIL_HOST, settings.DJANGOMAIL_PORT)
            else:
                s = smtplib.SMTP(settings.DJANGOMAIL_HOST, settings.DJANGOMAIL_PORT)

            s.helo()

            if settings.DJANGOMAIL_USE_TLS:
                s.starttls()

            if settings.DJANGOMAIL_USERNAME:
                s.login(settings.DJANGOMAIL_USERNAME, settings.DJANGOMAIL_PASSWORD)

            s.sendmail("", recipient, # Empty sender as per http://marc.merlins.org/netrants/autoresponders.txt
                       msg.as_string())
            s.quit()
            logging.getLogger('mail').info('Sent email with subject %s to %s' % (subject, recipient))
        except:
            traceback.print_exc()
            raise

    @classmethod
    def send_template_mail(cls, subject, recipient, body, attachments=[], **kw):
        """
        Format message and send it.
        """
        from djangomail import Mailer

        done = {}

        if hasattr(recipient,'email'):
            recipient_mail = recipient.email
        else:
            recipient_mail = recipient

        if recipient_mail is None:
            return

        if recipient_mail in done:
            return

        done[recipient_mail] = recipient

        kw['recipient']=recipient

        #d = ModelDict(kw)
        context = django.template.Context(kw)

        subject_template = django.template.Template(subject)
        subject = subject_template.render(context)

        body_template = django.template.Template(body)
        html = body

        html = body_template.render(context)

        # Make sure we have a str and not a unicode, or html2text will mess up
        if type(html) is str:
            pass
        else:
            html=html.encode('utf-8')

        plain = djangomail.html2text.html2text(html)

        # Make sure we have a unicode and not a str
        plain = plain.decode('utf-8')

        try:                    
            cls.send_email(subject, recipient_mail, plain, html, attachments)
        except:
            import traceback as tb
            msg = tb.format_exc()
            logging.getLogger('mail').error('Failed to send email to %s. Error: %s' % 
                                            (recipient.email, msg))

