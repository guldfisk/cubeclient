
from mtgorp.db.load import Loader

from cubeclient.endpoints import NativeApiClient



def test():

    db = Loader.load()

    client = NativeApiClient('localhost:7000', db)


    sealed_pool = client.get_sealed_pool('yikes')

    print(sealed_pool)
    print(sealed_pool.pool)


if __name__ == '__main__':
    test()