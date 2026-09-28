import logging

logger = logging.getLogger("aip-grpc")


class GrpcClientManager:
    """Manages binary gRPC connection pools to decoupled AI runtime serving nodes."""
    def __init__(self):
        self._channels = {}

    def get_channel(self, target_url: str):
        if target_url not in self._channels:
            logger.info(f"Initializing gRPC channel to {target_url}")
            # Stub for grpc.aio.insecure_channel(target_url)
            self._channels[target_url] = target_url
        return self._channels[target_url]


grpc_manager = GrpcClientManager()
