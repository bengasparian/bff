"""Run from the repository folder: python research/brain/train.py  (writes brain.json, which assemble.py puts in the page)
Train BFF Brain's intent model and export it for the page (brain.json).
Model: TF-IDF of words (1-2 grams) and character 3-4 grams (for typos) -> multinomial logistic regression.
Checked on hand-written questions it never trained on (corpus.TEST)."""
import json, base64, re, sys, os, numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report
from scipy.sparse import hstack
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE)); sys.path.insert(0, HERE)
import corpus

TOK = {'PLAYER': ' qqp ', 'TEAM2': ' qqt ', 'TEAM': ' qqt ', 'POSN': ' qqpos ', 'NUM': ' qqn '}


def norm(s):
    for k, v in TOK.items(): s = s.replace(k, v)
    s = s.lower(); s = re.sub(r"[^a-z0-9]+", ' ', s); return re.sub(r'\s+', ' ', s).strip()


X, Y = corpus.generate(600)
X += [q for q, _ in corpus.TEST + corpus.TEST2] * 3; Y += [a for _, a in corpus.TEST + corpus.TEST2] * 3   # dev questions join the training set
X = [norm(x) for x in X]
TX = [norm(q) for q, _ in corpus.TEST3]; TY = [a for _, a in corpus.TEST3]
mk = lambda: (TfidfVectorizer(analyzer='word', ngram_range=(1, 2), token_pattern=r'[a-z0-9]+', sublinear_tf=True, min_df=2),
              TfidfVectorizer(analyzer='char_wb', ngram_range=(3, 4), sublinear_tf=True, min_df=3))


def fit(vw, vc, X, Y, C):
    A = hstack([vw.fit_transform(X), vc.fit_transform(X)]).tocsr()
    m = LogisticRegression(C=C, max_iter=3000); m.fit(A, Y); return m


best = None
for C in (2, 5, 10, 20):
    vw, vc = mk(); m = fit(vw, vc, X, Y, C)
    acc = accuracy_score(TY, m.predict(hstack([vw.transform(TX), vc.transform(TX)]).tocsr()))
    print('C', C, 'held-out accuracy', round(acc, 3), 'vocab', len(vw.vocabulary_), len(vc.vocabulary_))
    if best is None or acc > best[0]: best = (acc, C)
C = best[1]
# keep the features that matter most, then refit on exactly those (what the page computes)
vw, vc = mk(); m = fit(vw, vc, X, Y, C); nw = len(vw.vocabulary_)
imp = np.abs(m.coef_).max(axis=0); W_names = vw.get_feature_names_out(); C_names = vc.get_feature_names_out()
kw = np.argsort(-imp[:nw])[:1800]; kc = np.argsort(-imp[nw:])[:1800]
vw2 = TfidfVectorizer(analyzer='word', ngram_range=(1, 2), token_pattern=r'[a-z0-9]+', sublinear_tf=True, vocabulary=list(W_names[kw]))
vc2 = TfidfVectorizer(analyzer='char_wb', ngram_range=(3, 4), sublinear_tf=True, vocabulary=list(C_names[kc]))
m2 = fit(vw2, vc2, X, Y, C)
P2 = m2.predict(hstack([vw2.transform(TX), vc2.transform(TX)]).tocsr()); acc2 = accuracy_score(TY, P2)
TX2 = [norm(q) for q, _ in corpus.TEST3]; TY2 = [a for _, a in corpus.TEST3]; PP2 = m2.predict(hstack([vw2.transform(TX2), vc2.transform(TX2)]).tocsr()); acc3 = accuracy_score(TY2, PP2)
print('FRESH held-out accuracy', round(acc3, 3), 'on', len(TY2))
for q, a, p in zip(TX2, TY2, PP2):
    if a != p: print('  MISS2', repr(q), 'want', a, 'got', p)
print('final held-out accuracy', round(acc2, 3), 'on', len(TY), 'hand-written questions')
print(classification_report(TY, P2, zero_division=0))
for q, a, p in zip(TX, TY, P2):
    if a != p: print('  MISS', repr(q), 'want', a, 'got', p)
# export: int8 weights with one scale
Wt = m2.coef_; sc = float(np.abs(Wt).max() / 127); Q = np.clip(np.round(Wt / sc), -127, 127).astype(np.int8)
out = {'v': 1, 'classes': list(m2.classes_), 'scale': sc, 'b': [round(float(x), 4) for x in m2.intercept_],
       'wv': list(vw2.get_feature_names_out()), 'wi': [round(float(x), 4) for x in vw2.idf_],
       'cv': list(vc2.get_feature_names_out()), 'ci': [round(float(x), 4) for x in vc2.idf_],
       'W': base64.b64encode(Q.tobytes()).decode(), 'acc': round(acc3, 3), 'ntest': len(TY2), 'ntrain': len(X)}
import voice   # how Ask BFF talks (Ben's voice); plain text the page assembles
out['voice'] = voice.BANK
json.dump(out, open(os.path.join(REPO, 'brain.json'), 'w'), separators=(',', ':'))
# a few reference predictions for the JS port test
REF = ['should i start qqp or qqp this week', 'what is ppr', 'qqp for qqp and qqp', 'who should i pick up at qqpos', 'is qqp playing tonight', 'hi']
A = hstack([vw2.transform(REF), vc2.transform(REF)]).tocsr(); pr = m2.predict_proba(A)
json.dump([{'q': q, 'top': m2.classes_[int(np.argmax(p))], 'p': round(float(p.max()), 4)} for q, p in zip(REF, pr)], open(os.path.join(HERE, 'ref.json'), 'w'))
print('exported', round(len(json.dumps(out)) / 1024), 'KB')
