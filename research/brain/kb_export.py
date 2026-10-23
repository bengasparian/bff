"""Run from the repository folder: python research/brain/kb_export.py  (writes kb.json)
Export the knowledge base with a TF-IDF index of its questions (words and word pairs, stop words kept low by idf).
The page finds the closest question by cosine similarity."""
import json, re, sys, os, numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE)); sys.path.insert(0, HERE)
from kb import KB


def norm(s): s = s.lower(); s = re.sub(r"[^a-z0-9]+", ' ', s); return re.sub(r'\s+', ' ', s).strip()


Q = []; E = []
for k, (id_, qs, a, *u) in enumerate(KB):
    for q in qs: Q.append(norm(q)); E.append(k)
v = TfidfVectorizer(analyzer='word', ngram_range=(1, 2), token_pattern=r'[a-z0-9]+', sublinear_tf=True)
M = v.fit_transform(Q)
voc = v.get_feature_names_out(); idf = v.idf_
rows = []
for i in range(M.shape[0]):
    r = M.getrow(i); rows.append([E[i], [[int(j), round(float(x), 4)] for j, x in zip(r.indices, r.data)]])
out = {'v': list(voc), 'i': [round(float(x), 4) for x in idf], 'q': rows, 'a': [[id_, a] + list(u) for id_, qs, a, *u in KB]}
json.dump(out, open(os.path.join(REPO, 'kb.json'), 'w'), separators=(',', ':'))
# self-check: paraphrases should land on the right entry
TESTS = [('how much is a safety worth', 'score_values'), ('explain nfl overtime', 'overtime'), ('whats a handcuff', 'handcuff'), 
         ('how many teams get into the playoffs', 'playoffs'), ('what does target share mean', 'usage_terms'), ('when does the trade deadline happen', 'dates_2026'),
         ('what is a pick 6', 'turnovers'), ('dynamic kickoff rules', 'kickoff'), ('how many players are on a practice squad', 'rosters')]
for q, want in TESTS:
    x = v.transform([norm(q)]); sims = (M @ x.T).toarray().ravel(); k = int(np.argmax(sims))
    print(('OK  ' if KB[E[k]][0] == want else 'MISS'), q, '->', KB[E[k]][0], round(float(sims[k]), 3))
print('kb entries', len(KB), 'questions', len(Q), 'size KB', round(len(json.dumps(out)) / 1024))
