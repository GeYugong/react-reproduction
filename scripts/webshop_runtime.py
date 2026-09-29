"""Disk-backed storage for the unchanged pinned WebShop Flask environment.

Only storage and paths are adapted. Product conversion, retrieval, templates,
goal construction and rewards remain the original author's implementations.
"""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
from collections.abc import Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / 'data/cache/webshop-store'
DOCUMENTS = ROOT / 'data/cache/webshop-search/resources/documents.jsonl'


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''): h.update(block)
    return h.hexdigest()


def setup_author():
    java = json.loads((ROOT / 'records/java_runtime.json').read_text())['java_home']
    os.environ['JAVA_HOME'] = java
    os.environ['JVM_PATH'] = java + '/lib/server/libjvm.so'
    os.environ['JAVA_TOOL_OPTIONS'] = '-Xmx2g'
    sys.path.insert(0, str(ROOT / 'vendor/WebShop'))


class Catalog(Sequence):
    def __init__(self):
        self.db = sqlite3.connect('file:' + str(STORE / 'catalog.sqlite') + '?mode=ro', uri=True)
        self.count = self.db.execute('select count(*) from products').fetchone()[0]

    def __len__(self): return self.count

    def read(self, offset):
        with DOCUMENTS.open('rb') as f:
            f.seek(offset)
            return json.loads(f.readline())['product']

    def __getitem__(self, i):
        if isinstance(i, slice): return [self[j] for j in range(*i.indices(len(self))) ]
        if i < 0: i += self.count
        row = self.db.execute('select offset from products where ordinal=?', (i,)).fetchone()
        if row is None: raise IndexError(i)
        return self.read(row[0])

    def __iter__(self):
        with DOCUMENTS.open('rb') as f:
            for line in f: yield json.loads(line)['product']


class ProductMap(Mapping):
    def __init__(self, catalog): self.catalog = catalog
    def __len__(self): return len(self.catalog)
    def __iter__(self): return (r[0] for r in self.catalog.db.execute('select asin from products order by ordinal'))
    def __contains__(self, asin):
        return self.catalog.db.execute('select 1 from products where asin=?', (asin,)).fetchone() is not None
    def __getitem__(self, asin):
        row = self.catalog.db.execute('select offset from products where asin=?', (asin,)).fetchone()
        if row is None: raise KeyError(asin)
        return self.catalog.read(row[0])


class PriceMap(Mapping):
    def __init__(self, catalog): self.catalog = catalog
    def __len__(self): return len(self.catalog)
    def __iter__(self): return iter(ProductMap(self.catalog))
    def __getitem__(self, asin):
        row = self.catalog.db.execute('select price from prices where asin=?', (asin,)).fetchone()
        if row is None: raise KeyError(asin)
        return row[0]


class AttributeMap:
    def __init__(self, catalog): self.catalog = catalog
    def __getitem__(self, attr):
        return {r[0] for r in self.catalog.db.execute(
            'select asin from products, json_each(products.attributes) where json_each.value=?', (attr,))}


def initialize():
    setup_author()
    from web_agent_site import app as author
    from pyserini.search.lucene import LuceneSearcher
    manifest = json.loads((STORE / 'manifest.json').read_text())
    assert manifest['status'] == 'completed' and manifest['products'] == 1181430
    assert sha(STORE / 'goals.json') == manifest['goals_sha256']
    catalog = Catalog()
    assert len(catalog) == manifest['products']
    author.all_products = catalog
    author.product_item_dict = ProductMap(catalog)
    author.product_prices = PriceMap(catalog)
    author.attribute_to_asins = AttributeMap(catalog)
    author.search_engine = LuceneSearcher(str(ROOT / 'data/cache/webshop-search/indexes'))
    assert author.search_engine.num_docs == 1181370
    author.goals = json.loads((STORE / 'goals.json').read_text())
    author.weights = [g['weight'] for g in author.goals]
    # Original done() print dumps all sessions; route behavior is unchanged.
    author.print = lambda *args, **kwargs: None
    return author, manifest
