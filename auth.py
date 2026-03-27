import os
from typing import Any, Optional
from auth0_server_python.auth_server.server_client import ServerClient
from auth0_server_python.store.abstract import StateStore, TransactionStore
from dotenv import load_dotenv

load_dotenv()


class MemoryTransactionStore(TransactionStore):
    def __init__(self):
        super().__init__(options={})
        self._store: dict[str, Any] = {}

    async def set(self, identifier: str, state: Any, remove_if_expires: bool = False, options: Optional[dict] = None) -> None:
        self._store[identifier] = state

    async def get(self, identifier: str, options: Optional[dict] = None) -> Optional[Any]:
        return self._store.get(identifier)

    async def delete(self, identifier: str, options: Optional[dict] = None) -> None:
        self._store.pop(identifier, None)


class MemoryStateStore(StateStore):
    def __init__(self):
        super().__init__(options={})
        self._store: dict[str, Any] = {}

    async def set(self, identifier: str, state: Any, remove_if_expires: bool = False, options: Optional[dict] = None) -> None:
        self._store[identifier] = state

    async def get(self, identifier: str, options: Optional[dict] = None) -> Optional[Any]:
        return self._store.get(identifier)

    async def delete(self, identifier: str, options: Optional[dict] = None) -> None:
        self._store.pop(identifier, None)


auth0 = ServerClient(
    domain=os.environ['AUTH0_DOMAIN'],
    client_id=os.environ['AUTH0_CLIENT_ID'],
    client_secret=os.environ['AUTH0_CLIENT_SECRET'],
    secret=os.environ['AUTH0_SECRET'],
    redirect_uri=os.environ['AUTH0_REDIRECT_URI'],
    transaction_store=MemoryTransactionStore(),
    state_store=MemoryStateStore(),
    authorization_params={'scope': 'openid profile email'},
)
