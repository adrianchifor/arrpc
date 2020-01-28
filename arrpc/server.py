import logging
import time
import ssl
import threading

from msgpack import packb, unpackb
from gevent.server import StreamServer
from prometheus_client import Summary, Counter

import arrpc.metrics as m
from arrpc.error import AuthException, RpcException
from arrpc.utils import recvall, verify_msg
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
        if metrics:
            with m.metrics_mutex:
                if not m.shared_hostname_label:
                    m.shared_hostname_label = m.hostname()
                if not m.shared_namespace_label:
                    m.shared_namespace_label = m.k8s_namespace()

                if not m.shared_metrics["arrpc_server_metric_seconds"]:
                    m.shared_metrics["arrpc_server_metric_seconds"] = Summary(
                        "arrpc_server_req_seconds",
                        "Time spent handling server requests",
                        ("hostname", "k8s_namespace", "remote_address", "handler_func", "signed_payload", "tls")
                    )
                if not m.shared_metrics["arrpc_server_metric_bytes"]:
                    m.shared_metrics["arrpc_server_metric_bytes"] = Summary(
                        "arrpc_server_req_bytes",
                        "Size of server requests in bytes",
                        ("hostname", "k8s_namespace", "remote_address", "handler_func", "signed_payload", "tls")
                    )
                if not m.shared_metrics["arrpc_server_metric_errors"]:
                    m.shared_metrics["arrpc_server_metric_errors"] = Counter(
                        "arrpc_server_errors",
                        "RPC server errors",
                        ("hostname", "k8s_namespace", "remote_address", "handler_func", "signed_payload", "tls", "reason")
                    )

    def start(self, background: bool = False):
        def _gevent_handler(socket, address):
            logger.debug(f"Connection from {address}")
            while True:
                msg = None
                try:
                    msg = recvall(socket)
                except ConnectionResetError:
                    pass
                if not msg:
                    logger.debug(f"Connection from {address} closed")
                    break

                if self.metrics:
                    start_time = time.time()

                try:
                    msg_unpacked = unpackb(msg, raw=False)
                except Exception as e:
                    logger.debug(f"Failed to unpack message, most likely not MessagePack: {e}")
                    msg_unpacked = None

                if msg_unpacked:
                    logger.debug(f"Received message from {address}")
                    response = None
                    if self.auth_secret:
                        try:
                            msg_unpacked = verify_msg(msg_unpacked, self.auth_secret)
                            logger.debug(f"Verified message signature")
                        except AuthException as e:
                            logger.debug(e)
                            error_msg = "Invalid or missing message signature, make sure 'auth_secret' is set/correct"
                            if self.metrics:
                                m.shared_metrics["arrpc_server_metric_errors"].labels(
                                    m.shared_hostname_label,       # hostname
                                    m.shared_namespace_label,      # k8s_namespace
                                    address[0],                    # remote_address
                                    self.handler.__name__,         # handler_func
                                    self.auth_secret is not None,  # signed_payload
                                    self.ssl_context is not None,  # tls
                                    error_msg                      # reason
                                ).inc()
                            response = f"arrpc.error.AuthException: {error_msg}"

                    if not response:
                        logger.debug(f"Passing message to handler function")
                        try:
                            response = self.handler(msg_unpacked)
                        except RpcException as e:
                            if self.metrics:
                                m.shared_metrics["arrpc_server_metric_errors"].labels(
                                    m.shared_hostname_label,       # hostname
                                    m.shared_namespace_label,      # k8s_namespace
                                    address[0],                    # remote_address
                                    self.handler.__name__,         # handler_func
                                    self.auth_secret is not None,  # signed_payload
                                    self.ssl_context is not None,  # tls
                                    str(e)                         # reason
                                ).inc()
                            response = f"arrpc.error.RpcException: {e}"

                    response_packed = packb(response, use_bin_type=True)
                    try:
                        socket.sendall(response_packed)
                        logger.debug(f"Sent response back to {address}")
                    except Exception as e:
                        logger.debug(f"Failed to send response back to {address}: {e}")
                        break

                if self.metrics:
                    m.shared_metrics["arrpc_server_metric_seconds"].labels(
                        m.shared_hostname_label,       # hostname
                        m.shared_namespace_label,      # k8s_namespace
                        address[0],                    # remote_address
                        self.handler.__name__,         # handler_func
                        self.auth_secret is not None,  # signed_payload
                        self.ssl_context is not None   # tls
                    ).observe(time.time() - start_time)

                    m.shared_metrics["arrpc_server_metric_bytes"].labels(
                        m.shared_hostname_label,       # hostname
                        m.shared_namespace_label,      # k8s_namespace
                        address[0],                    # remote_address
                        self.handler.__name__,         # handler_func
                        self.auth_secret is not None,  # signed_payload
                        self.ssl_context is not None   # tls
                    ).observe(len(msg))

        if self.metrics:
            m.start_metrics_server(self.metrics_port)

        if self.ssl_context:
            server = StreamServer((self.host, self.port), _gevent_handler,
                                  ssl_context=self.ssl_context)
            logger.info(f"Listening on TCP/TLS {self.host}:{self.port}\n")
        else:
            server = StreamServer((self.host, self.port), _gevent_handler)
            logger.info(f"Listening on TCP {self.host}:{self.port}\n")

        if background:
            t = threading.Thread(target=server.serve_forever)
            t.setDaemon(True)
            t.start()
        else:
            server.serve_forever()
