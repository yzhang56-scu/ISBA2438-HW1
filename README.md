# ISBA 2438 — Assignment 1: CLI Inventory Tool

A Python 3 command-line tool that manages a small store's product inventory in a
local JSON file. Built with only the Python standard library — no third-party
packages required.

## Getting Started

Requires Python 3. Run commands from a terminal:

```
python3 products.py [--file PATH] COMMAND [OPTIONS]
```

On Windows, `py -3` may replace `python3`. The optional `--file PATH` flag must
appear **before** the command and selects the JSON data file; the default is
`products.json` in the current working directory.

## Commands

| Command | Description |
|---|---|
| `add --name NAME --price PRICE --quantity QTY` | Create one product; prints the new product as JSON. |
| `list` | Print all products as a JSON array sorted by ID; `[]` when empty. |
| `get ID` | Print one product as a JSON object. |
| `update ID [--name NAME] [--price PRICE] [--quantity QTY]` | Change one or more fields; prints the updated product. |
| `delete ID --yes` | Remove a product; prints `{"deleted_id": ID}`. |
| `low-stock [--threshold N]` | **Custom feature** — print products with quantity at or below a threshold. |

Run `python3 products.py --help` or `python3 products.py COMMAND --help` for
usage details.

## Custom Feature: Low-Stock Report

### Who it helps

A store owner reordering stock cares about one question: *which products are
running low right now?* The core commands can only list everything or look up
one product by ID, neither of which answers that question. The `low-stock`
command scans the inventory and returns exactly the products whose quantity has
fallen to or below a threshold, so the owner can see what to reorder without
reading through the whole list. The default threshold of 5 works for a quick
daily check, and `--threshold` lets the owner raise or lower the cutoff — for
example, `--threshold 0` to catch only out-of-stock items.

### Command syntax

```
python3 products.py low-stock [--threshold N]
```

- `N` is a nonnegative whole number (default: `5`).
- A product matches when its quantity is **at or below** the threshold
  (inclusive boundary).
- Matching products are printed as a JSON array sorted by ID; `[]` if none match.

### Example

Fully runnable from an empty directory (products are created first, then reported):

```
$ python3 products.py add --name "Pen" --price 1.00 --quantity 3
{"id": 1, "name": "Pen", "price": "1.00", "quantity": 3}
$ python3 products.py add --name "Desk" --price 99.00 --quantity 7
{"id": 2, "name": "Desk", "price": "99.00", "quantity": 7}
$ python3 products.py add --name "Clip" --price 0.10 --quantity 0
{"id": 3, "name": "Clip", "price": "0.10", "quantity": 0}
$ python3 products.py low-stock --threshold 5
[{"id": 1, "name": "Pen", "price": "1.00", "quantity": 3}, {"id": 3, "name": "Clip", "price": "0.10", "quantity": 0}]
```

Edge case — no products at or below the threshold (a separate data file whose
only product, quantity 7, is above the default threshold of 5):

```
$ python3 products.py --file fresh.json add --name "Desk" --price 99.00 --quantity 7
{"id": 1, "name": "Desk", "price": "99.00", "quantity": 7}
$ python3 products.py --file fresh.json low-stock
[]
```

Invalid input (negative or non-integer threshold) exits with code 2 and an
error message on standard error:

```
$ python3 products.py low-stock --threshold -1
usage: products.py low-stock [-h] [--threshold N]
products.py low-stock: error: argument --threshold: must be a nonnegative integer, got '-1'
```

## Data File

Inventory is stored as UTF-8 JSON with a `next_id` counter and a `products`
array. IDs start at 1, are assigned automatically, and are never reused.
Prices are stored as strings with exactly two decimal places.

```json
{
  "next_id": 2,
  "products": [
    {"id": 1, "name": "Notebook", "price": "4.50", "quantity": 10}
  ]
}
```

A missing data file is treated as an empty store; the file is created by the
first successful `add`. Read-only commands (`list`, `get`, `low-stock`, and
`--help`) never create or modify the file.

## Exit Codes

| Code | Meaning |
|---|---|
| 0 | Successful command (including an empty result or a help request) |
| 1 | Product ID not found, invalid stored data, or a file read/write failure |
| 2 | Invalid syntax, missing arguments, or invalid input values |

Error messages go to standard error; successful commands print only their JSON
result to standard output.

## Tests

`test_products.py` runs the tool as a subprocess and checks the command
contract, persistence, file-integrity rules, and the low-stock feature:

```
python test_products.py
```
