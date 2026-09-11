# -*- coding: utf-8 -*-
"""
Created on Thu Feb  3 20:32:09 2022

@author: jhutchison

conda install keras
conda install -c conda-forge tensorflow
conda install -c anaconda scikit-learn


pip install scikit-multilearn
"""

# %% Packages

import itertools

from keras.preprocessing.text import Tokenizer
from keras.models import Sequential
from keras.layers import Dense

import matplotlib.pyplot as plt

from nltk.corpus import stopwords
from nltk.stem.snowball import SnowballStemmer

from numpy import mean
from numpy import std
import numpy as np

import pandas as pd

import re

from scipy.sparse import csr_matrix, lil_matrix

from sentence_transformers import SentenceTransformer, util

from sklearn.datasets import make_multilabel_classification
from sklearn.decomposition import TruncatedSVD
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score
from sklearn.model_selection import cross_val_score
from sklearn.model_selection import GridSearchCV
from sklearn.model_selection import KFold
from sklearn.model_selection import RepeatedKFold
from sklearn.model_selection import StratifiedKFold
from sklearn.model_selection import train_test_split
from sklearn.multiclass import OneVsRestClassifier
from sklearn.naive_bayes import MultinomialNB
from sklearn.neighbors import KNeighborsClassifier
from sklearn.neural_network import MLPClassifier
from sklearn.neural_network import MLPRegressor
from sklearn.pipeline import Pipeline
from sklearn.svm import SVC

from skmultilearn.adapt import MLkNN, MLTSVM
from skmultilearn.problem_transform import BinaryRelevance
from skmultilearn.problem_transform import ClassifierChain
from skmultilearn.problem_transform import LabelPowerset

import string

import time
import torch

from tqdm import tqdm

# Local Imports
from utils.utils_excel_table_save import table_save

time_script = time.time()


# %% Functions
def preprocess_text(sen):
    # Remove punctuations and numbers
    sentence = re.sub("[^a-zA-Z]", " ", sen)
    # Single character removal
    sentence = re.sub(r"\s+[a-zA-Z]\s+", " ", sentence)
    # Removing multiple spaces
    sentence = re.sub(r"\s+", " ", sentence)
    return sentence


stop_words = set(stopwords.words("english"))
stop_words.update(
    [
        "zero",
        "one",
        "two",
        "three",
        "four",
        "five",
        "six",
        "seven",
        "eight",
        "nine",
        "ten",
        "may",
        "also",
        "across",
        "among",
        "beside",
        "yet",
        "within",
    ]
)
re_stop_words = re.compile(r"\b(" + "|".join(stop_words) + ")\\W", re.I)


def removeStopWords(sentence):
    global re_stop_words
    return re_stop_words.sub(" ", sentence)


stemmer = SnowballStemmer("english")


def stemming(sentence):
    stemSentence = ""
    for word in sentence.split():
        stem = stemmer.stem(word)
        stemSentence += stem
        stemSentence += " "
    stemSentence = stemSentence.strip()
    return stemSentence


def bin_rel_subtask_d(X, y, model, arg):
    """Calculate binary relevance by model for each subtask"""
    time_start = time.time()
    if model == "KNN":
        print("k = {}".format(arg))

    # n_inputs, n_outputs = X.shape[0], y.shape[1]
    # define evaluation procedure
    cv = RepeatedKFold(n_splits=10, n_repeats=3, random_state=1)
    # enumerate folds
    results = list()
    for train_ix, test_ix in cv.split(X):
        # prepare data
        X_train, X_test = X[train_ix], X[test_ix]
        y_train, y_test = y[train_ix], y[test_ix]

        vectorizer = TfidfVectorizer(
            strip_accents="unicode", analyzer="word", ngram_range=(1, 3), norm="l2"
        )
        vectorizer.fit(X_train)
        vectorizer.fit(X_test)

        x_train = vectorizer.transform(X_train)
        x_test = vectorizer.transform(X_test)
        if model == "KNN":
            classifier = BinaryRelevance(KNeighborsClassifier(n_neighbors=arg))
        elif model == "SVM":
            classifier = BinaryRelevance(SVC())
        elif model == "NB":
            classifier = BinaryRelevance(MultinomialNB())
        elif model == "RF":
            classifier = BinaryRelevance(RandomForestClassifier())
        elif model == "MLP":
            classifier = BinaryRelevance(
                MLPClassifier(
                    solver="lbfgs",
                    alpha=1e-5,
                    hidden_layer_sizes=(5, 2),
                    random_state=1,
                )
            )
        # train
        classifier.fit(x_train, y_train)

        # predict
        predictions = classifier.predict(x_test)
        predictions = predictions.toarray()
        # Score over a vector, or a matrix prediction
        shape = predictions.shape[0] * predictions.shape[1]
        if predictions.shape[1] == 1:
            acc_count = accuracy_score(y_test, predictions, normalize=False)
            acc_score = acc_count / shape
            results.append(acc_score)
        else:
            acc_count = 0
            for i in range(predictions.shape[0]):
                acc_count = acc_count + accuracy_score(
                    y_test[i], predictions[i], normalize=False
                )
            acc_score = acc_count / shape
            results.append(acc_score)
    print()
    print(
        "{} Accuracy: {:.2f}% (std: {:.2f}%)".format(model, mean(results), std(results))
    )
    print("Runtime: {:.0f}s".format(time.time() - time_start))
    print()
    res_d = {
        "model": model,
        "arg": arg,
        "mean": mean(results),
        "sd": std(results),
        "time": round(time.time() - time_start, 2),
    }
    return pd.Series(res_d)


# Just for completeness, if the decimal places are variable,
# e.g. d=3, then the syntax is "{:.{}f}".format(5, d)

# %% Variables

arg_list = range(1, 10)

alphabet = string.ascii_lowercase

cols_subtask = ["subtask_{}".format(col) for col in alphabet[3:11]]
cols_subtask.remove("subtask_i")

subtask_d_to_val = {"VL": 0, "L": 1, "M": 2, "H": 3, "VH": 4}

subtask_d = {
    "Very low concern": "VL",
    "Low Concern": "L",
    "Medium Concern": "M",
    "High Concern": "H",
    "Very High Concern": "VH",
}

subtask_e = {
    "Research": "R",
    "Planning": "Pg",
    "Preparation": "Pn",
    "Implementation": "I",
}

subtask_f = {
    "Perseveration of person or cause": "PoP",
    "Strident Opinion": "SO",
    "Negative Characterization": "NC",
    "Angry emotional undertone": "AEU",
    "Social or occupational deterioration": "SOD",
}

subtask_g = {
    "Warrior": "Wr",
    "Weapons": "Ws",
    "Identify with attackers": "IwA",
    "Agent for cause": "AfC",
}

subtask_h = {
    "Testing violent action": "TVA",
    "Response Tendency": "RT",
    "Motivation to act": "MtA",
    "Behavioral Tryout": "BT",
    "Proof of action": "PoA",
}

subtask_j = {
    "Communicating Intent": "CI",
}

subtask_k = {
    "Violent Action Imperative": "VAI",
    "Desperation": "Dn",
    "Distress": "Ds",
    "No alternative, trapped": "NAT",
    "Justification": "J",
    "NA": "NA",
}

subtask_all = {
    "Very low concern": "VL",
    "Low Concern": "L",
    "Medium Concern": "M",
    "High Concern": "H",
    "Very High Concern": "VH",
    "Research": "R",
    "Planning": "Pg",
    "Preparation": "Pn",
    "Implementation": "I",
    "Perseveration of person or cause": "PoP",
    "Strident Opinion": "SO",
    "Negative Characterization": "NC",
    "Angry emotional undertone": "AEU",
    "Social or occupational deterioration": "SOD",
    "Warrior": "Wr",
    "Weapons": "Ws",
    "Identify with attackers": "IwA",
    "Agent for cause": "AfC",
    "Testing violent action": "TVA",
    "Response Tendency": "RT",
    "Motivation to act": "MtA",
    "Behavioral Tryout": "BT",
    "Proof of action": "PoA",
    "Communicating Intent": "CI",
    "Violent Action Imperative": "VAI",
    "Desperation": "Dn",
    "Distress": "Ds",
    "No alternative, trapped": "NAT",
    "Justification": "J",
    "NA": "NA",
}

subtasks = {
    "Flag": subtask_d,
    "Pathway Warning": subtask_e,
    "Fixation Warning": subtask_f,
    "Identification": subtask_g,
    "Novel Aggresion": subtask_h,
    "Leakage Warning": subtask_j,
    "Last Resort Warning": subtask_k,
}

subtasks = dict(zip(cols_subtask, subtasks.values()))

subtasks_tng = [subtask_e, subtask_f, subtask_g, subtask_h, subtask_j, subtask_k]

subtasks_test = [subtask_d]

res_list = []

# %% Data

tweets = pd.read_excel("data/data_tier.xlsx", sheet_name="tweets", skiprows=7)
shooters = pd.read_excel("data/data_tier.xlsx", sheet_name="shooters", skiprows=7)
fps_data = pd.read_excel("data/data_tier.xlsx", sheet_name="fps", skiprows=7)

data = pd.concat([tweets, shooters, fps_data], axis=0)

# Drop Total Row and Incomplete, Missing Primary Subtask_D
data = data.dropna(subset=["id_text", "subtask_d"], axis=0)
data = data.reset_index(drop=True)
data.info()


# %% Clean

data = data.fillna("NA")
for col in cols_subtask:
    data[col] = data[col].str.upper()
    data[col] = data[col].str.replace("-", ",")
    data[col] = data[col].str.replace("/s", "", regex=True)
    data[col] = data[col].str.replace("?", "", regex=False)

data["subtask_d"] = data["subtask_d"].str.replace("HV", "VH")
data["subtask_d"] = data["subtask_d"].str.replace("N", "M")
data["subtask_d"] = data["subtask_d"].str.lower()

# Create a wide format
df_w = pd.DataFrame(0, index=data.index, columns=subtask_all.values())
for row in tqdm(data.index):
    for task, task_d in subtasks.items():
        for key, col in task_d.items():
            if col.upper() in data.loc[row, task]:
                df_w.loc[row, col] = 1
print("low appearing with VL (finding L)")
for task, task_d in subtasks.items():
    if "NA" in task_d.values():
        df_w[task] = df_w[task_d.values()].drop(["NA"], axis=1).sum(axis=1)
    else:
        df_w[task] = df_w[task_d.values()].sum(axis=1)
df_w = df_w.drop("subtask_d", axis=1)
df_w["tot"] = df_w[cols_subtask[1:]].sum(axis=1)
df_w.sum()


# %% Preprocess

data["text"] = data["text"].apply(preprocess_text)
data["text"] = data["text"].apply(removeStopWords)


# %% BERT
""" This is a sentence-transformers model: It maps sentences & paragraphs to 
a 768 dimensional dense vector space and can be used for tasks like 
clustering or semantic search"""

embedder = SentenceTransformer("msmarco-distilbert-base-v2")
svd = TruncatedSVD(n_components=100, n_iter=7, random_state=42)

corpus = data["text"].to_list()
corpus_embeddings = embedder.encode(corpus, convert_to_tensor=True)
corpus_svd = svd.fit_transform(corpus_embeddings)

df_d = data["subtask_d"].copy(deep=True).map(subtask_d_to_val)
df_d = data["subtask_d"].copy(deep=True)

X = corpus_svd
y = df_d.values
# prep data: train and test sets
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=101
)

# grid_layers = [x for x in itertools.product((10,20,30,40,50),repeat=4)]
# len(grid_layers)
grid_layers = [x for x in itertools.product((10, 30, 50), repeat=3)]
len(grid_layers)

params = {
    "hidden_layer_sizes": grid_layers,
    "activation": ["relu"],
    "solver": ["adam"],
    "alpha": [1e-4],
    "learning_rate": ["invscaling"],
    "random_state": [101],
}


grid = GridSearchCV(MLPClassifier(), params, verbose=2)
grid.fit(X, y)
print(grid.best_estimator_)
print(grid.best_params_)
res_grid = pd.DataFrame(grid.cv_results_)
res_grid.to_excel("res_grid_genesis.xlsx")

# Neural Net
# model, fit, predict
clf_reg = MLPClassifier(**grid.best_params_)
clf_reg.fit(X_train, y_train)
y_pred = clf_reg.predict(X_test)

print(
    "{} R^2, coef of determination of the prediction".format(
        clf_reg.score(X_test, y_test)
    )
)
# print("Number of mislabeled points out of a total %d points : %d" % (X_test.shape[0], (y_test != y_pred).sum()))
# print("%d percent correct" % (100*float((y_test == y_pred).sum()/X_test.shape[0])))

# %% Final
# check = df_d.loc[df_d == 4].index
y_pred = pd.Series(clf_reg.predict(X))
y_clf = pd.concat([df_d, y_pred], axis=1).rename({0: "pred"}, axis=1)
y_clf = y_clf.sort_values(["subtask_d"], ascending=False)
y_clf.loc[y_clf["subtask_d"] == "vh"].head(25)
y_agg_clf = y_clf.groupby(["subtask_d", "pred"])["subtask_d"].count()
y_agg_clf = y_agg_clf.to_frame()
y_agg_clf["relative_rate"] = (
    y_agg_clf["subtask_d"] / y_agg_clf["subtask_d"].groupby(level=0).sum()
)
y_agg_clf = y_agg_clf.rename({"subtask_d": "st_d"}, axis=1)
y_agg_clf = y_agg_clf.reset_index(drop=False)


# %% BERT Regressor
""" This is a sentence-transformers model: It maps sentences & paragraphs to 
a 768 dimensional dense vector space and can be used for tasks like 
clustering or semantic search"""

embedder = SentenceTransformer("msmarco-distilbert-base-v2")
svd = TruncatedSVD(n_components=100, n_iter=7, random_state=42)

corpus = data["text"].to_list()
corpus_embeddings = embedder.encode(corpus, convert_to_tensor=True)
corpus_svd = svd.fit_transform(corpus_embeddings)

subtask_d_to_val = {key.lower(): val for key, val in subtask_d_to_val.items()}
df_d = data["subtask_d"].copy(deep=True).map(subtask_d_to_val)
# df_d = data["subtask_d"].copy(deep=True)

X = corpus_svd
y = df_d.values
# prep data: train and test sets
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=101
)

# grid_layers = [x for x in itertools.product((10,20,30,40,50),repeat=4)]
# len(grid_layers)
grid_layers = [x for x in itertools.product((10, 30, 50), repeat=3)]
len(grid_layers)

params = {
    "hidden_layer_sizes": grid_layers,
    "activation": ["relu"],
    "solver": ["adam"],
    "alpha": [1e-4],
    "learning_rate": ["invscaling"],
    "random_state": [101],
}


grid = GridSearchCV(MLPRegressor(), params, verbose=2)
grid.fit(X, y)
print(grid.best_estimator_)
print(grid.best_params_)
res_grid = pd.DataFrame(grid.cv_results_)
res_grid.to_excel("res_grid_genesis.xlsx")

# Neural Net
# model, fit, predict
mlp_reg = MLPRegressor(**grid.best_params_)
mlp_reg.fit(X_train, y_train)
y_pred = mlp_reg.predict(X_test)

print(
    "{} R^2, coef of determination of the prediction".format(
        mlp_reg.score(X_test, y_test)
    )
)
# print("Number of mislabeled points out of a total %d points : %d" % (X_test.shape[0], (y_test != y_pred).sum()))
# print("%d percent correct" % (100*float((y_test == y_pred).sum()/X_test.shape[0])))

# %% Final
# check = df_d.loc[df_d == 4].index
y_pred = pd.Series(mlp_reg.predict(X))

y_reg = pd.concat([df_d, y_pred], axis=1).rename({0: "pred"}, axis=1)
y_reg = y_reg.sort_values(["subtask_d"], ascending=False)
y_reg.loc[y_reg["subtask_d"] == 4].head(25)
y_agg_reg = y_reg.groupby(["subtask_d"])["pred"].describe()

# %% Subtask K
""" This is a sentence-transformers model: It maps sentences & paragraphs to 
a 768 dimensional dense vector space and can be used for tasks like 
clustering or semantic search"""

embedder = SentenceTransformer("msmarco-distilbert-base-v2")
svd = TruncatedSVD(n_components=100, n_iter=7, random_state=42)

corpus = data["text"].to_list()
corpus_embeddings = embedder.encode(corpus, convert_to_tensor=True)
corpus_svd = svd.fit_transform(corpus_embeddings)

df_k = df_w[subtask_k.values()]
[df_k[col].unique() for col in df_k.columns]
df_k.sum()
X = data["text"].values
y = df_k.values

df_j = df_w[subtask_j.values()]
[df_j[col].unique() for col in df_j.columns]
df_j.sum()
X = data["text"].values
y = df_j.values

X = corpus_svd
y = df_j.values
# prep data: train and test sets
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=101
)

# grid_layers = [x for x in itertools.product((10,20,30,40,50),repeat=4)]
# len(grid_layers)
grid_layers = [x for x in itertools.product((10, 30, 50), repeat=3)]
len(grid_layers)

params = {
    "hidden_layer_sizes": grid_layers,
    "activation": ["relu"],
    "solver": ["adam"],
    "alpha": [1e-4],
    "learning_rate": ["invscaling"],
    "random_state": [101],
}


grid = GridSearchCV(MLPRegressor(), params, verbose=2)
grid.fit(X, y)
print(grid.best_estimator_)
print(grid.best_params_)
res_grid = pd.DataFrame(grid.cv_results_)
res_grid.to_excel("res_grid_genesis.xlsx")

# Neural Net
# model, fit, predict
mlp_reg = MLPRegressor(**grid.best_params_)
mlp_reg.fit(X_train, y_train)
y_pred = mlp_reg.predict(X_test)

print(
    "{} R^2, coef of determination of the prediction".format(
        mlp_reg.score(X_test, y_test)
    )
)
# print("Number of mislabeled points out of a total %d points : %d" % (X_test.shape[0], (y_test != y_pred).sum()))
# print("%d percent correct" % (100*float((y_test == y_pred).sum()/X_test.shape[0])))

# %% Final
y_pred = pd.Series(mlp_reg.predict(X))

y_reg_j = pd.concat([df_j, y_pred], axis=1).rename({0: "pred"}, axis=1)
y_reg_j = y_reg_j.sort_values(["CI"], ascending=False)
y_reg_j.loc[y_reg_j["CI"] == 4].head(25)
y_agg_reg_j = y_reg_j.groupby(["CI"])["pred"].describe()


# %% Subtask K Categorization
""" This is a sentence-transformers model: It maps sentences & paragraphs to 
a 768 dimensional dense vector space and can be used for tasks like 
clustering or semantic search"""

embedder = SentenceTransformer("msmarco-distilbert-base-v2")
svd = TruncatedSVD(n_components=100, n_iter=7, random_state=42)

corpus = data["text"].to_list()
corpus_embeddings = embedder.encode(corpus, convert_to_tensor=True)
corpus_svd = svd.fit_transform(corpus_embeddings)

df_k = df_w[subtask_k.values()]
[df_k[col].unique() for col in df_k.columns]
df_k.sum()
X = data["text"].values
y = df_k.values

df_j = df_w[subtask_j.values()]
[df_j[col].unique() for col in df_j.columns]
df_j.sum()
X = data["text"].values
y = df_j.values

X = corpus_svd
y = df_j.values
# prep data: train and test sets
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=101
)

# grid_layers = [x for x in itertools.product((10,20,30,40,50),repeat=4)]
# len(grid_layers)
grid_layers = [x for x in itertools.product((10, 30, 50), repeat=3)]
len(grid_layers)

params = {
    "hidden_layer_sizes": grid_layers,
    "activation": ["relu"],
    "solver": ["adam"],
    "alpha": [1e-4],
    "learning_rate": ["invscaling"],
    "random_state": [101],
}


grid = GridSearchCV(MLPClassifier(), params, verbose=2)
grid.fit(X, y)
print(grid.best_estimator_)
print(grid.best_params_)
res_grid = pd.DataFrame(grid.cv_results_)
res_grid.to_excel("res_grid_genesis.xlsx")

# Neural Net
# model, fit, predict
mlp_clf = MLPClassifier(**grid.best_params_)
mlp_clf.fit(X_train, y_train)
y_pred = mlp_clf.predict(X_test)

print(
    "{} R^2, coef of determination of the prediction".format(
        mlp_clf.score(X_test, y_test)
    )
)
# print("Number of mislabeled points out of a total %d points : %d" % (X_test.shape[0], (y_test != y_pred).sum()))
# %% Final
# check = df_d.loc[df_d == 4].index
y_pred = pd.Series(clf_reg.predict(X))
y_clf = pd.concat([df_j, y_pred], axis=1).rename({0: "pred"}, axis=1)
y_clf = y_clf.sort_values(["CI"], ascending=False)
y_clf.loc[y_clf["CI"] == "vh"].head(25)
y_agg_clf = y_clf.groupby(["CI", "pred"])["CI"].count()
y_agg_clf = y_agg_clf.to_frame()
y_agg_clf["relative_rate"] = y_agg_clf["CI"] / y_agg_clf["CI"].groupby(level=0).sum()
y_agg_clf = y_agg_clf.rename({"CI": "st_j"}, axis=1)
y_agg_clf = y_agg_clf.reset_index(drop=False)


# %% Write
out = {
    "reg_st_d": y_agg_reg,
    "reg_st_d_details": y_reg.join(data["text"]),
    "clf_st_d": y_agg_clf,
    "clf_st_d_details": y_clf.join(data["text"]),
}
file_name = "outputs/mlp_results.xlsx"
table_save(out, file_name, keep_index=True)

time_final = time.time()
print(f"total run time: {(time_final - time_script):.0f}s")
