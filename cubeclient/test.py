
from mtgorp.db.load import Loader

from cubeclient.endpoints import NativeApiClient



def test():

    db = Loader.load()

    client = NativeApiClient('localhost:7000', db)


    patch = client.patch(26)

    for possibility in patch.distribution_possibilities:
        print(possibility.fitness)


if __name__ == '__main__':
    test()