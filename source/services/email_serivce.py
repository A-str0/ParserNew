from handlers.datetime_handler import current_formatted_time
from handlers.logging_handler import setup_logger, logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
# from handlers.format_handler import format_email_subject
import smtplib, os


class EmailService:
    logger: logging.Logger = None

    def __init__(self):
        # Setup logger
        cur_time: str = current_formatted_time()
        log_filename: str = f"EmailService_Log_{cur_time}.log"
        self.logger = setup_logger("Email", "Logs", log_filename)


    def send_email(self, smtp_config: dict, subject: str, body: str):
        # Send an email with optional attachment
        self.logger.debug("Sending email...")

        try:
            msg = MIMEMultipart()
            msg["From"] = smtp_config["user"]
            msg["To"] = smtp_config["recipient"]
            msg["Subject"] = subject

            # Attach body text
            msg.attach(MIMEText(body, "plain", "utf-8"))

            # Connect to SMTP server
            self.logger.debug(f"Connecting to SMTP server: {smtp_config['smtp_server']}:{smtp_config['smtp_port']}")
            with smtplib.SMTP(smtp_config["smtp_server"], smtp_config["smtp_port"]) as server:
                server.starttls()
                server.login(smtp_config["user"], smtp_config["password"])
                server.send_message(msg, from_addr=smtp_config["user"], to_addrs=smtp_config["recipient"])

            self.logger.info("Email sent successfully")
        except Exception as e:
            self.logger.error(f"Error sending email: {e}")
            raise

