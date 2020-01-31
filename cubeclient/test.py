
from mtgorp.db.load import Loader

from cubeclient.endpoints import NativeApiClient
from mtgorp.models.persistent.cardboard import Cardboard
from mtgorp.models.persistent.printing import Printing


def test():
    db = Loader.load()

    client = NativeApiClient('localhost:7000', db)

    print('l go')
    for cardboard in (
        set(client.search('block=theros !t;basic', search_target = Cardboard, limit = 10))
        & set(client.search('e=thb', search_target = Cardboard, limit = 1000))
    ):
        if cardboard.original_printing.expansion.block == db.expansions['THS'].block:
            print(cardboard.name)


if __name__ == '__main__':
    test()