from __future__ import annotations

import datetime
import typing as t

import requests as r

from cubeclient import models
from cubeclient.models import (
    PaginatedResponse, VersionedCube, PatchModel, DistributionPossibility, SealedPool, P, SealedSession
)
from magiccube.collections.cube import Cube
from magiccube.collections.laps import TrapCollection
from magiccube.collections.meta import MetaCube
from magiccube.collections.nodecollection import NodeCollection, GroupMap
from magiccube.update.cubeupdate import VerboseCubePatch
from mtgorp.db.database import CardDatabase
from mtgorp.models.persistent.printing import Printing
from mtgorp.models.serilization.strategies.raw import RawStrategy


class NativeApiClient(models.ApiClient):
    _DATETIME_FORMAT = '%Y-%m-%dT%H:%M:%S'

    def __init__(self, domain: str, db: CardDatabase, *, token: t.Optional[str] = None):
        super().__init__(token = token)
        self._domain = domain
        self._db = db

        self._strategy = RawStrategy(db)

    def _make_request(
        self,
        endpoint: str,
        method: str = 'GET',
        data: t.Optional[t.Mapping[str, t.Any]] = None,
        **kwargs,
    ) -> t.Any:
        if data is None:
            data = {}

        kwargs.setdefault('native', True)

        headers = {}
        if self._token is not None:
            headers.setdefault('Authorization', 'Token ' + self._token)

        url = f'http://{self._domain}/api/{endpoint}/'

        print('request', url)

        response = r.request(
            method,
            url,
            data = data,
            params = kwargs,
            headers = headers,
        )
        response.raise_for_status()
        return response.json()

    def login(self, username: str, password: str) -> str:
        token = self._make_request(
            'auth/login',
            method = 'POST',
            data = {
                'username': username,
                'password': password,
            }
        )['token']
        self._token = token
        return token

    def _deserialize_cube_release(self, remote: t.Any) -> models.CubeRelease:
        return models.CubeRelease(
            model_id = remote['id'],
            created_at = datetime.datetime.strptime(remote['created_at'], self._DATETIME_FORMAT),
            name = remote['name'],
            intended_size = remote['intended_size'],
            cube = (
                RawStrategy(self._db).deserialize(
                    Cube,
                    remote['cube']
                )
                if 'cube' in remote else
                None
            ),
            client = self,
        )

    def release(self, release: t.Union[models.CubeRelease, str, int]) -> models.CubeRelease:
        return self._deserialize_cube_release(
            self._make_request(
                'cube-releases/{}'.format(
                    release.id
                    if isinstance(release, models.CubeRelease) else
                    release
                )
            )
        )

    def _deserialize_versioned_cube(self, remote) -> VersionedCube:
        return VersionedCube(
            model_id = remote['id'],
            name = remote['name'],
            created_at = datetime.datetime.strptime(remote['created_at'], self._DATETIME_FORMAT),
            description = remote['description'],
            releases = [
                self._deserialize_cube_release(release)
                for release in
                remote['releases']
            ],
            client = self,
        )

    def _versioned_cubes(self, offset: int, limit: int) -> t.List[t.Any]:
        return self._make_request('versioned-cubes', offset = offset, limit = limit)

    def versioned_cube(self, versioned_cube_id: t.Union[str, int]) -> VersionedCube:
        return self._deserialize_versioned_cube(
            self._make_request(
                f'versioned-cubes/{versioned_cube_id}'
            )
        )

    def versioned_cubes(self, offset: int = 0, limit: int = 10) -> PaginatedResponse[VersionedCube]:
        return PaginatedResponse(
            self._versioned_cubes,
            self._deserialize_versioned_cube,
            offset,
            limit,
        )

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
        return PaginatedResponse(
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
        return MetaCube(
            cube = RawStrategy(self._db).deserialize(Cube, result['cube']),
            nodes = RawStrategy(self._db).deserialize(NodeCollection, result['nodes']['constrained_nodes']),
            groups = RawStrategy(self._db).deserialize(GroupMap, result['group_map']),
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
        return PaginatedResponse(
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

        return PaginatedResponse(
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

    def _deserialize_sealed_pool(self, remote: t.Any) -> SealedPool:
        return SealedPool(
            pool_id = remote['id'],
            client = self,
            session = self._deserialize_sealed_session(remote['session']) if 'session' in remote else None,
            pool = RawStrategy(self._db).deserialize(Cube, remote['pool']) if 'pool' in remote else None,
        )

    def _deserialize_sealed_session(self, remote: t.Any) -> SealedSession:
        return SealedSession(
            model_id = remote['id'],
            name = remote['name'],
            release = remote['release'],
            state = SealedSession.SealedSessionState[remote['state']],
            pool_size = remote['pool_size'],
            game_format = remote['format'],
            created_at = datetime.datetime.strptime(remote['created_at'], self._DATETIME_FORMAT),
            client = self,
            pools = [
                self._deserialize_sealed_pool(pool)
                for pool in
                remote['pools']
            ] if 'pools' in remote else None
        )

    def sealed_session(self, session_id: t.Union[str, int]) -> SealedSession:
        return self._deserialize_sealed_session(
            self._make_request(
                f'sealed/sessions/{session_id}'
            )
        )

    def _sealed_sessions(
        self,
        offset: int,
        limit: int,
    ) -> t.Any:
        return self._make_request(
            f'sealed/sessions',
            offset = offset,
            limit = limit,
        )

    def sealed_sessions(self, offset: int = 0, limit: int = 10) -> PaginatedResponse[SealedSession]:
        return PaginatedResponse(
            lambda _offset, _limit: self._sealed_sessions(_offset, _limit),
            self._deserialize_sealed_session,
            offset,
            limit,
        )

    def sealed_pool(self, pool_id: t.Union[str, int]) -> SealedPool:
        return self._deserialize_sealed_pool(
            self._make_request(f'sealed/pools/{pool_id}')
        )

    # def patch_report(self, patch: t.Union[PatchModel, int, str]) -> UpdateReport:
    #     pass

    # def release_delta(self, from_release_id: int, to_release_id):
    #     result = r.get(
    #         self._get_api_url + f'cube-releases/{to_release_id}/delta-from/{from_release_id}/'
    #     )
    #     return result.content
