from __future__ import annotations

import datetime
import threading
import typing as t
from abc import ABC, abstractmethod
from decimal import Decimal
from enum import Enum
from urllib.parse import urlparse

from magiccube.collections.cube import Cube
from magiccube.collections.cubeable import (
    CardboardCubeable,
    Cubeable,
    deserialize_cardboard_cubeable,
    deserialize_cardboard_node_child,
    deserialize_cubeable,
)
from magiccube.collections.infinites import Infinites
from magiccube.collections.laps import TrapCollection
from magiccube.collections.meta import MetaCube
from magiccube.collections.nodecollection import GroupMap, NodeCollection
from magiccube.laps.traps.tree.printingtree import CardboardNodeChild
from magiccube.update.cubeupdate import VerboseCubePatch
from mtgorp.db.database import CardDatabase
from mtgorp.models.collections.deck import Deck
from mtgorp.models.interfaces import Cardboard, Expansion, Printing
from mtgorp.models.serilization.strategies.raw import RawStrategy
from mtgorp.models.tournaments import tournaments as to
from mtgorp.models.tournaments.matches import MatchType
from promise import Promise


T = t.TypeVar("T")
R = t.TypeVar("R")
P = t.TypeVar("P", bound=t.Union[Printing, Cardboard])

DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%S"


class BaseClient(ABC):
    @classmethod
    def parse_host(cls, host: str, scheme: str = "https") -> t.Tuple[str, str]:
        parsed = urlparse(host if "//" in host else "//" + host)
        return parsed.scheme or scheme, parsed.netloc or parsed.path

    @property
    def synchronous(self) -> BaseClient:
        return self

    @property
    @abstractmethod
    def scheme(self) -> str:
        pass

    @property
    @abstractmethod
    def host(self) -> str:
        pass

    @property
    @abstractmethod
    def db(self) -> CardDatabase:
        pass

    @property
    @abstractmethod
    def token(self) -> str:
        pass

    @property
    @abstractmethod
    def user(self) -> t.Optional[User]:
        pass

    @property
    def inflator(self) -> RawStrategy:
        pass


class ApiClient(BaseClient):
    def __init__(
        self,
        host: str,
        db: CardDatabase,
        *,
        scheme: str = "https",
        token: t.Optional[str] = None,
        verify_ssl: bool = True,
    ):
        self._scheme, self._host = self.parse_host(host, scheme)
        self._db = db
        self._token = token
        self._user = None
        self._inflator: t.Optional[RawStrategy] = None
        self._verify_ssl = verify_ssl

        self._user_lock = threading.Lock()

    @property
    def scheme(self) -> str:
        return self._scheme

    @property
    def host(self) -> str:
        return self._host

    @property
    def db(self) -> CardDatabase:
        return self._db

    @property
    def token(self) -> str:
        with self._user_lock:
            return self._token

    @token.setter
    def token(self, value: str) -> None:
        with self._user_lock:
            self._token = value

    @property
    def user(self) -> t.Optional[User]:
        with self._user_lock:
            return self._user

    @property
    def inflator(self) -> RawStrategy:
        if self._inflator is None:
            self._inflator = RawStrategy(self._db)
        return self._inflator

    @abstractmethod
    def download_db_from_remote(self, target: t.Union[t.BinaryIO, str]) -> None:
        pass

    @abstractmethod
    def report_error(self, error: str, traceback: str) -> None:
        pass

    @abstractmethod
    def login(self, username: str, password: str) -> str:
        pass

    @abstractmethod
    def logout(self) -> None:
        pass

    @abstractmethod
    def db_info(self) -> DbInfo:
        pass

    @abstractmethod
    def min_client_version(self) -> str:
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
        limit=10,
        order_by: str = "name",
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
        sort_key: str = "created_at",
        ascending: bool = False,
    ) -> PaginatedResponse[LimitedSession]:
        pass

    @abstractmethod
    def limited_pool(self, pool_id: t.Union[str, int]) -> LimitedPool:
        pass

    @abstractmethod
    def limited_deck(self, deck_id: t.Union[str, int]) -> LimitedDeck:
        pass

    @abstractmethod
    def upload_limited_deck(self, pool_id: t.Union[str, int], name: str, deck: Deck) -> LimitedDeck:
        pass

    @abstractmethod
    def tournament(self, tournament_id: t.Union[str, int]) -> Tournament:
        pass

    @abstractmethod
    def scheduled_match(self, match_id: t.Union[str, int]) -> ScheduledMatch:
        pass

    @abstractmethod
    def scheduled_matches(
        self,
        user: t.Union[str, int, User],
        offset: int = 0,
        limit: int = 10,
    ) -> PaginatedResponse[ScheduledMatch]:
        pass

    @abstractmethod
    def rating_history_for_cardboard_cubeable(
        self,
        release_id: t.Union[str, int],
        cubeable: t.Union[str, CardboardCubeable],
    ) -> t.Sequence[RatingPoint]:
        pass

    @abstractmethod
    def rating_history_for_node(
        self,
        release_id: t.Union[str, int],
        node: t.Union[str, CardboardNodeChild],
    ) -> t.Sequence[NodeRatingPoint]:
        pass

    @abstractmethod
    def ratings(self, ratings_id: t.Union[str, int]) -> RatingMap:
        pass

    @abstractmethod
    def ratings_for_versioned_cube(self, cube_id: t.Union[str, int]) -> RatingMap:
        pass

    @abstractmethod
    def ratings_for_release(self, release_id: t.Union[str, int]) -> RatingMap:
        pass


class AsyncClient(BaseClient):
    @abstractmethod
    def download_db_from_remote(self, target: t.Union[t.BinaryIO, str]) -> Promise[None]:
        pass

    @abstractmethod
    def report_error(self, error: str, traceback: str) -> Promise[None]:
        pass

    @abstractmethod
    def login(self, username: str, password: str) -> Promise[str]:
        pass

    @abstractmethod
    def logout(self) -> None:
        pass

    @abstractmethod
    def db_info(self) -> Promise[DbInfo]:
        pass

    @abstractmethod
    def min_client_version(self) -> Promise[str]:
        pass

    @abstractmethod
    def release(self, release: t.Union[CubeRelease, str, int]) -> Promise[CubeRelease]:
        pass

    @abstractmethod
    def versioned_cubes(
        self,
        offset: int = 0,
        limit: int = 10,
        cached: bool = True,
    ) -> Promise[StaticPaginationResult[VersionedCube]]:
        pass

    @abstractmethod
    def versioned_cube(self, versioned_cube_id: t.Union[str, int]) -> Promise[VersionedCube]:
        pass

    @abstractmethod
    def patch(self, patch_id: t.Union[str, int]) -> Promise[PatchModel]:
        pass

    @abstractmethod
    def patches(
        self,
        versioned_cube: t.Union[VersionedCube, int, str],
        offset: int = 0,
        limit: int = 10,
    ) -> Promise[StaticPaginationResult[PatchModel]]:
        pass

    @abstractmethod
    def preview_patch(self, patch: t.Union[PatchModel, int, str]) -> Promise[MetaCube]:
        pass

    @abstractmethod
    def verbose_patch(self, patch: t.Union[PatchModel, int, str]) -> Promise[VerboseCubePatch]:
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
        limit=10,
        order_by: str = "name",
        descending: bool = False,
        search_target: t.Type[P] = Printing,
    ) -> Promise[StaticPaginationResult[P]]:
        pass

    @abstractmethod
    def limited_session(self, session_id: t.Union[str, int]) -> Promise[LimitedSession]:
        pass

    @abstractmethod
    def limited_sessions(
        self,
        offset: int = 0,
        limit: int = 10,
        *,
        filters: t.Optional[t.Mapping[str, t.Any]] = None,
        sort_key: str = "created_at",
        ascending: bool = False,
    ) -> Promise[StaticPaginationResult[LimitedSession]]:
        pass

    @abstractmethod
    def limited_pool(self, pool_id: t.Union[str, int]) -> Promise[LimitedPool]:
        pass

    @abstractmethod
    def limited_deck(self, deck_id: t.Union[str, int]) -> Promise[LimitedDeck]:
        pass

    @abstractmethod
    def upload_limited_deck(self, pool_id: t.Union[str, int], name: str, deck: Deck) -> Promise[LimitedDeck]:
        pass

    @abstractmethod
    def tournament(self, tournament_id: t.Union[str, int]) -> Promise[Tournament]:
        pass

    @abstractmethod
    def scheduled_match(self, match_id: t.Union[str, int]) -> Promise[ScheduledMatch]:
        pass

    @abstractmethod
    def scheduled_matches(
        self,
        user: t.Union[str, int, User],
        offset: int = 0,
        limit: int = 10,
    ) -> Promise[PaginatedResponse[ScheduledMatch]]:
        pass

    @abstractmethod
    def rating_history_for_cardboard_cubeable(
        self,
        release_id: t.Union[str, int],
        cubeable: t.Union[str, CardboardCubeable],
    ) -> Promise[t.Sequence[RatingPoint]]:
        pass

    @abstractmethod
    def rating_history_for_node(
        self,
        release_id: t.Union[str, int],
        node: t.Union[str, CardboardNodeChild],
    ) -> Promise[t.Sequence[NodeRatingPoint]]:
        pass

    @abstractmethod
    def ratings(self, ratings_id: t.Union[str, int]) -> Promise[RatingMap]:
        pass

    @abstractmethod
    def ratings_for_versioned_cube(self, cube_id: t.Union[str, int]) -> Promise[RatingMap]:
        pass

    @abstractmethod
    def ratings_for_release(self, release_id: t.Union[str, int]) -> Promise[RatingMap]:
        pass


class PaginatedResponse(t.Sequence[R]):
    @property
    @abstractmethod
    def hits(self) -> int:
        pass

    @abstractmethod
    def __getitem__(self, index) -> R:
        pass

    @abstractmethod
    def __iter__(self) -> t.Iterator[R]:
        pass

    @abstractmethod
    def __contains__(self, item) -> bool:
        pass

    @abstractmethod
    def __len__(self):
        pass


class StaticPaginationResult(PaginatedResponse[R]):
    def __init__(
        self,
        items: t.Sequence[R],
        hits: int,
        offset: int,
        limit: int,
    ):
        self._items = items
        self._hits = hits
        self._offset = offset
        self._limit = limit

    @property
    def hits(self) -> int:
        return self._hits

    @property
    def offset(self) -> int:
        return self._offset

    @property
    def limit(self) -> int:
        return self._limit

    def __getitem__(self, index) -> R:
        return self._items[index]

    def __iter__(self) -> t.Iterator[R]:
        return self._items.__iter__()

    def __contains__(self, item) -> bool:
        return item in self._items

    def __len__(self):
        return self._items.__len__()

    def __repr__(self):
        return "{}({}, {}, {}, {})".format(
            self.__class__.__name__,
            self._hits,
            self._offset,
            self._limit,
            self._items,
        )


class DynamicPaginatedResponse(PaginatedResponse[R]):
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

        self._count = response["count"]
        self._items: t.List[t.Optional[R]] = [None for _ in range(self._count)]
        items = list(map(serializer, response["results"]))
        self._items[offset : offset + len(items)] = items

    @property
    def hits(self) -> int:
        return self._count

    def _fetch_page(self, index: int) -> None:
        for offset_index, item in enumerate(
            map(
                self._serializer,
                self._endpoint(index, self._limit)["results"],
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

    def __len__(self) -> int:
        return self._count

    def _repr_iter(self) -> t.Iterator[str]:
        in_none = False
        for item in self._items:
            if item is None:
                if in_none:
                    continue
                in_none = True
                yield "..."
            else:
                in_none = False
                yield str(item)

    def __repr__(self):
        return "{}({}, [{}])".format(self.__class__.__name__, self._count, ", ".join(self._repr_iter()))


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
        raise NotImplementedError()

    def __hash__(self) -> int:
        return hash(self._id)

    def __eq__(self, other) -> bool:
        return isinstance(other, self.__class__) and self._id == other._id

    def __repr__(self):
        return "{}({})".format(
            self.__class__.__name__,
            self._id,
        )


class DbInfo(object):
    _datetime_format = "%Y-%m-%dT%H:%M:%S"

    def __init__(
        self,
        created_at: datetime.datetime,
        json_updated_at: datetime.datetime,
        last_expansion_name: str,
        checksum: str,
    ):
        self._created_at = created_at
        self._json_updated_at = json_updated_at
        self._last_expansion_name = last_expansion_name
        self._checksum = checksum

    @property
    def created_at(self) -> datetime.datetime:
        return self._created_at

    @property
    def json_updated_at(self) -> datetime.datetime:
        return self._json_updated_at

    @property
    def last_expansion_name(self) -> str:
        return self._last_expansion_name

    @property
    def checksum(self) -> str:
        return self._checksum

    @classmethod
    def deserialize(cls, remote: t.Mapping[str, t.Any]) -> DbInfo:
        return cls(
            created_at=datetime.datetime.strptime(remote["created_at"], cls._datetime_format),
            json_updated_at=datetime.datetime.strptime(remote["json_updated_at"], cls._datetime_format),
            last_expansion_name=remote["last_expansion_name"],
            checksum=remote["checksum"],
        )


class User(RemoteModel):
    def __init__(self, model_id: t.Union[str, int], username: str, client: ApiClient):
        super().__init__(model_id, client)
        self._username = username

    @classmethod
    def deserialize(cls, remote: t.Any, client: ApiClient) -> User:
        return cls(
            model_id=remote["id"],
            username=remote["username"],
            client=client,
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
        client: ApiClient,
        releases: t.Optional[t.List[CubeRelease]] = None,
    ):
        super().__init__(model_id, client)
        self._name = name
        self._created_at = created_at
        self._description = description
        self._releases = releases

        self._patches: t.Optional[PaginatedResponse[PatchModel]] = None

    def _fetch(self) -> None:
        remote = self._api_client.synchronous.versioned_cube(self.id)
        self._releases = remote._releases

    @classmethod
    def deserialize(cls, remote: t.Any, client: ApiClient) -> VersionedCube:
        return cls(
            model_id=remote["id"],
            name=remote["name"],
            created_at=datetime.datetime.strptime(remote["created_at"], DATETIME_FORMAT),
            description=remote["description"],
            releases=[CubeRelease.deserialize(release, client) for release in remote["releases"]]
            if "releases" in remote
            else None,
            client=client,
        )

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
        if self._releases is None:
            self._fetch()
        return self._releases

    @property
    def latest_release(self) -> t.Optional[CubeRelease]:
        if not self._releases:
            return None
        return self._releases[-1]

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
        versioned_cube: t.Optional[VersionedCube] = None,
        constrained_nodes: t.Optional[NodeCollection] = None,
        group_map: t.Optional[GroupMap] = None,
        infinites: t.Optional[Infinites] = None,
    ):
        super().__init__(model_id, client)
        self._created_at = created_at
        self._name = name
        self._intended_size = intended_size
        self._cube = cube
        self._versioned_cube = versioned_cube
        self._constrained_nodes = constrained_nodes
        self._group_map = group_map
        self._infinites = infinites

    def _fetch(self) -> None:
        release = self._api_client.synchronous.release(self)
        self._created_at = release._created_at
        self._intended_size = release._intended_size
        self._cube = release._cube
        self._constrained_nodes = release._constrained_nodes
        self._group_map = release._group_map
        self._versioned_cube = release._versioned_cube

    @classmethod
    def deserialize(cls, remote: t.Any, client: ApiClient) -> CubeRelease:
        strategy = RawStrategy(client.db)
        return cls(
            model_id=remote["id"],
            created_at=(
                datetime.datetime.strptime(remote["created_at"], DATETIME_FORMAT) if "created_at" in remote else None
            ),
            name=remote["name"],
            intended_size=remote.get("intended_size"),
            cube=(strategy.deserialize(Cube, remote["cube"]) if "cube" in remote else None),
            versioned_cube=(
                VersionedCube.deserialize(remote["versioned_cube"], client) if "versioned_cube" in remote else None
            ),
            constrained_nodes=(
                strategy.deserialize(
                    NodeCollection,
                    remote["constrained_nodes"]["constrained_nodes"],
                )
                if "constrained_nodes" in remote
                else None
            ),
            group_map=(
                strategy.deserialize(
                    GroupMap,
                    remote["constrained_nodes"]["group_map"],
                )
                if "constrained_nodes" in remote
                else None
            ),
            infinites=(
                strategy.deserialize(
                    Infinites,
                    remote["infinites"],
                )
                if "infinites" in remote
                else None
            ),
            client=client,
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

    @property
    def versioned_cube(self) -> VersionedCube:
        if self._versioned_cube is None:
            self._fetch()
        return self._versioned_cube

    @property
    def constrained_nodes(self) -> NodeCollection:
        if self._constrained_nodes is None:
            self._fetch()
        return self._constrained_nodes

    @property
    def group_map(self) -> GroupMap:
        if self._group_map is None:
            self._fetch()
        return self._group_map

    @property
    def infinites(self) -> Infinites:
        if self._infinites is None:
            self._fetch()
        return self._infinites


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
        _type = _booster_specification_map[remote["type"]]
        return _type(
            model_id=remote["id"],
            amount=remote["amount"],
            client=client,
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
        client: ApiClient,
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
            "release": CubeRelease.deserialize(remote["release"], client),
            "size": remote["size"],
            "allow_intersection": remote["allow_intersection"],
            "allow_repeat": remote["allow_repeat"],
        }


class ExpansionBoosterSpecification(BoosterSpecification):
    def __init__(self, model_id: t.Union[str, int], amount: int, expansion: Expansion, client: ApiClient):
        super().__init__(model_id, amount, client)
        self._expansion = expansion

    @property
    def expansion(self) -> Expansion:
        return self._expansion

    @classmethod
    def deserialize_values(cls, remote: t.Any, client: ApiClient) -> t.Mapping[str, t.Any]:
        return {
            "expansion": client.db.expansions[remote["expansion_code"]],
        }


class AllCardsBoosterSpecification(BoosterSpecification):
    def __init__(self, model_id: t.Union[str, int], amount: int, respect_printings: bool, client: ApiClient):
        super().__init__(model_id, amount, client)
        self._respect_printings = respect_printings

    @property
    def respect_printings(self) -> bool:
        return self._respect_printings

    @classmethod
    def deserialize_values(cls, remote: t.Any, client: ApiClient) -> t.Mapping[str, t.Any]:
        return {
            "respect_printings": remote["respect_printings"],
        }


class ChaosBoosterSpecification(BoosterSpecification):
    def __init__(
        self,
        model_id: t.Union[str, int],
        amount: int,
        same: bool,
        client: ApiClient,
    ):
        super().__init__(model_id, amount, client)
        self._same = same

    @property
    def same(self) -> bool:
        return self._same

    @classmethod
    def deserialize_values(cls, remote: t.Any, client: ApiClient) -> t.Mapping[str, t.Any]:
        return {
            "same": remote["same"],
        }


_booster_specification_map = {
    "CubeBoosterSpecification": CubeBoosterSpecification,
    "ExpansionBoosterSpecification": ExpansionBoosterSpecification,
    "AllCardsBoosterSpecification": AllCardsBoosterSpecification,
    "ChaosBoosterSpecification": ChaosBoosterSpecification,
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
            model_id=remote["id"],
            booster_specifications=[
                BoosterSpecification.deserialize(booster_specification, client)
                for booster_specification in remote["specifications"]
            ],
            client=client,
        )


class LimitedSession(RemoteModel):
    class LimitedSessionState(Enum):
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
        state: LimitedSessionState,
        open_decks: bool,
        open_pools: bool,
        created_at: datetime.datetime,
        pool_specification: PoolSpecification,
        infinites: Infinites,
        client: ApiClient,
        pools: t.Optional[t.List[LimitedPool]] = None,
    ):
        super().__init__(model_id, client)
        self._name = name
        self._game_type = game_type
        self._game_format = game_format
        self._players = players
        self._state = state
        self._open_decks = open_decks
        self._open_pools = open_pools
        self._created_at = created_at
        self._pool_specification = pool_specification
        self._infinites = infinites
        self._pools = pools

    @classmethod
    def deserialize(cls, remote: t.Any, client: ApiClient) -> LimitedSession:
        return cls(
            model_id=remote["id"],
            name=remote["name"],
            game_type=remote["game_type"],
            players={User.deserialize(player, client) for player in remote["players"]},
            state=cls.LimitedSessionState[remote["state"]],
            open_decks=remote["open_decks"],
            open_pools=remote["open_pools"],
            game_format=remote["format"],
            created_at=datetime.datetime.strptime(remote["created_at"], DATETIME_FORMAT),
            pool_specification=PoolSpecification.deserialize(remote["pool_specification"], client),
            infinites=RawStrategy(client.db).deserialize(Infinites, remote["infinites"]),
            client=client,
            pools=[LimitedPool.deserialize(pool, client) for pool in remote["pools"]] if "pools" in remote else None,
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
    def state(self) -> LimitedSessionState:
        return self._state

    @property
    def open_decks(self) -> bool:
        return self._open_decks

    @property
    def open_pools(self) -> bool:
        return self._open_pools

    @property
    def created_at(self) -> datetime.datetime:
        return self._created_at

    @property
    def pool_specification(self) -> PoolSpecification:
        return self._pool_specification

    @property
    def infinites(self) -> Infinites:
        return self._infinites

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
        user: User,
        client: ApiClient,
        deck: t.Optional[Deck],
    ):
        super().__init__(deck_id, client)
        self._name = name
        self._created_at = created_at
        self._deck = deck
        self._user = user

    @classmethod
    def deserialize(cls, remote: t.Any, client: ApiClient) -> LimitedDeck:
        return cls(
            deck_id=remote["id"],
            name=remote["name"],
            created_at=datetime.datetime.strptime(remote["created_at"], DATETIME_FORMAT),
            deck=RawStrategy(client.db).deserialize(Deck, remote["deck"]) if "deck" in remote else None,
            user=User.deserialize(remote["user"], client=client),
            client=client,
        )

    @property
    def name(self) -> str:
        return self._name

    @property
    def created_at(self) -> datetime.datetime:
        return self._created_at

    @property
    def deck(self) -> Deck:
        if self._deck is None:
            self._deck = self._api_client.limited_deck(self._id).deck
        return self._deck

    @property
    def user(self) -> User:
        return self._user


class LimitedPool(RemoteModel):
    def __init__(
        self,
        pool_id: t.Union[str, int],
        user: User,
        client: ApiClient,
        decks: t.Sequence[t.Union[LimitedDeck, int]] = (),
        session: t.Optional[LimitedSession] = None,
        pool: t.Optional[Cube] = None,
    ):
        super().__init__(pool_id, client)
        self._user = user
        self._decks = decks
        self._pool = pool
        self._session = session

        self._fetched_full: bool = False

    @classmethod
    def deserialize(cls, remote: t.Any, client: ApiClient) -> LimitedPool:
        return cls(
            pool_id=remote["id"],
            user=User.deserialize(remote["user"], client),
            client=client,
            decks=[
                deck if isinstance(deck, int) else LimitedDeck.deserialize(deck, client) for deck in remote["decks"]
            ],
            session=LimitedSession.deserialize(remote["session"], client) if "session" in remote else None,
            pool=RawStrategy(client.db).deserialize(Cube, remote["pool"]) if "pool" in remote else None,
        )

    def _fetch(self) -> None:
        pool = self._api_client.synchronous.limited_pool(self._id)
        self._decks = pool._decks
        self._pool = pool._pool
        self._session = pool._session
        self._fetched_full = True

    @property
    def user(self) -> user:
        return self._user

    @property
    def decks(self) -> t.Sequence[LimitedDeck]:
        if self._decks and isinstance(self._decks[0], int) and not self._fetched_full:
            self._fetch()
        return self._decks

    @property
    def deck(self) -> t.Optional[LimitedDeck]:
        return None if not self._decks else self._decks[-1]

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


class Tournament(RemoteModel):
    class TournamentState(Enum):
        ONGOING = 0
        FINISHED = 1
        CANCELED = 2

    def __init__(
        self,
        tournament_id: int,
        state: TournamentState,
        name: str,
        tournament_type: t.Type[to.Tournament],
        match_type: MatchType,
        participants: t.FrozenSet[TournamentParticipant],
        created_at: datetime.datetime,
        client: ApiClient,
        finished_at: t.Optional[datetime.datetime] = None,
        rounds: t.Optional[t.Sequence[TournamentRound]] = None,
    ):
        super().__init__(tournament_id, client)
        self._state = state
        self._name = name
        self._tournament_type = tournament_type
        self._match_type = match_type
        self._participants = participants
        self._created_at = created_at
        self._rounds = rounds
        self._finished_at = finished_at

    @classmethod
    def deserialize(cls, remote: t.Any, client: ApiClient) -> Tournament:
        match_type = MatchType.matches_map[remote["match_type"]["name"]]
        tournament = cls(
            tournament_id=remote["id"],
            state=cls.TournamentState[remote["state"]],
            name=remote["name"],
            tournament_type=to.Tournament.tournaments_map[remote["tournament_type"]],
            match_type=match_type(**match_type.options_schema.deserialize_raw(remote["match_type"])),
            participants=frozenset(
                TournamentParticipant.deserialize(
                    participant,
                    client=client,
                )
                for participant in remote["participants"]
            ),
            created_at=datetime.datetime.strptime(remote["created_at"], DATETIME_FORMAT),
            rounds=[
                TournamentRound.deserialize(
                    _round,
                    client=client,
                )
                for _round in remote["rounds"]
            ]
            if isinstance(remote.get("rounds"), list)
            else None,
            finished_at=(
                datetime.datetime.strptime(remote["finished_at"], DATETIME_FORMAT) if remote["finished_at"] else None
            ),
            client=client,
        )

        if tournament._rounds:
            for _round in tournament._rounds:
                for match in _round.matches:
                    match._tournament = tournament

        return tournament

    @property
    def state(self) -> TournamentState:
        return self._state

    @property
    def name(self) -> str:
        return self._name

    @property
    def tournament_type(self) -> t.Type[to.Tournament]:
        return self._tournament_type

    @property
    def match_type(self) -> MatchType:
        return self._match_type

    @property
    def participants(self) -> t.FrozenSet[TournamentParticipant]:
        return self._participants

    @property
    def created_at(self) -> datetime.datetime:
        return self._created_at

    @property
    def rounds(self) -> t.Sequence[TournamentRound]:
        if self._rounds is None:
            self._rounds = self._api_client.tournament(self._id)._rounds
        return self._rounds

    @property
    def finished_at(self) -> t.Optional[datetime.datetime]:
        return self._finished_at


class TournamentParticipant(RemoteModel):
    def __init__(
        self,
        participant_id: int,
        deck: LimitedDeck,
        player: t.Optional[User],
        seed: float,
        client: ApiClient,
    ):
        super().__init__(participant_id, client)
        self._deck = deck
        self._player = player
        self._seed = seed

    @classmethod
    def deserialize(cls, remote: t.Any, client: ApiClient) -> TournamentParticipant:
        return cls(
            participant_id=remote["id"],
            deck=LimitedDeck.deserialize(remote["deck"], client=client),
            player=User.deserialize(
                remote["player"],
                client=client,
            )
            if remote.get("player")
            else None,
            seed=remote["seed"],
            client=client,
        )

    @property
    def deck(self) -> LimitedDeck:
        return self._deck

    @property
    def player(self) -> t.Optional[User]:
        return self._player

    @property
    def seed(self) -> float:
        return self._seed

    @property
    def tag_line(self):
        if self._player is None:
            return f"{self._deck.name} ({self._deck.user.username}"
        return f"{self._player.username} - {self._deck.name}"


class TournamentRound(RemoteModel):
    def __init__(
        self,
        round_id: int,
        index: int,
        matches: t.FrozenSet[ScheduledMatch],
        client: ApiClient,
    ):
        super().__init__(round_id, client)
        self._index = index
        self._matches = matches

    @classmethod
    def deserialize(cls, remote: t.Any, client: ApiClient) -> TournamentRound:
        return cls(
            round_id=remote["id"],
            index=remote["index"],
            matches=frozenset(
                ScheduledMatch.deserialize(
                    match,
                    client=client,
                )
                for match in remote["matches"]
            ),
            client=client,
        )

    @property
    def matches(self) -> t.FrozenSet[ScheduledMatch]:
        return self._matches


class ScheduledMatch(RemoteModel):
    def __init__(
        self,
        match_id: int,
        seats: t.FrozenSet[ScheduledSeat],
        result: t.Optional[MatchResult],
        client: ApiClient,
        tournament: t.Optional[Tournament] = None,
        tournament_round: t.Optional[int] = None,
    ):
        super().__init__(match_id, client)
        self._seats = seats
        self._result = result
        self._tournament = tournament
        self._round = tournament_round

    @classmethod
    def deserialize(cls, remote: t.Any, client: ApiClient) -> ScheduledMatch:
        return cls(
            match_id=remote["id"],
            seats=frozenset(
                ScheduledSeat.deserialize(
                    seat,
                    client=client,
                )
                for seat in remote["seats"]
            ),
            result=MatchResult.deserialize(
                remote["result"],
                client=client,
            )
            if remote.get("result")
            else None,
            tournament=Tournament.deserialize(
                remote["tournament"],
                client=client,
            )
            if "tournament" in remote
            else None,
            tournament_round=remote.get("round"),
            client=client,
        )

    @property
    def tournament(self) -> Tournament:
        if self._tournament is None:
            self._tournament = self._api_client.scheduled_match(self._id).tournament
        return self._tournament

    @property
    def seats(self) -> t.FrozenSet[ScheduledSeat]:
        return self._seats

    @property
    def result(self) -> t.Optional[MatchResult]:
        return self._result

    @property
    def round(self) -> int:
        if self._round is None:
            c = 0
            for _round in self.tournament.rounds:
                if self in _round.matches:
                    break
                c += 1
            self._round = c
        return self._round


class MatchResult(RemoteModel):
    def __init__(
        self,
        result_id: int,
        draws: int,
        client: ApiClient,
    ):
        super().__init__(result_id, client)
        self._draws = draws

    @classmethod
    def deserialize(cls, remote: t.Any, client: ApiClient) -> MatchResult:
        return cls(
            result_id=remote["id"],
            draws=remote["draws"],
            client=client,
        )

    @property
    def draws(self) -> int:
        return self._draws


class ScheduledSeat(RemoteModel):
    def __init__(
        self,
        seat_id: int,
        participant: TournamentParticipant,
        result: t.Optional[SeatResult],
        client: ApiClient,
    ):
        super().__init__(seat_id, client)
        self._participant = participant
        self._result = result

    @classmethod
    def deserialize(cls, remote: t.Any, client: ApiClient) -> ScheduledSeat:
        return cls(
            seat_id=remote["id"],
            participant=TournamentParticipant.deserialize(
                remote["participant"],
                client=client,
            ),
            result=SeatResult.deserialize(
                remote["result"],
                client=client,
            )
            if remote.get("result")
            else None,
            client=client,
        )

    @property
    def participant(self) -> TournamentParticipant:
        return self._participant

    @property
    def result(self) -> t.Optional[SeatResult]:
        return self._result


class SeatResult(RemoteModel):
    def __init__(
        self,
        result_id: int,
        wins: int,
        client: ApiClient,
    ):
        super().__init__(result_id, client)
        self._wins = wins

    @classmethod
    def deserialize(cls, remote: t.Any, client: ApiClient) -> SeatResult:
        return cls(
            result_id=remote["id"],
            wins=remote["wins"],
            client=client,
        )

    @property
    def wins(self) -> int:
        return self._wins


class RatingPoint(RemoteModel):
    def __init__(
        self,
        rating_id: int,
        rating: int,
        rating_map: RatingMap,
        client: ApiClient,
    ):
        super().__init__(rating_id, client)
        self._rating = rating
        self._rating_map = rating_map

    @property
    def rating(self) -> int:
        return self._rating

    @property
    def rating_map(self) -> RatingMap:
        return self._rating_map

    @classmethod
    def deserialize(cls, remote: t.Any, client: ApiClient) -> RatingPoint:
        return cls(
            rating_id=remote["id"],
            rating=remote["rating"],
            rating_map=RatingMap.deserialize(remote["rating_map"], client),
            client=client,
        )


class NodeRatingPoint(RatingPoint):
    def __init__(
        self,
        rating_id: int,
        rating: int,
        weight: Decimal,
        rating_map: RatingMap,
        client: ApiClient,
    ):
        super().__init__(rating_id, rating, rating_map, client)
        self._weight = weight

    @property
    def weight(self) -> Decimal:
        return self._weight

    @property
    def rating_component(self) -> int:
        return self._rating

    @classmethod
    def deserialize(cls, remote: t.Any, client: ApiClient) -> NodeRatingPoint:
        return cls(
            rating_id=remote["id"],
            rating=remote["rating_component"],
            weight=Decimal(remote["weight"]),
            rating_map=RatingMap.deserialize(remote["rating_map"], client),
            client=client,
        )


class CardboardCubeableRating(RemoteModel):
    def __init__(
        self,
        rating_id: int,
        cardboard_cubeable: CardboardCubeable,
        example_cubeable: Cubeable,
        rating: int,
        client: ApiClient,
    ):
        super().__init__(rating_id, client)
        self._cardboard_cubeable = cardboard_cubeable
        self._example_cubeable = example_cubeable
        self._rating = rating

    @property
    def cardboard_cubeable(self) -> CardboardCubeable:
        return self._cardboard_cubeable

    @property
    def example_cubeable(self) -> Cubeable:
        return self._example_cubeable

    @property
    def rating(self) -> int:
        return self._rating

    @classmethod
    def deserialize(cls, remote: t.Any, client: ApiClient) -> CardboardCubeableRating:
        return cls(
            rating_id=remote["id"],
            cardboard_cubeable=deserialize_cardboard_cubeable(remote["cardboard_cubeable"], client.inflator),
            example_cubeable=deserialize_cubeable(remote["example_cubeable"], client.inflator),
            rating=remote["rating"],
            client=client,
        )


class NodeRatingComponent(RemoteModel):
    def __init__(
        self,
        rating_id: int,
        node: CardboardNodeChild,
        rating_component: int,
        weight: Decimal,
        client: ApiClient,
    ):
        super().__init__(rating_id, client)
        self._node = node
        self._rating_component = rating_component
        self._weight = weight

    @property
    def node(self) -> CardboardNodeChild:
        return self._node

    @property
    def weight(self) -> Decimal:
        return self._weight

    @property
    def rating_component(self) -> int:
        return self._rating_component

    @property
    def rating(self) -> int:
        return self._rating_component

    @classmethod
    def deserialize(cls, remote: t.Any, client: ApiClient) -> NodeRatingComponent:
        return cls(
            rating_id=remote["id"],
            node=deserialize_cardboard_node_child(remote["node"], client.inflator),
            rating_component=remote["rating_component"],
            weight=Decimal(remote["weight"]),
            client=client,
        )


class RatingMap(RemoteModel):
    def __init__(
        self,
        map_id: int,
        release: CubeRelease,
        created_at: datetime.datetime,
        client: ApiClient,
        ratings: t.Optional[t.Sequence[CardboardCubeableRating]] = None,
        node_components_ratings: t.Optional[t.Sequence[NodeRatingComponent]] = None,
    ):
        super().__init__(map_id, client)
        self._release = release
        self._ratings = ratings
        self._node_ratings = node_components_ratings
        self._created_at = created_at

        self._map: t.Optional[t.Mapping[CardboardCubeable, CardboardCubeableRating]] = None

    def _inflate(self) -> None:
        remote = self._api_client.synchronous.ratings(self._id)
        self._ratings = remote._ratings
        self._node_ratings = remote._node_ratings

    def inflate(self) -> None:
        if self._ratings is None:
            self._inflate()

    @property
    def release(self) -> CubeRelease:
        return self._release

    @property
    def ratings(self) -> t.Sequence[CardboardCubeableRating]:
        self.inflate()
        return self._ratings

    @property
    def node_component_ratings(self) -> t.Sequence[NodeRatingComponent]:
        self.inflate()
        return self._node_ratings

    @property
    def created_at(self) -> datetime.datetime:
        return self._created_at

    def __getitem__(self, item: CardboardCubeable) -> CardboardCubeableRating:
        if self._map is None:
            self.inflate()
            self._map = {rating.cardboard_cubeable: rating for rating in self._ratings}
        return self._map[item]

    def get(self, item: CardboardCubeable, default: T = None) -> t.Union[CardboardCubeableRating, T]:
        if self._map is None:
            self.inflate()
            self._map = {rating.cardboard_cubeable: rating for rating in self._ratings}
        return self._map.get(item, default)

    @classmethod
    def deserialize(cls, remote: t.Any, client: ApiClient) -> RatingMap:
        return cls(
            map_id=remote["id"],
            release=CubeRelease.deserialize(remote["release"], client),
            ratings=[
                CardboardCubeableRating.deserialize(cardboard_cubeable, client)
                for cardboard_cubeable in remote["ratings"]
            ]
            if "ratings" in remote
            else None,
            node_components_ratings=[
                NodeRatingComponent.deserialize(node_rating, client)
                for node_rating in remote["node_rating_components"]
            ]
            if "node_rating_components" in remote
            else None,
            created_at=datetime.datetime.strptime(remote["created_at"], DATETIME_FORMAT),
            client=client,
        )
