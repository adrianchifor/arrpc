import logging

from gevent import monkey

logging.basicConfig(level=logging.INFO, format='arrpc -- %(asctime)s -- %(message)s')
logger = logging.getLogger(__name__)

# http://www.gevent.org/api/gevent.monkey.html
monkey.patch_all()

from arrpc.server import Server
from arrpc.client import Client
