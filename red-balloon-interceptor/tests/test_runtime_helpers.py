"""Runtime evidence parsing must handle long recordings without inventing results."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from validate_world_runtime import parse_messages, seconds

class RuntimeHelperTests(unittest.TestCase):
    def test_long_capture_is_not_treated_as_one_oversized_message(self):
        data='{"sim":{"sec":"12","nsec":1000000}}\n'*70000
        self.assertGreater(len(data),2_000_000)
        messages=parse_messages(data)
        self.assertEqual(len(messages),70000)
        self.assertEqual(seconds(messages[-1]['sim']),12.001)

    def test_truncated_capture_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'Incomplete'):
            parse_messages('{"sim": {"sec": 1')

if __name__=='__main__': unittest.main()
