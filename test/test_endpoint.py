# Copyright 2018 Palantir Technologies, Inc.
# pylint: disable=redefined-outer-name
# from concurrent import futures
import asyncio
import time
import mock
import pytest

from pyls_jsonrpc import exceptions
from pyls_jsonrpc.endpoint import Endpoint

MSG_ID = 'id'


async def async_magic():
    pass

mock.MagicMock.__await__ = lambda x: async_magic().__await__()
mock.Mock.__await__ = lambda x: async_magic().__await__()


@pytest.fixture()
def dispatcher():
    return {}


@pytest.fixture()
def consumer():
    return mock.MagicMock()


@pytest.fixture()
def endpoint(dispatcher, consumer, event_loop):
    return Endpoint(
        dispatcher, consumer, id_generator=lambda: MSG_ID, loop=event_loop)


@pytest.mark.asyncio
async def test_bad_message(endpoint: Endpoint):
    # Ensure doesn't raise for a bad message
    await endpoint.consume({'key': 'value'})


@pytest.mark.asyncio
async def test_notify(endpoint, consumer):
    await endpoint.notify('methodName', {'key': 'value'})
    consumer.assert_called_once_with({
        'jsonrpc': '2.0',
        'method': 'methodName',
        'params': {'key': 'value'}
    })


@pytest.mark.asyncio
async def test_notify_none_params(endpoint, consumer):
    await endpoint.notify('methodName', None)
    consumer.assert_called_once_with({
        'jsonrpc': '2.0',
        'method': 'methodName',
    })


@pytest.mark.asyncio
async def test_request(endpoint: Endpoint, consumer):
    future = await endpoint.request('methodName', {'key': 'value'})
    assert not future.done()

    consumer.assert_called_once_with({
        'jsonrpc': '2.0',
        'id': MSG_ID,
        'method': 'methodName',
        'params': {'key': 'value'}
    })

    # Send the response back to the endpoint
    result = 1234
    await endpoint.consume({
        'jsonrpc': '2.0',
        'id': MSG_ID,
        'result': result
    })
    fut_result = await future
    assert fut_result == result


@pytest.mark.asyncio
async def test_request_error(endpoint: Endpoint, consumer):
    future = await endpoint.request('methodName', {'key': 'value'})
    assert not future.done()

    consumer.assert_called_once_with({
        'jsonrpc': '2.0',
        'id': MSG_ID,
        'method': 'methodName',
        'params': {'key': 'value'}
    })

    # Send an error back from the client
    error = exceptions.JsonRpcInvalidRequest(data=1234)
    await endpoint.consume({
        'jsonrpc': '2.0',
        'id': MSG_ID,
        'error': error.to_dict()
    })

    # Verify the exception raised by the future is the same as the error
    # the client serialized
    with pytest.raises(exceptions.JsonRpcException) as exc_info:
        await future  # .result(timeout=2)
    assert exc_info.type == exceptions.JsonRpcInvalidRequest
    assert exc_info.value == error


@pytest.mark.asyncio
async def test_request_cancel(endpoint: Endpoint, consumer):
    future = await endpoint.request('methodName', {'key': 'value'})
    assert not future.done()

    consumer.assert_called_once_with({
        'jsonrpc': '2.0',
        'id': MSG_ID,
        'method': 'methodName',
        'params': {'key': 'value'}
    })

    # Cancel the request
    future.cancel()
    await asyncio.sleep(0.5)
    consumer.assert_any_call({
        'jsonrpc': '2.0',
        'method': '$/cancelRequest',
        'params': {'id': MSG_ID}
    })


@pytest.mark.asyncio
async def test_consume_notification(endpoint: Endpoint, dispatcher):
    handler = mock.Mock()
    # handler = asyncio.Future()
    dispatcher['methodName'] = handler

    await endpoint.consume({
        'jsonrpc': '2.0',
        'method': 'methodName',
        'params': {'key': 'value'}
    })
    # await handler
    handler.assert_called_once_with({'key': 'value'})


@pytest.mark.asyncio
async def test_consume_notification_error(endpoint, dispatcher):
    handler = mock.Mock(side_effect=ValueError)
    dispatcher['methodName'] = handler
    # Verify the consume doesn't throw
    await endpoint.consume({
        'jsonrpc': '2.0',
        'method': 'methodName',
        'params': {'key': 'value'}
    })
    handler.assert_called_once_with({'key': 'value'})


@pytest.mark.asyncio
async def test_consume_notification_method_not_found(endpoint):
    # Verify consume doesn't throw for method not found
    await endpoint.consume({
        'jsonrpc': '2.0',
        'method': 'methodName',
        'params': {'key': 'value'}
    })


@pytest.mark.asyncio
async def test_consume_async_notification_error(endpoint, dispatcher):
    async def _async_handler():
        raise ValueError()

    handler = mock.Mock(wraps=_async_handler)
    dispatcher['methodName'] = handler

    # Verify the consume doesn't throw
    await endpoint.consume({
        'jsonrpc': '2.0',
        'method': 'methodName',
        'params': {'key': 'value'}
    })
    handler.assert_called_once_with({'key': 'value'})


@pytest.mark.asyncio
async def test_consume_request(endpoint, consumer, dispatcher):
    result = 1234
    handler = mock.Mock(return_value=result)
    dispatcher['methodName'] = handler

    await endpoint.consume({
        'jsonrpc': '2.0',
        'id': MSG_ID,
        'method': 'methodName',
        'params': {'key': 'value'}
    })

    handler.assert_called_once_with({'key': 'value'})
    consumer.assert_called_once_with({
        'jsonrpc': '2.0',
        'id': MSG_ID,
        'result': result
    })


@pytest.mark.asyncio
async def test_consume_future_request(
        endpoint: Endpoint, consumer, dispatcher):
    # future_response = futures.ThreadPoolExecutor().submit(lambda: 1234)
    async def future_wrap(*args, **kwargs):  # pylint: disable=unused-argument
        return 1234

    task = asyncio.ensure_future(future_wrap())
    handler = mock.Mock(return_value=task)
    dispatcher['methodName'] = handler

    await endpoint.consume({
        'jsonrpc': '2.0',
        'id': MSG_ID,
        'method': 'methodName',
        'params': {'key': 'value'}
    })

    handler.assert_called_once_with({'key': 'value'})
    await asyncio.sleep(0.5)
    consumer.assert_called_once_with({
        'jsonrpc': '2.0',
        'id': MSG_ID,
        'result': 1234
    })


@pytest.mark.asyncio
async def test_consume_async_request(endpoint, consumer, dispatcher):
    async def _async_handler(*args, **kwargs):  # pylint: disable=unused-argument
        return 1234

    handler = mock.Mock(wraps=_async_handler)
    dispatcher['methodName'] = handler

    await endpoint.consume({
        'jsonrpc': '2.0',
        'id': MSG_ID,
        'method': 'methodName',
        'params': {'key': 'value'}
    })

    handler.assert_called_once_with({'key': 'value'})
    await asyncio.sleep(0.5)
    consumer.assert_called_once_with({
        'jsonrpc': '2.0',
        'id': MSG_ID,
        'result': 1234
    })


@pytest.mark.asyncio
@pytest.mark.parametrize('exc_type, error', [
    (ValueError, exceptions.JsonRpcInternalError(message='ValueError')),
    (KeyError, exceptions.JsonRpcInternalError(message='KeyError')),
    (exceptions.JsonRpcMethodNotFound, exceptions.JsonRpcMethodNotFound()),
])
async def test_consume_async_request_error(exc_type, error, endpoint: Endpoint,
                                           consumer, dispatcher):
    async def _async_handler(*args, **kwargs):
        raise exc_type()

    handler = mock.Mock(wraps=_async_handler)
    dispatcher['methodName'] = handler

    await endpoint.consume({
        'jsonrpc': '2.0',
        'id': MSG_ID,
        'method': 'methodName',
        'params': {'key': 'value'}
    })

    handler.assert_called_once_with({'key': 'value'})
    await asyncio.sleep(0.5)
    assert_consumer_error(consumer, error)


@pytest.mark.asyncio
async def test_consume_request_method_not_found(endpoint, consumer):
    await endpoint.consume({
        'jsonrpc': '2.0',
        'id': MSG_ID,
        'method': 'methodName',
        'params': {'key': 'value'}
    })
    assert_consumer_error(consumer, exceptions.JsonRpcMethodNotFound.of('methodName'))


@pytest.mark.asyncio
@pytest.mark.parametrize('exc_type, error', [
    (ValueError, exceptions.JsonRpcInternalError(message='ValueError')),
    (KeyError, exceptions.JsonRpcInternalError(message='KeyError')),
    (exceptions.JsonRpcMethodNotFound, exceptions.JsonRpcMethodNotFound()),
])
async def test_consume_request_error(exc_type, error, endpoint, consumer, dispatcher):
    handler = mock.Mock(side_effect=exc_type)
    dispatcher['methodName'] = handler

    await endpoint.consume({
        'jsonrpc': '2.0',
        'id': MSG_ID,
        'method': 'methodName',
        'params': {'key': 'value'}
    })

    handler.assert_called_once_with({'key': 'value'})
    assert_consumer_error(consumer, error)


@pytest.mark.asyncio
async def test_consume_request_cancel(endpoint, dispatcher):
    async def async_handler():
        await asyncio.sleep(3)

    handler = mock.Mock(wraps=async_handler)
    dispatcher['methodName'] = handler

    await endpoint.consume({
        'jsonrpc': '2.0',
        'id': MSG_ID,
        'method': 'methodName',
        'params': {'key': 'value'}
    })
    handler.assert_called_once_with({'key': 'value'})

    await endpoint.consume({
        'jsonrpc': '2.0',
        'method': '$/cancelRequest',
        'params': {'id': MSG_ID}
    })

    # Because Python's Future cannot be cancelled once it's started, the request is never actually cancelled
    # consumer.assert_called_once_with({
    #     'jsonrpc': '2.0',
    #     'id': MSG_ID,
    #     'error': exceptions.JsonRpcRequestCancelled().to_dict()
    # })


@pytest.mark.asyncio
async def test_consume_request_cancel_unknown(endpoint):
    # Verify consume doesn't throw
    await endpoint.consume({
        'jsonrpc': '2.0',
        'method': '$/cancelRequest',
        'params': {'id': 'unknown identifier'}
    })


def assert_consumer_error(consumer_mock, exception):
    """Assert that the consumer mock has had once call with the given error message and code.

    The error's data part is not compared since it contains the traceback.
    """
    assert len(consumer_mock.mock_calls) == 1
    _name, args, _kwargs = consumer_mock.mock_calls[0]
    assert args[0]['error']['message'] == exception.message
    assert args[0]['error']['code'] == exception.code


def await_assertion(condition, timeout=3.0, interval=0.1, exc=None):
    if timeout <= 0:
        raise exc if exc else AssertionError("Failed to wait for condition %s" % condition)
    try:
        condition()
    except AssertionError as e:
        time.sleep(interval)
        await_assertion(condition, timeout=(timeout - interval), interval=interval, exc=e)
