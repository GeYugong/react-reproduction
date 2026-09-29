"""Freeze full-catalog prices/goals using original author functions and seed 42.

The offset database avoids loading the 6.8 GB converted JSONL into RAM.
All products (including the 60 with empty searchable contents) remain present.
"""
from datetime import datetime, timezone
import hashlib
import json
import random
import sqlite3
from webshop_runtime import ROOT, STORE, DOCUMENTS, sha, setup_author


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def main():
    setup_author()
    from web_agent_site.engine.engine import generate_product_prices
    from web_agent_site.engine.goal import get_goals
    STORE.mkdir(parents=True, exist_ok=True)
    if (STORE / 'manifest.json').exists():
        raise RuntimeError('Frozen store already exists; validate it without rebuilding')
    path = STORE / 'catalog.partial.sqlite'
    if path.exists(): raise RuntimeError('Partial store exists; preserve and inspect before retry')
    db = sqlite3.connect(str(path))
    db.execute('create table products(ordinal integer primary key, asin text unique not null, offset integer not null, attributes text not null)')
    db.execute('create table prices(asin text primary key, price real not null)')
    goals_products = []
    state = {'status':'building', 'products':0, 'price_seed':42, 'goal_shuffle_seed':233,
             'started_at_utc':datetime.now(timezone.utc).isoformat()}
    record = ROOT / 'records/webshop_store_preparation.json'
    checksum = hashlib.sha256()
    def products():
        offset = 0
        with DOCUMENTS.open('rb') as f:
            for i, line in enumerate(f):
                checksum.update(line)
                p = json.loads(line)['product']
                db.execute('insert into products values(?,?,?,?)', (i,p['asin'],offset,json.dumps(p['Attributes'])))
                offset += len(line)
                if 'instructions' in p: goals_products.append(p)
                state['products'] = i + 1
                if (i+1) % 10000 == 0:
                    db.commit(); save(record, state)
                yield p
    # This is a single call over the original complete order: RNG draws match
    # original generate_product_prices(all_products), not per-batch restarts.
    random.seed(42)
    prices = generate_product_prices(products())
    exported = json.loads((DOCUMENTS.parent.parent / 'export_manifest.json').read_text())
    assert state['products'] == exported['product_count'] == 1181430
    assert checksum.hexdigest() == exported['documents_sha256']
    db.executemany('insert into prices values(?,?)', prices.items())
    db.commit()
    assert db.execute('pragma integrity_check').fetchone()[0] == 'ok'
    db.close()
    path.replace(STORE / 'catalog.sqlite')
    # Author get_human_goals immediately skips products without instructions.
    # Filtering those entries preserves iteration order and random draw order.
    goals = get_goals(goals_products, prices)
    random.seed(233)
    random.shuffle(goals)
    save(STORE / 'goals.json', goals)
    state.update(status='completed', goals=len(goals), products_with_instructions=len(goals_products),
                 documents_sha256=checksum.hexdigest(), goals_sha256=sha(STORE / 'goals.json'),
                 database_sha256=sha(STORE / 'catalog.sqlite'),
                 completed_at_utc=datetime.now(timezone.utc).isoformat(),
                 source='Original generate_product_prices and get_goals; seed 42 added before prices for reproducibility; original goal shuffle seed 233 retained',
                 formal_indices=list(range(500)), pilot_indices=[500,501])
    save(STORE / 'manifest.json', state)
    save(record, state)
    targets=[{'goal_index':i,'goal_sha256':hashlib.sha256(json.dumps(goals[i],sort_keys=True).encode()).hexdigest(),
              'instruction_text':goals[i]['instruction_text']} for i in range(502)]
    save(ROOT / 'data/webshop_eval_goals.json', {'source_manifest':state, 'formal':targets[:500], 'pilot':targets[500:]})
    print(json.dumps({'status':state['status'],'products':state['products'],'goals':len(goals)}))


if __name__ == '__main__': main()
