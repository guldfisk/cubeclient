
from mtgorp.db.load import Loader

from cubeclient.endpoints import CubeApiClient



def test():

    db = Loader.load()

    client = CubeApiClient('prohunterdogkeeper.dk', db)

    print(client.release(1).persistent_hash())



if __name__ == '__main__':
    test()