"""Verify disk storage and the original Flask routes without a model call."""
from datetime import datetime, timezone
import itertools
import json
import random
from types import SimpleNamespace
import sys
from webshop_runtime import ROOT, STORE, Catalog, ProductMap, PriceMap, initialize, sha


def main():
    author, manifest=initialize()
    from web_agent_site.engine.engine import generate_product_prices
    from web_agent_site.engine.goal import get_reward
    sys.path.insert(0,str(ROOT/'src'))
    from react_reproduction.author import webshop_env as original
    catalog=author.all_products
    with (ROOT/'data/cache/webshop-search/resources/documents.jsonl').open() as f:
        first=[json.loads(line)['product'] for line in itertools.islice(f,1000)]
    for i,p in enumerate(first):
        assert catalog[i]==p and author.product_item_dict[p['asin']]==p
    random.seed(42)
    reference_prices=generate_product_prices(first)
    assert all(author.product_prices[k]==v for k,v in reference_prices.items())
    assert sha(STORE/'catalog.sqlite')==manifest['database_sha256']
    # Blank search entries remain purchasable products in the full environment.
    index=json.loads((ROOT/'records/webshop_index_preparation.json').read_text())
    assert index['status']=='index_built_search_smoke_passed'
    assert all(asin in author.product_item_dict for asin in index['empty_document_ids'])
    targets=json.loads((ROOT/'data/webshop_eval_goals.json').read_text())
    assert {x['goal_index'] for x in targets['formal']}==set(range(500))
    assert not {x['goal_index'] for x in targets['formal']} & {x['goal_index'] for x in targets['pilot']}
    flask=author.app.test_client()
    http=[]
    def get(url):
        path=url.removeprefix(original.WEBSHOP_URL) if hasattr(url,'removeprefix') else url[len(original.WEBSHOP_URL):]
        response=flask.get(path)
        assert response.status_code==200, (path,response.status_code)
        text=response.get_data(as_text=True)
        http.append({'url':url,'status':response.status_code,'html':text})
        return SimpleNamespace(text=text,raise_for_status=lambda:None)
    original.HTTP_GET=get
    env=original.webshopEnv()
    checks=[]
    positive_checks=[]
    for t in targets['pilot']:
        i=t['goal_index'];act=f'check_act_fixed_{i}';react=f'check_react_fixed_{i}'
        oa=env.step(act,'reset')[0];orr=env.step(react,'reset')[0]
        assert oa==orr and t['instruction_text'] in oa
        assert author.user_sessions[act]['goal']==author.user_sessions[react]['goal']==author.goals[i]
        ob,_,_=env.step(act,'search[apple cinnamon]')
        asins=env.sessions[act]['asins'];assert len(asins)>0
        asin=asins[0]
        env.step(act,f'click[{asin}]')
        env.step(act,'click[Description]')
        env.step(act,'click[< Prev]')
        option_types=env.sessions[act].get('option_types',{})
        if option_types:env.step(act,f'click[{next(iter(option_types))}]')
        options=env.sessions[act].get('options',{})
        expected=get_reward(author.product_item_dict[asin],author.goals[i],price=author.product_prices[asin],options=options)
        ob,reward,done=env.step(act,'click[Buy Now]')
        assert done and reward==expected and author.user_sessions[act]['reward']==reward
        checks.append({'goal_index':i,'equal_method_initial_observation':True,'purchased_asin':asin,
                       'reward':reward,'author_reward_equal':True})
        # Backend-only oracle fixture, never a model trajectory or reported score.
        # Exercise a positive reward as well as an unrelated zero-reward purchase.
        oracle=f'check_oracle_fixed_{i}'
        env.step(oracle,'reset')
        goal=author.goals[i];product=author.product_item_dict[goal['asin']]
        selected={name:value for name,values in product['options'].items()
                  for value in values if value in goal['goal_options']}
        expected=get_reward(product,goal,price=author.product_prices[goal['asin']],options=selected)
        _,info=original.webshop_text(session=oracle,page_type='end',asin=goal['asin'],options=selected)
        assert expected>0 and info['reward']==expected
        positive_checks.append({'goal_index':i,'reward':info['reward'],'author_reward_equal':True,
                                'scope':'Oracle backend fixture only; no model call or benchmark result'})
    raw=ROOT/'data/cache/webshop-runtime-http.json'
    raw.write_text(json.dumps(http,ensure_ascii=False,indent=2)+'\n')
    result={'status':'passed','recorded_at_utc':datetime.now(timezone.utc).isoformat(),
            'products':len(catalog),'goals':len(author.goals),'source_manifest':manifest,
            'exact_product_checks':1000,'exact_price_checks':1000,'empty_products_retained':len(index['empty_document_ids']),
            'routes':['reset','search','item','Description','previous','option','buy'],
            'pilot_goal_checks':checks,'positive_reward_checks':positive_checks,'model_calls':0,
            'http_trace':str(raw.relative_to(ROOT)),'http_trace_sha256':sha(raw)}
    (ROOT/'records/webshop_runtime_check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':'passed','products':len(catalog),'goals':len(author.goals),'checks':checks}))


if __name__=='__main__':main()
