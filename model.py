## model creation on Keras


from keras.models import Model
from keras.layers import Input
from keras.layers.embeddings import Embedding
from keras.layers.recurrent import GRU
from keras.layers.wrappers import Bidirectional, TimeDistributed
from keras.layers.core import Dropout, Dense, Lambda, Masking
from keras.engine.topology import merge, Layer

from keras import backend as K, initializations

class AttentionLayer(Layer):
    '''
    Attention layer. 
    '''
    def __init__(self, init='glorot_uniform', **kwargs):
        super(AttentionLayer, self).__init__(**kwargs)
        self.supports_masking = True
        self.init = initializations.get(init)
        
    def build(self, input_shape):
        input_dim = input_shape[-1]
        self.Uw = self.init((input_dim, ))
        self.trainable_weights = [self.Uw]
        super(AttentionLayer, self).build(input_shape)  
    
    def compute_mask(self, input, mask):
        return mask
    
    def call(self, x, mask=None):
        multData =  K.exp(K.dot(x, self.Uw))
        if mask is not None:
            multData = mask*multData
        output = multData/(K.sum(multData, axis=1)+K.epsilon())[:,None]
        return K.reshape(output, (output.shape[0],output.shape[1],1))

    def get_output_shape_for(self, input_shape):
        newShape = list(input_shape)
        newShape[-1] = 1
        return tuple(newShape)

# dropSentenceRnnOut = 0.5


def createHierarchicalAttentionModel(maxSeq, 
                                     embWeights=None, embeddingSize = None, vocabSize = None, #embedding
                                  recursiveClass = GRU, wordRnnSize=100, sentenceRnnSize=100,  #rnn 
                                  #wordDenseSize = 100, sentenceHiddenSize = 128, #dense
                                  dropWordEmb = 0.2, dropWordRnnOut = 0.2, dropSentenceRnnOut = 0.5):
    '''
    Creates a model based on the Hierarchical Attention model according to : https://arxiv.org/abs/1606.02393
    inputs:
        maxSeq : max size for sentences
        embedding
            embWeights : numpy matrix with embedding values
            embeddingSize (if embWeights is None) : embedding size
            vocabSize (if embWeights is None) : vocabulary size
        Recursive Layers 
            recursiveClass : class for recursive class. Default is GRU
            wordRnnSize : RNN size for word sequence 
            sentenceRnnSize :  RNN size for sentence sequence
        Dense Layers
            wordDenseSize: dense layer at exit from RNN , on sentence at word level
            sentenceHiddenSize : dense layer at exit from RNN , on document at sentence level 
        Dropout
            
    returns : Two models. They are the same, but the second contains multiple outputs that can be use to analyse attention. 
    '''
    
    ##
    ## Sentence level logic 
    wordsInputs = Input(shape=(maxSeq,), dtype='int32', name='words_input')
    if embWeights is None:
        emb = Embedding(vocabSize, embeddingSize, mask_zero=True)(wordsInputs)
    else:
        emb = Embedding(embWeights.shape[0], embWeights.shape[1], mask_zero=True, weights=[embWeights], trainable=False)(wordsInputs)
    if dropWordEmb != 0.0:
        emb = Dropout(dropWordEmb)(emb)
    wordRnn = Bidirectional(recursiveClass(wordRnnSize, return_sequences=True), merge_mode='concat')(emb)
    if dropWordRnnOut  > 0.0:
        wordRnn = Dropout(dropWordRnnOut)(wordRnn)
    attention = AttentionLayer()(wordRnn)
    sentenceEmb = merge([wordRnn, attention], mode=lambda x:x[1]*x[0], output_shape=lambda x:x[0])
    sentenceEmb = Lambda(lambda x:K.sum(x, axis=1), output_shape=lambda x:(x[0],x[2]))(sentenceEmb)
    modelSentence = Model(wordsInputs, sentenceEmb)
    modelSentAttention = Model(wordsInputs, attention)
    
    
    documentInputs = Input(shape=(None,maxSeq), dtype='int32', name='document_input')
    sentenceMasking = Masking(mask_value=0)(documentInputs)
    sentenceEmbbeding = TimeDistributed(modelSentence)(sentenceMasking)
    sentenceAttention = TimeDistributed(modelSentAttention)(sentenceMasking)
    sentenceRnn = Bidirectional(recursiveClass(wordRnnSize, return_sequences=True), merge_mode='concat')(sentenceEmbbeding)
    if dropSentenceRnnOut > 0.0:
        sentenceRnn = Dropout(dropSentenceRnnOut)(sentenceRnn)
    attentionSent = AttentionLayer()(sentenceRnn)
    documentEmb = merge([sentenceRnn, attentionSent], mode=lambda x:x[1]*x[0], output_shape=lambda x:x[0])
    documentEmb = Lambda(lambda x:K.sum(x, axis=1), output_shape=lambda x:(x[0],x[2]), name="att2")(documentEmb)
    documentOut = Dense(1, activation="sigmoid", name="documentOut")(documentEmb)
    
    
    model = Model(input=[documentInputs], output=[documentOut])
    model.compile(loss='binary_crossentropy',
              optimizer='rmsprop',
              metrics=['accuracy'])
    
    modelAttentionEv = Model(input=[documentInputs], output=[documentOut,  sentenceAttention, attentionSent])
    modelAttentionEv.compile(loss='binary_crossentropy',
              optimizer='rmsprop',
              metrics=['accuracy'])
    return model, modelAttentionEv
