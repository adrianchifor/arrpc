from multiprocessing import Lock

from prometheus_client import start_http_server

from arrpc import logger

metrics_mutex = Lock()
metrics_server_started = False

shared_hostname_label = ""
shared_namespace_label = ""
shared_metrics = {
    "arrpc_client_metric_seconds": None,
    "arrpc_client_metric_bytes": None,
    "arrpc_client_metric_errors": None,
    "arrpc_server_metric_seconds": None,
    "arrpc_server_metric_bytes": None,
    "arrpc_server_metric_errors": None,
}


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
