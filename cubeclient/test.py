
from mtgorp.db.load import Loader

from cubeclient.endpoints import NativeApiClient



def test():

    db = Loader.load()

    client = NativeApiClient('localhost:7000', db)


    for versioned_cube in client.versioned_cubes():
        for patch in versioned_cube.patches:
            print(patch.verbose)



if __name__ == '__main__':
    test()