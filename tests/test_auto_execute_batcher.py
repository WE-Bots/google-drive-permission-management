from mock import patch

from googleapiclient.http import HttpRequest

from GoogleDriveOperations import EnhancedBatchHttpRequest


def test_auto_execute():
    EnhancedBatchHttpRequest.CAP = 2
    batcher = EnhancedBatchHttpRequest(None, batch_uri="http://localhost")
    with patch.object(EnhancedBatchHttpRequest, "execute") as mock:
        batcher.add(HttpRequest(None, None, None))
        batcher.add(HttpRequest(None, None, None))
        batcher.add(HttpRequest(None, None, None))

    mock.assert_called_once()


def test_no_auto_execute():
    EnhancedBatchHttpRequest.CAP = 5
    batcher = EnhancedBatchHttpRequest(None, batch_uri="http://localhost")
    with patch.object(EnhancedBatchHttpRequest, "execute") as mock:
        batcher.add(HttpRequest(None, None, None))
        batcher.add(HttpRequest(None, None, None))
        batcher.add(HttpRequest(None, None, None))

    mock.assert_not_called()
