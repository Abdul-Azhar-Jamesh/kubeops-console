import unittest

from dashboard.main import endpoint_rows


class EndpointTests(unittest.TestCase):
    def test_owner_uid_and_tristate_conditions(self):
        service = {"metadata": {"uid": "current"}}
        item = {"metadata": {"name": "slice", "ownerReferences": [{"uid": "current", "kind": "Service"}]},
                "addressType": "IPv6", "ports": [{"port": 8080}], "endpoints": [
                    {"addresses": ["::1"], "conditions": {"ready": False, "serving": True, "terminating": True}},
                    {"addresses": ["::2"]},
                ]}
        rows = endpoint_rows(service, [item])
        self.assertEqual((rows[0]["ready"], rows[0]["serving"], rows[0]["terminating"]), ("No", "Yes", "Yes"))
        self.assertEqual(rows[1]["ready"], "Unknown")
        self.assertEqual(rows[0]["ports"], "8080/TCP")
        item["metadata"]["ownerReferences"][0]["uid"] = "old"
        self.assertEqual(endpoint_rows(service, [item]), [])
        self.assertEqual(endpoint_rows({}, [item]), [])
