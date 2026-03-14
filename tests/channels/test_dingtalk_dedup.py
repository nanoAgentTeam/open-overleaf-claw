import time
import unittest

from channels.im_api.dingtalk.dingtalk.dedup import DedupStore


class TestDedupStore(unittest.TestCase):
    def test_mark_and_check(self):
        store = DedupStore(ttl_seconds=10)
        self.assertFalse(store.is_processed("k1"))
        store.mark_processed("k1")
        self.assertTrue(store.is_processed("k1"))

    def test_expire(self):
        store = DedupStore(ttl_seconds=0.1)
        store.mark_processed("k2")
        time.sleep(0.2)
        self.assertFalse(store.is_processed("k2"))


if __name__ == "__main__":
    unittest.main()
