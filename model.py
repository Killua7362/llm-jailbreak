import gc
from transformers import AutoModelForCausalLM, AutoTokenizer,BitsAndBytesConfig
import torch
from utils import extract_json
from prompts import judge_prompt
from fastchat.model import get_conversation_template
import re


def get_model(model_name):
        nf4_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=torch.bfloat16
            )
        
        model = AutoModelForCausalLM.from_pretrained(
            model_name,
            quantization_config=nf4_config
            ).eval()
        
        tokenizer = AutoTokenizer.from_pretrained(model_name) 
        tokenizer.pad_token = tokenizer.unk_token
        tokenizer.padding_left = 'left'
        return Model(model_name,model,tokenizer)

class AttackLM:
    def __init__(self):
        self.model_name = ""
        self.temperatures = 1
        self.max_n_tokens = 150
        self.max_n_attempts = 5
        self.top_p = 1
        self.model = get_model(self.model_name)
    
    def get_attacker(self,conv_list,prompts_list):
        batch_size = len(conv_list)
        valid_outputs = [None] * batch_size 
        
        init_message = """
            {\"improvement\": \"
        """
        
        full_prompts = []
        for conv,prompt in zip(conv_list,prompts_list):
            conv.append_message(conv.roles[0],prompt)
            conv.append_message(conv.roles[1],init_message)
            full_prompts.append(conv.get_prompt()[:-len(conv.sep2)])
            
        indices_to_generate = list(range(batch_size))
        
        for _ in range(self.max_n_attempts):
            full_prompt_subsets = [full_prompts[i] for i in indices_to_generate]
            output_lists = self.model.generate(
                full_prompt_subsets,
                max_new_tokens=self.max_n_tokens,
                temperature=self.temperatures,
                top_p=self.top_p
            )
            new_indices = []
            for i,full_output in enumerate(output_lists):
                orig_idx = indices_to_generate[i]
                full_output = init_message + full_output
                
                attack_dict,json_str = extract_json(full_output)
                
                if attack_dict == None:
                    new_indices.append(orig_idx) 
                else:
                    valid_outputs[orig_idx] = attack_dict
                    conv_list[orig_idx].update_last_message(json_str)
                    
            indices_to_generate = new_indices
            
            if not indices_to_generate:
                break
            
        return valid_outputs
                
class TargetLM:
    def __init__(self):
        self.model_name = ""
        self.max_n_tokens = 150
        self.temperature = 0
        self.top_k = 1
        
        self.model = get_model(self.model_name)
    
    def get_response(self,prompt_list):
        batch_size = len(prompt_list) 
        template = get_conversation_template('llama-2')
        template.sep2 = template.sep2.strip()
        self.template = template
        
        convs_list = [self.template for _ in range(batch_size)] 
        full_prompts = []
        
        for conv,prompt in zip(convs_list,prompt_list):
            conv.append_message(conv.roles[0],prompt)
            conv.append_message(conv.roles[1],None)
            full_prompts.append(conv.get_prompt())
        
        output_lists = self.model.generate(
            full_prompts,
            self.max_n_tokens,
            self.temperature,
            self.top_k
        )
        return output_lists

class JudgeLM:
    def __init__(self,input_string,target_string):
        self.model = get_model(model_name="")
        self.system_prompt = judge_prompt(
            input_string,target_string
        )
        
        self.max_n_tokens=10
        self.temperature = 0
    
    def create_conv(self,full_prompt):
        conv = get_conversation_template("one_shot")
        conv.set_system_message(self.system_prompt)
        conv.append_message(conv.roles[0],full_prompt)
        return conv

    def get_judge_prompt(self,prompt,response):
        return f"[PROMPT]:{prompt}\n[ASSISTANT'S RESPONSE]: {response}"
    
    def process_output(self,raw_out):
        pattern = r'\[\[(\d+)\]\]'
        match = re.search(pattern,raw_out)
        output = int(match.group(1)) if match else None
        return output if output else 1

    def score(self,attack_prompt_list,target_response_list):
        convs_list = []
        for prompt, response in zip(attack_prompt_list,target_response_list):
            convs_list.append(self.create_conv(self.get_judge_prompt(prompt,response)))
        raw_outputs = self.model.generate(
            convs_list,
            max_new_tokens=self.max_n_tokens,
            temperature=self.temperature
        )
        outputs = [self.process_output(out) for out in raw_outputs]
    
class Model:
    def __init__(self,model_name,model,tokenizer):
        self.model_name = model_name 
        self.model = model
        self.tokenizer = tokenizer
        self.eos_token_ids = [self.tokenizer.eos_token_id]
        self.eos_token_ids.extend([
            self.tokenizer.encode("}")[1],
            29913, 
            9092,
            16675])

    def generate(
        self,
        full_prompts,
        max_new_tokens,
        temperature,
        top_p=1.0
        ):
        inputs = self.tokenizer(full_prompts,return_tensors='pt',padding=True)
        inputs = {k:v for k,v in inputs}
        
        output_ids = self.model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample = True if temperature>0 else False,
            temperature = temperature if temperature > 0 else 1,
            top_p = top_p if temperature > 0 else 1,
            eos_token_id=self.eos_token_ids
        )
        
        output_list = self.tokenizer.batch_decode(output_ids,skip_special_tokens=True)
        
        del inputs
        gc.collect()
        return output_list


def get_source_target_judge_model():
    attachLLM = AttackLM()
    targetLLM = TargetLM()
    judgeLLM = JudgeLM()
    
    return attachLLM,targetLLM,judgeLLM