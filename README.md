# arrpc
Simple, speedy and light Python3 RPC using [MessagePack](https://msgpack.org/) for object serialization and [gevent](http://www.gevent.org/) for networking.

Great choice if you a need a quick, easy and secure RPC setup or you think an HTTP framework or GRPC is too complex for sending messages between two services.

As [MessagePack](https://msgpack.org/) is cross-platform, you can open TCP connections and send MessagePack-encoded messages from any supported language to the Python `arrpc.Server()`. Same goes for the `arrpc.Client()` as long as you have a TCP server listening and understanding MessagePack.

Features:
- Efficient serialization of messages with [MessagePack](https://msgpack.org/)
- Fast and parallel handling of messages with [gevent](http://www.gevent.org/)
- TCP over TLS
- Message authentication and authorization
- Retries and timeouts
- Prometheus metrics

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

### Message authentication and authorization
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
Currently `arrpc.Client().send()` will retry TCP connections 5 times (`con_max_retries=5` default) with increasing back offs every time, and once connected the timeout for send/receive is the default of gevent (`timeout=None` default).
#### Client
```python
# e.g. 3 retries with 5s timeout on send/receive
client = arrpc.Client(..., timeout=5, con_max_retries=3)
```

### Prometheus metrics
Both the server and client can expose the following metrics:
```
arrpc_[server/client]_req_seconds_count  - Total number of requests
arrpc_[server/client]_req_seconds_sum    - Total seconds spent on requests
arrpc_[server/client]_req_bytes_sum      - Total bytes in requests
```

Prometheus's `rate` function allows calculation of requests, bytes and latency over time from these 3 metrics.

The metrics support the following labels:
```
hostname               - Value of /etc/hostname, pod name on Kubernetes
k8s_namespace          - The Kubernetes namespace where the pod runs (empty otherwise)
remote_address         - The address receiving requests from or sending requests to
(server) handler_func  - Name of the server request handler function
signed_payload         - True if the payload for the request was signed and verified
tls                    - True if the request was made over TLS
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
