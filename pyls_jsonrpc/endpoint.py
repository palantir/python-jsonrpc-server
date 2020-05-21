# Copyright 2018 Palantir Technologies, Inc.
import asyncio
import logging
import uuid
import sys

from typing import Dict, Coroutine, Union, Callable, Awaitable

from .exceptions import (
    JsonRpcException, JsonRpcRequestCancelled,
    JsonRpcInternalError, JsonRpcMethodNotFound)

log = logging.getLogger(__name__)
JSONRPC_VERSION = '2.0'
CANCEL_METHOD = '$/cancelRequest'


class Endpoint(object):

    def __init__(self,
                 dispatcher: Dict[str, Union[Coroutine, Dict, None]],
                 consumer: Coroutine,
                 id_generator: Callable[[], str] = lambda: str(uuid.uuid4()),
                 max_workers: int = 5,
                 loop: asyncio.BaseEventLoop = None):
        """A JSON RPC endpoint for managing messages sent to/from the client.

        Args:
            dispatcher (dict): A dictionary of method name to handler function.
                The handler functions should return either the result or a
                callable that will be used to asynchronously compute
                the result.
            consumer (fn): A function that consumes JSON RPC message dicts and
                sends them to the client.
            id_generator (fn, optional): A function used to generate
                request IDs. Defaults to the string value
                of :func:`uuid.uuid4`.
            max_workers (int, optional): The number of workers in the
                asynchronous executor pool.
        """
        self._dispatcher = dispatcher
        self._consumer = consumer
        self._id_generator = id_generator

        self.loop: asyncio.BaseEventLoop = (
            asyncio.get_running_loop() if loop is None else loop)
        self._client_request_futures = {}  # type: Dict[str, Awaitable]
        self._server_request_futures = {}  # type: Dict[str, Awaitable]

    def shutdown(self) -> None:
        # self._executor_service.shutdown()
        self.loop.close()

    async def notify(self, method: str, params: Dict = None) -> None:
        """Send a JSON RPC notification to the client.

         Args:
             method (str): The method name of the notification to send
             params (any): The payload of the notification
         """
        log.debug('Sending notification: %s %s', method, params)
        message = {
            'jsonrpc': JSONRPC_VERSION,
            'method': method,
        }
        if params is not None:
            message['params'] = params

        await self._consumer(message)

    async def request(self, method: str, params: Dict = None) -> Awaitable:
        """Send a JSON RPC request to the client.

        Args:
            method (str): The method name of the message to send
            params (any): The payload of the message

        Returns:
            Future that will resolve once a response has been received
        """
        msg_id = self._id_generator()
        log.debug('Sending request with id %s: %s %s', msg_id, method, params)

        message = {
            'jsonrpc': JSONRPC_VERSION,
            'id': msg_id,
            'method': method,
        }
        if params is not None:
            message['params'] = params

        request_future = asyncio.Future()
        request_future.add_done_callback(self._cancel_callback(msg_id))

        self._server_request_futures[msg_id] = request_future
        await self._consumer(message)

        return request_future

    def _cancel_callback(self, request_id: int) -> Coroutine:
        """Construct a cancellation callback for the given request ID."""
        def callback(future: asyncio.Future):
            if future.cancelled():
                asyncio.ensure_future(
                    self.notify(CANCEL_METHOD, {'id': request_id}),
                    loop=self.loop)
                # self.loop.run_until_complete(
                #     self.notify(CANCEL_METHOD, {'id': request_id}))
                # future.set_exception(JsonRpcRequestCancelled())
        return callback

    async def consume(self, message: Dict) -> None:
        """Consume a JSON RPC message from the client.

        Args:
            message (dict): The JSON RPC message sent by the client
        """
        if 'jsonrpc' not in message or message['jsonrpc'] != JSONRPC_VERSION:
            log.warn("Unknown message type %s", message)
            return

        if 'id' not in message:
            log.debug("Handling notification from client %s", message)
            await self._handle_notification(
                message['method'], message.get('params'))
        elif 'method' not in message:
            log.debug("Handling response from client %s", message)
            await self._handle_response(
                message['id'], message.get('result'), message.get('error'))
        else:
            try:
                log.debug("Handling request from client %s", message)
                await self._handle_request(
                    message['id'], message['method'], message.get('params'))
            except JsonRpcException as e:
                log.exception("Failed to handle request %s", message['id'])
                await self._consumer({
                    'jsonrpc': JSONRPC_VERSION,
                    'id': message['id'],
                    'error': e.to_dict()
                })
            except Exception:  # pylint: disable=broad-except
                log.exception("Failed to handle request %s", message['id'])
                await self._consumer({
                    'jsonrpc': JSONRPC_VERSION,
                    'id': message['id'],
                    'error': JsonRpcInternalError.of(sys.exc_info()).to_dict()
                })

    async def _handle_notification(self, method: str, params: Dict) -> None:
        """Handle a notification from the client."""
        if method == CANCEL_METHOD:
            await self._handle_cancel_notification(params['id'])
            return

        try:
            handler = self._dispatcher[method]
        except KeyError:
            log.warn("Ignoring notification for unknown method %s", method)
            return

        try:
            handler_result = handler(params)
        except Exception:  # pylint: disable=broad-except
            log.exception(
                "Failed to handle notification %s: %s", method, params)
            return

        if callable(handler_result):
            log.debug(
                "Executing async notification handler %s", handler_result)
            notification_task = asyncio.ensure_future(handler_result)
            notification_task.add_done_callback(
                self._notification_callback(method, params))

    @staticmethod
    def _notification_callback(method: str, params: Dict) -> Coroutine:
        """Construct a notification callback for the given request ID."""
        def callback(future: Awaitable) -> None:
            try:
                future.result()
                log.debug("Successfully handled async notification %s %s",
                          method, params)
            except Exception:  # pylint: disable=broad-except
                log.exception("Failed to handle async notification %s %s",
                              method, params)
        return callback

    async def _handle_cancel_notification(self, msg_id: int) -> None:
        """Handle a cancel notification from the client."""
        request_future = self._client_request_futures.pop(msg_id, None)

        if not request_future:
            log.warn("Received cancel notification for unknown message id %s",
                     msg_id)
            return

        # Will only work if the request hasn't started executing
        if request_future.cancel():
            log.debug("Cancelled request with id %s", msg_id)

    async def _handle_request(self, msg_id: int, method: str,
                              params: Dict) -> None:
        """Handle a request from the client."""
        try:
            handler = self._dispatcher[method]
        except KeyError:
            raise JsonRpcMethodNotFound.of(method)

        handler_result = handler(params)

        if callable(handler_result) or asyncio.iscoroutine(handler_result):
            log.debug("Executing async request handler %s", handler_result)
            # request_future = self._executor_service.submit(handler_result)
            request_task = asyncio.ensure_future(handler_result)
            self._client_request_futures[msg_id] = request_task
            request_task.add_done_callback(self._request_callback(msg_id))
        elif isinstance(handler_result, asyncio.Future):
            log.debug("Request handler is already a future %s", handler_result)
            self._client_request_futures[msg_id] = handler_result
            handler_result.add_done_callback(self._request_callback(msg_id))
        else:
            log.debug("Got result from synchronous request handler: %s",
                      handler_result)
            await self._consumer({
                'jsonrpc': JSONRPC_VERSION,
                'id': msg_id,
                'result': handler_result
            })

    def _request_callback(self, request_id: int) -> Callable:
        """Construct a request callback for the given request ID."""
        def callback(future: Awaitable) -> None:
            # Remove the future from the client requests map
            self._client_request_futures.pop(request_id, None)

            if future.cancelled():
                future.set_exception(JsonRpcRequestCancelled())

            message = {
                'jsonrpc': JSONRPC_VERSION,
                'id': request_id,
            }

            try:
                message['result'] = future.result()
            except JsonRpcException as e:
                log.exception("Failed to handle request %s", request_id)
                message['error'] = e.to_dict()
            except Exception:  # pylint: disable=broad-except
                log.exception("Failed to handle request %s", request_id)
                message['error'] = JsonRpcInternalError.of(
                    sys.exc_info()).to_dict()

            asyncio.ensure_future(self._consumer(message), loop=self.loop)

        return callback

    async def _handle_response(self, msg_id: int,
                               result: Union[Dict, None] = None,
                               error: Union[Dict, None] = None) -> None:
        """Handle a response from the client."""
        request_future = self._server_request_futures.pop(msg_id, None)  # type: asyncio.Future

        if not request_future:
            log.warn("Received response to unknown message id %s", msg_id)
            return

        if error is not None:
            log.debug(
                "Received error response to message %s: %s", msg_id, error)
            request_future.set_exception(JsonRpcException.from_dict(error))
        else:
            log.debug("Received result for message %s: %s", msg_id, result)
            request_future.set_result(result)
