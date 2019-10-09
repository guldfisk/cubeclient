
from mtgorp.db.load import Loader

from cubeclient.endpoints import NativeApiClient



def test():

    db = Loader.load()

    client = NativeApiClient('localhost:7000', db)

    versioned_cubes = client.versioned_cubes(limit = 2)

    print(versioned_cubes)
    print(versioned_cubes[2])
    for item in versioned_cubes:
        print(item)
    print(versioned_cubes)



if __name__ == '__main__':
    test()