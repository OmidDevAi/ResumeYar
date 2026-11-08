import mimetypes
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from pathlib import Path


class EmailError(Exception):
    pass


def smtp_ready(settings):
    return bool(settings.get("smtp_host") and settings.get("smtp_from_email"))


def _ssl_context():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _connect(settings):
    host = settings.get("smtp_host", "").strip()
    try:
        port = int(settings.get("smtp_port", "587") or 587)
    except ValueError as exc:
        raise EmailError("پورت SMTP معتبر نیست.") from exc
    security = settings.get("smtp_security", "starttls")
    context = _ssl_context()
    try:
        if security == "ssl":
            server = smtplib.SMTP_SSL(host, port, timeout=30, context=context)
        else:
            server = smtplib.SMTP(host, port, timeout=30)
            server.ehlo()
            if security == "starttls":
                server.starttls(context=context)
                server.ehlo()
        user = settings.get("smtp_user", "").strip()
        password = settings.get("smtp_password", "")
        if user:
            server.login(user, password)
        return server
    except (smtplib.SMTPException, OSError, ssl.SSLError) as exc:
        raise EmailError(f"اتصال به سرور ایمیل ناموفق بود: {exc}") from exc


def test_connection(settings):
    if not smtp_ready(settings):
        return False, "میزبان SMTP و ایمیل فرستنده را پر کنید."
    try:
        server = _connect(settings)
        try:
            server.noop()
        finally:
            server.quit()
        return True, "اتصال و ورود به سرور ایمیل با موفقیت انجام شد."
    except EmailError as exc:
        return False, str(exc)


def send(settings, to, subject, body, attachment_paths, reply_to=""):
    if not smtp_ready(settings):
        raise EmailError("تنظیمات ایمیل کامل نیست. در صفحه تنظیمات، SMTP را پیکربندی کنید.")
    to = (to or "").strip()
    if "@" not in to:
        raise EmailError("ایمیل گیرنده معتبر نیست.")
    from_email = settings.get("smtp_from_email", "").strip()
    from_name = settings.get("smtp_from_name", "").strip()
    message = EmailMessage()
    message["From"] = formataddr((from_name, from_email)) if from_name else from_email
    message["To"] = to
    message["Subject"] = (subject or "").strip() or "Job application"
    message["Date"] = formatdate(localtime=True)
    domain = from_email.rsplit("@", 1)[-1] if "@" in from_email else None
    message["Message-ID"] = make_msgid(domain=domain)
    if reply_to:
        message["Reply-To"] = reply_to
    message.set_content(body or "")
    for item in attachment_paths:
        if isinstance(item, (tuple, list)):
            raw_path, display_name = item
        else:
            raw_path, display_name = item, None
        path = Path(raw_path)
        if not path.is_file():
            continue
        content_type, _ = mimetypes.guess_type(path.name)
        if content_type:
            maintype, subtype = content_type.split("/", 1)
        else:
            maintype, subtype = "application", "octet-stream"
        message.add_attachment(
            path.read_bytes(), maintype=maintype, subtype=subtype,
            filename=display_name or path.name,
        )
    try:
        server = _connect(settings)
        try:
            server.send_message(message)
        finally:
            server.quit()
    except (smtplib.SMTPException, OSError) as exc:
        raise EmailError(f"ارسال ایمیل ناموفق بود: {exc}") from exc
    return message.get("Message-ID", "")
