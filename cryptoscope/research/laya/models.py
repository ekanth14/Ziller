"""Model architecture and calibration primitives for Laya (Phase 8).

Defines:
1. MultinomialLogisticRegression: Softmax regression with L2 regularization & analytic gradients.
2. PlattCalibrator: Multiclass Platt scaling (sigmoid calibration) with cross-validation.
"""

from typing import List, Optional
import numpy as np
import scipy.optimize as opt
from scipy.special import expit
import lightgbm as lgb


class MultinomialLogisticRegression:
    """Multinomial Softmax Logistic Regression with L2 Regularization & Analytic Gradients."""

    def __init__(self, C: float = 1.0, max_iter: int = 100):
        self.C = C
        self.max_iter = max_iter
        self.W_all = None

    def fit(self, X: np.ndarray, y: np.ndarray):
        n_samples, n_features = X.shape
        n_classes = int(np.max(y)) + 1
        X_b = np.hstack([X, np.ones((n_samples, 1), dtype=np.float32)])
        dim = (n_features + 1) * n_classes

        Y = np.zeros((n_samples, n_classes), dtype=np.float32)
        Y[np.arange(n_samples), y] = 1.0

        def obj_and_grad(weights):
            W_all = weights.reshape(n_features + 1, n_classes)
            logits = X_b @ W_all
            exp_l = np.exp(logits - np.max(logits, axis=1, keepdims=True))
            probs = exp_l / np.sum(exp_l, axis=1, keepdims=True)
            loss = -np.mean(np.sum(Y * np.log(probs + 1e-12), axis=1))
            reg = (0.5 / self.C) * np.sum(W_all[:-1, :] ** 2) / n_samples

            diff = (probs - Y) / n_samples
            grad = X_b.T @ diff
            grad[:-1, :] += (1.0 / self.C) * W_all[:-1, :] / n_samples
            return loss + reg, grad.ravel()

        res = opt.minimize(obj_and_grad, np.zeros(dim), jac=True, method="L-BFGS-B", options={"maxiter": self.max_iter})
        self.W_all = res.x.reshape(n_features + 1, n_classes)
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        n_samples = X.shape[0]
        X_b = np.hstack([X, np.ones((n_samples, 1), dtype=np.float32)])
        logits = X_b @ self.W_all
        exp_l = np.exp(logits - np.max(logits, axis=1, keepdims=True))
        return exp_l / np.sum(exp_l, axis=1, keepdims=True)

    def predict(self, X: np.ndarray) -> np.ndarray:
        return np.argmax(self.predict_proba(X), axis=1)


class PlattCalibrator:
    """Platt scaling (sigmoid calibration) per class using cross-validated margins."""

    def __init__(self, base_estimator, cv: int = 3):
        self.base_estimator = base_estimator
        self.cv = cv
        self.params: List[np.ndarray] = []
        self.fitted_model = None

    def fit(self, X: np.ndarray, y: np.ndarray):
        n = len(X)
        n_classes = len(np.unique(y))
        oof_preds = np.zeros((n, n_classes), dtype=np.float32)
        fold_size = n // self.cv

        is_lgb = isinstance(self.base_estimator, lgb.LGBMClassifier)

        for fold in range(self.cv):
            val_idx = np.arange(fold * fold_size, (fold + 1) * fold_size if fold < self.cv - 1 else n)
            train_idx = np.setdiff1d(np.arange(n), val_idx)

            if is_lgb:
                fold_model = lgb.LGBMClassifier(**self.base_estimator.get_params())
            else:
                fold_model = MultinomialLogisticRegression(C=self.base_estimator.C)

            fold_model.fit(X[train_idx], y[train_idx])
            oof_preds[val_idx] = fold_model.predict_proba(X[val_idx])

        self.params = []
        for c in range(n_classes):
            target = (y == c).astype(np.float32)
            p = oof_preds[:, c]
            eps = 1e-6
            p_clipped = np.clip(p, eps, 1 - eps)
            logit_p = np.log(p_clipped / (1 - p_clipped))

            def nll_and_grad(ab):
                a, b = ab
                prob = expit(a * logit_p + b)
                loss = -np.mean(target * np.log(prob + eps) + (1 - target) * np.log(1 - prob + eps))
                diff = (prob - target) / len(target)
                grad_a = np.sum(diff * logit_p)
                grad_b = np.sum(diff)
                return loss, np.array([grad_a, grad_b])

            res = opt.minimize(nll_and_grad, [1.0, 0.0], jac=True, method="L-BFGS-B")
            self.params.append(res.x)

        if is_lgb:
            self.fitted_model = lgb.LGBMClassifier(**self.base_estimator.get_params())
        else:
            self.fitted_model = MultinomialLogisticRegression(C=self.base_estimator.C)

        self.fitted_model.fit(X, y)
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        raw_probs = self.fitted_model.predict_proba(X)
        n_samples, n_classes = raw_probs.shape
        cal_probs = np.zeros_like(raw_probs)
        eps = 1e-6
        for c in range(n_classes):
            a, b = self.params[c]
            p = np.clip(raw_probs[:, c], eps, 1 - eps)
            logit_p = np.log(p / (1 - p))
            cal_probs[:, c] = expit(a * logit_p + b)
        return cal_probs / np.sum(cal_probs, axis=1, keepdims=True)

    def predict(self, X: np.ndarray) -> np.ndarray:
        return np.argmax(self.predict_proba(X), axis=1)
