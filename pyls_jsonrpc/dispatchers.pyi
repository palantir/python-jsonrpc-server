
from typing import Coroutine, Any


class MethodDispatcher(object):
    def __getitem__(self, item: Any) -> Coroutine: ...
