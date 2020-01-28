# arrpc
Simple, speedy and light Python3 RPC using [MessagePack](https://msgpack.org/) for object serialization and [gevent](http://www.gevent.org/) for networking.

Great choice if you a need a quick, easy and secure RPC setup or you think an HTTP framework or GRPC is too complex for sending messages between two services.

As [MessagePack](https://msgpack.org/) is cross-platform, you can open TCP connections and send MessagePack-encoded messages from any supported language to the `arrpc.Server()`. Same goes for the `arrpc.Client()` as long as you have a TCP server listening and understanding MessagePack.

Features:
- Efficient serialization of messages with [MessagePack](https://msgpack.org/)
- Fast and parallel handling of messages with [gevent](http://www.gevent.org/)
- TCP over TLS
- Message authentication
- Retries and timeouts
- Prometheus metrics
- Exception propagation

Benchmarks (using n1-standard-1 VM on GCP):
- Raw client and server ~ 9000 qps
  - with TCP/TLS ~ 8700 qps
  - with TCP/TLS + msg authentication ~ 7400 qps
  - with TCP/TLS + msg authentication + Prometheus metrics ~ 7100 qps

## Install
```
pip3 install arrpc
```

## Usage
#### Server
```python
import arrpc

def handler(message):
    print(message)
    # {
    #   'foo': 'bar'
    # }
    return "got it"

server = arrpc.Server("127.0.0.1", 8080, handler)
server.start()
```

You can also run the server in the background (non-blocking):
```python
server.start(background=True)
```

#### Client
```python
import arrpc

client = arrpc.Client("127.0.0.1", 8080)
response = client.send({"foo": "bar"})
print(response)
# "got it"
```

### TCP over TLS
#### Server
```python
server = arrpc.Server("127.0.0.1", 8443, handler,
                      tls_certfile="server.crt",
                      tls_keyfile="server.key")
```

#### Client (known CA)
```python
client = arrpc.Client("127.0.0.1", 8443,
                      tls_cafile="ca.crt")
```

#### Client (self-signed)
```python
client = arrpc.Client("127.0.0.1", 8443,
                      tls_cafile="server.crt",
                      tls_self_signed=True)
```

### Message authentication
Signs messages between server and clients with HMAC-SHA256 using a shared secret in order to prevent message tampering and to ensure only correctly signed messages reach the handler.

**Before**: Object on client -> MessagePack encode -> binary over TCP (/TLS?) -> MessagePack decode -> Object on server

**After**: Object on client -> MessagePack encode -> _Sign payload, attach and re-encode_ -> binary over TCP (/TLS?) -> MessagePack decode -> _Verify signature of payload_ -> Object on server

This feature can be used together with TCP over TLS to achieve a highly secure setup, however note that this comes at a performance cost.

#### Server
```python
server = arrpc.Server(..., auth_secret="<high entropy string>")
```

#### Client
```python
client = arrpc.Client(..., auth_secret="<same high entropy string>")
```

### Retries and timeout
Currently `arrpc.Client().send()` will retry TCP connections 5 times (`con_max_retries=5` default) with increasing back offs every time, and once connected the timeout for send() is unlimited (`timeout=None` default).
#### Client
```python
# e.g. 3 max retries to establish TCP connection and 5s timeout for send()
client = arrpc.Client(..., timeout=5, con_max_retries=3)
```

### Prometheus metrics
Both the server and client can expose the following metrics:
```
arrpc_[server/client]_req_seconds_count  - Total number of requests
arrpc_[server/client]_req_seconds_sum    - Total seconds spent on requests
arrpc_[server/client]_req_bytes_sum      - Total bytes in requests
arrpc_[server/client]_errors_total       - Total number of errors
```

Prometheus's `rate` function allows calculation of requests, bytes and latency over time from the top 3 metrics.

The metrics support the following labels:
```
hostname                    - Value of /etc/hostname, pod name on Kubernetes
k8s_namespace               - The Kubernetes namespace where the pod runs (empty otherwise)
remote_address              - The address receiving requests from or sending requests to
(server-only) handler_func  - Name of the server request handler function
signed_payload              - True if the payload for the request was signed and verified
tls                         - True if the request was made over TLS
(errors-only) reason        - The error message
```
#### Server
```python
server = arrpc.Server(..., metrics=True)
```

#### Client
```python
client = arrpc.Client(..., metrics=True)
```

Default metrics port is `9095` so you can see the exposed Prometheus metrics by going to `http://HOST:9095/metrics`. You can change the port by defining `metrics_port` in the server/client args.


### Debug logs
#### Server
```python
server = arrpc.Server(..., debug=True)
```

#### Client
```python
client = arrpc.Client(..., debug=True)
```

### Exceptions
#### ConnectException
Failure to connect to the server on client `send()`.
```python
import arrpc

client = arrpc.Client("127.0.0.1", 8080)
try:
    response = client.send({"foo": "bar"})
    # Handle response
except arrpc.error.ConnectException as e:
    # Handle server not available even after 5 retries (default)
```

#### AuthException
Message authentication failed, most likely because `auth_secret` is set on server but not on client or the secret doesn't match.
```python
import arrpc

client = arrpc.Client("127.0.0.1", 8080, auth_secret="<high entropy string>")
try:
    response = client.send({"foo": "bar"})
    # Handle response
except arrpc.error.AuthException as e:
    # Handle 'auth_secret' mismatch
```

#### RpcTimeoutException
RPC timeout error, raised on `send()`.
```python
import arrpc

client = arrpc.Client("127.0.0.1", 8080, timeout=0.1)
try:
    response = client.send({"foo": "bar"})
    # Handle response
except arrpc.error.RpcTimeoutException as e:
    # Handle send() timeout
```

#### RpcException
Custom RPC error, can be raised manually in the server handler and it will be propagated to the client.

##### Server
```python
import arrpc
from arrpc.error import RpcException

def handler(message):
    # Do stuff
    raise RpcException("Something went wrong")

server = arrpc.Server("127.0.0.1", 8080, handler)
server.start()
```

##### Client
```python
import arrpc

client = arrpc.Client("127.0.0.1", 8080)
try:
    response = client.send({"foo": "bar"})
    # Handle response
except arrpc.error.RpcException as e:
    print(e)  # Will print "Something went wrong"
```
