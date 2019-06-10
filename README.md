# arrpc
Simple, speedy and light Python RPC using [MessagePack](https://msgpack.org/) for object serialization and [gevent](http://www.gevent.org/) for networking.

Great choice if you a need a quick, easy and secure RPC setup or you think an HTTP framework or GRPC is too complex/overkill for sending messages between a few services.

As [MessagePack](https://msgpack.org/) is cross-platform, you can open TCP connections and send MessagePack-encoded messages from any supported language to the Python `arrpc.Server()`. Same goes for the `arrpc.Client()` as long as you have a TCP server listening and understanding MessagePack.

Features:
- Efficient serialization of messages with [MessagePack](https://msgpack.org/)
- Fast and parallel handling of messages with [gevent](http://www.gevent.org/)
- TCP over TLS
- Message authentication and authorization
- Retries and timeouts
- Telemetry (coming soon)
- Tracing (coming soon)
- Automatic mTLS on Kubernetes (coming soon)

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
server = arrpc.Server("127.0.0.1", 8080, handler,
                      auth_secret="<high entropy string>")
```

#### Client
```python
client = arrpc.Client("127.0.0.1", 8080,
                      auth_secret="<same high entropy string>")
```

### Retries and timeout
Currently `arrpc.Client().send()` will retry TCP connections 5 times (`con_max_retries=5` default) with increasing back offs every time, and once connected the timeout for send/receive is the default of gevent (`timeout=None` default).
#### Client
```python
# e.g. 3 retries with 5s timeout on send/receive
client = arrpc.Client("127.0.0.1", 8080, timeout=5,
                      con_max_retries=3)
```

### Debug
#### Server
```python
server = arrpc.Server("127.0.0.1", 8080, handler, debug=True)
```

#### Client
```python
client = arrpc.Client("127.0.0.1", 8080, debug=True)
```

### Telemetry (coming soon)

[Prometheus](https://github.com/prometheus/client_python)

### Tracing (coming soon)

[OpenTracing](https://github.com/opentracing/opentracing-python)

### Automatic mTLS on Kubernetes (coming soon)
