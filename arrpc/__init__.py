import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s -- %(message)s')
logger = logging.getLogger(__name__)

from arrpc.server import Server
from arrpc.client import Client
from arrpc.error import ConnectException, AuthException
