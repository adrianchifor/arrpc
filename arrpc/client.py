import logging
import time
import ssl
import socket

from msgpack import packb, unpackb
from prometheus_client import Summary, Counter

import arrpc.metrics as m
from arrpc.error import ConnectException, RpcTimeoutException
from arrpc.utils import recvall, sign_and_wrap_msg, parse_response
from arrpc import logger


class Client(object):
    def __init__(self, host: str, port: int, timeout: float = None, con_max_retries: int = 5,
                 debug: bool = False, tls_cafile: str = None, tls_self_signed: bool = False,
                 auth_secret: str = None, metrics: bool = False, metrics_port: int = 9095):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.con_max_retries = con_max_retries
        self.auth_secret = auth_secret
        self.ssl_context = None
        if tls_cafile:
            self.ssl_context = ssl.create_default_context(cafile=tls_cafile)
            if tls_self_signed:
                self.ssl_context.check_hostname = False
                self.ssl_context.verify_mode = ssl.CERT_NONE
        if debug:
            logger.setLevel(logging.DEBUG)
        self.socket = None

        self.metrics = metrics
        if metrics:
            with m.metrics_mutex:
                if not m.shared_hostname_label:
                    m.shared_hostname_label = m.hostname()
                if not m.shared_namespace_label:
                    m.shared_namespace_label = m.k8s_namespace()

                if not m.shared_metrics["arrpc_client_metric_seconds"]:
                    m.shared_metrics["arrpc_client_metric_seconds"] = Summary(
                        "arrpc_client_req_seconds",
                        "Time spent making client requests",
                        ("hostname", "k8s_namespace", "remote_address", "signed_payload", "tls")
                    )
                if not m.shared_metrics["arrpc_client_metric_bytes"]:
                    m.shared_metrics["arrpc_client_metric_bytes"] = Summary(
                        "arrpc_client_req_bytes",
                        "Size of client requests in bytes",
                        ("hostname", "k8s_namespace", "remote_address", "signed_payload", "tls")
                    )
                if not m.shared_metrics["arrpc_client_metric_errors"]:
                    m.shared_metrics["arrpc_client_metric_errors"] = Counter(
                        "arrpc_client_errors",
                        "RPC client errors",
                        ("hostname", "k8s_namespace", "remote_address", "signed_payload", "tls", "reason")
                    )

            m.start_metrics_server(metrics_port)

    def send(self, msg):
        try:
            if self.ssl_context:
                with self.ssl_context.wrap_socket(self.socket, server_hostname=self.host) as ssock:
                    logger.debug(f"Connected to {self.host}:{self.port} over {ssock.version()}")
                    return self._handle_send(ssock, msg)
            else:
                return self._handle_send(self.socket, msg)
        except (BrokenPipeError, ConnectionResetError, AttributeError):
            logger.debug(f"Socket disconnected or not initialized yet, connecting to {self.host}:{self.port}")
            self.socket = self._socket_connect()
            return self.send(msg)

    def _handle_send(self, sock, msg):
        if self.metrics:
            start_time = time.time()

        msg_packed = packb(msg, use_bin_type=True)
        if self.auth_secret:
            msg_packed = sign_and_wrap_msg(msg_packed, self.auth_secret)

        try:
            sock.sendall(msg_packed)
            logger.debug(f"Sent message to {self.host}:{self.port}")
            response = recvall(sock)
        except socket.timeout:
            error_msg = "Timed out"
            if self.metrics:
                m.shared_metrics["arrpc_client_metric_errors"].labels(
                    m.shared_hostname_label,       # hostname
                    m.shared_namespace_label,      # k8s_namespace
                    f"{self.host}:{self.port}",    # remote_address
                    self.auth_secret is not None,  # signed_payload
                    self.ssl_context is not None,  # tls
                    error_msg                      # reason
                ).inc()
            raise RpcTimeoutException(error_msg)

        try:
            response_unpacked = unpackb(response, raw=False)
        except Exception as e:
            logger.debug(f"Failed to unpack response, most likely not MessagePack: {e}")
            response_unpacked = None

        if response_unpacked:
            logger.debug(f"Got response from {self.host}:{self.port}")

            if self.metrics:
                m.shared_metrics["arrpc_client_metric_seconds"].labels(
                    m.shared_hostname_label,       # hostname
                    m.shared_namespace_label,      # k8s_namespace
                    f"{self.host}:{self.port}",    # remote_address
                    self.auth_secret is not None,  # signed_payload
                    self.ssl_context is not None   # tls
                ).observe(time.time() - start_time)

                m.shared_metrics["arrpc_client_metric_bytes"].labels(
                    m.shared_hostname_label,       # hostname
                    m.shared_namespace_label,      # k8s_namespace
                    f"{self.host}:{self.port}",    # remote_address
                    self.auth_secret is not None,  # signed_payload
                    self.ssl_context is not None   # tls
                ).observe(len(msg_packed))

            try:
                response_unpacked = parse_response(response_unpacked)
            except Exception as e:
                if self.metrics:
                    m.shared_metrics["arrpc_client_metric_errors"].labels(
                        m.shared_hostname_label,       # hostname
                        m.shared_namespace_label,      # k8s_namespace
                        f"{self.host}:{self.port}",    # remote_address
                        self.auth_secret is not None,  # signed_payload
                        self.ssl_context is not None,  # tls
                        str(e)                         # reason
                    ).inc()
                raise

            return response_unpacked

    def _socket_connect(self):
        attempt = 1
        retry_back_off_time = 1

        while attempt <= self.con_max_retries:
            try:
                if self.timeout:
                    return socket.create_connection((self.host, self.port), self.timeout)
                else:
                    return socket.create_connection((self.host, self.port))
            except Exception as e:
                logger.debug(f"Failed to connect to {self.host}:{self.port} on attempt {attempt}: {e}")
                if attempt == self.con_max_retries:
                    # Do not wait after last retry was made
                    break
                time.sleep(retry_back_off_time)
                retry_back_off_time += 1
                attempt += 1

        error_msg = f"Failed to connect to {self.host}:{self.port} with {self.con_max_retries} attempts"
        if self.metrics:
            m.shared_metrics["arrpc_client_metric_errors"].labels(
                m.shared_hostname_label,       # hostname
                m.shared_namespace_label,      # k8s_namespace
                f"{self.host}:{self.port}",    # remote_address
                self.auth_secret is not None,  # signed_payload
                self.ssl_context is not None,  # tls
                error_msg                      # reason
            ).inc()
        raise ConnectException(error_msg)
