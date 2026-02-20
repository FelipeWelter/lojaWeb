import smtplib
from email.message import EmailMessage


class Message:
    def __init__(self, subject='', recipients=None, body=''):
        self.subject = subject
        self.recipients = recipients or []
        self.body = body


class Mail:
    def __init__(self, app=None):
        self.app = app

    def send(self, message: Message):
        if not self.app:
            raise RuntimeError('Mail não configurado.')

        username = self.app.config.get('MAIL_USERNAME')
        password = self.app.config.get('MAIL_PASSWORD')
        sender = self.app.config.get('MAIL_DEFAULT_SENDER') or username
        server = self.app.config.get('MAIL_SERVER', 'smtp.gmail.com')
        port = int(self.app.config.get('MAIL_PORT', 587))
        use_tls = bool(self.app.config.get('MAIL_USE_TLS', True))

        if not username or not password or not sender:
            raise RuntimeError('Credenciais SMTP não configuradas.')

        email = EmailMessage()
        email['Subject'] = message.subject
        email['From'] = sender
        email['To'] = ', '.join(message.recipients)
        email.set_content(message.body)

        with smtplib.SMTP(server, port, timeout=30) as smtp:
            if use_tls:
                smtp.starttls()
            smtp.login(username, password)
            smtp.send_message(email)
