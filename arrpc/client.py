import logging
import time

from msgpack import packb, unpackb
from gevent import ssl, socket as gsocket

from arrpc.error import ConnectException, AuthException
from arrpc.utils import recvall, sign_and_wrap_msg, verify_msg
from arrpc import logger


class Client(object):
    def __init__(self, host: str, port: int, timeout: int = None, con_max_retries: int = 5,
                 debug: bool = False, tls_cafile: str = None, tls_self_signed: bool = False,
                 auth_secret: str = None):
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

    def send(self, msg):
        with self._socket_connect() as socket:
            if self.ssl_context:
                with self.ssl_context.wrap_socket(socket, server_hostname=self.host) as ssocket:
                    logger.debug(f"Connected to {self.host}:{self.port} over {ssocket.version()}")
                    return self._handle_send(ssocket, msg)
            else:
                return self._handle_send(socket, msg)

    def _handle_send(self, socket, msg):
        msg_packed = packb(msg, use_bin_type=True)
        if self.auth_secret:
            msg_packed = sign_and_wrap_msg(msg_packed, self.auth_secret)

        socket.sendall(msg_packed)
        logger.debug(f"Sent message to {self.host}:{self.port}")
        # Wait for response
        response = recvall(socket)
        try:
            response_unpacked = unpackb(response, raw=False)
        except Exception as e:
            logger.debug(f"Failed to unpack response, most likely not MessagePack: {e}")
            response_unpacked = None

        if response_unpacked:
            logger.debug(f"Got response from {self.host}:{self.port}")
            if self.auth_secret:
                try:
                    response_unpacked = verify_msg(response_unpacked, self.auth_secret)
                    logger.debug(f"Verified message signature")
                except AuthException as e:
                    logger.error(e)
                    return None

            return response_unpacked

    def _socket_connect(self):
        attempt = 1
        retry_back_off_time = 1

        while attempt <= self.con_max_retries:
            try:
                if self.timeout:
                    return gsocket.create_connection((self.host, self.port), self.timeout)
                else:
                    return gsocket.create_connection((self.host, self.port))
            except Exception as e:
                logger.debug(f"Failed to connect to {self.host}:{self.port} on attempt {attempt}: {e}")
                if attempt == self.con_max_retries:
                    # Do not wait after last retry was made
                    break
                time.sleep(retry_back_off_time)
                retry_back_off_time += 1
                attempt += 1

        raise ConnectException(f"Failed to connect to {self.host}:{self.port} with {self.con_max_retries} attempts")
