# -*- coding: utf-8 -*-
"""22b1074_week_3.ipynb

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/14hAW8DEYK-iZPTCPB8O3FFCzyOnah63K
"""

# Commented out IPython magic to ensure Python compatibility.
import torch
import torch.nn.functional as F
import matplotlib.pyplot as plt
# %matplotlib inline

from google.colab import files
uploaded = files.upload()
#upload names.txt

# read in all the words
words = open('names.txt', 'r').read().splitlines()
len(words)

# mappings of characters to/from integers
chars = sorted(list(set(''.join(words))))
stoi = {s:i+1 for i,s in enumerate(chars)}
stoi['.'] = 0
itos = {i:s for s,i in stoi.items()}
print(itos)
vocab_size = len(itos)
print(vocab_size)

# building dataset
block_size = 3 # context length: how many characters do we take to predict

def build_dataset(words):
   X, Y = [], []
   for w in words:
     context = [0] * block_size
     for ch in w + '.':
        ix = stoi[ch]
        X.append(context)
        Y.append(ix)
        context = context[1:] + [ix]
   X = torch.tensor(X)
   Y = torch.tensor(Y)
   print(X.shape, Y.shape)
   return X, Y

import random
random.seed(42)
random.shuffle(words)
train_size = int(0.8 * len(words))
dev_size = int(0.9 * len(words))
X_train, Y_train = build_dataset(words[:train_size])
X_dev, Y_dev = build_dataset(words[train_size:dev_size])
X_test, Y_test = build_dataset(words[dev_size:])
X , Y = build_dataset(words)

#print(X.shape, Y.shape, X.dtype, Y.dtype)

n_embd = 10
n_hidden = 200

g = torch.Generator().manual_seed(2147483647) # for reproducibility
C = torch.randn((vocab_size, n_embd), generator=g)
W1 = torch.randn((n_embd * block_size, n_hidden), generator=g) * (5/3)/((n_embd * block_size) ** 0.5)
#b1 = torch.randn(n_hidden, generator=g) * 0.01
W2 = torch.randn((n_hidden, vocab_size), generator=g) * 0.01
b2 = torch.randn(vocab_size, generator=g) * 0

bngain = torch.ones((1, n_hidden))
bnbias = torch.zeros((1, n_hidden))
bnmean_running = torch.zeros((1, n_hidden))
bnstd_running = torch.ones((1, n_hidden))

parameters = [C, W1, b1, W2, b2, bngain, bnbias]
#l = sum(p.nelement() for p in parameters) # number of parameters in total
for p in parameters:
  p.requires_grad = True
#print(l)

# Wrap the model with DataParallel
# Ensure this is done before any model operations or training
#from torch.nn.parallel import DataParallel
from torch import nn
C = nn.DataParallel(C)
W1 = nn.DataParallel(W1)
b1 = nn.DataParallel(b1)
W2 = nn.DataParallel(W2)
b2 = nn.DataParallel(b2)

lre = torch.linspace(-3, 0, 1000)
lrs = 10**lre

lri = []
stepi = []

max_steps = 200000
batch_size = 32
lossi = []
for i in range(max_steps):
    # minibatch
    ix = torch.randint(0, X_train.shape[0], (32,))
    #ix_tensor = torch.tensor(ix).cuda() if torch.cuda.is_available() else torch.tensor(ix)
    # forward pass
    Xb, Yb = X_train[ix], Y_train[ix]
    emb = C[Xb]
    embcat = emb.view(emb.shape[0], -1)
    hpreact = embcat @ W1
    bnmeani = hpreact.mean(0, keepdim=True)
    bnstdi = hpreact.std(0, keepdim=True)
    hpreact = bngain * (hpreact - bnmeani) / bnstdi + bnbias

    with torch.no_grad():
      bnmean_running = 0.999 * bnmean_running + 0.001 * bnmeani
      bnstd_running = 0.999 * bnstd_running + 0.001 * bnstdi


    h = torch.tanh(hpreact)
    logits = h @ W2 + b2
    loss = F.cross_entropy(logits, Yb)
    #print(loss.item())
    # backward pass
    for p in parameters:
      p.grad = None
    loss.backward()
    #update
    lr = 0.1 if i < 100000 else 0.01
    for p in parameters:
      p.data += -lr * p.grad
    stepi.append(i)
    #lri.append(lre[i])
    # tracking stats
    if i % 10000 == 0:
      print(f'{i:7d}/{max_steps:7d}: {loss.item():.4f}')
    lossi.append(loss.log10().item())
    break
#print(loss.item())

with torch.no_grad():
  emb = C[X_train]
  embcat = emb.view(emb.shape[0], -1)
  hpreact = embcat @ W1 + b1
  bnmean = hpreact.mean(0, keepdim=True)
  bnstd = hpreact.std(0, keepdim=True)

@torch.no_grad() # this decorator disables gradient tracking
def split_loss(split):
  x,y = {
    'train': (X_train, Y_train),
    'val': (X_dev, Y_dev),
    'test': (X_test, Y_test),
  }[split]
  emb = C[x] # (N, block_size, n_embd)
  embcat = emb.view(emb.shape[0], -1) # concat into (N, block_size * n_embd)
  hpreact = embcat @ W1
  #hpreact = bngain * (hpreact - hpreact.mean(0, keepdim=True)) / hpreact.std(0, keepdim=True) + bnbias
  hpreact = bngain * (hpreact - bnmean_running) / bnstd_running + bnbias
  h = torch.tanh(embcat @ W1 + b1) # (N, n_hidden)
  logits = h @ W2 + b2 # (N, vocab_size)
  loss = F.cross_entropy(logits, y)
  print(split, loss.item())

split_loss('train')
split_loss('val')

plt.plot(lossi)

plt.hist(hpreact.view(-1).tolist(), 50);

plt.figure(figsize=(20, 10))
plt.imshow(h.abs() > 0.99, cmap = 'gray', interpolation='nearest')

emb = C[X_dev]
h = torch.tanh(emb.view(-1, 30) @ W1 + b1)
logits = h @ W2 + b2
loss = F.cross_entropy(logits, Y_dev)
print(loss.item())

emb = C[X_train]
h = torch.tanh(emb.view(-1, 30) @ W1 + b1)
logits = h @ W2 + b2
loss = F.cross_entropy(logits, Y_train)
print(loss.item())

emb = C[X_test]
h = torch.tanh(emb.view(-1, 30) @ W1 + b1)
logits = h @ W2 + b2
loss = F.cross_entropy(logits, Y_test)
print(loss.item())

#train parameters - train set
#train hyperparameters - dev set
# evaluate performance of model at end - test set

# sample from the model
g = torch.Generator().manual_seed(2147483647 + 10)

for _ in range(20):

    out = []
    context = [0] * block_size # initialize with all ...
    while True:
      emb = C[torch.tensor([context])] # (1,block_size,d)
      h = torch.tanh(emb.view(1, -1) @ W1 + b1)
      logits = h @ W2 + b2
      probs = F.softmax(logits, dim=1)
      ix = torch.multinomial(probs, num_samples=1, generator=g).item()
      context = context[1:] + [ix]
      out.append(ix)
      if ix == 0:
        break

    print(''.join(itos[i] for i in out))

#probs = torch.full((1, 27), 1/27)
#loss_uniform_expected = ln(27)
g_uni = torch.Generator().manual_seed(2147483647)
C_uni = torch.randn((27, 10), generator=g_uni) * 0.01
W1_uni = torch.randn((30, 200), generator=g_uni) * 0.01
b1_uni = torch.zeros(200)
W2_uni = torch.randn((200, 27), generator=g_uni) * 0.01
b2_uni = torch.zeros(27)

emb_uni = C_uni[X_dev]
h_uni = torch.tanh(emb_uni.view(-1, 30) @ W1_uni + b1_uni)
logits_uni = h_uni @ W2_uni + b2_uni
loss_uni = F.cross_entropy(logits_uni, Y_dev)
loss_uni  #is closer to ln(27) which is loss when predicted probabilities at initialization were perfectly uniform

