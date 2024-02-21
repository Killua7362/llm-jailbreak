from flask import Flask,jsonify,request
from flask_cors import CORS
from model import get_source_target_judge_model
from inference import inference

app = Flask(__name__)
CORS(app)

attackLM, targetLM, judgeLM = get_source_target_judge_model()

@app.route("/home",methods=['POST'])
def regress():
    input = request.json()
    
    user = input['user']
    res,logs =inference(user,[attackLM,targetLM,judgeLM])
    return jsonify({
        'result':res
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0',port=8000)