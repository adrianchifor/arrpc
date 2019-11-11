from multiprocessing import Lock

from prometheus_client import start_http_server, Summary

from arrpc import logger

metrics_mutex = Lock()
metrics_server_started = False
# We need this here because we share metrics across multiple clients
client_metrics = {
    "arrpc_client_metric_seconds": None,
    "arrpc_client_metric_bytes": None,
    "hostname_label": "",
    "namespace_label": ""
}


def server_metrics_summary():
    return Summary(
        "arrpc_server_req_seconds",
        "Time spent handling server requests",
        ("hostname", "k8s_namespace", "remote_address", "handler_func", "signed_payload", "tls")
    ), Summary(
        "arrpc_server_req_bytes",
        "Size of server requests in bytes",
        ("hostname", "k8s_namespace", "remote_address", "handler_func", "signed_payload", "tls")
    )


def client_metrics_summary():
    return Summary(
        "arrpc_client_req_seconds",
        "Time spent making client requests",
        ("hostname", "k8s_namespace", "remote_address", "signed_payload", "tls")
    ), Summary(
        "arrpc_client_req_bytes",
        "Size of client requests in bytes",
        ("hostname", "k8s_namespace", "remote_address", "signed_payload", "tls")
    )


def hostname():
    try:
        with open("/etc/hostname", "r") as hn:
            return hn.read().strip()
    except FileNotFoundError:
        logger.debug("/etc/hostname not found")

    return ""


def k8s_namespace():
    try:
        with open("/var/run/secrets/kubernetes.io/serviceaccount/namespace", "r") as ns:
            return ns.read().strip()
    except FileNotFoundError:
        logger.debug("Namespace file not found, not on Kubernetes")

    return ""


def start_metrics_server(port: int):
    global metrics_server_started, metrics_mutex
    with metrics_mutex:
        if not metrics_server_started:
            start_http_server(port)
            metrics_server_started = True
            logger.info(f"Serving prometheus metrics on port {port}")
