import logging, re


class RedactCapabilities(logging.Filter):
    def filter(self, record):
        message = record.getMessage()
        record.msg = re.sub(
            r"(/(?:api/)?join/|/api/receipts/)[A-Za-z0-9_-]+", r"\1[redacted]", message
        )
        record.args = ()
        return True
