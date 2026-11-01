import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TOOL = ROOT / "products.py"

VALID_STORE = {
    "next_id": 3,
    "products": [
        {"id": 1, "name": "Notebook", "price": "4.50", "quantity": 10},
        {"id": 2, "name": "Pencil", "price": "1.25", "quantity": 5},
    ],
}


class ToolTestCase(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.data = self.dir / "products.json"

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def run_tool(self, *args, cwd=None):
        return subprocess.run(
            [sys.executable, str(TOOL)] + [str(a) for a in args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=cwd if cwd is not None else self.dir,
        )

    def write_store(self, text):
        self.data.write_text(text, encoding="utf-8")

    def read_store(self):
        return self.data.read_text(encoding="utf-8")

    def read_store_bytes(self):
        return self.data.read_bytes()

    def out_json(self, proc):
        return json.loads(proc.stdout)

    def assertOk(self, proc):
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)
        return proc

    def assertFail(self, proc, code, contains=None):
        self.assertEqual(proc.returncode, code, msg=proc.stderr)
        self.assertTrue(proc.stderr, "expected a stderr message")
        self.assertNotIn("Traceback", proc.stderr)
        self.assertEqual(proc.stdout, "", "no JSON expected on stdout for failures")
        if contains is not None:
            self.assertIn(contains, proc.stderr)
        return proc


class HelpTests(ToolTestCase):
    def test_main_help_lists_all_commands(self):
        proc = self.assertOk(self.run_tool("--help"))
        for command in ("add", "list", "get", "update", "delete", "low-stock"):
            self.assertIn(command, proc.stdout)
        self.assertFalse(self.data.exists())

    def test_each_command_help_exits_zero(self):
        for command in ("add", "list", "get", "update", "delete", "low-stock"):
            proc = self.assertOk(self.run_tool(command, "--help"))
            self.assertTrue(proc.stdout.strip())
        self.assertFalse(self.data.exists())

    def test_help_does_not_modify_existing_file(self):
        self.write_store(json.dumps(VALID_STORE))
        before = self.read_store_bytes()
        self.assertOk(self.run_tool("--help"))
        self.assertOk(self.run_tool("add", "--help"))
        self.assertEqual(self.read_store_bytes(), before)

    def test_no_command_is_rejected(self):
        self.assertFail(self.run_tool(), 2)

    def test_unknown_command_is_rejected(self):
        self.assertFail(self.run_tool("bogus"), 2)

    def test_unknown_flag_is_rejected(self):
        self.assertFail(self.run_tool("--bogus", "list"), 2)

    def test_abbreviated_flags_are_rejected(self):
        self.assertFail(self.run_tool("--fil", "demo.json", "list"), 2)
        self.assertFail(
            self.run_tool("add", "--na", "A", "--price", "1", "--quantity", "1"), 2
        )
        self.assertFail(self.run_tool("delete", "1", "--y"), 2)
        self.assertFail(self.run_tool("delete", "1", "--ye"), 2)


class AddTests(ToolTestCase):
    def test_add_creates_product_and_file(self):
        proc = self.assertOk(
            self.run_tool("add", "--name", "Notebook", "--price", "4.5", "--quantity", "10")
        )
        self.assertEqual(
            self.out_json(proc),
            {"id": 1, "name": "Notebook", "price": "4.50", "quantity": 10},
        )
        store = json.loads(self.read_store())
        self.assertEqual(store["next_id"], 2)
        self.assertEqual(len(store["products"]), 1)

    def test_add_normalizes_price(self):
        self.assertOk(self.run_tool("add", "--name", "A", "--price", "0", "--quantity", "1"))
        self.assertOk(self.run_tool("add", "--name", "B", "--price", "4.50", "--quantity", "1"))
        store = json.loads(self.read_store())
        self.assertEqual([p["price"] for p in store["products"]], ["0.00", "4.50"])

    def test_add_accepts_zero_quantity(self):
        proc = self.assertOk(
            self.run_tool("add", "--name", "A", "--price", "1", "--quantity", "0")
        )
        self.assertEqual(self.out_json(proc)["quantity"], 0)

    def test_add_trims_name(self):
        proc = self.assertOk(
            self.run_tool("add", "--name", "  Notebook  ", "--price", "1", "--quantity", "1")
        )
        self.assertEqual(self.out_json(proc)["name"], "Notebook")

    def test_add_allows_duplicate_names(self):
        self.assertOk(self.run_tool("add", "--name", "Pen", "--price", "1", "--quantity", "1"))
        self.assertOk(self.run_tool("add", "--name", "Pen", "--price", "2", "--quantity", "2"))
        store = json.loads(self.read_store())
        self.assertEqual(len(store["products"]), 2)

    def test_add_rejects_invalid_prices(self):
        for price in ("-4.5", "$4.50", "4.555", "1e2", ".50", "4.", "4,50", "+4.5"):
            proc = self.run_tool("add", "--name", "A", "--price", price, "--quantity", "1")
            self.assertFail(proc, 2, contains=price)
        self.assertFalse(self.data.exists())

    def test_add_rejects_invalid_quantities(self):
        for quantity in ("-1", "2.5", "abc", "1_0", "+2"):
            proc = self.run_tool("add", "--name", "A", "--price", "1", "--quantity", quantity)
            self.assertFail(proc, 2, contains=quantity)
        self.assertFalse(self.data.exists())

    def test_add_rejects_blank_names(self):
        for name in ("", "   "):
            proc = self.run_tool("add", "--name", name, "--price", "1", "--quantity", "1")
            self.assertFail(proc, 2)
        self.assertFalse(self.data.exists())

    def test_add_requires_all_flags(self):
        self.assertFail(self.run_tool("add", "--name", "A"), 2)
        self.assertFail(self.run_tool("add", "--name", "A", "--price", "1"), 2)
        self.assertFalse(self.data.exists())

    def test_failed_add_keeps_file_and_next_id(self):
        self.assertOk(self.run_tool("add", "--name", "A", "--price", "1", "--quantity", "1"))
        before = self.read_store_bytes()
        self.assertFail(
            self.run_tool("add", "--name", "B", "--price", "-1", "--quantity", "1"), 2
        )
        self.assertEqual(self.read_store_bytes(), before)
        proc = self.assertOk(
            self.run_tool("add", "--name", "B", "--price", "1", "--quantity", "1")
        )
        self.assertEqual(self.out_json(proc)["id"], 2)

    def test_add_rejects_extra_positional(self):
        self.assertFail(
            self.run_tool("add", "extra", "--name", "A", "--price", "1", "--quantity", "1"), 2
        )

    def test_add_unicode_name_round_trips(self):
        proc = self.assertOk(
            self.run_tool("add", "--name", "Café ☕", "--price", "1", "--quantity", "1")
        )
        self.assertEqual(self.out_json(proc)["name"], "Café ☕")
        self.assertIn("Café ☕", self.read_store())

    def test_add_wont_create_missing_parent_dir(self):
        target = self.dir / "nodir" / "data.json"
        proc = self.run_tool(
            "--file", target, "add", "--name", "A", "--price", "1", "--quantity", "1"
        )
        self.assertFail(proc, 1)
        self.assertFalse(target.parent.exists())


class ListTests(ToolTestCase):
    def test_list_missing_file_prints_empty_array(self):
        proc = self.assertOk(self.run_tool("list"))
        self.assertEqual(proc.stdout.strip(), "[]")
        self.assertFalse(self.data.exists())

    def test_list_sorts_numerically_by_id(self):
        store = {
            "next_id": 12,
            "products": [
                {"id": 10, "name": "B", "price": "2.00", "quantity": 2},
                {"id": 2, "name": "A", "price": "1.00", "quantity": 1},
            ],
        }
        self.write_store(json.dumps(store))
        proc = self.assertOk(self.run_tool("list"))
        self.assertEqual([p["id"] for p in self.out_json(proc)], [2, 10])

    def test_list_does_not_modify_file(self):
        self.write_store(json.dumps(VALID_STORE))
        before = self.read_store_bytes()
        self.assertOk(self.run_tool("list"))
        self.assertEqual(self.read_store_bytes(), before)


class GetTests(ToolTestCase):
    def test_get_returns_matching_product(self):
        self.write_store(json.dumps(VALID_STORE))
        proc = self.assertOk(self.run_tool("get", "2"))
        self.assertEqual(self.out_json(proc)["name"], "Pencil")

    def test_get_missing_id_fails_with_exit_1(self):
        self.write_store(json.dumps(VALID_STORE))
        before = self.read_store_bytes()
        proc = self.run_tool("get", "99")
        self.assertFail(proc, 1, contains="99")
        self.assertEqual(self.read_store_bytes(), before)

    def test_get_rejects_invalid_ids(self):
        self.write_store(json.dumps(VALID_STORE))
        for bad_id in ("abc", "0", "-1", "1.5", ""):
            self.assertFail(self.run_tool("get", bad_id), 2)
        self.assertFail(self.run_tool("get"), 2)

    def test_get_extra_positional_rejected(self):
        self.assertFail(self.run_tool("get", "1", "2"), 2)


class UpdateTests(ToolTestCase):
    def test_update_changes_only_supplied_fields(self):
        self.write_store(json.dumps(VALID_STORE))
        proc = self.assertOk(self.run_tool("update", "1", "--quantity", "12"))
        self.assertEqual(
            self.out_json(proc),
            {"id": 1, "name": "Notebook", "price": "4.50", "quantity": 12},
        )

    def test_update_multiple_fields(self):
        self.write_store(json.dumps(VALID_STORE))
        proc = self.assertOk(self.run_tool("update", "1", "--name", "Pad", "--price", "2"))
        self.assertEqual(
            self.out_json(proc),
            {"id": 1, "name": "Pad", "price": "2.00", "quantity": 10},
        )
        store = json.loads(self.read_store())
        self.assertEqual(store["next_id"], 3)

    def test_update_requires_at_least_one_field(self):
        self.write_store(json.dumps(VALID_STORE))
        before = self.read_store_bytes()
        self.assertFail(self.run_tool("update", "1"), 2)
        self.assertEqual(self.read_store_bytes(), before)

    def test_update_missing_product(self):
        self.write_store(json.dumps(VALID_STORE))
        before = self.read_store_bytes()
        proc = self.run_tool("update", "99", "--quantity", "1")
        self.assertFail(proc, 1, contains="99")
        self.assertEqual(self.read_store_bytes(), before)

    def test_update_invalid_value_leaves_file_unchanged(self):
        self.write_store(json.dumps(VALID_STORE))
        before = self.read_store_bytes()
        for args in (
            ("update", "1", "--price", "4.555"),
            ("update", "1", "--quantity", "-1"),
            ("update", "1", "--name", "  "),
        ):
            self.assertFail(self.run_tool(*args), 2)
        self.assertEqual(self.read_store_bytes(), before)

    def test_update_on_missing_file(self):
        self.assertFail(self.run_tool("update", "1", "--quantity", "1"), 1)


class DeleteTests(ToolTestCase):
    def test_delete_requires_yes(self):
        self.write_store(json.dumps(VALID_STORE))
        before = self.read_store_bytes()
        self.assertFail(self.run_tool("delete", "2"), 2)
        self.assertEqual(self.read_store_bytes(), before)

    def test_delete_reports_missing_id(self):
        self.write_store(json.dumps(VALID_STORE))
        before = self.read_store_bytes()
        proc = self.run_tool("delete", "99", "--yes")
        self.assertFail(proc, 1, contains="99")
        self.assertEqual(self.read_store_bytes(), before)

    def test_delete_removes_only_selected_product(self):
        self.write_store(json.dumps(VALID_STORE))
        proc = self.assertOk(self.run_tool("delete", "2", "--yes"))
        self.assertEqual(self.out_json(proc), {"deleted_id": 2})
        store = json.loads(self.read_store())
        self.assertEqual([p["id"] for p in store["products"]], [1])
        self.assertEqual(store["next_id"], 3)

    def test_deleted_id_is_never_reused(self):
        self.write_store(json.dumps(VALID_STORE))
        self.assertOk(self.run_tool("delete", "2", "--yes"))
        proc = self.assertOk(
            self.run_tool("add", "--name", "Eraser", "--price", "0.75", "--quantity", "3")
        )
        self.assertEqual(self.out_json(proc)["id"], 3)


class LowStockTests(ToolTestCase):
    def seed(self):
        self.write_store(
            json.dumps(
                {
                    "next_id": 4,
                    "products": [
                        {"id": 1, "name": "Pen", "price": "1.00", "quantity": 3},
                        {"id": 2, "name": "Desk", "price": "99.00", "quantity": 7},
                        {"id": 3, "name": "Clip", "price": "0.10", "quantity": 0},
                    ],
                }
            )
        )

    def test_default_threshold_is_applied(self):
        self.seed()
        proc = self.assertOk(self.run_tool("low-stock"))
        self.assertEqual([p["id"] for p in self.out_json(proc)], [1, 3])

    def test_threshold_boundary_is_inclusive(self):
        self.seed()
        proc = self.assertOk(self.run_tool("low-stock", "--threshold", "7"))
        self.assertEqual([p["id"] for p in self.out_json(proc)], [1, 2, 3])

    def test_zero_threshold_matches_only_zero_quantity(self):
        self.seed()
        proc = self.assertOk(self.run_tool("low-stock", "--threshold", "0"))
        self.assertEqual([p["id"] for p in self.out_json(proc)], [3])

    def test_no_matches_returns_empty_array(self):
        self.write_store(
            json.dumps(
                {
                    "next_id": 2,
                    "products": [
                        {"id": 1, "name": "Desk", "price": "99.00", "quantity": 50}
                    ],
                }
            )
        )
        proc = self.assertOk(self.run_tool("low-stock", "--threshold", "5"))
        self.assertEqual(self.out_json(proc), [])

    def test_rejects_invalid_thresholds(self):
        self.seed()
        before = self.read_store_bytes()
        for threshold in ("-1", "abc", "2.5", ""):
            self.assertFail(self.run_tool("low-stock", "--threshold", threshold), 2)
        self.assertEqual(self.read_store_bytes(), before)

    def test_low_stock_does_not_modify_file(self):
        self.seed()
        before = self.read_store_bytes()
        self.assertOk(self.run_tool("low-stock"))
        self.assertEqual(self.read_store_bytes(), before)


class FileIntegrityTests(ToolTestCase):
    def test_empty_file_is_an_error(self):
        self.write_store("")
        before = self.read_store_bytes()
        self.assertFail(self.run_tool("list"), 1)
        self.assertEqual(self.read_store_bytes(), before)

    def test_whitespace_file_is_an_error(self):
        self.write_store("  \n  ")
        self.assertFail(self.run_tool("list"), 1)

    def test_malformed_json_is_an_error(self):
        self.write_store("{oops")
        self.assertFail(self.run_tool("list"), 1)

    def test_non_object_top_level_is_an_error(self):
        self.write_store("[1,2]")
        self.assertFail(self.run_tool("list"), 1)

    def test_missing_or_bad_next_id_is_an_error(self):
        self.write_store(json.dumps({"products": []}))
        self.assertFail(self.run_tool("list"), 1)
        self.write_store(json.dumps({"next_id": "2", "products": []}))
        self.assertFail(self.run_tool("list"), 1)
        self.write_store(json.dumps({"next_id": 0, "products": []}))
        self.assertFail(self.run_tool("list"), 1)
        self.write_store(json.dumps({"next_id": True, "products": []}))
        self.assertFail(self.run_tool("list"), 1)

    def test_next_id_must_exceed_every_product_id(self):
        self.write_store(
            json.dumps(
                {
                    "next_id": 2,
                    "products": [
                        {"id": 1, "name": "A", "price": "1.00", "quantity": 1},
                        {"id": 2, "name": "B", "price": "1.00", "quantity": 1},
                    ],
                }
            )
        )
        self.assertFail(self.run_tool("list"), 1)

    def test_duplicate_ids_are_an_error(self):
        self.write_store(
            json.dumps(
                {
                    "next_id": 3,
                    "products": [
                        {"id": 1, "name": "A", "price": "1.00", "quantity": 1},
                        {"id": 1, "name": "B", "price": "1.00", "quantity": 1},
                    ],
                }
            )
        )
        self.assertFail(self.run_tool("list"), 1)

    def test_bad_stored_field_types_are_errors(self):
        cases = [
            {"id": True, "name": "A", "price": "1.00", "quantity": 1},
            {"id": 1, "name": "", "price": "1.00", "quantity": 1},
            {"id": 1, "name": "A", "price": 1.0, "quantity": 1},
            {"id": 1, "name": "A", "price": "1.0", "quantity": 1},
            {"id": 1, "name": "A", "price": "1", "quantity": 1},
            {"id": 1, "name": "A", "price": "1.00", "quantity": True},
            {"id": 1, "name": "A", "price": "1.00", "quantity": "1"},
            {"id": 1, "name": "A", "price": "1.00", "quantity": 1, "note": "x"},
        ]
        for product in cases:
            self.write_store(json.dumps({"next_id": 2, "products": [product]}))
            self.assertFail(self.run_tool("list"), 1)

    def test_extra_top_level_key_is_an_error(self):
        self.write_store(json.dumps({"next_id": 1, "products": [], "extra": 1}))
        self.assertFail(self.run_tool("list"), 1)

    def test_corrupt_file_blocks_mutation(self):
        self.write_store("not json")
        before = self.read_store_bytes()
        self.assertFail(
            self.run_tool("add", "--name", "A", "--price", "1", "--quantity", "1"), 1
        )
        self.assertEqual(self.read_store_bytes(), before)

    def test_file_as_directory_is_an_error(self):
        target = self.dir / "somedir.json"
        target.mkdir()
        self.assertFail(self.run_tool("--file", target, "list"), 1)


class CliContractTests(ToolTestCase):
    def test_file_flag_selects_separate_data_file(self):
        demo = self.dir / "demo.json"
        proc = self.run_tool("--file", demo, "add", "--name", "A", "--price", "1", "--quantity", "1")
        self.assertOk(proc)
        self.assertTrue(demo.exists())
        self.assertFalse(self.data.exists())

    def test_file_flag_must_precede_command(self):
        self.assertFail(
            self.run_tool("add", "--name", "A", "--price", "1", "--quantity", "1",
                          "--file", "demo.json"),
            2,
        )

    def test_persistence_across_invocations(self):
        self.assertOk(
            self.run_tool("add", "--name", "Notebook", "--price", "4.5", "--quantity", "10")
        )
        proc = self.assertOk(self.run_tool("get", "1"))
        self.assertEqual(self.out_json(proc)["name"], "Notebook")
        proc = self.assertOk(self.run_tool("list"))
        self.assertEqual(len(self.out_json(proc)), 1)

    def test_default_file_used_without_flag(self):
        self.assertOk(
            self.run_tool("add", "--name", "A", "--price", "1", "--quantity", "1",
                          cwd=None)
        )
        self.assertTrue(self.data.exists())

    def test_quoted_path_with_spaces(self):
        target = self.dir / "my data.json"
        self.assertOk(
            self.run_tool("--file", target, "add", "--name", "A", "--price", "1",
                          "--quantity", "1")
        )
        self.assertTrue(target.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
