import logging
import signal
import sys

def handle_sigterm(signum, frame):
    logging.info("Received SIGTERM. Exiting gracefully...")
    sys.exit(0)

# Register the signal handler for SIGTERM
signal.signal(signal.SIGTERM, handle_sigterm)