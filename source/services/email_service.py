import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from handlers.datetime_handler import current_formatted_time
from handlers.logging_handler import setup_logger, logging


class EmailService:
    logger: logging.Logger = None


    def __init__(self):
        # Setup logger
        cur_time: str = current_formatted_time()
        log_filename: str = f"EmailService_Log_{cur_time}.log"
        self.logger = setup_logger("Email", "Logs", log_filename)


    def send_email(self, smtp_config: dict, subject: str, body: str):
        # Send an email
        self.logger.debug("Preparing to send email...")
        try:
            msg = MIMEMultipart()
            msg["From"] = smtp_config["user"]
            msg["To"] = smtp_config["recipient"]
            msg["Subject"] = subject

            msg.attach(MIMEText(body, "plain", "utf-8"))

            self.logger.debug(f"Connecting to SMTP server: {smtp_config['smtp_server']}:{smtp_config['smtp_port']}")
            with smtplib.SMTP(smtp_config["smtp_server"], smtp_config["smtp_port"]) as server:
                server.starttls()
                server.login(smtp_config["user"], smtp_config["password"])
                server.send_message(msg, from_addr=smtp_config["user"], to_addrs=smtp_config["recipient"])

            self.logger.info("Email sent successfully")
        except Exception as e:
            self.logger.error(f"Error sending email: {e}")
            raise