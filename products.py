import argparse
import json
import os
import re
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

DEFAULT_FILE = "products.json"
DEFAULT_LOW_STOCK_THRESHOLD = 5

PRICE_INPUT_RE = re.compile(r"\d+(\.\d{1,2})?")
PRICE_STORED_RE = re.compile(r"\d+\.\d{2}")
NONNEGATIVE_INT_RE = re.compile(r"\d+")
CENT = Decimal("0.01")
PRODUCT_FIELDS = {"id", "name", "price", "quantity"}


class CliError(Exception):
    def __init__(self, message, code=1):
        super().__init__(message)
        self.code = code


def positive_int(text):
    if not NONNEGATIVE_INT_RE.fullmatch(text) or int(text) < 1:
        raise argparse.ArgumentTypeError(f"must be a positive integer, got {text!r}")
    return int(text)


def nonnegative_int(text):
    if not NONNEGATIVE_INT_RE.fullmatch(text):
        raise argparse.ArgumentTypeError(f"must be a nonnegative integer, got {text!r}")
    return int(text)


def parse_name(text):
    name = text.strip()
    if not name:
        raise CliError("invalid name: use at least one non-whitespace character", 2)
    return name


def parse_price(text):
    if not PRICE_INPUT_RE.fullmatch(text):
        raise CliError(
            f"invalid price {text!r}: use digits with at most two decimal places, e.g. 4.50",
            2,
        )
    return format(Decimal(text).quantize(CENT), "f")


def parse_quantity(text):
    if not NONNEGATIVE_INT_RE.fullmatch(text):
        raise CliError(
            f"invalid quantity {text!r}: use a nonnegative whole number", 2
        )
    return int(text)


def empty_store():
    return {"next_id": 1, "products": []}


def validate_store(data, path):
    def bad(reason):
        raise CliError(f"data file {path} has invalid stored data: {reason}", 1)

    if not isinstance(data, dict):
        bad("top level must be a JSON object")
    if set(data) != {"next_id", "products"}:
        bad('top level must contain exactly "next_id" and "products"')
    next_id = data["next_id"]
    if isinstance(next_id, bool) or not isinstance(next_id, int) or next_id < 1:
        bad('"next_id" must be a positive integer')
    products = data["products"]
    if not isinstance(products, list):
        bad('"products" must be a JSON array')
    seen_ids = set()
    for product in products:
        if not isinstance(product, dict):
            bad("each product must be a JSON object")
        if set(product) != PRODUCT_FIELDS:
            bad("each product must contain exactly id, name, price, and quantity")
        product_id = product["id"]
        if isinstance(product_id, bool) or not isinstance(product_id, int) or product_id < 1:
            bad("product id must be a positive integer")
        if product_id in seen_ids:
            bad(f"duplicate product id {product_id}")
        seen_ids.add(product_id)
        name = product["name"]
        if not isinstance(name, str) or not name.strip():
            bad("product name must be text with at least one non-whitespace character")
        price = product["price"]
        if not isinstance(price, str) or not PRICE_STORED_RE.fullmatch(price):
            bad("product price must be a string with exactly two decimal places")
        quantity = product["quantity"]
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 0:
            bad("product quantity must be a nonnegative integer")
    if seen_ids and next_id <= max(seen_ids):
        bad('"next_id" must be greater than every existing product id')


def load_store(path):
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return empty_store()
    except UnicodeDecodeError:
        raise CliError(f"cannot read data file {path}: not valid UTF-8", 1)
    except OSError as exc:
        raise CliError(f"cannot read data file {path}: {exc.strerror or exc}", 1)
    if not raw.strip():
        raise CliError(f"cannot read data file {path}: file is empty", 1)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CliError(f"cannot read data file {path}: not valid JSON ({exc})", 1)
    validate_store(data, path)
    return data


def save_store(path, store):
    text = json.dumps(store, ensure_ascii=False, indent=2) + "\n"
    try:
        fd, temp_name = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
        temp_path = Path(temp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(text)
            os.replace(temp_path, path)
        except BaseException:
            try:
                temp_path.unlink()
            except OSError:
                pass
            raise
    except OSError as exc:
        raise CliError(f"cannot write data file {path}: {exc.strerror or exc}", 1)


def find_product(store, product_id, path):
    for product in store["products"]:
        if product["id"] == product_id:
            return product
    raise CliError(f"product {product_id} not found in {path}", 1)


def product_key(product):
    return product["id"]


def cmd_add(args, path):
    name = parse_name(args.name)
    price = parse_price(args.price)
    quantity = parse_quantity(args.quantity)
    store = load_store(path)
    product = {
        "id": store["next_id"],
        "name": name,
        "price": price,
        "quantity": quantity,
    }
    store["products"].append(product)
    store["next_id"] += 1
    save_store(path, store)
    print(json.dumps(product))


def cmd_list(args, path):
    store = load_store(path)
    products = sorted(store["products"], key=product_key)
    print(json.dumps(products))


def cmd_get(args, path):
    store = load_store(path)
    product = find_product(store, args.id, path)
    print(json.dumps(product))


def cmd_update(args, path):
    if args.name is None and args.price is None and args.quantity is None:
        raise CliError("update requires at least one of --name, --price, --quantity", 2)
    fields = {}
    if args.name is not None:
        fields["name"] = parse_name(args.name)
    if args.price is not None:
        fields["price"] = parse_price(args.price)
    if args.quantity is not None:
        fields["quantity"] = parse_quantity(args.quantity)
    store = load_store(path)
    product = find_product(store, args.id, path)
    product.update(fields)
    save_store(path, store)
    print(json.dumps(product))


def cmd_delete(args, path):
    if not args.yes:
        raise CliError("delete requires --yes to confirm", 2)
    store = load_store(path)
    product = find_product(store, args.id, path)
    store["products"].remove(product)
    save_store(path, store)
    print(json.dumps({"deleted_id": product["id"]}))


def cmd_low_stock(args, path):
    store = load_store(path)
    matches = [p for p in store["products"] if p["quantity"] <= args.threshold]
    matches.sort(key=product_key)
    print(json.dumps(matches))


def build_parser():
    parser = argparse.ArgumentParser(
        prog="products.py",
        description="Manage a small store's product inventory in a local JSON file.",
        allow_abbrev=False,
    )
    parser.add_argument(
        "--file",
        metavar="PATH",
        default=DEFAULT_FILE,
        help=f"path to the JSON data file (default: {DEFAULT_FILE})",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND", required=True)

    add_parser = subparsers.add_parser("add", help="create one product", allow_abbrev=False)
    add_parser.add_argument("--name", required=True, metavar="NAME")
    add_parser.add_argument("--price", required=True, metavar="PRICE")
    add_parser.add_argument("--quantity", required=True, metavar="QTY")
    add_parser.set_defaults(func=cmd_add)

    list_parser = subparsers.add_parser(
        "list", help="print all products as a JSON array", allow_abbrev=False
    )
    list_parser.set_defaults(func=cmd_list)

    get_parser = subparsers.add_parser(
        "get", help="print one product as a JSON object", allow_abbrev=False
    )
    get_parser.add_argument("id", type=positive_int, metavar="ID")
    get_parser.set_defaults(func=cmd_get)

    update_parser = subparsers.add_parser(
        "update", help="change one or more fields of a product", allow_abbrev=False
    )
    update_parser.add_argument("id", type=positive_int, metavar="ID")
    update_parser.add_argument("--name", metavar="NAME")
    update_parser.add_argument("--price", metavar="PRICE")
    update_parser.add_argument("--quantity", metavar="QTY")
    update_parser.set_defaults(func=cmd_update)

    delete_parser = subparsers.add_parser(
        "delete", help="remove a product", allow_abbrev=False
    )
    delete_parser.add_argument("id", type=positive_int, metavar="ID")
    delete_parser.add_argument("--yes", action="store_true", help="confirm deletion")
    delete_parser.set_defaults(func=cmd_delete)

    low_stock_parser = subparsers.add_parser(
        "low-stock",
        help="print products with quantity at or below a threshold",
        allow_abbrev=False,
    )
    low_stock_parser.add_argument(
        "--threshold",
        type=nonnegative_int,
        default=DEFAULT_LOW_STOCK_THRESHOLD,
        metavar="N",
        help="quantity threshold (default: %(default)s)",
    )
    low_stock_parser.set_defaults(func=cmd_low_stock)

    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    path = Path(args.file)
    try:
        args.func(args, path)
    except CliError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.code
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:
        print(f"error: unexpected failure: {exc}", file=sys.stderr)
        sys.exit(1)
