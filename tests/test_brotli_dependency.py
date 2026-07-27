import json
import unittest

import aiohttp
import brotli
from aiohttp import web


class BrotliDependencyTests(unittest.IsolatedAsyncioTestCase):
    async def test_aiohttp_decodes_brotli_json_response(self):
        expected = {"room_status": "public"}

        async def handler(_request):
            return web.Response(
                body=brotli.compress(json.dumps(expected).encode()),
                headers={
                    "Content-Encoding": "br",
                    "Content-Type": "application/json",
                },
            )

        app = web.Application()
        app.router.add_get("/", handler)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"http://127.0.0.1:{port}/") as response:
                    self.assertEqual(expected, await response.json())
        finally:
            await runner.cleanup()
