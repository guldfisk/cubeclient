from __future__ import annotations

import datetime
import logging
import threading
import typing as t
from abc import abstractmethod, ABCMeta
from concurrent.futures.thread import ThreadPoolExecutor

import requests as r
from promise import Promise

from yeetlong.taskawaiter import TaskAwaiter

from mtgorp.db.database import CardDatabase
from mtgorp.models.collections.deck import Deck
from mtgorp.models.interfaces import Printing
from mtgorp.models.serilization.strategies.jsonid import JsonId
from mtgorp.models.serilization.strategies.raw import RawStrategy

from magiccube.collections.cube import Cube
from magiccube.collections.cubeable import CardboardCubeable
from magiccube.collections.infinites import Infinites
from magiccube.collections.laps import TrapCollection
from magiccube.collections.meta import MetaCube
from magiccube.collections.nodecollection import NodeCollection, GroupMap
from magiccube.laps.traps.tree.printingtree import CardboardNodeChild
from magiccube.update.cubeupdate import VerboseCubePatch

from cubeclient import models
from cubeclient.models import (
    PaginatedResponse, VersionedCube, PatchModel, DistributionPossibility, LimitedPool, P, LimitedSession,
    LimitedDeck, User, CubeRelease, AsyncClient, StaticPaginationResult, R, DynamicPaginatedResponse, DbInfo,
    Tournament, ScheduledMatch, RatingMap, RatingPoint, NodeRatingPoint
)


T = t.TypeVar('T')


def _download_db_from_remote(host: str, target: t.BinaryIO) -> None:
    uri = f'https://{host}/db'
    logging.info(f'Downloading db from {uri}')
    for chunk in r.get(uri, stream = True).iter_content(chunk_size = 1024):
        target.write(chunk)


def download_db_from_remote(host: str, target: t.Union[t.BinaryIO, str]) -> None:
    if isinstance(target, str):
        with open(target, 'wb') as f:
            _download_db_from_remote(host, f)
    else:
        _download_db_from_remote(host, target)


class BaseNativeApiClient(models.ApiClient):
    _DATETIME_FORMAT = '%Y-%m-%dT%H:%M:%S'

    def __init__(
        self,
        host: str,
        db: CardDatabase,
        *,
        scheme: str = 'https',
        token: t.Optional[str] = None,
        verify_ssl: bool = True,
    ):
        super().__init__(host, db, token = token, scheme = scheme, verify_ssl = verify_ssl)

        self._strategy = RawStrategy(db)

        self._versioned_cubes = None

    @classmethod
    @abstractmethod
    def _get_paginated_response(
        cls,
        endpoint: t.Callable[[int, int], t.Any],
        serializer: t.Callable[[t.Any], R],
        offset: int = 0,
        limit: int = 50,
    ) -> PaginatedResponse[R]:
        pass

    def _make_request(
        self,
        endpoint: str,
        method: str = 'GET',
        data: t.Optional[t.Mapping[str, t.Any]] = None,
        stream: bool = False,
        exclude_api: bool = False,
        **kwargs,
    ) -> t.Any:
        if data is None:
            data = {}

        kwargs.setdefault('native', True)

        headers = {}
        if self._token is not None:
            headers.setdefault('Authorization', 'Token ' + self._token)

        url = f'{self._scheme}://{self._host}/{"" if exclude_api else "api/"}{endpoint}{"" if exclude_api else "/"}'

        logging.info('{} {} {}'.format(method, url, kwargs))

        response = r.request(
            method,
            url,
            data = data,
            params = kwargs,
            headers = headers,
            stream = stream,
            verify = self._verify_ssl,
        )
        response.raise_for_status()
        if stream:
            return response
        return response.json()

    def download_db_from_remote(self, target: t.Union[t.BinaryIO, str]) -> None:
        download_db_from_remote(self._host, target)

    def login(self, username: str, password: str) -> str:
        response = self._make_request(
            'auth/login',
            method = 'POST',
            data = {
                'username': username,
                'password': password,
            }
        )
        with self._user_lock:
            self._user = User.deserialize(response['user'], self)
            self._token = response['token']
        return self._token

    def logout(self) -> None:
        with self._user_lock:
            self._user = None
            self._token = None

    def db_info(self) -> DbInfo:
        return DbInfo.deserialize(self._make_request('db-info'))

    def min_client_version(self) -> str:
        return self._make_request('min-supported-client-version')['version']

    def release(self, release: t.Union[models.CubeRelease, str, int]) -> models.CubeRelease:
        return CubeRelease.deserialize(
            self._make_request(
                'cube-releases/{}'.format(
                    release.id
                    if isinstance(release, models.CubeRelease) else
                    release
                )
            ),
            self,
        )

    def _get_versioned_cubes(self, offset: int, limit: int) -> t.List[t.Any]:
        return self._make_request('versioned-cubes', offset = offset, limit = limit)

    def versioned_cube(self, versioned_cube_id: t.Union[str, int]) -> VersionedCube:
        return VersionedCube.deserialize(
            self._make_request(
                f'versioned-cubes/{versioned_cube_id}'
            ),
            self,
        )

    def versioned_cubes(
        self,
        offset: int = 0,
        limit: int = 10,
        cached: bool = True,
    ) -> PaginatedResponse[VersionedCube]:
        if self._versioned_cubes is not None and cached:
            return self._versioned_cubes

        self._versioned_cubes = self._get_paginated_response(
            self._get_versioned_cubes,
            lambda remote: VersionedCube.deserialize(remote, self),
            offset,
            limit,
        )

        return self._versioned_cubes

    def _serialize_patch(self, remote: t.Any) -> PatchModel:
        return PatchModel(
            model_id = remote['id'],
            name = remote['name'],
            created_at = datetime.datetime.strptime(remote['created_at'], self._DATETIME_FORMAT),
            description = remote['description'],
            client = self,
        )

    def _patches(
        self,
        versioned_cube_id: t.Union[int, str],
        offset: int = 0,
        limit: int = 10,
    ) -> t.List[t.Any]:
        return self._make_request(f'versioned-cubes/{versioned_cube_id}/patches', offset = offset, limit = limit)

    def patch(self, patch_id: t.Union[str, int]) -> PatchModel:
        return self._serialize_patch(
            self._make_request(
                f'patches/{patch_id}'
            )
        )

    def patches(
        self,
        versioned_cube: t.Union[VersionedCube, int, str],
        offset: int = 0,
        limit: int = 10,
    ) -> PaginatedResponse[PatchModel]:
        versioned_cube_id = (
            versioned_cube.id
            if isinstance(versioned_cube, VersionedCube) else
            versioned_cube
        )
        return self._get_paginated_response(
            lambda _offset, _limit: self._patches(versioned_cube_id, _offset, _limit),
            self._serialize_patch,
            offset,
            limit,
        )

    def preview_patch(self, patch: t.Union[PatchModel, int, str]) -> MetaCube:
        result = self._make_request(
            'patches/{}/preview'.format(
                patch.id
                if isinstance(patch, PatchModel) else
                patch
            )
        )
        strategy = self.inflator
        return MetaCube(
            cube = strategy.deserialize(Cube, result['cube']),
            nodes = strategy.deserialize(NodeCollection, result['nodes']['constrained_nodes']),
            groups = strategy.deserialize(GroupMap, result['group_map']),
            infinites = strategy.deserialize(Infinites, result['infinites'])
        )

    def verbose_patch(self, patch: t.Union[PatchModel, int, str]) -> VerboseCubePatch:
        return RawStrategy(self._db).deserialize(
            VerboseCubePatch,
            self._make_request(
                'patches/{}/verbose'.format(
                    patch.id
                    if isinstance(patch, PatchModel) else
                    patch
                )
            ),
        )

    def _deserialize_distribution_possibility(self, remote: t.Any) -> DistributionPossibility:
        return DistributionPossibility(
            model_id = remote['id'],
            created_at = remote['created_at'],
            pdf_url = remote['pdf_url'],
            fitness = remote['fitness'],
            trap_collection = RawStrategy(self._db).deserialize(TrapCollection, remote['trap_collection']),
            client = self,
        )

    def _distribution_possibilities(
        self,
        patch: t.Union[PatchModel, int, str],
        offset: int,
        limit: int,
    ) -> t.Any:
        return self._make_request(
            'patches/{}/distribution-possibilities'.format(
                patch.id
                if isinstance(patch, PatchModel) else
                patch
            ),
            offset = offset,
            limit = limit,
        )

    def distribution_possibilities(
        self,
        patch: t.Union[PatchModel, int, str],
        offset: int = 0,
        limit: int = 10,
    ) -> PaginatedResponse[DistributionPossibility]:
        return self._get_paginated_response(
            lambda _offset, _limit: self._distribution_possibilities(patch, _offset, _limit),
            self._deserialize_distribution_possibility,
            offset,
            limit,
        )

    def _search(
        self,
        query: str,
        offset: int = 0,
        limit = 10,
        order_by: str = 'name',
        descending: bool = False,
        search_target: str = 'printings',
    ) -> t.Any:
        return self._make_request(
            'search',
            query = query,
            offset = offset,
            limit = limit,
            order_by = order_by,
            descending = str(descending),
            search_target = search_target,
        )

    def search(
        self,
        query: str,
        offset: int = 0,
        limit = 10,
        order_by: str = 'name',
        descending: bool = False,
        search_target: t.Type[P] = Printing,
    ) -> PaginatedResponse[P]:

        return self._get_paginated_response(
            lambda _offset, _limit: self._search(
                query,
                _offset,
                _limit,
                order_by,
                descending,
                'printings' if search_target == Printing else 'cardboards',
            ),
            (
                (lambda p: self._db.printings[p])
                if search_target == Printing else
                (lambda c: self._db.cardboards[c])
            ),
            offset,
            limit,
        )

    def limited_session(self, session_id: t.Union[str, int]) -> LimitedSession:
        return LimitedSession.deserialize(
            self._make_request(
                f'limited/sessions/{session_id}'
            ),
            self,
        )

    def _sealed_sessions(
        self,
        offset: int = 0,
        limit: int = 10,
        *,
        filters: t.Mapping[str, t.Any],
        sort_key: str = 'created_at',
        ascending: bool = False,
    ) -> t.Any:
        return self._make_request(
            f'limited/sessions',
            offset = offset,
            limit = limit,
            sort_key = sort_key,
            ascending = ascending,
            **filters,
        )

    def limited_sessions(
        self,
        offset: int = 0,
        limit: int = 10,
        *,
        filters: t.Optional[t.Mapping[str, t.Any]] = None,
        sort_key: str = 'created_at',
        ascending: bool = False,
    ) -> PaginatedResponse[LimitedSession]:
        return self._get_paginated_response(
            lambda _offset, _limit: self._sealed_sessions(
                _offset,
                _limit,
                filters = {} if filters is None else filters,
                sort_key = sort_key,
                ascending = ascending,
            ),
            lambda remote: LimitedSession.deserialize(remote, self),
            offset,
            limit,
        )

    def limited_pool(self, pool_id: t.Union[str, int]) -> LimitedPool:
        return LimitedPool.deserialize(
            self._make_request(f'limited/pools/{pool_id}'),
            self,
        )

    def upload_limited_deck(self, pool_id: t.Union[str, int], name: str, deck: Deck) -> LimitedDeck:
        return LimitedDeck.deserialize(
            self._make_request(
                f'limited/pools/{pool_id}',
                method = 'POST',
                data = {
                    'deck': JsonId.serialize(deck),
                    'name': name,
                }
            ),
            self,
        )

    def limited_deck(self, deck_id: t.Union[str, int]) -> LimitedDeck:
        return LimitedDeck.deserialize(
            self._make_request(f'limited/deck/{deck_id}'),
            self,
        )

    def tournament(self, tournament_id: t.Union[str, int]) -> Tournament:
        return Tournament.deserialize(
            self._make_request(f'tournaments/{tournament_id}'),
            self,
        )

    def scheduled_match(self, match_id: t.Union[str, int]) -> ScheduledMatch:
        return ScheduledMatch.deserialize(
            self._make_request(f'tournaments/scheduled-matches/{match_id}'),
            self,
        )

    def _scheduled_matches(
        self,
        user: t.Union[str, int, User],
        offset: int = 0,
        limit: int = 10,
    ):
        return self._make_request(
            'tournaments/users/{}/scheduled-matches'.format(
                user.id
                if isinstance(user, User) else
                user
            ),
            offset = offset,
            limit = limit,
        )

    def scheduled_matches(
        self,
        user: t.Union[str, int, User],
        offset: int = 0,
        limit: int = 10,
    ) -> PaginatedResponse[ScheduledMatch]:
        return self._get_paginated_response(
            lambda _offset, _limit: self._scheduled_matches(user, _offset, _limit),
            lambda remote: ScheduledMatch.deserialize(remote, self),
            offset,
            limit,
        )

    def rating_history_for_cardboard_cubeable(
        self,
        release_id: t.Union[str, int],
        cubeable: t.Union[str, CardboardCubeable],
    ) -> t.Sequence[RatingPoint]:
        return [
            RatingPoint.deserialize(
                point,
                self,
            )
            for point in
            self._make_request(
                'ratings/history/'
                f'{release_id}/'
                f'{cubeable if isinstance(cubeable, str) else cubeable.id}'
            )
        ]

    def rating_history_for_node(
        self,
        release_id: t.Union[str, int],
        node: t.Union[str, CardboardNodeChild],
    ) -> t.Sequence[NodeRatingPoint]:
        return [
            NodeRatingPoint.deserialize(
                point,
                self,
            )
            for point in
            self._make_request(
                'ratings/node-history/'
                f'{release_id}/'
                f'{node if isinstance(node, str) else node.id}'
            )
        ]

    def ratings(self, ratings_id: t.Union[str, int]) -> RatingMap:
        return RatingMap.deserialize(
            self._make_request(f'ratings/{ratings_id}'),
            self,
        )

    def ratings_for_versioned_cube(self, cube_id: t.Union[str, int]) -> RatingMap:
        return RatingMap.deserialize(
            self._make_request(f'ratings/versioned-cube/{cube_id}'),
            self,
        )

    def ratings_for_release(self, release_id: t.Union[str, int]) -> RatingMap:
        return RatingMap.deserialize(
            self._make_request(f'ratings/release/{release_id}'),
            self,
        )


class NativeApiClient(BaseNativeApiClient):

    @classmethod
    def _get_paginated_response(
        cls,
        endpoint: t.Callable[[int, int], t.Any],
        serializer: t.Callable[[t.Any], R],
        offset: int = 0,
        limit: int = 50,
    ) -> DynamicPaginatedResponse[R]:
        return DynamicPaginatedResponse(
            endpoint,
            serializer,
            offset,
            limit,
        )

    def versioned_cubes(
        self,
        offset: int = 0,
        limit: int = 10,
        cached: bool = True,
    ) -> DynamicPaginatedResponse[VersionedCube]:
        return super().versioned_cubes(offset, limit, cached)

    def patches(
        self,
        versioned_cube: t.Union[VersionedCube, int, str],
        offset: int = 0,
        limit: int = 10,
    ) -> DynamicPaginatedResponse[PatchModel]:
        return super().patches(versioned_cube, offset, limit)

    def distribution_possibilities(
        self,
        patch: t.Union[PatchModel, int, str],
        offset: int = 0,
        limit: int = 10,
    ) -> DynamicPaginatedResponse[DistributionPossibility]:
        return super().distribution_possibilities(patch, offset, limit)

    def search(
        self,
        query: str,
        offset: int = 0,
        limit = 10,
        order_by: str = 'name',
        descending: bool = False,
        search_target: t.Type[P] = Printing,
    ) -> DynamicPaginatedResponse[P]:
        return super().search(query, offset, limit, order_by, descending, search_target)

    def limited_sessions(
        self,
        offset: int = 0,
        limit: int = 10,
        *,
        filters: t.Optional[t.Mapping[str, t.Any]] = None,
        sort_key: str = 'created_at',
        ascending: bool = False,
    ) -> DynamicPaginatedResponse[LimitedSession]:
        return super().limited_sessions(offset, limit, filters = filters, sort_key = sort_key, ascending = ascending)

    def scheduled_matches(
        self,
        user: t.Union[str, int, User],
        offset: int = 0,
        limit: int = 10,
    ) -> DynamicPaginatedResponse[ScheduledMatch]:
        return super().scheduled_matches(user, offset, limit)


class StaticNativeApiClient(BaseNativeApiClient):

    @classmethod
    def _get_paginated_response(
        cls,
        endpoint: t.Callable[[int, int], t.Any],
        serializer: t.Callable[[t.Any], R],
        offset: int = 0,
        limit: int = 50,
    ) -> StaticPaginationResult[R]:
        response = endpoint(offset, limit)
        return StaticPaginationResult(
            list(map(serializer, response['results'])),
            response['count'],
            offset,
            limit,
        )

    def versioned_cubes(
        self,
        offset: int = 0,
        limit: int = 10,
        cached: bool = True,
    ) -> StaticPaginationResult[VersionedCube]:
        return super().versioned_cubes(offset, limit, cached)

    def patches(
        self,
        versioned_cube: t.Union[VersionedCube, int, str],
        offset: int = 0,
        limit: int = 10,
    ) -> StaticPaginationResult[PatchModel]:
        return super().patches(versioned_cube, offset, limit)

    def distribution_possibilities(
        self,
        patch: t.Union[PatchModel, int, str],
        offset: int = 0,
        limit: int = 10,
    ) -> StaticPaginationResult[DistributionPossibility]:
        return super().distribution_possibilities(patch, offset, limit)

    def search(
        self,
        query: str,
        offset: int = 0,
        limit = 10,
        order_by: str = 'name',
        descending: bool = False,
        search_target: t.Type[P] = Printing,
    ) -> StaticPaginationResult[P]:
        return super().search(query, offset, limit, order_by, descending, search_target)

    def limited_sessions(
        self,
        offset: int = 0,
        limit: int = 10,
        *,
        filters: t.Optional[t.Mapping[str, t.Any]] = None,
        sort_key: str = 'created_at',
        ascending: bool = False,
    ) -> StaticPaginationResult[LimitedSession]:
        return super().limited_sessions(offset, limit, filters = filters, sort_key = sort_key, ascending = ascending)

    def scheduled_matches(
        self,
        user: t.Union[str, int, User],
        offset: int = 0,
        limit: int = 10,
    ) -> StaticPaginationResult[ScheduledMatch]:
        return super().scheduled_matches(user, offset, limit)


class _AsyncMeta(ABCMeta):
    excluded = ('host', 'db', 'token', 'user', 'logout')

    @classmethod
    def _wrap(mcs, name: str) -> t.Callable[..., Promise[T]]:
        def _wrapped(self: AsyncNativeApiClient, *args, **kwargs):
            return Promise.resolve(
                self._executor.submit(
                    getattr(self._wrapping, name),
                    *args,
                    **kwargs,
                )
            )

        return _wrapped

    def __new__(mcs, classname, base_classes, attributes):
        for name, value in base_classes[-1].__dict__.items():
            if getattr(value, '__isabstractmethod__', False) and not name in mcs.excluded:
                attributes[name] = mcs._wrap(name)

        return type.__new__(mcs, classname, base_classes, attributes)


class AsyncNativeApiClient(AsyncClient, metaclass = _AsyncMeta):

    def __init__(
        self,
        host: str,
        db: CardDatabase,
        *,
        executor: t.Union[ThreadPoolExecutor, int, None] = None,
        token: t.Optional[str] = None,
        verify_ssl: bool = True,
    ):
        self._wrapping = StaticNativeApiClient(host, db, token = token, verify_ssl = verify_ssl)
        self._executor = (
            executor
            if isinstance(executor, ThreadPoolExecutor) else
            ThreadPoolExecutor(5 if executor is None else executor)
        )

        self._release_lock = threading.Lock()
        self._release_map: t.MutableMapping[int, CubeRelease] = {}
        self._release_processing: TaskAwaiter[int, CubeRelease] = TaskAwaiter()

    @property
    def executor(self) -> ThreadPoolExecutor:
        return self._executor

    def get_release_managed_noblock(self, release_id: int) -> t.Optional[CubeRelease]:
        with self._release_lock:
            return self._release_map.get(release_id)

    def _get_release_managed(self, release_id: int) -> CubeRelease:
        release = self.get_release_managed_noblock(release_id)
        if release is not None:
            return release

        event, in_progress = self._release_processing.get_condition(release_id)

        if in_progress:
            event.wait()
            return event.value

        release = self._wrapping.release(release_id)
        with self._release_lock:
            self._release_map[release_id] = release
        event.set_value(release)

        return release

    def get_release_managed(self, release_id: int) -> Promise[CubeRelease]:
        return Promise.resolve(
            self._executor.submit(
                self._get_release_managed,
                release_id,
            )
        )

    @property
    def synchronous(self) -> StaticNativeApiClient:
        return self._wrapping

    @property
    def scheme(self) -> str:
        return self._wrapping.scheme

    @property
    def host(self) -> str:
        return self._wrapping.host

    @property
    def db(self) -> CardDatabase:
        return self._wrapping.db

    @property
    def token(self) -> str:
        return self._wrapping.token

    @token.setter
    def token(self, value: str) -> None:
        self._wrapping.token = value

    @property
    def user(self) -> t.Optional[User]:
        return self._wrapping.user

    def logout(self) -> None:
        self._wrapping.logout()
