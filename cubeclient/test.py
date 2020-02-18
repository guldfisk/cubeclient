from requests import HTTPError

from cubeclient.models import SealedSession
from mtgorp.db.load import Loader

from cubeclient.endpoints import NativeApiClient
from mtgorp.models.collections.deck import Deck
from mtgorp.models.persistent.cardboard import Cardboard
from mtgorp.models.persistent.printing import Printing


def test():
    db = Loader.load()

    client = NativeApiClient('localhost:7000', db)

    client.login('root', '1')

    for session in client.sealed_sessions(limit = 2, filters = {'name_filter': 'foamy'}):
        for pool in session.pools:
            try:
                client.upload_sealed_deck(
                    pool.id,
                    'some deck',
                    Deck(
                        (db.cardboards['Mountain'].printing,) * 40,
                        (db.cardboards['Mountain'].printing,) * 15,
                    )
                )
            except HTTPError as e:
                print(e, e.response.json())

    # print('l go')
    # for cardboard in (
    #     set(client.search('block=theros !t;basic', search_target = Cardboard, limit = 10))
    #     & set(client.search('e=thb', search_target = Cardboard, limit = 1000))
    # ):
    #     if cardboard.original_printing.expansion.block == db.expansions['THS'].block:
    #         print(cardboard.name)


if __name__ == '__main__':
    test()
