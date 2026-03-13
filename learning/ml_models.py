"""
learning/ml_models.py
Machine Learning models for classification and regression.
"""
import numpy as np
from sklearn.naive_bayes import GaussianNB
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import IsolationForest

class MLModels:
    def __init__(self):
        self.task_classifier = GaussianNB()
        self.time_predictor = LinearRegression()
        self.anomaly_detector = IsolationForest(contamination=0.1)
        self.is_trained = False
        
        # Dummy init for sklearn to avoid errors on early prediction
        self.task_classifier.fit([[0, 0]], [0])
        self.time_predictor.fit([[0]], [0])
        self.anomaly_detector.fit([[0, 0]])

    def train_classifier(self, X: np.ndarray, y: np.ndarray):
        """Train task classifier"""
        if len(X) > 0:
            self.task_classifier.fit(X, y)
            self.is_trained = True

    def predict_task_priority(self, features: np.ndarray) -> np.ndarray:
        return self.task_classifier.predict(features)

    def train_time_predictor(self, X: np.ndarray, y: np.ndarray):
        if len(X) > 0:
            self.time_predictor.fit(X, y)

    def predict_execution_time(self, features: np.ndarray) -> np.ndarray:
        return self.time_predictor.predict(features)

    def detect_anomalies(self, features: np.ndarray) -> np.ndarray:
        return self.anomaly_detector.predict(features)
