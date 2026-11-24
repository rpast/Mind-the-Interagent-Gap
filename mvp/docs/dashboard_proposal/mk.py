import csv, json, yaml, re
r = list(csv.DictReader(open('mvp/out/incident_index.csv')))
def url(x):
    fm = yaml.safe_load(re.match(r'---\n(.*?)\n---', open(x['path']).read(), re.S).group(1))
    s = fm.get('sources') or []
    c = [y for y in s if y.get('source_id') == x['canonical_source']] or s
    return c[0].get('url', '') if c else ''
inc = [dict(k=x['mig_key'], t=x['title'], d=x['occurrence_date'], e=x['evidence_type'], fm=x['failure_mode'],
            i=[i for i in x['instances'].split(';') if i], v=x['verification'], c=x['canonical_source'],
            s=sorted(set(x['sources'].split(';'))), u=url(x)) for x in r]
risks = [dict(id=x['risk_id'], n=x['risk'], k=x['risk_type'], d=x['definition']) for x in csv.DictReader(open('mvp/taxonomy/risks.csv'))]
inst = [dict(id=x['instance_id'], n=x['instance'], r=x['risk_id'], p=x['provenance'], d=x['definition']) for x in csv.DictReader(open('mvp/taxonomy/instances.csv'))]
src = {x['source_id']: dict(n=x['name'], u=x['url']) for x in csv.DictReader(open('mvp/registry/sources.csv'))}
print(json.dumps(dict(inc=inc, risks=risks, inst=inst, src=src), ensure_ascii=False, separators=(',', ':')))
