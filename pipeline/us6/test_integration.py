"""Exercise the supplied main schema, native output paths, and both CLI modes."""
import json
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
if __package__:
    from .run_validation import validate_survey, validate_document, flags_only
    from .input_adapter import CODED_FIELDS, normalize_survey
else:
    from run_validation import validate_survey, validate_document, flags_only
    from input_adapter import CODED_FIELDS, normalize_survey

ROOT=Path(__file__).parent

class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.m=json.loads((ROOT/'example_main.json').read_text(encoding='utf-8'))
        self.c=json.loads((ROOT/'example_coded.json').read_text(encoding='utf-8'))

    def test_real_main_schema_adapter(self):
        result=validate_survey(self.m,self.c,survey_id='test')
        self.assertFalse(result['has_flags'])
        self.assertEqual(result['validation_flags'],[])
        # NUMBER must not accidentally select main.number=99.
        self.assertEqual(result['main']['number'],'99')

    def test_native_nested_statuses_and_preserved_values(self):
        self.c['number_of_bedrooms']='4'
        original=deepcopy(self.m)
        result=validate_survey(self.m,self.c)
        self.assertEqual(self.m,original)
        self.assertEqual(result['main']['rooms']['number_of_separate_bedrooms'],'3')
        self.assertEqual(result['main']['rooms']['number_of_separate_bedrooms_review_status'],'ToBeReviewed')
        self.assertTrue(any('Page 1: rooms.number_of_separate_bedrooms' in i['fields'] for i in result['validation_flags']))

    def test_native_age_derivation(self):
        self.m['residents'][2]['age']='8'
        self.m['residents'][3]['age']='7'
        self.c.update({'number_5_to_10':'2','children_under_14':'2','number_over_10_m':'1','number_over_10_f':'1'})
        self.assertFalse(validate_survey(self.m,self.c)['has_flags'])
        self.c['children_under_14']='1'
        result=validate_survey(self.m,self.c)
        self.assertTrue(any(i['type']=='Page 1–3 conflict' and 'Page 1: residents[2].age' in i['fields'] for i in result['validation_flags']))
        self.assertEqual(result['main']['residents'][2]['age_review_status'],'ToBeReviewed')

    def test_missing_native_location(self):
        del self.c['number_of_bedrooms']
        result=validate_survey(self.m,self.c)
        self.assertTrue(any(i['fields'].get('Page 3: number_of_bedrooms')=='<missing>' for i in result['validation_flags']))

    def test_blank_upstream_template_is_not_zero_known_residents(self):
        blank=json.loads((ROOT/'main_schema.json').read_text(encoding='utf-8'))
        coded={}
        for candidates in CODED_FIELDS.values():
            target=coded
            for p in candidates[0][:-1]: target=target.setdefault(p,{})
            target[candidates[0][-1]]=None
        self.assertFalse(validate_survey(blank,coded)['has_flags'])
        self.assertTrue(validate_survey(blank,self.c)['has_flags'])

    def test_unrecognised_coded_schema_is_not_silent_success(self):
        with self.assertRaises(ValueError): validate_survey(self.m,{'unknown_count':4})

    def test_conflicting_coded_aliases_are_rejected(self):
        self.c['rooms']={'number_of_bedrooms':'8'}
        with self.assertRaises(ValueError): validate_survey(self.m,self.c)

    def test_number_does_not_fallback_without_definition(self):
        del self.m['number_of_dwelling']
        result=validate_survey(self.m,self.c)
        self.assertTrue(any(i['fields'].get('Page 1: number_of_dwelling')=='<missing>' for i in result['validation_flags']))

    def test_notes_and_unknown_fields_preserved(self):
        self.m['additional_handwritten_field']='[?]'
        result=validate_survey(self.m,self.c,notes={'body':'[?]'},survey_id='x')
        self.assertFalse(result['has_flags'])
        self.assertEqual(result['notes'],{'body':'[?]'})
        self.assertEqual(result['main']['additional_handwritten_field'],'[?]')

    def test_other_children_list_not_guessed_count(self):
        self.m['other_children']['died']=[{'raw':'two children'}]
        result=validate_survey(self.m,self.c)
        self.assertTrue(any('other_children' in w for w in result['validation_warnings']))
        self.assertFalse(result['has_flags'])

    def test_cli_two_page_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            result=subprocess.run([sys.executable,str(ROOT/'run_validation.py'),'--main',str(ROOT/'example_main.json'),'--coded',str(ROOT/'example_coded.json'),'--survey-id','cli','--output-dir',tmp],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(json.loads((Path(tmp)/'output_flags_only.json').read_text(encoding='utf-8')),{'survey_id':'cli','flags':[]})

    def test_cli_grouped_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            result=subprocess.run([sys.executable,str(ROOT/'run_validation.py'),str(ROOT/'example_survey.json'),'--output-dir',tmp],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            full=json.loads((Path(tmp)/'output_flagged.json').read_text(encoding='utf-8'))
            self.assertFalse(full['has_flags'])
            self.assertEqual(full['notes']['text'],'Preserve these notes.')

    def test_batch_separates_surveys(self):
        second=deepcopy(self.c);second['number_of_dwelling']='2'
        result=validate_document({'surveys':[{'survey_id':'a','main':self.m,'coded':self.c},{'survey_id':'b','main':self.m,'coded':second}]})
        self.assertFalse(result['surveys'][0]['has_flags'])
        self.assertTrue(result['surveys'][1]['has_flags'])
        self.assertEqual(len(flags_only(result)['surveys']),2)

    def test_missing_page_fails_before_output(self):
        with self.assertRaises(ValueError): validate_document({'main':self.m})

    def test_package_import(self):
        sys.path.insert(0,str(ROOT.parent))
        try:
            module=__import__(ROOT.name,fromlist=['validate_survey'])
            self.assertFalse(module.validate_survey(self.m,self.c)['has_flags'])
        finally:
            sys.path.pop(0)

if __name__=='__main__': unittest.main()
