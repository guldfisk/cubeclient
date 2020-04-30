import logging
import time

from requests import HTTPError

from cubeclient.models import LimitedSession, CubeBoosterSpecification
from mtgorp.db.load import Loader

from cubeclient.endpoints import NativeApiClient, AsyncNativeApiClient
from mtgorp.models.collections.deck import Deck
from mtgorp.models.persistent.cardboard import Cardboard
from mtgorp.models.persistent.printing import Printing


def _handle_error(v):
    print('haha', v)
    raise Exception()

def test():
    logging.basicConfig(format = '%(levelname)s %(message)s', level = logging.INFO)
    db = Loader.load()

    client = AsyncNativeApiClient('localhost:7000', db)

    client.db_info().then(lambda i: print(i.checksum)).catch(lambda e: print(e))

    # # fetch_cubes = client.login('ce', 'fraekesteguyaround1').then(lambda v: print('logged in')).then(client.versioned_cubes)
    # fetch_cubes = (
    #     client
    #         .login('ce', 'fraekesteguyaround1')
    #         .then(lambda v: print('logged in'))
    #         .catch(_handle_error)
    #         # .then(did_reject = lambda e: print('and this'))
    # )
    #
    # print('running')
    #
    # print(fetch_cubes.done(
    #     lambda v: print('got there', v),
    #     lambda v: print('oh no', v),
    # ))

    # print(client.user.username)
    #
    # for session in client.limited_sessions(limit = 2, filters = {'name_filter': 'penny'}):
    #     for specification in session.pool_specification.booster_specifications:
    #         if isinstance(specification, CubeBoosterSpecification):
    #             print(specification.release.name)
    #             print(specification.release.intended_size)
    #         print(specification.amount)
    #     # for pool in session.pools:
    #     #     try:
    #     #         client.upload_limited_deck(
    #     #             pool.id,
    #     #             'some deck',
    #     #             Deck(
    #     #                 (db.cardboards['Mountain'].printing,) * 40,
    #     #                 (db.cardboards['Mountain'].printing,) * 15,
    #     #             )
    #     #         )
    #     #     except HTTPError as e:
    #     #         print(e, e.response.json())
    #
    # client.versioned_cubes()
    # for vc in client.versioned_cubes():
    #     print(vc.releases)


if __name__ == '__main__':
    test()
