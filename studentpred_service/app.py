import os
import pickle

import requests
from flask import Flask, request, jsonify

from pymongo import MongoClient


EVIDENTLY_SERVICE_ADDRESS = os.getenv('EVIDENTLY_SERVICE', 'http://127.0.0.1:5000')
MONGODB_ADDRESS = os.getenv("MONGODB_ADDRESS", "mongodb://127.0.0.1:27017")
MODEL = os.getenv('PROD_MODEL', './model.pkl')

with open(MODEL, 'rb') as f_in:
    (model, dv) = pickle.load(f_in)


app = Flask('student_performence_prediction')
mongo_client = MongoClient(MONGODB_ADDRESS)
database = mongo_client.get_database("student_performence_service")
collection = database.get_collection("data")


# Create a LabelEncoder object
@task
def label_encoding(data):
    encoder = LabelEncoder()

    # Encode the Country column
    data['gender'] = encoder.fit_transform(data['gender'])
    data['NationalITy'] = encoder.fit_transform(data['NationalITy'])
    data['PlaceofBirth'] = encoder.fit_transform(data['PlaceofBirth'])
    data['StageID'] = encoder.fit_transform(data['StageID'])
    data['GradeID'] = encoder.fit_transform(data['GradeID'])
    data['SectionID'] = encoder.fit_transform(data['SectionID'])
    data['Topic'] = encoder.fit_transform(data['Topic'])
    data['Semester'] = encoder.fit_transform(data['Semester'])
    data['Relation'] = encoder.fit_transform(data['Relation'])
    data['ParentAnsweringSurvey'] = encoder.fit_transform(data['ParentAnsweringSurvey'])
    data['ParentschoolSatisfaction'] = encoder.fit_transform(data['ParentschoolSatisfaction'])
    data['StudentAbsenceDays'] = encoder.fit_transform(data['StudentAbsenceDays'])
    data['Class'] = encoder.fit_transform(data['Class'])

    return data

def predict(model, data):
    X = dv.transform(data)
    print(X)
    y_pred = model.predict(X)
    return y_pred


@app.route('/predict', methods=['POST'])
def studentpred():

    data = request.get_json()
    data_encoded = label_encoding(data)
    print(data_encoded)
    pred = predict(model, data_encoded)
    
    if float(pred) == "M":
        result = {
            'data_studentpred': "Middle"
        }
    if float(pred) == "L":
        result = {
            'data_studentpred': "Low"
        }
    else:
        result = {
            'data_studentpred': "High"
        }
    print(result)
    save_to_database(data, float(pred))
    send_to_evidently_service(data, float(pred))
    return jsonify(result)

def save_to_database(data, pred):
    obj = data.copy()
    obj['prediction'] = pred
    collection.insert_one(dict(obj))


def send_to_evidently_service(data, pred):
    obj = data.copy()
    obj['prediction'] = pred
    requests.post(f"{EVIDENTLY_SERVICE_ADDRESS}/iterate/studentpred", json=[obj])

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=9696)
