# Copyright 2018 Palantir Technologies, Inc.
import asyncio
import logging
from typing import Coroutine, Dict, Union, Any

try:
    import ujson as json
except Exception:  # pylint: disable=broad-except
    import json

log = logging.getLogger(__name__)


class JsonRpcStreamReader(object):

    def __init__(self, rfile: asyncio.StreamReader):
        self._rfile = rfile
        self.close = False

    def close(self) -> None:
        # self.close = True
        self._rfile.feed_eof()
        # self._rfile.close()

    async def listen(self, message_consumer: Coroutine) -> Any:
        """Blocking call to listen for messages on the rfile.

        Args:
            message_consumer (fn): function that is passed each message as it
            is read off the socket.
        """
        while not self._rfile.at_eof():
            try:
                request_str = await self._read_message()
            except ValueError:
                if self._rfile.at_eof():
                    return
                else:
                    log.exception("Failed to read from rfile")

            if request_str is None:
                break

            try:
                asyncio.ensure_future(
                    message_consumer(json.loads(request_str.decode('utf-8'))))
            except ValueError:
                log.exception("Failed to parse JSON message %s", request_str)
                continue

    async def _read_message(self) -> Union[str, None]:
        """Reads the contents of a message.

        Returns:
            body of message if parsable else None
        """
        line = await self._rfile.readline()

        if not line:
            return None

        content_length = self._content_length(line)

        # Blindly consume all header lines
        while line and line.strip():
            line = await self._rfile.readline()

        if not line:
            return None

        content = await self._rfile.read(content_length)
        # Grab the body
        return content

    @staticmethod
    def _content_length(line: str) -> Union[int, None]:
        """Extract the content length from an input line."""
        if line.startswith(b'Content-Length: '):
            _, value = line.split(b'Content-Length: ')
            value = value.strip()
            try:
                return int(value)
            except ValueError:
                raise ValueError(
                    "Invalid Content-Length header: {}".format(value))

        return None


class JsonRpcStreamWriter(object):

    def __init__(self, wfile: asyncio.StreamWriter, **json_dumps_args):
        self._wfile = wfile
        self._wfile_lock = asyncio.Lock()
        # self._wfile_lock = threading.Lock()
        self._json_dumps_args = json_dumps_args

    async def close(self) -> None:
        async with self._wfile_lock:
            self._wfile.close()
            await self._wfile.wait_closed()

    async def write(self, message: Dict) -> None:
        loop = asyncio.get_event_loop()
        async with self._wfile_lock:
            if self._wfile.is_closing():
                return
            try:
                body = await loop.run_in_executor(
                    None, json.dumps(message, **self._json_dumps_args))

                # Ensure we get the byte length, not the character length
                content_length = (len(body) if isinstance(body, bytes) else
                                  len(body.encode('utf-8')))

                response = (
                    "Content-Length: {}\r\n"
                    "Content-Type: application/vscode-jsonrpc; "
                    "charset=utf8\r\n\r\n"
                    "{}".format(content_length, body)
                )

                self._wfile.write(response.encode('utf-8'))
                self._wfile.drain()
            except Exception:  # pylint: disable=broad-except
                log.exception(
                    "Failed to write message to output file %s", message)
