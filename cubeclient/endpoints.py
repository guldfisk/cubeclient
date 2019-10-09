from __future__ import annotations

import typing as t

from abc import ABC
import itertools
import json
import datetime

import requests as r

from cubeclient import models
from cubeclient.models import PaginatedResponse, VersionedCube
from magiccube.laps.purples.purple import Purple
from magiccube.laps.tickets.ticket import Ticket
from magiccube.laps.traps.trap import Trap
from mtgorp.db.database import CardDatabase
from mtgorp.models.persistent.printing import Printing
from mtgorp.models.serilization.strategies.jsonid import JsonId
from mtgorp.models.serilization.strategies.raw import RawStrategy

from magiccube.collections.cube import Cube
from yeetlong.multiset import FrozenMultiset


class NativeApiClient(models.ApiClient):
    _DATETIME_FORMAT = '%Y-%m-%dT%H:%M:%S.%f'

    def __init__(self, domain: str, db: CardDatabase):
        self._domain = domain
        self._db = db

        self._strategy = RawStrategy(db)

    def _make_request(self, endpoint: str, **kwargs) -> t.Any:
        kwargs.update(native=True)
        url = f'http://{self._domain}/api/{endpoint}/'
        print('request to', url, kwargs)
        return r.get(
            url,
            params = kwargs,
        ).json()
    def release(self, release_id: int) -> models.CubeRelease:
        result = self._make_request(f'cube-releases/{release_id}')
        return models.CubeRelease(
            model_id = result['id'],
            created_at = datetime.datetime.strptime(result['created_at'].split('Z')[0], self._DATETIME_FORMAT),
            name = result['name'],
            intended_size = result['intended_size'],
            cube = RawStrategy(self._db).deserialize(
                Cube,
                result['cube']
            ),
            client = self,
        )

    def _serialize_versioned_cube(self, remote) -> VersionedCube:
        return VersionedCube(
            model_id = remote['id'],
            name = remote['name'],
            created_at = datetime.datetime.strptime(remote['created_at'].split('Z')[0], self._DATETIME_FORMAT),
            description = remote['description'],
            client = self,
        )

    def _versioned_cubes(self, offset: int, limit: int) -> t.List[t.Any]:
        return self._make_request('versioned-cubes', offset=offset, limit=limit)

    def versioned_cubes(self, offset: int = 0, limit: int = 10) -> PaginatedResponse[VersionedCube]:
        return PaginatedResponse(
            self._versioned_cubes,
            self._serialize_versioned_cube,
            offset,
            limit,
        )

    # def release_delta(self, from_release_id: int, to_release_id):
    #     result = r.get(
    #         self._get_api_url + f'cube-releases/{to_release_id}/delta-from/{from_release_id}/'
    #     )
    #     return result.content
