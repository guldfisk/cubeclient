from __future__ import annotations

import typing as t

from abc import ABC, abstractmethod
import datetime
from enum import Enum

from magiccube.collections.cube import Cube
from magiccube.collections.laps import TrapCollection
from magiccube.collections.meta import MetaCube
from magiccube.update.cubeupdate import VerboseCubePatch
from mtgorp.models.collections.deck import Deck
from mtgorp.models.persistent.cardboard import Cardboard
from mtgorp.models.persistent.printing import Printing

R = t.TypeVar('R')
P = t.TypeVar('P', bound = t.Union[Printing, Cardboard])


class ApiClient(ABC):

    def __init__(self, host: str, *, token: t.Optional[str] = None):
        self._host = host
        self._token = token
        self._user = None

    @property
    def host(self) -> str:
        return self._host

    @property
    def token(self) -> str:
        return self._token

    @token.setter
    def token(self, value: str) -> None:
        self._token = value

    @property
    def user(self) -> t.Optional[User]:
        return self._user

    @abstractmethod
    def login(self, username: str, password: str) -> str:
        pass

    @abstractmethod
    def release(self, release: t.Union[CubeRelease, str, int]) -> CubeRelease:
        pass

    @abstractmethod
    def versioned_cubes(self, offset: int = 0, limit: int = 10) -> PaginatedResponse[VersionedCube]:
        pass

    @abstractmethod
    def versioned_cube(self, versioned_cube_id: t.Union[str, int]) -> VersionedCube:
        pass

    @abstractmethod
    def patch(self, patch_id: t.Union[str, int]) -> PatchModel:
        pass

    @abstractmethod
    def patches(
        self,
        versioned_cube: t.Union[VersionedCube, int, str],
        offset: int = 0,
        limit: int = 10,
    ) -> PaginatedResponse[PatchModel]:
        pass

    @abstractmethod
    def preview_patch(self, patch: t.Union[PatchModel, int, str]) -> MetaCube:
        pass

    @abstractmethod
    def verbose_patch(self, patch: t.Union[PatchModel, int, str]) -> VerboseCubePatch:
        pass

    @abstractmethod
    def distribution_possibilities(
        self,
        patch: t.Union[PatchModel, int, str],
        offset: int = 0,
        limit: int = 10,
    ) -> PaginatedResponse[DistributionPossibility]:
        pass

    @abstractmethod
    def search(
        self,
        query: str,
        offset: int = 0,
        limit = 10,
        order_by: str = 'name',
        descending: bool = False,
        search_target: t.Type[P] = Printing,
    ) -> PaginatedResponse[P]:
        pass

    @abstractmethod
    def sealed_session(self, session_id: t.Union[str, int]) -> SealedSession:
        pass

    @abstractmethod
    def sealed_sessions(
        self,
        offset: int = 0,
        limit: int = 10,
        *,
        filters: t.Optional[t.Mapping[str, t.Any]] = None,
        sort_key: str = 'created_at',
        ascending: bool = False,
    ) -> PaginatedResponse[SealedSession]:
        pass

    @abstractmethod
    def sealed_pool(self, pool_id: t.Union[str, int]) -> SealedPool:
        pass

    @abstractmethod
    def upload_sealed_deck(self, pool_id: t.Union[str, int], name: str, deck: Deck) -> LimitedDeck:
        pass

    # @abstractmethod
    # def patch_report(self, patch: t.Union[PatchModel, int, str]) -> UpdateReport:
    #     pass


class PaginatedResponse(t.Sequence[R]):

    def __init__(
        self,
        endpoint: t.Callable[[int, int], t.Any],
        serializer: t.Callable[[t.Any], R],
        offset: int = 0,
        limit: int = 50,
    ):
        self._endpoint = endpoint
        self._serializer = serializer
        self._limit = limit

        response = endpoint(offset, limit)

        self._count = response['count']
        self._items: t.List[t.Optional[R]] = [None for _ in range(self._count)]
        items = list(map(serializer, response['results']))
        self._items[offset:offset + len(items)] = items

    def _fetch_page(self, index: int) -> None:
        for offset_index, item in enumerate(
            map(
                self._serializer,
                self._endpoint(index, self._limit)['results'],
            )
        ):
            try:
                if self._items[index + offset_index] is None:
                    self._items[index + offset_index] = item
            except IndexError:
                break

    def __getitem__(self, index) -> R:
        if self._items[index] is None:
            self._fetch_page(index)
        return self._items[index]

    def __iter__(self) -> t.Iterator[R]:
        for index, item in enumerate(self._items):
            if item is None:
                self._fetch_page(index)
                yield self._items[index]
            else:
                yield item

    def __contains__(self, item) -> bool:
        return item in self.__iter__()

    def __len__(self):
        return self._count

    def _repr_iter(self) -> t.Iterator[str]:
        in_none = False
        for item in self._items:
            if item is None:
                if in_none:
                    continue
                in_none = True
                yield '...'
            else:
                in_none = False
                yield str(item)

    def __repr__(self):
        return '{}({}, [{}])'.format(
            self.__class__.__name__,
            self._count,
            ', '.join(self._repr_iter())
        )


class RemoteModel(ABC):

    def __init__(self, model_id: t.Union[str, int], client: ApiClient):
        self._id = model_id
        self._api_client = client

    @property
    def id(self) -> t.Union[str, int]:
        return self._id

    def __hash__(self) -> int:
        return hash(self._id)

    def __eq__(self, other) -> bool:
        return (
            isinstance(other, self.__class__)
            and self._id == other._id
        )

    def __repr__(self):
        return '{}({})'.format(
            self.__class__.__name__,
            self._id,
        )


class User(RemoteModel):

    def __init__(self, model_id: t.Union[str, int], username: str, client: ApiClient):
        super().__init__(model_id, client)
        self._username = username

    @property
    def username(self) -> str:
        return self._username


class VersionedCube(RemoteModel):

    def __init__(
        self,
        model_id: t.Union[str, int],
        name: str,
        created_at: datetime.datetime,
        description: str,
        releases: t.List[CubeRelease],
        client: ApiClient,
    ):
        super().__init__(model_id, client)
        self._name = name
        self._created_at = created_at
        self._description = description
        self._releases = releases

        self._patches: t.Optional[PaginatedResponse[PatchModel]] = None

    @property
    def name(self) -> str:
        return self._name

    @property
    def created_at(self) -> datetime.datetime:
        return self._created_at

    @property
    def description(self) -> str:
        return self._description

    @property
    def releases(self) -> t.Sequence[CubeRelease]:
        return self._releases

    @property
    def patches(self) -> PaginatedResponse[PatchModel]:
        if self._patches is None:
            self._patches = self._api_client.patches(self)
        return self._patches


class CubeRelease(RemoteModel):

    def __init__(
        self,
        model_id: t.Union[str, int],
        created_at: datetime.datetime,
        name: str,
        intended_size: int,
        cube: t.Optional[Cube],
        client: ApiClient,
    ):
        super().__init__(model_id, client)
        self._created_at = created_at
        self._name = name
        self._intended_size = intended_size
        self._cube = cube

    @property
    def created_at(self) -> datetime.datetime:
        return self._created_at

    @property
    def name(self) -> str:
        return self._name

    @property
    def intended_size(self) -> int:
        return self._intended_size

    @property
    def cube(self) -> Cube:
        if self._cube is None:
            self._cube = self._api_client.release(self).cube
        return self._cube


class PatchModel(RemoteModel):

    def __init__(
        self,
        model_id: t.Union[str, int],
        created_at: datetime.datetime,
        name: str,
        description: str,
        client: ApiClient,
    ):
        super().__init__(model_id, client)
        self._created_at = created_at
        self._name = name
        self._description = description

        self._preview: t.Optional[MetaCube] = None
        self._verbose: t.Optional[VerboseCubePatch] = None
        self._distribution_possibilities: t.Optional[PaginatedResponse[DistributionPossibility]] = None

    @property
    def created_at(self) -> datetime.datetime:
        return self._created_at

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def preview(self) -> MetaCube:
        if self._preview is None:
            self._preview = self._api_client.preview_patch(self)
        return self._preview

    @property
    def verbose(self):
        if self._verbose is None:
            self._verbose = self._api_client.verbose_patch(self)
        return self._verbose

    @property
    def distribution_possibilities(self) -> PaginatedResponse[DistributionPossibility]:
        if self._distribution_possibilities is None:
            self._distribution_possibilities = self._api_client.distribution_possibilities(self)
        return self._distribution_possibilities


class DistributionPossibility(RemoteModel):

    def __init__(
        self,
        model_id: t.Union[str, int],
        created_at: datetime.datetime,
        pdf_url: t.Optional[str],
        fitness: float,
        trap_collection: TrapCollection,
        client: ApiClient,
    ):
        super().__init__(model_id, client)
        self._created_at = created_at
        self._pdf_url = pdf_url
        self._fitness = fitness
        self._trap_collection = trap_collection

    @property
    def created_at(self) -> datetime.datetime:
        return self._created_at

    @property
    def pdf_url(self) -> t.Optional[str]:
        return self._pdf_url

    @property
    def fitness(self) -> float:
        return self._fitness

    @property
    def trap_collection(self) -> TrapCollection:
        return self._trap_collection


class SealedSession(RemoteModel):
    class SealedSessionState(Enum):
        DECK_BUILDING = 0
        PLAYING = 1
        FINISHED = 2

    def __init__(
        self,
        model_id: t.Union[str, int],
        name: str,
        release: t.Any,
        players: t.AbstractSet[User],
        state: SealedSessionState,
        pool_size: int,
        game_format: str,
        created_at: datetime.datetime,
        client: ApiClient,
        pools: t.Optional[t.List[SealedPool]] = None,
    ):
        super().__init__(model_id, client)
        self._name = name
        self._release = release
        self._players = players
        self._state = state
        self._pool_size = pool_size
        self._game_format = game_format
        self._created_at = created_at
        self._pools = pools

    @property
    def name(self) -> str:
        return self._name

    @property
    def release(self):
        return self._release

    @property
    def players(self) -> t.AbstractSet[User]:
        return self._players

    @property
    def state(self) -> SealedSessionState:
        return self._state

    @property
    def pool_size(self) -> int:
        return self._pool_size

    @property
    def game_format(self) -> str:
        return self._game_format

    @property
    def created_at(self) -> datetime.datetime:
        return self._created_at

    @property
    def pools(self) -> t.List[SealedPool]:
        if self._pools is None:
            self._pools = self._api_client.sealed_session(self._id)._pools
        return self._pools


class LimitedDeck(RemoteModel):

    def __init__(
        self,
        deck_id: t.Union[str, int],
        name: str,
        created_at: datetime.datetime,
        deck: Deck,
        client: ApiClient,
    ):
        super().__init__(deck_id, client)
        self._name = name
        self._created_at = created_at
        self._deck = deck

    @property
    def name(self) -> str:
        return self._name

    @property
    def created_at(self) -> datetime.datetime:
        return self._created_at

    @property
    def deck(self) -> Deck:
        return self._deck


class SealedPool(RemoteModel):

    def __init__(
        self,
        pool_id: t.Union[str, int],
        user: User,
        client: ApiClient,
        decks: t.Optional[t.List[LimitedDeck]] = None,
        session: t.Optional[SealedSession] = None,
        pool: t.Optional[Cube] = None,
    ):
        super().__init__(pool_id, client)
        self._user = user
        self._decks = decks
        self._pool = pool
        self._session = session

    def _fetch(self) -> None:
        pool = self._api_client.sealed_pool(self._id)
        self._decks = pool._decks if pool._decks else []
        self._pool = pool._pool
        self._session = pool._session

    @property
    def user(self) -> user:
        return self._user

    @property
    def decks(self) -> t.List[LimitedDeck]:
        if self._decks is None:
            self._fetch()
        return self._decks

    @property
    def pool(self) -> Cube:
        if self._pool is None:
            self._fetch()
        return self._pool

    @property
    def session(self) -> SealedSession:
        if self._session is None:
            self._fetch()
        return self._session
