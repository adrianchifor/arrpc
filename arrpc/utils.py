import hmac
import hashlib

from msgpack import packb, unpackb

from arrpc.error import AuthException, RpcException


def recvall(socket, buffer_size: int = 4096):
    data = b""
    while True:
        part = socket.recv(buffer_size)
        data += part
        if len(part) < buffer_size:
            break
    return data


def sign_and_wrap_msg(msg_packed, auth_secret: str):
    signature = hmac.new(auth_secret.encode("utf-8"), msg_packed, hashlib.sha256).hexdigest()
    signed_msg = {"arrpc.sign": signature, "data": msg_packed}
    return packb(signed_msg, use_bin_type=True)


def verify_msg(msg_unpacked, auth_secret: str):
    if not (isinstance(msg_unpacked, dict) and "arrpc.sign" in msg_unpacked and "data" in msg_unpacked):
        raise AuthException("Failed to authenticate message, signature not found")

    data = msg_unpacked["data"]
    signature_in_msg = msg_unpacked["arrpc.sign"]
    signature = hmac.new(auth_secret.encode("utf-8"), data, hashlib.sha256).hexdigest()
    if signature_in_msg == signature:
        return unpackb(data, raw=False)
    else:
        raise AuthException("Failed to authenticate message, signature is incorrect")


def parse_response(response):
    if response and isinstance(response, str):
        if "arrpc.error.AuthException" in response:
            raise AuthException(response.replace("arrpc.error.AuthException: ", ""))

        if "arrpc.error.RpcException" in response:
            raise RpcException(response.replace("arrpc.error.RpcException: ", ""))

    return response
