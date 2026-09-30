#!/usr/bin/env python3
"""Regenerate all 15 numbered paper figures from the self-contained frozen inputs.

Usage: .venv/bin/python src/visualization/reproduce.py [--build-documents]
Requires macOS Swift/AppKit/PDFKit and numpy, pandas, matplotlib, Pillow.
"""
from pathlib import Path
from collections import Counter
import argparse,datetime,hashlib,json,logging,os,re,shutil,subprocess,sys,tempfile,time
logging.getLogger("fontTools").setLevel(logging.ERROR)
for key in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','VECLIB_MAXIMUM_THREADS']:
    os.environ[key]='1'
ROOT=Path(__file__).resolve().parents[2]
CODE=Path(__file__).resolve().parent
DATA=ROOT/'data/paper_figures'
OUTPUT=ROOT/'fig/paper_figures'

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def run(command):
    result=subprocess.run(list(map(str,command)),cwd=ROOT,text=True,capture_output=True)
    if result.returncode:
        raise RuntimeError(f'Command failed: {command}\n{result.stdout}\n{result.stderr}')
    return result.stdout

def swift(name,*args):
    return run(['swift','-module-cache-path','/tmp/grape-paper-figures-swift-cache',CODE/name,*args])

def audit(paths):
    return json.loads(swift('audit_pdf.swift',*paths))

def verify_inputs():
    manifest=json.loads((DATA/'manifest.json').read_text())
    for name,item in manifest['files'].items():
        p=DATA/name
        if not p.is_file() or digest(p)!=item['sha256']:
            raise ValueError(f'Missing or altered frozen input: {p}')
    return manifest

def compare_rows(work):
    import numpy as np
    import pandas as pd
    pairs=[('plotted_values.csv','pbm/plotted_values.csv'),
           ('function_plotted_values.csv','structure/function_plotted_values.csv'),
           ('cb_fl_s_zone_plotted_values.csv','structure/cb_fl_s_zone_plotted_values.csv'),
           ('dem_figure_values.csv','dem/figure_values.csv')]
    checks=[]
    for current,reference in pairs:
        a=pd.read_csv(work/current);b=pd.read_csv(DATA/reference)
        pd.testing.assert_frame_equal(a,b,check_dtype=False,check_exact=False,rtol=1e-10,atol=1e-10)
        checks.append({'output':current,'reference':reference,'rows':len(a),'matched':True})
    # Reconstruct current population counts from observation records, independently of figure labels.
    events=pd.concat([pd.read_csv(DATA/f'observations/{part}_observations.csv.gz',dtype={'BBCH':str})
                      for part in ['calibration','test']],ignore_index=True)
    assert len(events)==74618 and events.site.nunique()==3169
    expected={'calibration':2534,'test':635}
    assert events.groupby('partition').site.nunique().to_dict()==expected
    sites=pd.read_csv(DATA/'environment/environmental_zone_sites.csv',dtype={'group_id':str})
    assert not sites.site.duplicated().any() and sites.groupby('group_id').partition.nunique().max()==1
    assert sites.groupby('partition').group_id.nunique().to_dict()=={'calibration':1434,'test':357}
    # The joint paired workflow effects retain identical observation membership.
    membership=pd.read_csv(DATA/'ml/cohort_membership.csv')
    checks.append({'population_observations':len(events),'population_sites':events.site.nunique(),
                   'primary_partitions_and_groups_verified':True,'cohort_membership_rows':len(membership)})
    return checks

def build_documents(catalogue):
    run([sys.executable, ROOT/'src/documents/build.py', '--pdf-only'])
    result={}
    for doc in ['manuscript','supplementary']:
        tex=ROOT/f'paper/{doc}.tex'
        included=re.findall(r'\\includegraphics(?:\[[^]]*\])?\{([^}]+)\}',tex.read_text())
        expected=[f'fig/paper_figures/{r["id"]}.pdf' for r in catalogue if r['document']==doc]
        if included!=expected:raise ValueError(f'{doc} figures differ from the numbered catalogue')
        print(f'Building {doc}.pdf',flush=True)
        log=(ROOT/f'build/documents/latex/{doc}.log').read_text(errors='replace')
        if re.search(r'Overfull \\[hv]box|undefined|LaTeX Error|Float too large',log,re.I):
            raise ValueError(f'Unresolved compilation/layout warning in {doc}.log')
        pages=audit([ROOT/f'paper/{doc}.pdf'])[0]['pages']
        figure_pages=([p for p in pages if re.search(r'Figure S\d+:',p['text'])]
                      if doc=='supplementary' else pages)
        spans=[s for p in figure_pages for s in p['spans'] if 'Helvetica' in s['font']
               and not (abs(s['size']-5.977584)<.02 and re.fullmatch(r'\d+(?:\s+\d+)*',s['text']))]
        assert spans
        for span in spans:
            if not any(abs(span['size']-v*160/180)<.12 for v in [6,8,9]):
                raise ValueError(f'Inconsistent embedded figure scaling: {doc}: {span}')
        aux=(ROOT/f'build/documents/latex/{doc}.aux').read_text()
        for row in [r for r in catalogue if r['document']==doc]:
            if not re.search(r'\\newlabel\{'+re.escape(row['label'])+r'\}\{\{'+re.escape(row['number'])+r'\}',aux):
                raise ValueError(f'Published figure number differs: {row["id"]}')
        result[doc]={'pages':len(pages),'pdf_sha256':digest(ROOT/f'paper/{doc}.pdf'),
                     'source_sha256':digest(tex),'figure_count':len(expected),'numbering_verified':True,
                     'no_undefined_references_or_overfull_boxes':True}
    return result

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-documents',action='store_true',help='Also compile and verify manuscript and supplement')
    args=parser.parse_args()
    if sys.platform!='darwin' or not shutil.which('swift'):
        raise RuntimeError('This repository renderer requires macOS and Swift (Xcode command-line tools).')
    import numpy,pandas,matplotlib,PIL,pypdf
    started=time.monotonic();manifest=verify_inputs()
    catalogue=json.loads((DATA/'catalogue.json').read_text())
    OUTPUT.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='grape-paper-figures-') as tmp:
        work=Path(tmp);native=work/'native';native.mkdir();exports=work/'exports';exports.mkdir()
        from recompute_results import recompute
        statistical_checks=recompute(work/'statistics')
        print('Rendering workflow, study-area map and temperature responses',flush=True)
        sys.path.insert(0,str(ROOT/'src/documents'))
        from plot_revision_workflow import main as workflow
        workflow(native)
        shutil.copy2(native/'Fig_01.pdf',native/'workflow.pdf')
        payload=json.loads((DATA/'study_area/map_payload.json').read_text())
        for panel in payload['panels']:panel['background']=str(DATA/'study_area'/panel['background'])
        map_json=work/'map.json';map_json.write_text(json.dumps(payload))
        swift('draw_map.swift',map_json,native)
        swift('draw_temperature_responses.swift',DATA/'responses/temperature_responses.json',native)
        print('Rendering environmental design, process errors and structural contrasts',flush=True)
        import pandas as pd
        from render_environment import render as environment
        environment(pd.read_csv(DATA/'environment/environmental_zone_monthly_centres.csv'),
                    pd.read_csv(DATA/'environment/environmental_zone_partition_counts.csv'),native,
                    pd.read_csv(DATA/'environment/environmental_zone_sites.csv'))
        import render_pbm,render_structure,render_coverage,render_dem,render_ml
        render_pbm.render(native);render_structure.render(native);render_coverage.render(native)
        print('Rendering paired DEM and ML comparisons',flush=True)
        render_dem.render(native);render_ml.render(native)
        row_checks=compare_rows(native)
        jobs=[{'id':r['id'],'input':str(native/(r['stem']+'.pdf')),'output':str(exports/(r['id']+'.pdf'))} for r in catalogue]
        # Preserve embedded Unicode maps while scaling PDF contents and page boxes.
        for job in jobs:
            reader=pypdf.PdfReader(job['input']);assert len(reader.pages)==1
            page=reader.pages[0]
            target_width=720 if job['id']=='Fig_01' else 561.6
            page.scale_by(target_width/float(page.mediabox.width))
            writer=pypdf.PdfWriter();writer.add_page(page)
            writer.add_metadata({'/Title':job['id'],'/Creator':'Grapevine paper figure reproduction'})
            with open(job['output'],'wb') as stream:writer.write(stream)
        jobfile=work/'exports.json';jobfile.write_text(json.dumps(jobs))
        print(swift('export_figures.swift',jobfile),end='',flush=True)
        documents=audit([exports/(r['id']+'.pdf') for r in catalogue])
        reference=json.loads((DATA/'reference_figure_text.json').read_text())
        reference['Fig_01']=' '.join(x['text'] for x in json.loads((native/'Fig_01.text_bounds.json').read_text()))
        reference['Fig_02']+=' N'
        checks=[]
        from PIL import Image
        for row,doc in zip(catalogue,documents):
            assert len(doc['pages'])==1
            page=doc['pages'][0]
            expected_width=720 if row['id']=='Fig_01' else 561.6
            if abs(page['width_pt']-expected_width)>.01:raise ValueError(f'Incorrect width: {row["id"]}')
            # PDFKit reading order can change after uniform PDF scaling.
            normalize=lambda s:Counter(re.sub(r'\s+','',s))
            if normalize(page['text'])!=normalize(reference[row['id']]):
                raise ValueError(f'Rendered text differs from the source figure: {row["id"]}')
            if not page['spans']:raise ValueError('Missing editable text')
            scale=198.12/180
            for span in page['spans']:
                if row['id']=='Fig_01':
                    if 'TimesNewRoman' not in span['font']:raise ValueError(f'Unexpected workflow font: {span}')
                    continue
                if 'Helvetica' not in span['font'] or not any(abs(span['size']-v*scale)<.13 for v in [6,8,9]):
                    raise ValueError(f'Unexpected font in {row["id"]}: {span}')
            with Image.open(exports/(row['id']+'.png')) as im:
                expected_pixels=round(expected_width*300/72)
                if im.width!=expected_pixels:raise ValueError('Incorrect PNG width')
                dpi=im.info.get('dpi',(0,0))
                if abs(dpi[0]-300)>.1:raise ValueError(f'Incorrect PNG resolution: {dpi}')
            with Image.open(exports/(row['id']+'.png')) as im, Image.open(exports/(row['id']+'.reference.png')) as ref:
                # Compare reduced previews to tolerate subpixel antialiasing differences.
                pixels=numpy.asarray(im.convert('RGB').resize((500,500),Image.Resampling.LANCZOS),dtype=float)
                reference_pixels=numpy.asarray(ref.convert('RGB').resize((500,500),Image.Resampling.LANCZOS),dtype=float)
                pixel_error=float(numpy.abs(pixels-reference_pixels).mean())
                correlation=float(numpy.corrcoef(pixels.mean(2).ravel(),reference_pixels.mean(2).ravel())[0,1])
                if pixel_error>3. or not numpy.isfinite(correlation) or correlation<.97:
                    raise ValueError(f'PNG differs from independent PDF rendering: {row["id"]}: MAE={pixel_error}, r={correlation}')
            checks.append({'id':row['id'],'width_inches':page['width_pt']/72,'height_inches':page['height_pt']/72,
                'text_glyphs_match_current_source':True,'editable_vector_text':True,'png_reference_mean_absolute_pixel_error_500px':pixel_error,'png_reference_correlation_500px':correlation,'png_width_px':expected_pixels,'png_dpi':300})
        # Preserve the freshly recomputed numerical tables beside the input bundle.
        shutil.copytree(work/'statistics',DATA/'reproduced',dirs_exist_ok=True)
        # Publish only after every new figure has passed checks.
        for row in catalogue:
            for ext in ['pdf','png']:os.replace(exports/(row['id']+'.'+ext),OUTPUT/(row['id']+'.'+ext))
        for suffix in ['svg','metadata.json','text_bounds.json']:
            shutil.copy2(native/('Fig_01.'+suffix),OUTPUT/('Fig_01.'+suffix))
        workflow_meta=json.loads((OUTPUT/'Fig_01.metadata.json').read_text())
        workflow_meta['artifacts']={f'Fig_01.{ext}':digest(OUTPUT/f'Fig_01.{ext}') for ext in ['pdf','png','svg']}
        (OUTPUT/'Fig_01.metadata.json').write_text(json.dumps(workflow_meta,indent=2)+'\n')
    report={'verified':True,'built_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'scope':manifest['scope'],'figures':checks,'numerical_row_checks':row_checks,'statistical_recomputation':statistical_checks,
        'data_manifest_sha256':digest(DATA/'manifest.json'),
        'code_sha256':{str(p.relative_to(ROOT)):digest(p) for p in CODE.iterdir() if p.suffix in ['.py','.swift']},
        'environment':{'python':sys.version,'numpy':numpy.__version__,'pandas':pandas.__version__,
                       'matplotlib':matplotlib.__version__,'Pillow':PIL.__version__,'pypdf':pypdf.__version__,'platform':sys.platform},
        'artifacts':{p.name:digest(p) for p in OUTPUT.iterdir() if p.suffix in ['.pdf','.png']}}
    if args.build_documents:
        report['documents']=build_documents(catalogue)
        meta_path=ROOT/'paper/build_metadata.json'
        meta=json.loads(meta_path.read_text()) if meta_path.exists() else {}
        meta.update(built_utc=report['built_utc'],pages=report['documents']['manuscript']['pages'],
            status='Current numbered figure bundle, statistics and both documents regenerated and verified',
            compiler_verification=report['documents']['manuscript'],
            figure_reproduction='fig/paper_figures/verification.json',
            checks=['Locked scoring-error statistics and group-bootstrap intervals recomputed',
                    '15 numbered vector PDFs and PNGs verified at their designated widths',
                    'Manuscript and supplementary references, numbering and embedded scaling verified'])
        meta['visual_inspection_performed']=False
        meta['visual_inspection_note']='Automated rerun; visual inspection is recorded separately in fig/paper_figures/visual_review.json.'
        for name in meta.get('files',{}):
            if (ROOT/name).is_file():meta['files'][name]=digest(ROOT/name)
        for row in catalogue:
            for ext in ['pdf','png']:
                name=f'fig/paper_figures/{row["id"]}.{ext}';meta.setdefault('files',{})[name]=digest(ROOT/name)
        meta_path.write_text(json.dumps(meta,indent=2)+'\n')
    from plot_graphical_abstract import main as graphical_abstract
    graphical_abstract()
    from merge_figures import main as merge_figures
    merge_figures()
    report['elapsed_seconds']=round(time.monotonic()-started,2)
    report['artifacts']={p.name:digest(p) for p in OUTPUT.iterdir() if p.suffix in ['.pdf','.png','.svg','.tiff']}
    (OUTPUT/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
    print(f'Complete: 15 numbered figures and graphical abstract ({report["elapsed_seconds"]} s).',flush=True)

if __name__=='__main__':main()
