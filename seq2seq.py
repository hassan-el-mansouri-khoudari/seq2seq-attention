import torch
import torch.nn as nn
import torch.optim as optim
from torchtext.datasets import Multi30k
from torchtext.data import Field, BucketIterator
import numpy as np
import spacy
import random
from torch.utils.tensorboard import SummaryWriter

spacy_de = spacy.load('de')
spacy_eng = spacy.load('en')

def tokenizer_de(text):
    return [tok.text for tok in spacy_de.tokenizer(text)]


def tokenizer_eng(text):
    return [tok.text for tok in spacy_eng.tokenizer(text)]


german = Field(tokenize = tokenizer_de, lower=True, init_token ='<sos>', eos_token = '<eos>')

english = Field(tokenize = tokenizer_eng, lower=True, init_token ='<sos>', eos_token = '<eos>')

train_data, validation_data, test_data = Multi30k.splits(exts = ('.de', '.en'), fields = (german, english))

german.build_vocab(train_data, max_size = 10000, min_freq = 2) 
english.build_vocab(train_data, max_size = 10000, min_freq = 2) 

class Encoder(nn.Module):
    def __init__(self, input_size, embedding_size, hidden_size, num_layers, p):
        super(Encoder, self).__init__()
        self.hidden_size = hidden_size
        self.num_layers = num_layers
        
        self.dropout = nn.Dropout(p)
        self.embedding = nn.Embedding(input_size, embedding_size)
        self.rnn = nn.LSTM(embedding_size, hidden_size, num_layers, dropout = p)

    def forward(self, x):
        # c_shape (seq_length, N)
        embedding = self.dropout(self.embedding(x))
        # embedding (seq_length, embedding_size)
        outputs, (hidden, cell) = self.rnn(embedding)

        return hidden, cell



class Decoder(nn.Module):
    def _init__(self, input_size, embedding_size, hidden_size, output_size, num_layers, p):
        super(Decoder, self).__init()
        self.hidden_size = hidden_size
        self.num_layers = num_layers
        self.dropout = nn.Dropout(p)

        self.embedding = nn.Embedding(input_size, embedding_size)
        self.rnn = nn.LSTM(embedding_size, hidden_size, num_layers, dropout=p)
        self.fc = nn.Linear(hidden_size, output_size)

    
    def forward(self, x, hidden, cell):
        # shape of x (N) but we want (1,N)

        x = x.unsqueeze(0)
        embedding = self.dropout(self.embedding(x))
        outputs, (hidden, cell) = self.rnn(embedding, (hidden, cell))
        # shape of outputs (1, N, hidden_size)

        predictions = self.fc(outputs)
        # shape 1, N, length of vocab

        predictions = predictions.squeeze(0)

        return predictions, hidden, cell

class Seq2Seq(nn.Module):
    def __init__(self, encoder, decoder):
        super(Seq2Seq, self).__init__()
        self.encoder = encoder
        self.decoder = decoder


    def forward(self, source, target, teacher_force_ratio = 0.5):
        batch_size = source.shape[1]
        target_len = target.shape[0]
        target_vocab_size = len(english.vocab)

        outputs = torch.zeros(target_len, batch_size, target_vocab_size).to(device)

        hidden, cell = self.encoder(source)
        
    
        #grab start toker
        x = target[0]

        for t in range(1, target_len):
            output, hidden, cell = self.decoder(x, hidden, cell)

            outputs[t] = output

            # (N, english_vocab_size)
            best_guess = output.argmax(1)

            x = target[t] if random.random() < teacher_force_ratio else best_guess


        return outputs

### Training

# training hyperparameters

num_epochs = 20
learning_rate = 0.001
batch_size = 64

# Model hyperparameters
load_model = False
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
input_size_encoder = len(german.vocab)
input_size_decoder = len(english.vocab)
output_size = len(english.vocab)
encoder_embedding_size = 300
decoder_embedding_size = 300
hidden_size = 1024
num_layers = 2
enc_dropout = 0.5
dec_dropout = 0.5

#Tensor board
writer = SummaryWriter(f'runs/loss_plot')
step = 0

train_iterator, valid_iterator, test_iterator = BucketIterator.splits(
    (train_data, validation_data, test_data),
    batch_size = batch_size,
    sort_within_batch = True,
    sort_key = lambda x: len(x.src),
    device = device
)

encoder_net = Encoder(input_size_encoder, encoder_embedding_size, hidden_size, num_layers, enc_dropout).to(device)


decoder_net = Decoder(input_size_decoder, decoder_embedding_size, hidden_size, num_layers, dec_dropout).to(device)

model =Seq2Seq(encoder_net, decoder_net).to(device)

pad_idx = english.vocab.stoi['<pad>']

criterion = nn.CrossEntropyLoss(ignore_index = pad_idx)

# saving stuff

for epoch in range(num_epochs):
    print(f'Epoch {epoch} / {num_epochs}')

    checkpoint = {'state_dict':model.state_dict(), 'optimizer':optimizer.state_dict()}

    save_checkpoint(checkpoint)

    for batch_idx, batch in enumerate(train_iterator):
        inp_data = batch.src.to(device)
        target = batch.trg.to(device)

        output = model(inp_data, target)
    #output shape (tgt_len ,b_size, output_dim)

        output = output[1:].reshape(-1, output.shape[2])
        target = target[1:].reshape(-1)

        optimizer.zero_grad()
        loss = criterion(output, target)

        loss.backward()

        torch.nn.utils.clip_grad_norm(model.parameters(), max_norm = 1)
        optimizer.step()

        writer.add_scalar('Training Loss', loss, global_step = step)
        step += 1


          