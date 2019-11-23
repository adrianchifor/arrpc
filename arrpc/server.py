import logging
import time
import ssl

from msgpack import packb, unpackb
from gevent.server import StreamServer

from arrpc.error import AuthException
from arrpc.utils import recvall, sign_and_wrap_msg, verify_msg
from arrpc.metrics import server_metrics_summary, hostname, k8s_namespace, start_metrics_server
from arrpc import logger


class Server(object):
    def __init__(self, host: str, port: int, handler, debug: bool = False,
                 tls_certfile: str = None, tls_keyfile: str = None, auth_secret: str = None,
                 metrics: bool = False, metrics_port: int = 9095):
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

        self.metrics = metrics
        self.metrics_port = metrics_port
        self.arrpc_server_metric_seconds = None
        self.arrpc_server_metric_bytes = None
        self.hostname_label = None
        self.namespace_label = None
        if metrics:
            self.arrpc_server_metric_seconds, self.arrpc_server_metric_bytes = server_metrics_summary()
            self.hostname_label = hostname()
            self.namespace_label = k8s_namespace()

    def start(self):
        def _gevent_handler(socket, address):
            if self.metrics:
                start_time = time.time()

            logger.debug(f"Connection from {address}")
            msg = recvall(socket)
            try:
                msg_unpacked = unpackb(msg, raw=False)
            except Exception as e:
                logger.debug(f"Failed to unpack message, most likely not MessagePack: {e}")
                msg_unpacked = None

            if msg_unpacked:
                logger.debug(f"Received message from {address}")
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

            if self.metrics:
                self.arrpc_server_metric_seconds.labels(
                    self.hostname_label,           # hostname
                    self.namespace_label,          # k8s_namespace
                    address[0],                    # remote_address
                    self.handler.__name__,         # handler_func
                    self.auth_secret is not None,  # signed_payload
                    self.ssl_context is not None   # tls
                ).observe(time.time() - start_time)

                self.arrpc_server_metric_bytes.labels(
                    self.hostname_label,           # hostname
                    self.namespace_label,          # k8s_namespace
                    address[0],                    # remote_address
                    self.handler.__name__,         # handler_func
                    self.auth_secret is not None,  # signed_payload
                    self.ssl_context is not None   # tls
                ).observe(len(msg))

        if self.metrics:
            start_metrics_server(self.metrics_port)

        if self.ssl_context:
            server = StreamServer((self.host, self.port), _gevent_handler,
                                  ssl_context=self.ssl_context)
            logger.info(f"Listening on TCP/TLS {self.host}:{self.port}\n")
        else:
            server = StreamServer((self.host, self.port), _gevent_handler)
            logger.info(f"Listening on TCP {self.host}:{self.port}\n")
        server.serve_forever()
