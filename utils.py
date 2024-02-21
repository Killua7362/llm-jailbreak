import ast

def extract_json(string):
    start_pos = string.find('{')
    end_pos = string.find('}')+1
    
    try:
        json_str = string[start_pos:end_pos]
        json_str = json_str.replace('\n',"")
        
        parsed = ast.literal_eval(json_str)
        return parsed,json_str
    except:
        return None,None