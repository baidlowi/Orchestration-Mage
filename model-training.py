# Import Library
import os
import pandas as pd
from imblearn.over_sampling import RandomOverSampler
import pickle
import random
from pathlib import Path

# Load libraries
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import f1_score
from sklearn.metrics import roc_auc_score
from sklearn.metrics import accuracy_score
from sklearn.metrics import classification_report
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import cross_val_score
from sklearn.feature_extraction import DictVectorizer
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score

import mlflow
from mlflow.tracking import MlflowClient
from mlflow.entities import ViewType

from prefect import flow, task
from prefect.task_runners import SequentialTaskRunner

#import data
@task
def read_dataframe(dataset_path: str):
    data = pd.read_csv("xAPI-Edu-Data.csv" , delimiter=',')

    return data

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

# Balance Dataset
@task
def prepare_dataset(data, test_size: float, random_state: int):
    X = data.drop('Class', axis=1)
    y = data['Class']
    y.value_counts()

    balancer = RandomOverSampler(random_state=42)
    X_balanced, y_balanced = balancer.fit_resample(X, y)

    X.reset_index(drop=True, inplace=True)
    y.reset_index(drop=True, inplace=True)

    # Now use the balanced data for train_test_split
    X_train, x_test, Y_train, y_test = train_test_split(X_balanced, y_balanced, test_size=0.3, shuffle=False)

    return X_train, x_test, Y_train, y_test

# Feature Scaling
def fscaling(X_train, x_test):
    scaler = StandardScaler()
    X_train['raisedhands'] = scaler.fit_transform(X_train[['raisedhands']])
    x_test['raisedhands'] = scaler.transform(x_test[['raisedhands']])
    X_train['VisITedResources'] = scaler.fit_transform(X_train[['VisITedResources']])
    x_test['VisITedResources'] = scaler.transform(x_test[['VisITedResources']])
    X_train['AnnouncementsView'] = scaler.fit_transform(X_train[['AnnouncementsView']])
    x_test['AnnouncementsView'] = scaler.transform(x_test[['AnnouncementsView']])
    X_train['Discussion'] = scaler.fit_transform(X_train[['Discussion']])
    x_test['Discussion'] = scaler.transform(x_test[['Discussion']])

    return X_train, x_test

# Predict
# def model_training(model, X_train, Y_train, x_test, y_test):
#     rf = RandomForestClassifier()
#     rf.fit(X_train, Y_train)
#     y_pred = rf.predict(x_test)
#     print("Train Result:\n===============================================")
#     print(f"Accuracy Score: {accuracy_score(y_test, y_pred) * 100:.2f}%")
#     print("_______________________________________________")
#     print(f"CLASSIFICATION REPORT:\n{classification_report(y_test, y_pred)}")

@task
def make_dict_victorizer(X_train, x_test):
    '''
    Uses dictionary vectorizer for processing the dictionaries
    '''
    dv = DictVectorizer()
    train_dicts = X_train.to_dict(orient='records')
    X_train = dv.fit_transform(train_dicts)

    test_dicts = x_test.to_dict(orient='records')
    x_test = dv.fit_transform(test_dicts)

    return X_train, x_test, dv


@task
def model_training(model, X_train, Y_train, x_val, y_test):
    '''
    Given the models list from the training session
    Then predict the validation set
    Return the metrices calculate from each model
    '''

    log_metrics = dict()

    performst = model.fit(X_train, Y_train)
    prediction = performst.predict(x_val)
    accuracy = accuracy_score(prediction, y_test)
    precision = precision_score(prediction, y_test, average='weighted')
    recall = recall_score(prediction, y_test, average='weighted')
    f1 = f1_score(prediction, y_test, average='weighted')

    print('############################################')
    print('Algorithm:', type(model).__name__)
    print('Accuracy Score', '{:.4f}'.format(accuracy))
    print('Precision Score', '{:.4f}'.format(precision))
    print('Recal score', '{:.4f}'.format(recall))
    print('F1 score', '{:.4f}'.format(f1))
    print("Evaluated model successfully...")
    print('############################################\n')

    log_metrics = {
        'accuracy': accuracy,
        'precision': precision,
        'recall': recall,
        'f1': f1
    }
    
    return log_metrics


@task
def save_model(model, dv):
    '''
    Save the model pickle
    '''
    model_path = Path("./env/dev/models/")
    model_path.mkdir(parents=True, exist_ok=True)

    with open(f'./env/dev/models/model.pkl', 'wb') as f_out:
        pickle.dump((model, dv), f_out)

    print("Saved model successfully...")


@task
def send_model_service(model_source):
    '''
    Send best model from model storage to the service
    '''
    model_service_path = Path("./env/stage/models/")
    model_service_path.mkdir(parents=True, exist_ok=True)

    cmd = f"cp {model_source} {model_service_path}"
    os.system(cmd)
    print("Send model to service is complete")


@flow(task_runner=SequentialTaskRunner())
def model_experiment(dataset_path: str="./xAPI-Edu-Data.csv"):

    model_version = 1
    model_stage = ["Staging", "Production"]
    experiment_id = 1
    experiment_name = "studentpred"
    MLFLOW_TRACKING_URI = "sqlite:///studentpred.db"
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    mlflow.set_experiment(experiment_name)

    with mlflow.start_run(run_name="model_training") as run:

        client = MlflowClient(tracking_uri=MLFLOW_TRACKING_URI)
        run_id = run.info.run_id
        model_uri = f"runs:/{run_id}/model"
        model_name = f"studentpred"

        test_size = .25
        random.seed(42)
        random_state = random.randint(1, 100)

        mlflow.set_tag("Project", "Student_Performence_Prediction")
        mlflow.set_tag("Developer", "Baidlowi")
        mlflow.set_tag("Dataset", dataset_path)
        mlflow.set_tag("Model", "RandomForestClassified")

        mlflow.log_param("random_state", random_state)
      
        data = read_dataframe(dataset_path)
        data = label_encoding(data)
        X_train, x_test, Y_train, y_test = prepare_dataset(data, test_size, random_state)
        X_train, x_test, dv = make_dict_victorizer(X_train, x_test)
        model = RandomForestClassifier(n_estimators=1000, min_samples_split = 2, min_samples_leaf = 1, max_depth = 15)
        log_metrics = model_training(model, X_train, Y_train, x_test, y_test)
        mlflow.log_metrics(log_metrics)

        save_model(model, dv)

        mlflow.log_artifact(f'./env/dev/models/model.pkl', artifact_path='models')
        mlflow.register_model(model_uri=model_uri, name=model_name)
        
        mlflow.end_run()

    model_source = f"./env/dev/models/model.pkl"
    send_model_service(model_source)

    for model in client.search_model_versions(f"name='{model_name}'"):
        model_id = model.run_id
        if model_id == run_id:
            new_model_name = model.name
            new_model_version = model.version
            client.transition_model_version_stage(
                name=new_model_name,
                version=new_model_version,
                stage=model_stage[0],
                archive_existing_versions=False
            )

if __name__ == "__main__":

    model_experiment()