from __future__ import annotations

import typing as t

from abc import ABC, abstractmethod
import datetime
from enum import Enum

from mtgorp.models.persistent.expansion import Expansion
from mtgorp.models.serilization.strategies.raw import RawStrategy
from mtgorp.db.database import CardDatabase
from mtgorp.models.collections.deck import Deck
from mtgorp.models.persistent.cardboard import Cardboard
from mtgorp.models.persistent.printing import Printing

from magiccube.collections.cube import Cube
from magiccube.collections.laps import TrapCollection
from magiccube.collections.meta import MetaCube
from magiccube.update.cubeupdate import VerboseCubePatch


R = t.TypeVar('R')
P = t.TypeVar('P', bound = t.Union[Printing, Cardboard])

DATETIME_FORMAT = '%Y-%m-%dT%H:%M:%S'


class ApiClient(ABC):

    def __init__(self, host: str, db: CardDatabase, *, token: t.Optional[str] = None):
        self._host = host
        self._db = db
        self._token = token
        self._user = None

    @property
    def host(self) -> str:
        return self._host

    @property
    def db(self) -> CardDatabase:
        return self._db

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
    def versioned_cubes(
        self,
        offset: int = 0,
        limit: int = 10,
        cached: bool = True,
    ) -> PaginatedResponse[VersionedCube]:
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
    def limited_session(self, session_id: t.Union[str, int]) -> LimitedSession:
        pass

    @abstractmethod
    def limited_sessions(
        self,
        offset: int = 0,
        limit: int = 10,
        *,
        filters: t.Optional[t.Mapping[str, t.Any]] = None,
        sort_key: str = 'created_at',
        ascending: bool = False,
    ) -> PaginatedResponse[LimitedSession]:
        pass

    @abstractmethod
    def limited_pool(self, pool_id: t.Union[str, int]) -> LimitedPool:
        pass

    @abstractmethod
    def upload_limited_deck(self, pool_id: t.Union[str, int], name: str, deck: Deck) -> LimitedDeck:
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

    # @abstractmethod  Not yet, too lazy to migrate
    @classmethod
    def deserialize(cls, remote: t.Any, client: ApiClient) -> RemoteModel:
        raise NotImplemented()

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

    @classmethod
    def deserialize(cls, remote: t.Any, client: ApiClient) -> User:
        return cls(
            model_id = remote['id'],
            username = remote['username'],
            client = client,
        )

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
        name: str,
        client: ApiClient,
        created_at: t.Optional[datetime.datetime] = None,
        intended_size: t.Optional[int] = None,
        cube: t.Optional[Cube] = None,
    ):
        super().__init__(model_id, client)
        self._created_at = created_at
        self._name = name
        self._intended_size = intended_size
        self._cube = cube

    def _fetch(self) -> None:
        release = self._api_client.release(self)
        self._created_at = release.created_at
        self._intended_size = release.intended_size
        self._cube = release.cube

    @classmethod
    def deserialize(cls, remote: t.Any, client: ApiClient) -> CubeRelease:
        return cls(
            model_id = remote['id'],
            created_at = (
                datetime.datetime.strptime(remote['created_at'], DATETIME_FORMAT)
                if 'created_at' in remote else
                None
            ),
            name = remote['name'],
            intended_size = remote.get('intended_size'),
            cube = (
                RawStrategy(client.db).deserialize(
                    Cube,
                    remote['cube']
                )
                if 'cube' in remote else
                None
            ),
            client = client,
        )

    @property
    def created_at(self) -> datetime.datetime:
        if self._created_at is None:
            self._fetch()
        return self._created_at

    @property
    def name(self) -> str:
        return self._name

    @property
    def intended_size(self) -> int:
        if self._intended_size is None:
            self._fetch()
        return self._intended_size

    @property
    def cube(self) -> Cube:
        if self._cube is None:
            self._fetch()
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


class BoosterSpecification(RemoteModel):

    def __init__(self, model_id: t.Union[str, int], amount: int, client: ApiClient):
        super().__init__(model_id, client)
        self._amount = amount

    @property
    def amount(self) -> int:
        return self._amount

    @classmethod
    def deserialize(cls, remote: t.Any, client: ApiClient) -> BoosterSpecification:
        _type = _booster_specification_map[remote['type']]
        return _type(
            model_id = remote['id'],
            amount = remote['amount'],
            client = client,
            **_type.deserialize_values(remote, client),
        )

    @classmethod
    @abstractmethod
    def deserialize_values(cls, remote: t.Any, client: ApiClient) -> t.Mapping[str, t.Any]:
        pass


class CubeBoosterSpecification(BoosterSpecification):

    def __init__(
        self,
        model_id: t.Union[str, int],
        amount: int,
        release: CubeRelease,
        size: int,
        allow_intersection: bool,
        allow_repeat: bool,
        client: ApiClient
    ):
        super().__init__(model_id, amount, client)
        self._release = release
        self._size = size
        self._allow_intersection = allow_intersection
        self._allow_repeat = allow_repeat

    @property
    def release(self) -> CubeRelease:
        return self._release

    @property
    def size(self) -> int:
        return self._size

    @property
    def allow_intersection(self) -> bool:
        return self._allow_intersection

    @property
    def allow_repeat(self) -> bool:
        return self._allow_repeat

    @classmethod
    def deserialize_values(cls, remote: t.Any, client: ApiClient) -> t.Mapping[str, t.Any]:
        return {
            'release': CubeRelease.deserialize(remote['release'], client),
            'size': remote['size'],
            'allow_intersection': remote['allow_intersection'],
            'allow_repeat': remote['allow_repeat'],
        }


class ExpansionBoosterSpecification(BoosterSpecification):

    def __init__(
        self,
        model_id: t.Union[str, int],
        amount: int,
        expansion: Expansion,
        client: ApiClient
    ):
        super().__init__(model_id, amount, client)
        self._expansion = expansion

    @property
    def expansion(self) -> Expansion:
        return self._expansion

    @classmethod
    def deserialize_values(cls, remote: t.Any, client: ApiClient) -> t.Mapping[str, t.Any]:
        return {
            'expansion': client.db.expansions[remote['expansion_code']],
        }


class AllCardsBoosterSpecification(BoosterSpecification):

    def __init__(
        self,
        model_id: t.Union[str, int],
        amount: int,
        respect_printings: bool,
        client: ApiClient
    ):
        super().__init__(model_id, amount, client)
        self._respect_printings = respect_printings

    @property
    def respect_printings(self) -> bool:
        return self._respect_printings

    @classmethod
    def deserialize_values(cls, remote: t.Any, client: ApiClient) -> t.Mapping[str, t.Any]:
        return {
            'respect_printings': remote['respect_printings'],
        }



_booster_specification_map = {
    'CubeBoosterSpecification': CubeBoosterSpecification,
    'ExpansionBoosterSpecification': ExpansionBoosterSpecification,
    'AllCardsBoosterSpecification': AllCardsBoosterSpecification,
}


class PoolSpecification(RemoteModel):

    def __init__(
        self,
        model_id: t.Union[str, int],
        booster_specifications: t.List[BoosterSpecification],
        client: ApiClient,
    ):
        super().__init__(model_id, client)
        self._booster_specifications = booster_specifications

    @property
    def booster_specifications(self) -> t.List[BoosterSpecification]:
        return self._booster_specifications

    @classmethod
    def deserialize(cls, remote: t.Any, client: ApiClient) -> PoolSpecification:
        return cls(
            model_id = remote['id'],
            booster_specifications = [
                BoosterSpecification.deserialize(booster_specification, client)
                for booster_specification in
                remote['specifications']
            ],
            client = client,
        )


class LimitedSession(RemoteModel):
    class SealedSessionState(Enum):
        DECK_BUILDING = 0
        PLAYING = 1
        FINISHED = 2

    def __init__(
        self,
        model_id: t.Union[str, int],
        name: str,
        game_type: str,
        game_format: str,
        players: t.AbstractSet[User],
        state: SealedSessionState,
        created_at: datetime.datetime,
        pool_specification: PoolSpecification,
        client: ApiClient,
        pools: t.Optional[t.List[LimitedPool]] = None,
    ):
        super().__init__(model_id, client)
        self._name = name
        self._game_type = game_type
        self._game_format = game_format
        self._players = players
        self._state = state
        self._created_at = created_at
        self._pool_specification = pool_specification
        self._pools = pools

    @classmethod
    def deserialize(cls, remote: t.Any, client: ApiClient) -> LimitedSession:
        return cls(
            model_id = remote['id'],
            name = remote['name'],
            game_type = remote['game_type'],
            players = {User.deserialize(player, client) for player in remote['players']},
            state = LimitedSession.SealedSessionState[remote['state']],
            game_format = remote['format'],
            created_at = datetime.datetime.strptime(remote['created_at'], DATETIME_FORMAT),
            pool_specification = PoolSpecification.deserialize(remote['pool_specification'], client),
            client = client,
            pools = [
                LimitedPool.deserialize(pool, client)
                for pool in
                remote['pools']
            ] if 'pools' in remote else None
        )

    @property
    def name(self) -> str:
        return self._name

    @property
    def game_type(self) -> str:
        return self._game_type

    @property
    def game_format(self) -> str:
        return self._game_format

    @property
    def players(self) -> t.AbstractSet[User]:
        return self._players

    @property
    def state(self) -> SealedSessionState:
        return self._state

    @property
    def created_at(self) -> datetime.datetime:
        return self._created_at

    @property
    def pool_specification(self) -> PoolSpecification:
        return self._pool_specification

    @property
    def pools(self) -> t.List[LimitedPool]:
        if self._pools is None:
            self._pools = self._api_client.limited_session(self._id)._pools
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

    @classmethod
    def deserialize(cls, remote: t.Any, client: ApiClient) -> LimitedDeck:
        return cls(
            deck_id = remote['id'],
            name = remote['name'],
            created_at = datetime.datetime.strptime(remote['created_at'], DATETIME_FORMAT),
            deck = RawStrategy(client.db).deserialize(Deck, remote['deck']),
            client = client,
        )

    @property
    def name(self) -> str:
        return self._name

    @property
    def created_at(self) -> datetime.datetime:
        return self._created_at

    @property
    def deck(self) -> Deck:
        return self._deck


class LimitedPool(RemoteModel):

    def __init__(
        self,
        pool_id: t.Union[str, int],
        user: User,
        client: ApiClient,
        decks: t.Optional[t.List[LimitedDeck]] = None,
        session: t.Optional[LimitedSession] = None,
        pool: t.Optional[Cube] = None,
    ):
        super().__init__(pool_id, client)
        self._user = user
        self._decks = decks
        self._pool = pool
        self._session = session

    @classmethod
    def deserialize(cls, remote: t.Any, client: ApiClient) -> LimitedPool:
        return cls(
            pool_id = remote['id'],
            user = User.deserialize(remote['user'], client),
            client = client,
            decks = (
                [LimitedDeck.deserialize(deck, client) for deck in remote['decks']]
                if remote['decks'] and not isinstance(remote['decks'][0], int) else
                None
            ),
            session = LimitedSession.deserialize(remote['session'], client) if 'session' in remote else None,
            pool = RawStrategy(client.db).deserialize(Cube, remote['pool']) if 'pool' in remote else None,
        )

    def _fetch(self) -> None:
        pool = self._api_client.limited_pool(self._id)
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
    def session(self) -> LimitedSession:
        if self._session is None:
            self._fetch()
        return self._session
