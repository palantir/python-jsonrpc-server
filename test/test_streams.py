# Copyright 2018 Palantir Technologies, Inc.
# pylint: disable=redefined-outer-name
import asyncio
import datetime
from io import BytesIO
import datetime
import os
import sys
import mock
import pytest

from pyls_jsonrpc.streams import JsonRpcStreamReader, JsonRpcStreamWriter


async def async_magic():
    pass

mock.MagicMock.__await__ = lambda x: async_magic().__await__()
mock.Mock.__await__ = lambda x: async_magic().__await__()


async def stdio(loop=None):
    if loop is None:
        loop = asyncio.get_event_loop()

    return _wrap_file(loop)


def _wrap_file(loop):
    # BytesIO cannot behave like a proper pipe/socket, thus we need to wrap it
    # to use an executor to read from stdio and write to stdout
    # note: if nothing ever drains the writer explicitly,
    # no flushing ever takes place!
    class InFileReader:
        def __init__(self):
            self.stdin = BytesIO()
            self.eof = False

        async def read(self, num_bytes):
            return self.stdin.read(num_bytes)

        def write(self, buf):
            self.stdin.write(buf)

        async def drain(self):
            pass

        def seek(self, offset):
            self.stdin.seek(offset)

        def feed_eof(self):
            self.eof = True
            self.stdin.close()

        def at_eof(self):
            return self.eof

        async def readline(self):
            # a single call to sys.stdin.readline() is thread-safe
            return await loop.run_in_executor(None, self.stdin.readline)

    class OutFileReader:
        def __init__(self):
            self.buffer = []
            self.pipe = BytesIO()
            # self.stdout = self.pipe.getbuffer()

        def write(self, data):
            self.buffer.append(data)

        def close(self):
            self.pipe.close()

        def seek(self, byte):
            self.pipe.seek(byte)

        async def read(self, num_bytes):
            return self.pipe.read(num_bytes)

        def is_closing(self):
            return self.pipe.closed

        async def drain(self):
            data, self.buffer = self.buffer, []
            data = b''.join(data)
            # a single call to sys.stdout.writelines() is thread-safe
            return await loop.run_in_executor(None, self.pipe.write, data)

        def getvalue(self):
            return self.pipe.getvalue()

    return InFileReader(), OutFileReader()


@pytest.fixture()
async def reader_writer(event_loop):
    return await stdio(loop=event_loop)


@pytest.fixture()
async def rfile(reader_writer):
    reader, _ = reader_writer
    return reader


@pytest.fixture()
async def wfile(reader_writer):
    _, writer = reader_writer
    return writer


@pytest.fixture()
async def reader(rfile, event_loop):
    return JsonRpcStreamReader(rfile, loop=event_loop)


@pytest.fixture()
async def writer(wfile, event_loop):
    return JsonRpcStreamWriter(wfile, loop=event_loop, sort_keys=True)


@pytest.mark.asyncio
async def test_reader(rfile, reader):
    rfile.write(
        b'Content-Length: 49\r\n'
        b'Content-Type: application/vscode-jsonrpc; charset=utf8\r\n'
        b'\r\n'
        b'{"id": "hello", "method": "method", "params": {}}'
    )
    await rfile.drain()
    rfile.seek(0)

    consumer = mock.Mock()
    await reader.listen(consumer)

    consumer.assert_called_once_with({
        'id': 'hello',
        'method': 'method',
        'params': {}
    })


@pytest.mark.asyncio
async def test_reader_bad_message(rfile, reader):
    rfile.write(b'Hello world')
    rfile.seek(0)

    # Ensure the listener doesn't throw
    consumer = mock.Mock()
    await reader.listen(consumer)
    consumer.assert_not_called()


@pytest.mark.asyncio
async def test_reader_bad_json(rfile, reader):
    rfile.write(
        b'Content-Length: 8\r\n'
        b'Content-Type: application/vscode-jsonrpc; charset=utf8\r\n'
        b'\r\n'
        b'{hello}}'
    )
    rfile.seek(0)

    # Ensure the listener doesn't throw
    consumer = mock.Mock()
    await reader.listen(consumer)
    consumer.assert_not_called()


@pytest.mark.asyncio
async def test_writer(wfile, writer):
    await writer.write({
        'id': 'hello',
        'method': 'method',
        'params': {}
    })

    if os.name == 'nt':
        assert wfile.getvalue() == (
            b'Content-Length: 49\r\n'
            b'Content-Type: application/vscode-jsonrpc; charset=utf8\r\n'
            b'\r\n'
            b'{"id": "hello", "method": "method", "params": {}}'
        )
    else:
        assert wfile.getvalue() == (
            b'Content-Length: 44\r\n'
            b'Content-Type: application/vscode-jsonrpc; charset=utf8\r\n'
            b'\r\n'
            b'{"id":"hello","method":"method","params":{}}'
        )


class JsonDatetime(datetime.datetime):
    """Monkey path json datetime."""
    def __json__(self):
        if sys.version_info.major == 3:
            dif = int(self.timestamp())
        else:
            dif = int((self - datetime.datetime(1970, 1, 1)).total_seconds())
        return '{0}'.format(dif)


@pytest.mark.asyncio
async def test_writer_bad_message(wfile, writer):
    # A datetime isn't serializable(or poorly serializable),
    # ensure the write method doesn't throw, but the result could be empty
    # or the correct datetime
    datetime.datetime = JsonDatetime
    await writer.write(datetime.datetime(
        year=2019,
        month=1,
        day=1,
        hour=1,
        minute=1,
        second=1,
    ))

    assert wfile.getvalue() in [
        b'',
        b'Content-Length: 10\r\n'
        b'Content-Type: application/vscode-jsonrpc; charset=utf8\r\n'
        b'\r\n'
        b'1546304461'
    ]
