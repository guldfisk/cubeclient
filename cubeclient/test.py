from requests import HTTPError

from cubeclient.models import LimitedSession, CubeBoosterSpecification
from mtgorp.db.load import Loader

from cubeclient.endpoints import NativeApiClient
from mtgorp.models.collections.deck import Deck
from mtgorp.models.persistent.cardboard import Cardboard
from mtgorp.models.persistent.printing import Printing


def test():
    db = Loader.load()

    client = NativeApiClient('localhost:7000', db)

    client.login('root', '1')

    print(client.user.username)

    for session in client.limited_sessions(limit = 2, filters = {'name_filter': 'penny'}):
        for specification in session.pool_specification.booster_specifications:
            if isinstance(specification, CubeBoosterSpecification):
                print(specification.release.name)
                print(specification.release.intended_size)
            print(specification.amount)
        # for pool in session.pools:
        #     try:
        #         client.upload_limited_deck(
        #             pool.id,
        #             'some deck',
        #             Deck(
        #                 (db.cardboards['Mountain'].printing,) * 40,
        #                 (db.cardboards['Mountain'].printing,) * 15,
        #             )
        #         )
        #     except HTTPError as e:
        #         print(e, e.response.json())



if __name__ == '__main__':
    test()
