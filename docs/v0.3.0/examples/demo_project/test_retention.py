"""Initial 24h/90d test inputs for the LATIS exhibition scenario."""

import unittest

from retention import retention_hours


class RetentionTests(unittest.TestCase):
    def test_normal_logs_follow_initial_agreement(self):
        self.assertEqual(retention_hours("normal"), 24)

    def test_audit_logs_remain_ninety_days(self):
        self.assertEqual(retention_hours("audit"), 90 * 24)

    def test_unknown_log_kind_is_rejected(self):
        with self.assertRaises(ValueError):
            retention_hours("unknown")


if __name__ == "__main__":
    unittest.main()
