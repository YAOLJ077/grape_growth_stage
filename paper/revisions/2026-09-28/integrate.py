from pathlib import Path
import sys, json, zipfile, re, uuid, copy, math, hashlib
sys.path.insert(0,'build/comment_revision/lib')
from lxml import etree as E
import fitz
ROOT=Path.cwd(); B=ROOT/'build/comment_revision'; R=ROOT/'paper/revisions/2026-09-28'
W='http://schemas.openxmlformats.org/wordprocessingml/2006/main'; M='http://schemas.openxmlformats.org/officeDocument/2006/math'; NS={'w':W,'m':M}
def tag(s):return '{'+W+'}'+s
def el(s,**attrs):
 n=E.Element(tag(s))
 for k,v in attrs.items():n.set(tag(k),str(v))
 return n
def txt(n):return ''.join(n.xpath('.//w:t/text()',namespaces=NS))
def norm(s):return ' '.join(s.replace('\xa0',' ').split())
def run(s,pr=None):
 r=el('r')
 if pr is not None:r.append(copy.deepcopy(pr))
 t=el('t');t.text=s;t.set('{http://www.w3.org/XML/1998/namespace}space','preserve');r.append(t);return r
z=zipfile.ZipFile(B/'manuscript_before_revision.docx');files={k:z.read(k) for k in z.namelist()};root=E.fromstring(files['word/document.xml']);body=root.find('w:body',NS);ps={i:p for i,p in enumerate(body.findall('w:p',NS),1)}
# Reuse the self-contained citation metadata supplied in the manuscript.
library={}; items={}
for node in root.findall('.//w:instrText',NS):
 code=node.text or ''
 if 'CSL_CITATION' not in code:continue
 d=json.loads(code[code.index('{'):].strip()); ci=d['citationItems'];display=norm(d['properties']['plainCitation'])
 for item in ci:items[item['id']]=item
 labels=display.strip('()').split('; ')
 if len(labels)==len(ci) and all(',' in l for l in labels):
  for label,item in zip(labels,ci):library[label]=item
for item in items.values():
 a=item['itemData']['author'];year=str(item['itemData']['issued']['date-parts'][0][0]); names=[x.get('family',x.get('literal','')) for x in a]
 name=names[0] if len(names)==1 else (' and '.join(names) if len(names)==2 else names[0]+' et al.')
 library.setdefault(name+', '+year,item)
# Cite provider datasets directly for data access.
providers={
 'Deutscher Wetterdienst, n.d.':('dwd_phenology','Phenological observations in Germany','https://opendata.dwd.de/climate_environment/CDC/observations_germany/phenology/','Deutscher Wetterdienst'),
 'PEP725, n.d.':('pep725','Pan European Phenology database','https://pep725.eu/','PEP725')}
for label,(key,title,url,author) in providers.items():
 item={'id':'revision/'+key,'uris':['urn:uuid:'+str(uuid.uuid5(uuid.NAMESPACE_URL,url))],'itemData':{'id':'revision/'+key,'type':'dataset','title':title,'author':[{'literal':author}],'URL':url}}
 library[label]=item;items[item['id']]=item

def fields(display,cis,pr,narrative=False):
 ci=copy.deepcopy(cis)
 for i in ci:
  i.pop('suppress-author',None)
  if narrative:i['suppress-author']=True
 d={'citationID':uuid.uuid4().hex[:8],'properties':{'plainCitation':display,'noteIndex':0},'citationItems':ci,'schema':'https://github.com/citation-style-language/schema/raw/master/csl-citation.json'}
 nodes=[]
 for kind in ['begin','instruction','separate','display','end']:
  if kind=='display':nodes.append(run(display,pr));continue
  r=el('r')
  if kind=='instruction':
   it=el('instrText');it.text=' ADDIN ZOTERO_ITEM CSL_CITATION '+json.dumps(d,ensure_ascii=False,separators=(',',':'))+' ';it.set('{http://www.w3.org/XML/1998/namespace}space','preserve');r.append(it)
  else:r.append(el('fldChar',fldCharType=kind,dirty='false'))
  nodes.append(r)
 return nodes
replacements={};deletes=[]
for f in ['intro_revisions','methods_revisions','discussion_revisions']:
 d=json.loads((R/(f+'.json')).read_text());replacements.update({int(k):v for k,v in d['replacements'].items()});deletes.extend(d.get('delete',[]))
replacements[17]=replacements[17].replace('(García de Cortázar-Atauri et al., 2009; Fila et al., 2014)','(Fila et al., 2014)')
replacements[33]=replacements[33].replace('(DWD; Kaspar et al., 2014)','(DWD; Deutscher Wetterdienst, n.d.)').replace('(Templ et al., 2018; accessed 1 July 2026)','(PEP725, n.d.; accessed 1 July 2026)')
replacements[44]+=' Duplicate dates, nonfinite values, coordinate agreement and the correction equation were checked before fitting.'
replacements[46]+=' Observation-network elevations are retained for comparison only.'
replacements[83]=replacements[83].replace('k-means clustering','k-means clustering (five clusters, 20 initializations; seed 20260909)')
replacements[84]=replacements[84].replace('use their mean standardized unique-cell profile for zone assignment','are assigned to the nearest centroid using their mean standardized unique-cell profile').replace('Within-zone allocation','Each zone contains at least five groups. Seeded within-zone allocation targets 20% test sites and').replace('and preserves','preserves')
replacements[84]=replacements[84].replace('sites preserves','sites while preserving')
replacements[162]=replacements[162].replace(' Its contribution lies in this process-guided residual formulation, rather than a new base neural architecture.','')
replacements[163]=replacements[163].replace(' No such ablation result is implied by the aggregate gains.','')
replacements[190]='Phenological observations are available through TEMPO, the DWD Climate Data Center and PEP725 under the respective providers’ access and licence conditions. ERA5-Land and Copernicus DEM are available from the cited repositories. Data supporting the findings will be made available on request, subject to these conditions.'
# Preserve every original comment, moving comments on removed prose to the condensed scope section.
for i in deletes:
 p=ps[i]
 for n in list(p):
  if n.tag in [tag('commentRangeStart'),tag('commentRangeEnd')] or n.find('.//w:commentReference',NS) is not None:
   ps[167].append(copy.deepcopy(n))
# Math tokens map to original editable OMML nodes.
aliases={50:['T_DEM,d','T_RAW,d','z_site','z_grid'],54:['max(T−0,0)'],66:['H07','H65','H81','H89'],74:['h','k','h','k','h'],83:['k'],89:['MAE_RAW−MAE_DEM'],90:['x≤q1/3','q1/3<x≤q2/3','q2/3']}
math_used={}; unresolved=[]
def rewrite(p,text,i=None):
 pr=next((r.find('w:rPr',NS) for r in p.findall('w:r',NS) if txt(r).strip()),None)
 # Use paragraph body style rather than inheriting comment-reference superscript.
 if pr is not None:
  pr=copy.deepcopy(pr)
  for n in pr.findall('w:vertAlign',NS):pr.remove(n)
 starts=[copy.deepcopy(n) for n in p.findall('w:commentRangeStart',NS)]
 ends=[copy.deepcopy(n) for n in p.findall('w:commentRangeEnd',NS)]
 refs=[copy.deepcopy(n) for n in p.findall('w:r',NS) if n.find('w:commentReference',NS) is not None]
 spans=[]
 for m in re.finditer(r'\(([^()]*)\)',text):
  inside=m[1];parts=inside.split('; '); selected=[];found=[]
  for part in parts:
   if part in library:selected.append(library[part]);found.append(part)
  if selected:
   # Keep provider abbreviations and access information outside citation fields.
   if len(found)==len(parts):spans.append((m.start(),m.end(),fields(m[0],selected,pr)))
   else:
    for part in found:
     start=text.index(part,m.start(),m.end());spans.append((start,start+len(part),fields(part,[library[part]],pr)))
  elif re.fullmatch(r'\d{4}[ab]?',inside):
   choices=[(label,item) for label,item in library.items() if label.endswith(', '+inside) and text[:m.start()].rstrip().endswith(label.rsplit(', ',1)[0])]
   if choices:spans.append((m.start(),m.end(),fields(m[0],[choices[0][1]],pr,True)))
  elif re.search(r'et al\.| and .*?, \d{4}',inside):unresolved.append((i,inside))
 maths=p.findall('.//m:oMath',NS)
 if i in aliases:
  used=set();after=0
  for token,node in zip(aliases[i],maths):
   matches=list(re.finditer(r'(?<![\w])'+re.escape(token)+r'(?![\w])',text))
   match=next((m for m in matches if (m.start(),m.end()) not in used and not any(a<=m.start()<b for a,b,_ in spans)),None)
   if match:
    used.add((match.start(),match.end()));spans.append((match.start(),match.end(),[copy.deepcopy(node)]))
   else:raise AssertionError(('math token missing',i,token))
  math_used[i]=len(used)
 for n in list(p):
  if n.tag!=tag('pPr'):p.remove(n)
 for n in starts:p.append(n)
 pos=0
 for a,b,nodes in sorted(spans,key=lambda s:s[0]):
  assert a>=pos,(i,a,pos)
  if a>pos:p.append(run(text[pos:a],pr))
  for n in nodes:p.append(n)
  pos=b
 if pos<len(text):p.append(run(text[pos:],pr))
 for n in ends+refs:p.append(n)
for i,t in replacements.items():rewrite(ps[i],t,i)
assert not unresolved,unresolved
# Retain italic caption text with only its figure label bold.
for rr in ps[26].findall('w:r',NS):
 rp=rr.find('w:rPr',NS)
 if rp is not None:
  for bb in rp.findall('w:b',NS):rp.remove(bb)
first=next(rr for rr in ps[26].findall('w:r',NS) if txt(rr))
caption_text=txt(first);assert caption_text.startswith('Fig. 1.')
pr=first.find('w:rPr',NS);prefix=run('Fig. 1.',pr)
if prefix.find('w:rPr',NS) is None:prefix.insert(0,el('rPr'))
prefix.find('w:rPr',NS).append(el('b'))
ps[26].insert(ps[26].index(first),prefix)
first.find('w:t',NS).text=caption_text[7:]
# Keep the abstract and keywords on one page without altering approved wording.
ppr=ps[12].find('w:pPr',NS)
if ppr is None:ppr=el('pPr');ps[12].insert(0,ppr)
spacing=ppr.find('w:spacing',NS)
if spacing is None:spacing=el('spacing');ppr.append(spacing)
spacing.set(tag('line'),'360');spacing.set(tag('lineRule'),'auto')
# Convert the former discussion heading to body prose.
ppr=ps[171].find('w:pPr',NS)
if ppr is not None:ps[171].remove(ppr)
ps[171].insert(0,copy.deepcopy(ps[170].find('w:pPr',NS)))
for rr in ps[171].findall('w:r',NS):
 old=rr.find('w:rPr',NS)
 if old is not None:rr.remove(old)
 ref=ps[170].find('w:r/w:rPr',NS)
 if ref is not None:rr.insert(0,copy.deepcopy(ref))
for i in deletes:body.remove(ps[i])
# Temperature-input motivation precedes the residual-learning rationale.
body.remove(ps[20]);body.insert(body.index(ps[18]),ps[20])
contrib='Linjia Yao: Data curation, Methodology, Writing – original draft. Gang Zhao: Methodology, Funding acquisition, Writing – original draft, Writing – review & editing. Qiang Yu: Funding acquisition, Supervision. Bin Chen, Yuxuan Li, Amit Kumar Srivastava, Linchao Li, Xuefei Wang, Simone Bregaglio and Hao Feng: Writing – review & editing.'
p=copy.deepcopy(ps[186]);rewrite(p,contrib);body.insert(body.index(ps[184])+1,p)
# Reconcile references with all surviving citation fields.
used={}
for node in body.findall('.//w:instrText',NS):
 code=node.text or ''
 if 'CSL_CITATION' in code:
  data=json.loads(code[code.index('{'):].strip())
  for item in data['citationItems']:used[item['id']]=item
removed=[]; matched=set()
for i in range(194,239):
 p=ps[i];s=norm(txt(p));match=[]
 for key,item in used.items():
  d=item['itemData'];doi=d.get('DOI','');title=d.get('title','')
  if (doi and doi.lower() in s.lower()) or (title and norm(title).lower() in s.lower()):match.append(key)
 if not match:
  assert not p.findall('.//w:fldChar',NS),('bibliography boundary',i)
  body.remove(p);removed.append(i)
 else:matched.update(match)
for label,(key,title,url,author) in providers.items():
 p=copy.deepcopy(ps[210]);rewrite(p,f'[dataset] {author}, n.d. {title}. {url}'+(' Accessed 1 July 2026.' if key=='pep725' else ''))
 # Alphabetical placement among existing references.
 anchor=ps[203] if key=='dwd_phenology' else ps[226]
 body.insert(body.index(anchor),p);matched.add('revision/'+key)
assert set(used)==matched,(set(used)-matched)
# Figure 2: vector north arrow, aligned with geographic north in the Lambert projection.
outdir=ROOT/'fig/paper_figures/ylj_revision'; outdir.mkdir(exist_ok=True)
payload=json.loads((ROOT/'data/paper_figures/study_area/map_payload.json').read_text());panel=payload['panels'][0]
rad=math.pi/180;p1,p2,p0=43*rad,59*rad,50*rad;n=math.log(math.cos(p1)/math.cos(p2))/math.log(math.tan(math.pi/4+p2/2)/math.tan(math.pi/4+p1/2));f=math.cos(p1)*math.tan(math.pi/4+p1/2)**n/n;radius=6371008.8;rho0=radius*f/math.tan(math.pi/4+p0/2)**n
pdf=fitz.open(ROOT/'fig/paper_figures/Fig_02.pdf');page=pdf[0];scale=page.rect.width/(180*72/25.4)
def pos(lon,lat):
 rho=radius*f/math.tan(math.pi/4+lat*rad/2)**n;theta=n*(lon-10)*rad;x,y=rho*math.sin(theta),rho0-rho*math.cos(theta);a,b,c,d=panel['bounds'];fx,fy,fw,fh=panel['frame'];return fitz.Point((fx+(x-a)/(c-a)*fw)*scale,(fy+(d-y)/(d-b)*fh)*scale)
base=pos(-3,61);north=pos(-3,61.2);dx,dy=north.x-base.x,north.y-base.y;length=math.hypot(dx,dy);u=fitz.Point(dx/length,dy/length);tip=base+u*17;perp=fitz.Point(-u.y,u.x);ink=(.15,.22,.27)
page.draw_line(base,tip,color=ink,width=1.2)
shape=page.new_shape();shape.draw_polyline([tip,tip-u*5+perp*2.2,tip-u*5-perp*2.2,tip]);shape.finish(color=ink,fill=ink);shape.commit();page.insert_text((tip.x-2.7,tip.y-3),'N',fontsize=8,fontname='hebo',color=ink)
pdf.save(outdir/'Fig_02.pdf');page.get_pixmap(matrix=fitz.Matrix(300/72,300/72),alpha=False).save(outdir/'Fig_02.png');pdf.close()
# Replace the two targeted images; preserve all other image bytes.
for num in (1,2):files[f'word/media/image{num}.png']=(outdir/f'Fig_0{num}.png').read_bytes()
# Preserve Fig. 1 width and use the new intrinsic aspect ratio.
WP='http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing';A='http://schemas.openxmlformats.org/drawingml/2006/main'
for n in ps[25].iter():
 if n.tag=='{'+WP+'}extent':
  width=int(n.get('cx'));n.set('cy',str(round(width*.88)))
 if n.tag=='{'+A+'}ext' and n.get('cx'):
  n.set('cy',str(round(int(n.get('cx'))*.88)))
# Exact invariants before writing.
assert txt(ps[1])==txt(E.fromstring(files['word/document.xml']).find('w:body',NS).findall('w:p',NS)[0])
assert len(root.findall('.//m:oMath',NS))==43
assert len(root.findall('.//w:tbl',NS))==4
comments=E.fromstring(files['word/comments.xml']);ids={x.get(tag('id')) for x in comments.findall('w:comment',NS)}
for name in ['commentRangeStart','commentRangeEnd','commentReference']:
 vals=[x.get(tag('id')) for x in root.findall('.//w:'+name,NS)];assert set(vals)==ids and len(vals)==len(ids),(name,vals,ids)
assert 'Front. Plant Sci.' not in txt(root)
files['word/document.xml']=E.tostring(root,xml_declaration=True,encoding='UTF-8',standalone=True)
target=ROOT/'paper/grape_pheno_manuscript_ylj.docx'
with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as out:
 for k,v in files.items():out.writestr(k,v)
report={'replaced_paragraphs':len(replacements),'removed_body_paragraphs':deletes,'removed_uncited_references':removed,'citation_items':len(used),'math_objects':43,'tables':4,'comments_preserved':len(ids),'sha256':hashlib.sha256(target.read_bytes()).hexdigest()}
(B/'integration_report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
(B/'revised_paragraphs.txt').write_text('\n'.join(txt(p) for p in body.findall('w:p',NS)))
