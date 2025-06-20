import datetime
import json
import ssl
import time
from email.header import Header
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr

import dkim

from src import smtpext
from src.configuration import Configuration
from src.structures import MailMessage
from src.utils import get_mx_server_address


def dkim_sign(dkim_key_path: str, dkim_selector: str, mail_domain: str, msg: MIMEBase) -> str | None:
    dkim_sig = dkim.sign(
        msg.as_bytes(),
        dkim_selector.encode(),
        mail_domain.encode(),
        open(dkim_key_path).read().encode(),
    ).decode()

    return dkim_sig[len("DKIM-Signature: "):]

def build_mime_message(conf: Configuration, mail_message: MailMessage) -> MIMEBase:
    if len(mail_message.data) == 1 and mail_message.data[0].type == 'text':
        msg = mail_message.data[0].mime_object
    else:
        msg = MIMEMultipart()
        [msg.attach(x.mime_object) for x in mail_message.data]

    date = datetime.datetime.fromtimestamp(
        conf.runtime[mail_message.guid].ts_added
    ).strftime('%a, %d %b %Y %H:%M:%S %z')

    msg['Received'] = '; '.join([
        f'by iaasstore/restmailer via API',
        f'id {mail_message.guid} for <{mail_message.address_to}>',
        date
    ])
    msg['Message-Id'] = f'<{mail_message.guid}@{conf.mail.server_name}>'
    msg['Date'] = date

    msg['Subject'] = Header(mail_message.subject, 'utf-8')
    msg['From'] = formataddr((str(Header(mail_message.from_name, 'utf-8')), f'{mail_message.from_user}@{conf.mail.domain}'))
    msg['To'] = mail_message.address_to

    if kp := conf.mail.dkim_key_path:
        try:
            dkim_sig = dkim_sign(kp, conf.mail.dkim_selector, conf.mail.domain, msg)
            msg['DKIM-Signature'] = dkim_sig

            conf.runtime[mail_message.guid].log(
                'mailer-dkim', f'sign generated, length={len(dkim_sig)}'
            )
        except Exception as e:
            conf.runtime[mail_message.guid].log(
                'mailer-dkim', f'sign generation error: {str(e)}'
            )

    return msg


def try_connect_server_and_send(
        conf: Configuration, mail_message: MailMessage, mx_host: str, message: MIMEBase
) -> tuple[bool, bool]:
    """

    :param conf:
    :param mail_message:
    :param mx_host:
    :param message:
    :return:
        (bool) - status
        (boot) - try with another mx server
    """
    server = smtpext.SMTP(conf.mail.server_name, conf.mail.def_smtp_connect_timeout)

    if conf.mail.proxy:
        conf.runtime[mail_message.guid].log(
            'smtp', f'[{mx_host}] using proxy from configuration for smtp connection'
        )
        server.enable_proxy(str(conf.mail.proxy))

    try:
        server.connect(mx_host)
    except Exception as e:
        conf.runtime[mail_message.guid].log(
            'smtp', f'[{mx_host}] cannot connect to mx server {e} {e.args}'
        )
        return False, True

    ehlo_code, ehlo_status = server.ehlo(name=conf.mail.server_name)

    if 'STARTTLS' in ehlo_status.decode():
        conf.runtime[mail_message.guid].log(
            'smtp-tls', f'[{mx_host}] STARTTLS is available, trying upgrade'
        )

        sslcontext = ssl.create_default_context()
        if mail_message.ignore_starttls_cert:
            sslcontext.check_hostname = False
            sslcontext.verify_mode = ssl.CERT_NONE

        try:
            tls_code, tls_status = server.starttls(context=sslcontext)
        except Exception as e:
            conf.runtime[mail_message.guid].log(
                'smtp-tls', f'[{mx_host}] exception on tls upgrade: {e} {e.args}'
            )
            return False, True

        conf.runtime[mail_message.guid].log(
            'smtp-tls', f'[{mx_host}] {tls_code}, {tls_status.decode()}'
        )

    try:
        # send_result = {}
        send_result: dict = server.send_message(from_addr=f'{mail_message.from_user}@{conf.mail.domain}', msg=message)
    except Exception as e:
        conf.runtime[mail_message.guid].log(
            'smtp', f'[{mx_host}] send mail error {e} {e.args}'
        )
        return False, True

    server.quit()

    if len(send_result) == 0:
        conf.runtime[mail_message.guid].log(
            'smtp',
            f'[{mx_host}] mail sended successfully in '
            f'{int(time.time()) - conf.runtime[mail_message.guid].ts_added}s'
        )
        return True, False

    if len(send_result) > 0:
        conf.runtime[mail_message.guid].log(
            'smtp', f'[{mx_host}] mail have some errors on send: {json.dumps(send_result)}'
        )
        return False, False

    return False, False


def api_send_message(conf: Configuration, mail_message: MailMessage):
    address_to_domain = str(mail_message.address_to).split('@')[1]
    mx_servers = get_mx_server_address(address_to_domain)

    if not mx_servers:
        conf.runtime[mail_message.guid].log(
            'mailer', f'cannot get mx servers for: {address_to_domain}'
        )
        return False

    conf.runtime[mail_message.guid].log(
        'mailer', f'mx servers for target_address: {', '.join(mx_servers)}'
    )

    message = build_mime_message(conf, mail_message)
    message_sended = False

    while len(mx_servers) > 0:
        current_mx_server = mx_servers[0]

        conf.runtime[mail_message.guid].log(
            'mailer', f'try mx server for send {current_mx_server}'
        )

        message_sended, try_again = try_connect_server_and_send(conf, mail_message, current_mx_server, message)
        mx_servers.remove(current_mx_server)

        if message_sended:
            break

        if int(time.time()) - conf.runtime[mail_message.guid].ts_added > mail_message.send_timeout:
            conf.runtime[mail_message.guid].log(
                'mailer', f'message send timeout reached'
            )
            break

        if not message_sended and not try_again:
            break

    if not message_sended:
        conf.runtime[mail_message.guid].log(
            'mailer', f'cannot send message: all mx servers is down or timeout reached'
        )
        conf.runtime[mail_message.guid].state = 'error'
        return False

    conf.runtime[mail_message.guid].state = 'sended'
    return True
