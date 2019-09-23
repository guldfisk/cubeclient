from __future__ import annotations

import typing as t

from abc import ABC
import itertools
import json

import requests as r

from magiccube.laps.purples.purple import Purple
from magiccube.laps.tickets.ticket import Ticket
from magiccube.laps.traps.trap import Trap
from mtgorp.db.database import CardDatabase
from mtgorp.models.persistent.printing import Printing
from mtgorp.models.serilization.strategies.jsonid import JsonId
from mtgorp.models.serilization.strategies.raw import RawStrategy

from magiccube.collections.cube import Cube
from yeetlong.multiset import FrozenMultiset


# def _parse_trap(remote: t.Mapping[str, t.Any]) -> Trap:
#     return Trap(
#         remote[],
#         Trap.IntentionType[remote['intention_type']] if 'intention_type' in remote else None,
#     )

class CubeApiClient(object):

    def __init__(self, domain: str, db: CardDatabase):
        self._domain = domain
        self._db = db

        self._strategy = RawStrategy(db)

    @property
    def _api_url(self):
        return f'http://{self._domain}/api/'

    def release(self, release_id: int) -> Cube:
        result = r.get(
            self._api_url + f'cube-releases/{release_id}/'
        ).json()
        release = result['cube_content']
        print(result['checksum'])
        return Cube(
            FrozenMultiset(
                {
                    value: multiplicity
                    for value, multiplicity in
                    itertools.chain(
                        (
                            (self._strategy.inflate(Printing, printing['id']), multiplicity)
                            for printing, multiplicity in
                            release['printings']
                        ),
                        (
                            (self._strategy.deserialize(Trap, trap), multiplicity)
                            for trap, multiplicity in
                            release['traps']
                        ),
                        (
                            (self._strategy.deserialize(Ticket, ticket), multiplicity)
                            for ticket, multiplicity in
                            release['tickets']
                        ),
                        (
                            (self._strategy.deserialize(Purple, purple), multiplicity)
                            for purple, multiplicity in
                            release['purples']
                        )
                    )
                }
            )
        )

    def release_delta(self, from_release_id: int, to_release_id):
        result = r.get(
            self._api_url + f'cube-releases/{to_release_id}/delta-from/{from_release_id}/'
        )
        return result.content
