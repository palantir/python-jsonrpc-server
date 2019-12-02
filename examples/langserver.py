import logging

from tornado import web, ioloop, websocket

from pyls_jsonrpc import dispatchers, endpoint

try:
    import ujson as json
except Exception:  # pylint: disable=broad-except
    import json

log = logging.getLogger(__name__)


class LanguageServer(dispatchers.MethodDispatcher):
    """Implement a JSON RPC method dispatcher for the language server protocol."""

    def __init__(self):
        # Endpoint is lazily set after construction
        self.endpoint = None

    def m_initialize(self, rootUri=None, **kwargs):
        log.info("Got initialize params: %s", kwargs)
        return {"capabilities": {
            "textDocumentSync": {
                "openClose": True,
            }
        }}

    def m_text_document__did_open(self, textDocument=None, **_kwargs):
        log.info("Opened text document %s", textDocument)
        self.endpoint.notify('textDocument/publishDiagnostics', {
            'uri': textDocument['uri'],
            'diagnostics': [{
                'range': {
                    'start': {'line': 0, 'character': 0},
                    'end': {'line': 1, 'character': 0},
                },
                'message': 'Some very bad Python code',
                'severity': 1  # DiagnosticSeverity.Error
            }]
        })


class LanguageServerWebSocketHandler(websocket.WebSocketHandler):
    """Setup tornado websocket handler to host language server."""

    def __init__(self, *args, **kwargs):
        # Create an instance of the language server used to dispatch JSON RPC methods
        langserver = LanguageServer()

        # Setup an endpoint that dispatches to the ls, and writes server->client messages
        # back to the client websocket
        self.endpoint = endpoint.Endpoint(langserver, lambda msg: self.write_message(json.dumps(msg)))

        # Give the language server a handle to the endpoint so it can send JSON RPC
        # notifications and requests.
        langserver.endpoint = self.endpoint

        super(LanguageServerWebSocketHandler, self).__init__(*args, **kwargs)

    def on_message(self, message):
        """Forward client->server messages to the endpoint."""
        self.endpoint.consume(json.loads(message))

    def check_origin(self, origin):
        return True


if __name__ == "__main__":
    app = web.Application([
        (r"/python", LanguageServerWebSocketHandler),
    ])
    app.listen(3000, address='127.0.0.1')
    ioloop.IOLoop.current().start()
