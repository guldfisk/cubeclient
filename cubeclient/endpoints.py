from __future__ import annotations

import typing as t

from abc import ABC
import itertools
import json
import datetime

import requests as r

from cubeclient import models
from cubeclient.models import PaginatedResponse, VersionedCube, PatchModel
from magiccube.collections.meta import MetaCube
from magiccube.collections.nodecollection import NodeCollection, GroupMap
from magiccube.laps.purples.purple import Purple
from magiccube.laps.tickets.ticket import Ticket
from magiccube.laps.traps.trap import Trap
from magiccube.update.cubeupdate import VerboseCubePatch
from magiccube.update.report import UpdateReport
from mtgorp.db.database import CardDatabase
from mtgorp.models.persistent.printing import Printing
from mtgorp.models.serilization.strategies.jsonid import JsonId
from mtgorp.models.serilization.strategies.raw import RawStrategy

from magiccube.collections.cube import Cube
from yeetlong.multiset import FrozenMultiset


class NativeApiClient(models.ApiClient):
    _DATETIME_FORMAT = '%Y-%m-%dT%H:%M:%S'

    def __init__(self, domain: str, db: CardDatabase):
        self._domain = domain
        self._db = db

        self._strategy = RawStrategy(db)

    def _make_request(self, endpoint: str, **kwargs) -> t.Any:
        kwargs.setdefault('native', True)
        url = f'http://{self._domain}/api/{endpoint}/'
        print('request to', url, kwargs)
        return r.get(
            url,
            params = kwargs,
        ).json()

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

    # def patch_report(self, patch: t.Union[PatchModel, int, str]) -> UpdateReport:
    #     pass

    # def release_delta(self, from_release_id: int, to_release_id):
    #     result = r.get(
    #         self._get_api_url + f'cube-releases/{to_release_id}/delta-from/{from_release_id}/'
    #     )
    #     return result.content
