import logging

from msgpack import packb, unpackb
from gevent.server import StreamServer
from gevent import ssl

from arrpc.error import AuthException
from arrpc.utils import recvall, sign_and_wrap_msg, verify_msg
from arrpc import logger


class Server(object):
    def __init__(self, host: str, port: int, handler, debug: bool = False,
                 tls_certfile: str = None, tls_keyfile: str = None,
                 auth_secret: str = None):
        self.host = host
        self.port = port
        self.handler = handler
        self.auth_secret = auth_secret
        self.ssl_context = None
        if tls_certfile and tls_keyfile:
            self.ssl_context = ssl.create_default_context(purpose=ssl.Purpose.CLIENT_AUTH)
            self.ssl_context.load_cert_chain(tls_certfile, tls_keyfile)
        if debug:
            logger.setLevel(logging.DEBUG)

    def start(self):
        def _gevent_handler(socket, address):
            logger.debug(f"Connection from {address}")
            msg = recvall(socket)
            try:
                msg_unpacked = unpackb(msg, raw=False)
            except Exception as e:
                logger.debug(f"Failed to unpack message, most likely not MessagePack: {e}")
                msg_unpacked = None

            if msg_unpacked:
                logger.debug(f"Received message from {address}")
                logger.debug(msg_unpacked)  # REMOVE
                if self.auth_secret:
                    try:
                        msg_unpacked = verify_msg(msg_unpacked, self.auth_secret)
                        logger.debug(f"Verified message signature")
                    except AuthException as e:
                        logger.error(e)
                        return

                logger.debug(f"Passing message to handler function")
                response = self.handler(msg_unpacked)
                response_packed = packb(response, use_bin_type=True)
                if self.auth_secret:
                    response_packed = sign_and_wrap_msg(response_packed, self.auth_secret)
                try:
                    socket.sendall(response_packed)
                    logger.debug(f"Sent response back to {address}")
                except Exception as e:
                    logger.error(f"Failed to send response back to {address}: {e}")

        if self.ssl_context:
            server = StreamServer((self.host, self.port), _gevent_handler,
                                  ssl_context=self.ssl_context)
            logger.info(f"Listening on TCP/TLS {self.host}:{self.port}\n")
        else:
            server = StreamServer((self.host, self.port), _gevent_handler)
            logger.info(f"Listening on TCP {self.host}:{self.port}\n")
        server.serve_forever()
