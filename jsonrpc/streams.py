# Copyright 2018 Palantir Technologies, Inc.
import json
import logging
import threading

log = logging.getLogger(__name__)


class _StreamError(Exception):
    """Raised on stream errors."""


class JsonRpcStreamReader(object):

    def __init__(self, rfile):
        self._rfile = rfile

    def close(self):
        self._rfile.close()

    def listen(self, message_consumer):
        """Blocking call to listen for messages on the rfile.

        Args:
            message_consumer (fn): function that is passed each message as it is read off the socket.
        """
        while not self._rfile.closed:
            try:
                request_str = self._read_message()
            except _StreamError:
                log.exception("Failed to read message.")
                break

            try:
                message_consumer(json.loads(request_str.decode('utf-8')))
            except ValueError:
                log.exception("Failed to parse JSON message %s", request_str)
                continue

    def _read_message(self):
        """Reads the contents of a message.

        Returns:
            body of message

        Raises:
            _StreamError: If message was not parsable.
        """
        # Read the headers
        headers = self._read_headers()

        try:
            content_length = int(headers[b"Content-Length"])
        except (ValueError, KeyError):
            raise _StreamError("Invalid or missing Content-Length headers: {}".format(headers))

        # Grab the body
        body = self._rfile.read(content_length)
        if not body:
            raise _StreamError("Got EOF when reading from stream")

        return body

    def _read_headers(self):
        """Read the headers from a LSP base message.

        Returns:
            dict: A dict containing the headers and their values.

        Raises:
            _StreamError: If headers are not parsable.
        """
        headers = {}
        while True:
            line = self._rfile.readline()
            if not line:
                raise _StreamError("Got EOF when reading from stream")
            if not line.strip():
                # Finished reading headers break while loop
                break

            try:
                key, value = line.split(b":")
            except ValueError:
                raise _StreamError("Invalid header {}: ".format(line))

            headers[key.strip()] = value.strip()

        return headers


class JsonRpcStreamWriter(object):

    def __init__(self, wfile, **json_dumps_args):
        self._wfile = wfile
        self._wfile_lock = threading.Lock()
        self._json_dumps_args = json_dumps_args

    def close(self):
        with self._wfile_lock:
            self._wfile.close()

    def write(self, message):
        with self._wfile_lock:
            if self._wfile.closed:
                return
            try:
                body = json.dumps(message, **self._json_dumps_args)

                # Ensure we get the byte length, not the character length
                content_length = len(body) if isinstance(body, bytes) else len(body.encode('utf-8'))

                response = (
                    "Content-Length: {}\r\n"
                    "Content-Type: application/vscode-jsonrpc; charset=utf8\r\n\r\n"
                    "{}".format(content_length, body)
                )

                self._wfile.write(response.encode('utf-8'))
                self._wfile.flush()
            except Exception:  # pylint: disable=broad-except
                log.exception("Failed to write message to output file %s", message)
