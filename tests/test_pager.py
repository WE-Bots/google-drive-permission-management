from GoogleDriveOperations import google_pager


class DummyPageGenerator(object):
    def __init__(self, field_name):
        self._results = [[1,2,3,4,5],[6,7,8,9,10]]
        self._field_name = field_name
        self._count = 0

    def execute(self):
        return {self._field_name: self._results[self._count]}

    def next(self, req, resp):
        self._count += 1
        return self if self._count < len(self._results) else None


def test_pager():
    expected = [1,2,3,4,5,6,7,8,9,10]
    actual = []

    pager = DummyPageGenerator("numbers")
    for res in google_pager(pager, "numbers", lambda x, y: pager.next(x,y)):
        actual.append(res)

    assert expected == actual
