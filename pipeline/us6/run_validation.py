"""Public US6 pipeline function and standalone CLI."""
from __future__ import annotations
import argparse
import json
from copy import deepcopy
from pathlib import Path
if __package__:
    from .codebook import load_dictionary, find_codebook_issues
    from .input_adapter import normalize_survey
    from .validator import find_issues, validate_document as validate_legacy, _get, MISSING, _has_content
else:
    from codebook import load_dictionary, find_codebook_issues
    from input_adapter import normalize_survey
    from validator import find_issues, validate_document as validate_legacy, _get, MISSING, _has_content


def _source_path(path,mapping):
    if path in mapping:
        return mapping[path]
    # Engine locations not mapped explicitly must not point at invented originals.
    raise ValueError(f'No source mapping for validation location: {path}')


def _label(path):
    category,*parts=path
    suffix=''
    for part in parts:
        suffix += f'[{part}]' if isinstance(part,int) else ('.' if suffix else '')+part
    return ('Page 1' if category=='main' else 'Page 3')+': '+suffix


def validate_survey(main: dict, coded: dict, *, notes=None, survey_id=None, codebook_path=None) -> dict:
    """Call immediately after both structured page JSONs for ONE survey exist.

    Returns original page data with flags/status and a compact relationship list.
    Reads the optional local codebook; no network calls or input mutations.
    """
    document={'survey_id':survey_id,'main':main,'coded':coded}
    if notes is not None:
        document['notes']=notes
    return validate_record(document, codebook_path=codebook_path)


def validate_record(document:dict, *, codebook_path=None) -> dict:
    normal,mapping,warnings=normalize_survey(document)
    issues=find_issues(normal)
    for issue in issues:
        for field in issue['fields']:
            field['path'] = _source_path(field['path'], mapping)
    dictionary, codebook_warnings = load_dictionary(codebook_path)
    warnings.extend(codebook_warnings)
    for field, special_codes in [('age_of_head', {0}), ('age_of_house', {0, 98}), ('length_of_residence', {99})]:
        value = document['coded'].get(field)
        if isinstance(value, (str, int)) and not isinstance(value, bool) and str(value).strip().isdigit() and int(str(value).strip()) in special_codes:
            warnings.append(f'coded.{field} uses a valid unknown/no-exact-value code; exact cross-page age/duration comparison is not performed.')
    issues.extend(find_codebook_issues(document, dictionary))
    output=deepcopy(document)
    compact=[]
    statuses=[]
    seen=set()
    for issue in issues:
        item={k:v for k,v in issue.items() if k!='fields'}
        item['fields']={}
        for field in issue['fields']:
            path=field['path']
            raw=_get(document,path)
            if raw is MISSING:
                value='<missing>'
            elif path==('main','residents') and isinstance(raw,list):
                value={'populated_records':sum(_has_content(p) for p in raw)}
            else:
                value=deepcopy(raw)
            item['fields'][_label(path)]=value
            if path not in seen:
                seen.add(path)
                statuses.append({'path':list(path),'status':'ToBeReviewed'})
                parent=_get(output,path[:-1])
                if isinstance(parent,dict):
                    parent[f'{path[-1]}_flag']=True
                    parent[f'{path[-1]}_review_status']='ToBeReviewed'
        compact.append(item)
    output['has_flags']=bool(compact)
    output['validation_flags']=compact
    output['review_statuses']=statuses
    output['validation_warnings']=warnings
    return output


def validate_document(document, *, codebook_path=None):
    if isinstance(document,list):
        return [validate_document(s, codebook_path=codebook_path) for s in document]
    if not isinstance(document,dict):
        raise ValueError('Input must be a survey object or a survey array')
    if 'surveys' in document:
        if not isinstance(document['surveys'],list):
            raise ValueError('surveys must be a list')
        return {**deepcopy(document),'surveys':validate_document(document['surveys'], codebook_path=codebook_path)}
    if 'pages' in document:
        # Existing package format remains supported without schema conversion.
        return validate_legacy(document)[0]
    return validate_record(document, codebook_path=codebook_path)


def flags_only(document):
    if isinstance(document,list):
        return [flags_only(s) for s in document]
    if 'surveys' in document:
        return {'surveys':flags_only(document['surveys'])}
    return {'survey_id':document.get('survey_id'),'flags':document['validation_flags']}


def main():
    parser=argparse.ArgumentParser(description='US6: validate one complete survey or a batch')
    parser.add_argument('input',nargs='?',help='Grouped JSON: {survey_id, main, coded, notes?}, legacy pages, or an array')
    parser.add_argument('--main',dest='main_file',help='Structured Page 1 JSON')
    parser.add_argument('--coded',help='Structured Page 3 JSON')
    parser.add_argument('--notes',help='Optional notes JSON, preserved without value checks')
    parser.add_argument('--survey-id')
    parser.add_argument('--codebook', type=Path, help='Override repository-root data_dict.json')
    parser.add_argument('--output-dir',type=Path)
    args=parser.parse_args()
    if args.input and any((args.main_file,args.coded,args.notes)):
        parser.error('Use a grouped input OR --main/--coded, not both')
    if not args.input and not (args.main_file and args.coded):
        parser.error('Provide a grouped input or both --main and --coded')
    if args.input and args.survey_id:
        parser.error('--survey-id is only for --main/--coded input')
    paths=[Path(p) for p in (args.input,args.main_file,args.coded,args.notes) if p]
    destination=args.output_dir or paths[0].parent
    targets=[destination/'output_flagged.json',destination/'output_flags_only.json']
    if any(p.resolve()==t.resolve() for p in paths for t in targets):
        parser.error('Output paths would overwrite an input file; choose --output-dir')
    def load(path):
        return json.loads(Path(path).read_text(encoding='utf-8'))
    try:
        if args.input:
            document=load(args.input)
        else:
            document={'survey_id':args.survey_id,'main':load(args.main_file),'coded':load(args.coded)}
            if args.notes:
                document['notes']=load(args.notes)
        result=validate_document(document, codebook_path=args.codebook)
        compact=flags_only(result)
        # Entire batch is checked before generating any outputs.
        texts=[json.dumps(v,ensure_ascii=False,indent=2)+'\n' for v in (result,compact)]
        destination.mkdir(parents=True,exist_ok=True)
        for target,text in zip(targets,texts):
            target.write_text(text,encoding='utf-8')
            print(f'Created {target}')
    except (ValueError,OSError) as error:
        parser.exit(2,f'US6 input/output error: {error}\n')


if __name__=='__main__':
    main()
