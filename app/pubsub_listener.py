import json
import logging
from google.cloud import pubsub_v1
from .config import PUBSUB_SUBSCRIPTION_NAME

log = logging.getLogger(__name__)


class PubSubListener:
    def __init__(self, on_event):
        self.on_event = on_event
        self.client = None
        self.future = None

    def start(self):
        if not PUBSUB_SUBSCRIPTION_NAME:
            raise RuntimeError('PUBSUB_SUBSCRIPTION_NAME não configurado')
        self.client = pubsub_v1.SubscriberClient()

        def callback(message):
            try:
                payload = json.loads(message.data.decode('utf-8')) if message.data else {}
                event_type = message.attributes.get('ce-type', '')
                self.on_event(event_type, payload, dict(message.attributes))
                message.ack()
            except Exception:
                log.exception('Falha processando evento Pub/Sub')
                message.nack()

        self.future = self.client.subscribe(PUBSUB_SUBSCRIPTION_NAME, callback=callback)

    def stop(self):
        if self.future:
            self.future.cancel()
        if self.client:
            self.client.close()
