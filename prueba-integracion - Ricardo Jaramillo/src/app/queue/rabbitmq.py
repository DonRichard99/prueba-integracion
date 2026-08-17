import json
import os

import aio_pika


QUEUE_NAME = "facturacion"


async def get_connection():

    rabbitmq_url = os.getenv(
        "RABBITMQ_URL",
        "amqp://guest:guest@rabbitmq:5672/"
    )

    return await aio_pika.connect_robust(rabbitmq_url)


async def publish_message(message: dict):

    connection = await get_connection()

    async with connection:

        channel = await connection.channel()

        queue = await channel.declare_queue(
            QUEUE_NAME,
            durable=True
        )

        await channel.default_exchange.publish(
            aio_pika.Message(
                body=json.dumps(message).encode(),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT
            ),
            routing_key=queue.name
        )