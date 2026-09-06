import json
import os
os.chdir(os.path.dirname(os.path.abspath(__file__)))

#one file per bundle?

def write_to_page2(text, confidence, bundle_id):
    with open('./'+bundle_id+'_page2.json', 'w') as f:
        data = {"text":text, "confidence_value":confidence}
        json.dump(data, f)

write_to_page2("test!!!\n\n", 1.5, "samplebundle")