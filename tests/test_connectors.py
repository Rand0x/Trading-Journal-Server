"""Tests for connector behavior that can run without broker credentials."""

import asyncio
import unittest

from server.connectors.ctrader_api import CTraderConnector


class _FakeSocket:
    def __init__(self, messages):
        self.messages = list(messages)
        self.sent = []

    async def send(self, message):
        self.sent.append(message)

    async def recv(self):
        return self.messages.pop(0)


class TestCTraderConnector(unittest.TestCase):
    def test_request_round_trip(self):
        socket = _FakeSocket([
            '{"payloadType": 2101, "payload": {"ok": true}}'
        ])
        connector = CTraderConnector("client", "secret", "token", "123")

        result = asyncio.run(connector._request(socket, 2100, {"clientId": "client"}, 2101))

        self.assertEqual(result, {"ok": True})
        self.assertEqual(len(socket.sent), 1)
        self.assertIn('"payloadType": 2100', socket.sent[0])

    def test_request_surfaces_api_error(self):
        socket = _FakeSocket([
            '{"payloadType": 2142, "payload": {"errorCode": "AUTH_FAILED", "description": "invalid token"}}'
        ])
        connector = CTraderConnector("client", "secret", "token", "123")

        with self.assertRaisesRegex(ValueError, "AUTH_FAILED"):
            asyncio.run(connector._request(socket, 2100, {}, 2101))


if __name__ == "__main__":
    unittest.main()
